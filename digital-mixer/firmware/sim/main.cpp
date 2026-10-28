// Desktop simulator: the same core (mixer, FX, UI, display) as the Teensy build, with an SDL2
// window that shows the display and a virtual control panel laid out like the board (DM25), and
// audio through the computer's sound card. --headless runs a script without a window or audio.
#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <atomic>
#include <chrono>
#include <fstream>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

#include "../src/core/gfx.h"
#include "../src/core/hal.h"
#include "../src/core/mixer.h"
#include "../src/core/recorder.h"
#include "../src/core/ui.h"
#include "png.h"
#include "sources.h"

static constexpr float FS = 48000.f;
static constexpr int WIN_W = 960, WIN_H = 930;

// ------------------------------------------------------------------ platform glue
class StdioSink : public FileSink {
public:
    bool open(const char* name) override { f_ = fopen(name, "wb"); return f_ != nullptr; }
    bool write(const void* d, uint32_t n) override { return f_ && fwrite(d, 1, n, f_) == n; }
    bool writeAt(uint32_t pos, const void* d, uint32_t n) override {
        if (!f_) return false;
        long cur = ftell(f_);
        fseek(f_, (long)pos, SEEK_SET);
        bool ok = fwrite(d, 1, n, f_) == n;
        fseek(f_, cur, SEEK_SET);
        return ok;
    }
    void close() override { if (f_) fclose(f_); f_ = nullptr; }
private:
    FILE* f_ = nullptr;
};

class SimHal : public Hal {
public:
    bool virtualClock = false;
    uint64_t virtualUs = 0;
    std::atomic<float> gainDb[NCH];
    std::atomic<int> backlight{80};
    std::atomic<float> cpu{0};
    bool verboseMidi = false;
    std::string dataDir = "sim-data";
    StdioSink sink;
    int recIndex = 1;

    SimHal() { for (auto& g : gainDb) g = 0; t0_ = std::chrono::steady_clock::now(); }
    uint32_t micros() override {
        if (virtualClock) return (uint32_t)virtualUs;
        return (uint32_t)std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - t0_).count();
    }
    uint32_t millis() override {
        if (virtualClock) return (uint32_t)(virtualUs / 1000);
        return micros() / 1000;
    }
    void setInputGain(int ch, float db) override { gainDb[ch] = db; }
    void midiOut(const uint8_t* m, int n) override {
        if (!verboseMidi || (n == 1 && m[0] == 0xF8)) return;
        printf("MIDI OUT");
        for (int i = 0; i < n; i++) printf(" %02X", m[i]);
        printf("\n");
    }
    std::string slotPath(int slot) { return dataDir + "/slot" + std::to_string(slot) + ".bin"; }
    bool load(int slot, void* d, uint32_t n) override {
        FILE* f = fopen(slotPath(slot).c_str(), "rb");
        if (!f) return false;
        bool ok = fread(d, 1, n, f) == n;
        fclose(f);
        return ok;
    }
    bool save(int slot, const void* d, uint32_t n) override {
        std::string cmd = "mkdir -p '" + dataDir + "'";
        if (system(cmd.c_str()) != 0) return false;
        FILE* f = fopen(slotPath(slot).c_str(), "wb");
        if (!f) return false;
        bool ok = fwrite(d, 1, n, f) == n;
        fclose(f);
        return ok;
    }
    void setBacklight(int p) override { backlight = p; }
    float batteryVolts() override { return 3.95f; }
    float cpuLoad() override { return cpu; }
    FileSink* recSink() override { return &sink; }
    void recFileName(char* buf, int n) override { snprintf(buf, n, "rec-%04d.wav", recIndex++); }
    int recChannels() override { return 10; }

private:
    std::chrono::steady_clock::time_point t0_;
};

// ------------------------------------------------------------------ simulator state
struct Sim {
    SimHal hal;
    Scene scene;
    Live live;
    Settings settings;
    Mixer mixer;
    Recorder recorder;
    Ui ui;
    Source src[NCH];
    Source usbSrc;
    bool usbOn = false;
    std::vector<int16_t> pool[NFX];
    std::vector<uint8_t> recRing;
    std::atomic<int> monitor{0};          // 0 MAIN, 1 AUX, 2 PHONES
    std::atomic<bool> paused{false};
    std::mutex audioLock;                 // only for the headless runner and the WAV writer
    FILE* outWav = nullptr;
    uint32_t outFrames = 0;
    uint16_t display[DISPLAY_W * DISPLAY_H];
    Canvas disp{display, DISPLAY_W, DISPLAY_H};

    void init(bool smallMem) {
        uint32_t poolSize = smallMem ? 96000 : 480000;     // ~1 s (no PSRAM) / 5 s (PSRAM) of stereo delay
        int16_t* pools[NFX];
        for (int i = 0; i < NFX; i++) { pool[i].assign(poolSize, 0); pools[i] = pool[i].data(); }
        mixer.init(FS, &scene, &live, pools, poolSize);
        recRing.assign(1 << 20, 0);
        recorder.init(recRing.data(), (uint32_t)recRing.size(), FS);
        mixer.recorder = &recorder;
        ui.init(&hal, &mixer, &scene, &live, &settings, &recorder);
        ui.begin();
    }

    // one block of audio: sources -> PGA -> mixer -> selected monitor output
    void process(float* outL, float* outR, int n) {
        float in[2 * NCH][Mixer::MAX_BLOCK], usb[2][Mixer::MAX_BLOCK], out[6][Mixer::MAX_BLOCK];
        float usbOut[2 * NCH][Mixer::MAX_BLOCK];
        auto t0 = std::chrono::steady_clock::now();
        for (int c = 0; c < NCH; c++) {
            if (paused) { memset(in[2 * c], 0, sizeof in[0]); memset(in[2 * c + 1], 0, sizeof in[0]); continue; }
            src[c].render(in[2 * c], in[2 * c + 1], n, FS);
            float g = dsp::dbToLin(hal.gainDb[c]);
            for (int i = 0; i < n; i++)                  // the PGA and the ADC clip at full scale
                for (int k = 0; k < 2; k++) in[2 * c + k][i] = dsp::clampf(in[2 * c + k][i] * g, -1.f, 1.f);
        }
        AudioIO io;
        for (int i = 0; i < 2 * NCH; i++) { io.in[i] = in[i]; io.usbOut[i] = usbOut[i]; }
        if (usbOn && !paused) { usbSrc.render(usb[0], usb[1], n, FS); io.usbIn[0] = usb[0]; io.usbIn[1] = usb[1]; }
        for (int i = 0; i < 6; i++) io.out[i] = out[i];
        io.n = n;
        mixer.process(io);
        int m = monitor;
        memcpy(outL, out[2 * m], n * sizeof(float));
        memcpy(outR, out[2 * m + 1], n * sizeof(float));
        if (outWav) {
            for (int i = 0; i < n; i++) {
                int16_t s[2] = {(int16_t)(dsp::clampf(out[0][i], -1, 1) * 32767), (int16_t)(dsp::clampf(out[1][i], -1, 1) * 32767)};
                fwrite(s, 2, 2, outWav);
            }
            outFrames += n;
        }
        double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count();
        float load = (float)(us / (n / FS * 1e6) * 100.0);
        hal.cpu = hal.cpu * 0.95f + load * 0.05f;
    }

    void openOutWav(const char* path) {
        outWav = fopen(path, "wb");
        if (!outWav) return;
        uint8_t h[44] = {};
        fwrite(h, 1, 44, outWav);
    }
    void closeOutWav() {
        if (!outWav) return;
        uint32_t data = outFrames * 4;
        auto u32 = [](uint8_t* p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; };
        uint8_t h[44];
        memcpy(h, "RIFF", 4); u32(h + 4, 36 + data); memcpy(h + 8, "WAVEfmt ", 8);
        u32(h + 16, 16); h[20] = 1; h[21] = 0; h[22] = 2; h[23] = 0; u32(h + 24, 48000); u32(h + 28, 48000 * 4);
        h[32] = 4; h[33] = 0; h[34] = 16; h[35] = 0; memcpy(h + 36, "data", 4); u32(h + 40, data);
        fseek(outWav, 0, SEEK_SET);
        fwrite(h, 1, 44, outWav);
        fclose(outWav);
        outWav = nullptr;
    }
};

static Sim* g_sim = nullptr;

static void audioCallback(void*, Uint8* stream, int len) {
    float* out = (float*)stream;
    int frames = len / (int)(2 * sizeof(float));
    float l[Mixer::MAX_BLOCK], r[Mixer::MAX_BLOCK];
    for (int done = 0; done < frames;) {
        int n = frames - done < Mixer::MAX_BLOCK ? frames - done : Mixer::MAX_BLOCK;
        g_sim->process(l, r, n);
        for (int i = 0; i < n; i++) { out[2 * (done + i)] = l[i]; out[2 * (done + i) + 1] = r[i]; }
        done += n;
    }
}

// ------------------------------------------------------------------ virtual panel
// Positions follow the board layout (DM25): channel columns, right column, master top right.
struct Panel {
    static constexpr int DX = 40, DY = 20;          // display at 2x
    static int colX(int ch) { return 120 + ch * 160; }
    static constexpr int RIGHT_X = 820, MASTER_Y = 190;
    static int rowY(int r) { return 440 + r * 80; }
    static constexpr int FADER_Y0 = 670, FADER_Y1 = 800, MUTE_Y = 850;

    struct Hit { enum T { None, Enc, Btn, Fader } t = None; int id = -1; };
    static Hit hit(int x, int y) {
        auto near = [&](int cx, int cy, int r) { return (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r; };
        for (int ch = 0; ch < NCH; ch++) {
            for (int r = 0; r < 3; r++)
                if (near(colX(ch), rowY(r), 30)) return {Hit::Enc, ch * 3 + r};
            if (abs(x - colX(ch)) <= 26 && y >= FADER_Y0 - 14 && y <= FADER_Y1 + 14) return {Hit::Fader, ch};
            if (abs(x - colX(ch)) <= 30 && abs(y - MUTE_Y) <= 20) return {Hit::Btn, B_MUTE1 + ch};
        }
        if (near(RIGHT_X, MASTER_Y, 34)) return {Hit::Enc, E_MASTER};
        const int rb[4] = {B_AUX, B_FX1, B_FX2, B_SHIFT};
        const int ry[4] = {rowY(0), rowY(1), rowY(2), MUTE_Y};
        for (int i = 0; i < 4; i++)
            if (abs(x - RIGHT_X) <= 30 && abs(y - ry[i]) <= 20) return {Hit::Btn, rb[i]};
        return {};
    }
};

static float faderFromY(int y) {
    return dsp::clampf(1.f - (float)(y - Panel::FADER_Y0) / (Panel::FADER_Y1 - Panel::FADER_Y0), 0, 1);
}

static void drawPanel(Sim& s, Canvas& w, const bool latched[B_COUNT], float encAngle[E_COUNT]) {
    w.clear(rgb(24, 24, 28));
    // display, 2x, dimmed by the backlight setting
    int bl = s.hal.backlight;
    for (int y = 0; y < DISPLAY_H; y++)
        for (int x = 0; x < DISPLAY_W; x++) {
            uint16_t p = s.display[y * DISPLAY_W + x];
            if (bl < 100) {
                int r = (p >> 11) * bl / 100, g = ((p >> 5) & 63) * bl / 100, b = (p & 31) * bl / 100;
                p = (uint16_t)(r << 11 | g << 5 | b);
            }
            uint16_t* d = w.data() + (Panel::DY + 2 * y) * w.width() + Panel::DX + 2 * x;
            d[0] = d[1] = d[w.width()] = d[w.width() + 1] = p;
        }
    w.rect(Panel::DX - 2, Panel::DY - 2, 2 * DISPLAY_W + 4, 2 * DISPLAY_H + 4, col::GREY);

    auto knob = [&](int cx, int cy, int r, float ang, bool pressed, uint16_t ring) {
        w.circle(cx, cy, r, pressed ? rgb(110, 110, 120) : rgb(60, 60, 66), true);
        w.circle(cx, cy, r, ring, false);
        w.line(cx, cy, cx + (int)(sinf(ang) * (r - 4)), cy - (int)(cosf(ang) * (r - 4)), col::WHITE);
    };
    auto button = [&](int cx, int cy, const char* label, uint16_t lit, bool down, bool latch) {
        w.fill(cx - 28, cy - 16, 56, 32, down ? rgb(140, 140, 150) : rgb(55, 55, 60));
        if (lit) w.rect(cx - 28, cy - 16, 56, 32, lit), w.rect(cx - 27, cy - 15, 54, 30, lit);
        w.textCentered(cx, cy - 3, label, latch ? col::YELLOW : col::WHITE);
    };
    static const uint16_t PCOL[] = {col::WHITE, col::CYAN, col::MAGENTA, col::ORANGE};
    char buf[32];
    for (int ch = 0; ch < NCH; ch++) {
        int x = Panel::colX(ch);
        snprintf(buf, sizeof buf, "IN%d %s", ch + 1, s.src[ch].name.substr(0, 10).c_str());
        w.textCentered(x, 392, buf, col::DIM);
        for (int r = 0; r < 3; r++) {
            int id = ch * 3 + r, pid = s.ui.rowParam(ch, r);
            uint16_t ring = pid == P_SEND_AUX ? PCOL[1] : pid == P_SEND_FX1 ? PCOL[2] : pid == P_SEND_FX2 ? PCOL[3]
                          : pid == P_GAIN ? col::YELLOW : pid == P_PAN ? col::GREEN : pid == P_FILTER ? col::BLUE
                          : pid == P_COMP ? col::RED : col::GREY;
            knob(x, Panel::rowY(r), 26, encAngle[id], s.ui.held(id), ring);
            w.text(x + 32, Panel::rowY(r) - 4, paramDesc(pid).name, ring == col::GREY ? col::DIM : ring);
        }
        w.fill(x - 3, Panel::FADER_Y0, 6, Panel::FADER_Y1 - Panel::FADER_Y0, rgb(10, 10, 10));
        int fy = Panel::FADER_Y0 + (int)((1.f - s.live.fader[ch]) * (Panel::FADER_Y1 - Panel::FADER_Y0));
        w.fill(x - 20, fy - 8, 40, 16, rgb(200, 200, 205));
        w.hline(x - 20, fy, 40, col::BLACK);
        const ChannelParams& p = s.scene.ch[ch];
        button(x, Panel::MUTE_Y, p.cue ? "MUTE/CUE" : "MUTE", p.mute ? col::RED : p.cue ? col::YELLOW : 0,
               s.ui.held(B_MUTE1 + ch), false);
    }
    knob(Panel::RIGHT_X, Panel::MASTER_Y, 32, encAngle[E_MASTER], s.ui.held(B_MASTER), col::WHITE);
    w.textCentered(Panel::RIGHT_X, Panel::MASTER_Y + 42, "MASTER", col::DIM);
    w.textCentered(Panel::RIGHT_X, Panel::MASTER_Y + 54, "PUSH = MENU", col::GREY);
    button(Panel::RIGHT_X, Panel::rowY(0), "AUX", s.ui.layerAux() ? col::CYAN : 0, s.ui.held(B_AUX), latched[B_AUX]);
    button(Panel::RIGHT_X, Panel::rowY(1), "FX I", s.ui.layerFx(0) ? col::MAGENTA : 0, s.ui.held(B_FX1), latched[B_FX1]);
    button(Panel::RIGHT_X, Panel::rowY(2), "FX II", s.ui.layerFx(1) ? col::ORANGE : 0, s.ui.held(B_FX2), latched[B_FX2]);
    button(Panel::RIGHT_X, Panel::MUTE_Y, "SHIFT", 0, s.ui.held(B_SHIFT), latched[B_SHIFT]);

    static const char* const MON[] = {"MAIN", "AUX", "PHONES"};
    snprintf(buf, sizeof buf, "OUT: %s", MON[s.monitor % 3]);
    w.text(720, 30, buf, col::GREEN, 2);
    snprintf(buf, sizeof buf, "HOST CPU %.1f%%", (double)s.hal.cpu.load());
    w.text(720, 56, buf, col::DIM);
    if (s.paused) w.text(720, 70, "PAUSED", col::RED);
    w.text(10, WIN_H - 34, "WHEEL/DRAG: TURN  CLICK: PUSH  RMB ON AUX/FX/SHIFT: LATCH  KEYS: SHIFT A F G = HOLD,", col::GREY);
    w.text(10, WIN_H - 20, "Q W E R = MUTE, UP/DOWN/ENTER = MASTER, O = OUTPUT, SPACE = PAUSE, P = SCREENSHOT, ESC", col::GREY);
}

// ------------------------------------------------------------------ script (headless and --script)
static int buttonByName(const std::string& n) {
    if (n == "master") return B_MASTER;
    if (n == "aux") return B_AUX;
    if (n == "fx1") return B_FX1;
    if (n == "fx2") return B_FX2;
    if (n == "shift") return B_SHIFT;
    if (n.rfind("mute", 0) == 0) return B_MUTE1 + atoi(n.c_str() + 4) - 1;
    if (n.rfind("e", 0) == 0) return atoi(n.c_str() + 1);
    return atoi(n.c_str());
}
static int encByName(const std::string& n) {
    if (n == "master" || n == "m") return E_MASTER;
    if (n.rfind("e", 0) == 0) return atoi(n.c_str() + 1);
    return atoi(n.c_str());
}

static void advance(Sim& s, int ms) {              // headless: run audio and UI on the virtual clock
    float l[Mixer::MAX_BLOCK], r[Mixer::MAX_BLOCK];
    int blocks = (int)(ms * FS / 1000.f / Mixer::MAX_BLOCK + 0.5f);
    for (int b = 0; b < blocks; b++) {
        s.process(l, r, Mixer::MAX_BLOCK);
        s.hal.virtualUs += (uint64_t)(Mixer::MAX_BLOCK * 1e6 / FS);
        s.ui.tick();
    }
}

static bool runScriptLine(Sim& s, const std::string& line, Canvas* panel, bool latched[], float ang[]) {
    std::istringstream in(line);
    std::string cmd;
    if (!(in >> cmd) || cmd[0] == '#') return true;
    if (cmd == "enc") { std::string id; int d; in >> id >> d; s.ui.encoder(encByName(id), d); }
    else if (cmd == "press") { std::string id; in >> id; s.ui.button(buttonByName(id), true); }
    else if (cmd == "release") { std::string id; in >> id; s.ui.button(buttonByName(id), false); }
    else if (cmd == "click") { std::string id; in >> id; int b = buttonByName(id); s.ui.button(b, true); s.ui.button(b, false); }
    else if (cmd == "fader") { int ch; float p; in >> ch >> p; s.ui.fader(ch - 1, p); }
    else if (cmd == "wait") { int ms; in >> ms; advance(s, ms); }
    else if (cmd == "monitor") { int m; in >> m; s.monitor = m; }
    else if (cmd == "midi") {
        uint8_t m[3]; int n = 0; std::string h;
        while (n < 3 && in >> h) m[n++] = (uint8_t)strtol(h.c_str(), nullptr, 16);
        s.ui.midiIn(m, n);
    } else if (cmd == "shot" || cmd == "panel") {
        std::string f; in >> f;
        s.ui.render(s.disp);
        if (cmd == "shot") writePng(f.c_str(), s.display, DISPLAY_W, DISPLAY_H);
        else if (panel) { drawPanel(s, *panel, latched, ang); writePng(f.c_str(), panel->data(), WIN_W, WIN_H); }
        printf("screenshot %s\n", f.c_str());
    } else if (cmd == "meters") {
        printf("meters dBFS: ");
        for (int c = 0; c < NCH; c++) printf("IN%d %.1f/%.1f  ", c + 1, dsp::linToDb(s.mixer.chMeter[c][0].peak),
                                               dsp::linToDb(s.mixer.chMeter[c][1].peak));
        printf("MAIN %.1f/%.1f AUX %.1f PH %.1f LIM %.1f\n", dsp::linToDb(s.mixer.mainMeter[0].peak),
               dsp::linToDb(s.mixer.mainMeter[1].peak), dsp::linToDb(s.mixer.auxMeter[0].peak),
               dsp::linToDb(s.mixer.phonesMeter[0].peak), (double)s.mixer.limGr);
    } else if (cmd == "quit") return false;
    else printf("unknown command: %s\n", cmd.c_str());
    return true;
}

// ------------------------------------------------------------------ main
static void usage() {
    printf("pocket-mixer-sim [options]\n"
           "  --in N FILE.wav     input N (1-4) from a WAV file (looped), default: built-in demo parts\n"
           "  --usb FILE.wav      stereo 'from DAW' stream into MAIN\n"
           "  --out FILE.wav      also write MAIN to a WAV file\n"
           "  --script FILE       run commands (enc/press/release/click/fader/wait/shot/panel/meters/midi)\n"
           "  --headless          no window, no sound card: run the script on a virtual clock\n"
           "  --small-mem         FX memory as on a Teensy without PSRAM\n"
           "  --data DIR          where scenes are kept (default sim-data)\n"
           "  --midi              print MIDI OUT messages\n");
}

int main(int argc, char** argv) {
    static Sim sim;
    g_sim = &sim;
    bool headless = false, smallMem = false;
    std::string script, outWav;
    for (int c = 0; c < NCH; c++) sim.src[c].setDemo(c);
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        if (a == "--in" && i + 2 < argc) {
            int ch = atoi(argv[++i]) - 1;
            const char* f = argv[++i];
            if (ch < 0 || ch >= NCH || !sim.src[ch].setFile(f, FS)) { fprintf(stderr, "cannot load %s\n", f); return 1; }
        } else if (a == "--usb" && i + 1 < argc) {
            if (!sim.usbSrc.setFile(argv[++i], FS)) { fprintf(stderr, "cannot load %s\n", argv[i]); return 1; }
            sim.usbOn = true;
        } else if (a == "--out" && i + 1 < argc) outWav = argv[++i];
        else if (a == "--script" && i + 1 < argc) script = argv[++i];
        else if (a == "--headless") headless = true;
        else if (a == "--small-mem") smallMem = true;
        else if (a == "--data" && i + 1 < argc) sim.hal.dataDir = argv[++i];
        else if (a == "--midi") sim.hal.verboseMidi = true;
        else { usage(); return a == "--help" || a == "-h" ? 0 : 1; }
    }
    sim.hal.virtualClock = headless;
    sim.init(smallMem);
    if (!outWav.empty()) sim.openOutWav(outWav.c_str());

    static uint16_t panelBuf[WIN_W * WIN_H];
    Canvas panel(panelBuf, WIN_W, WIN_H);
    bool latched[B_COUNT] = {};
    float ang[E_COUNT] = {};

    std::vector<std::string> lines;
    if (!script.empty()) {
        std::ifstream f(script);
        if (!f) { fprintf(stderr, "cannot open %s\n", script.c_str()); return 1; }
        for (std::string l; std::getline(f, l);) lines.push_back(l);
    }
    if (headless) {
        for (auto& l : lines)
            if (!runScriptLine(sim, l, &panel, latched, ang)) break;
        if (sim.recorder.active()) sim.recorder.stop();
        sim.closeOutWav();
        return 0;
    }

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO) != 0) { fprintf(stderr, "SDL: %s\n", SDL_GetError()); return 1; }
    SDL_Window* win = SDL_CreateWindow("Pocket digital mixer - simulator", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                                       WIN_W, WIN_H, SDL_WINDOW_ALLOW_HIGHDPI);
    SDL_Renderer* ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    SDL_RenderSetLogicalSize(ren, WIN_W, WIN_H);
    SDL_Texture* tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_RGB565, SDL_TEXTUREACCESS_STREAMING, WIN_W, WIN_H);
    SDL_AudioSpec want = {}, have = {};
    want.freq = (int)FS;
    want.format = AUDIO_F32SYS;
    want.channels = 2;
    want.samples = 256;
    want.callback = audioCallback;
    SDL_AudioDeviceID dev = SDL_OpenAudioDevice(nullptr, 0, &want, &have, 0);
    if (!dev) fprintf(stderr, "no audio device: %s (running silent)\n", SDL_GetError());
    else SDL_PauseAudioDevice(dev, 0);

    size_t scriptPos = 0;
    uint32_t scriptWaitUntil = 0;
    Panel::Hit drag;
    int dragY = 0, dragAcc = 0;
    bool dragMoved = false;
    float wheelAcc = 0;
    bool running = true;
    int shotN = 1;
    auto setHeld = [&](int b, bool down) { if (!latched[b]) sim.ui.button(b, down); };
    auto turn = [&](int id, int d) { sim.ui.encoder(id, d); ang[id] += d * 0.26f; };

    while (running) {
        SDL_Event e;
        while (SDL_PollEvent(&e)) {
            switch (e.type) {
                case SDL_QUIT: running = false; break;
                case SDL_MOUSEWHEEL: {
                    int mx, my;
                    SDL_GetMouseState(&mx, &my);
                    Panel::Hit h = Panel::hit(mx, my);
                    if (h.t == Panel::Hit::Enc) {
                        wheelAcc += e.wheel.preciseY;
                        while (wheelAcc >= 1) { turn(h.id, 1); wheelAcc -= 1; }
                        while (wheelAcc <= -1) { turn(h.id, -1); wheelAcc += 1; }
                    } else if (h.t == Panel::Hit::Fader) {
                        sim.ui.fader(h.id, sim.live.fader[h.id] + e.wheel.preciseY * 0.01f);
                    }
                    break;
                }
                case SDL_MOUSEBUTTONDOWN: {
                    Panel::Hit h = Panel::hit(e.button.x, e.button.y);
                    if (e.button.button == SDL_BUTTON_RIGHT) {
                        if (h.t == Panel::Hit::Btn && (h.id == B_AUX || h.id == B_FX1 || h.id == B_FX2 || h.id == B_SHIFT)) {
                            latched[h.id] = !latched[h.id];
                            sim.ui.button(h.id, latched[h.id]);
                        } else if (h.t == Panel::Hit::Enc) sim.ui.button(h.id == E_MASTER ? B_MASTER : h.id, true), drag = h;
                        break;
                    }
                    drag = h; dragY = e.button.y; dragAcc = 0; dragMoved = false;
                    if (h.t == Panel::Hit::Btn) setHeld(h.id, true);
                    if (h.t == Panel::Hit::Fader) sim.ui.fader(h.id, faderFromY(e.button.y));
                    break;
                }
                case SDL_MOUSEMOTION:
                    if (!(e.motion.state & SDL_BUTTON_LMASK)) break;
                    if (drag.t == Panel::Hit::Fader) sim.ui.fader(drag.id, faderFromY(e.motion.y));
                    if (drag.t == Panel::Hit::Enc) {
                        dragAcc += dragY - e.motion.y;
                        dragY = e.motion.y;
                        while (dragAcc >= 8) { turn(drag.id, 1); dragAcc -= 8; dragMoved = true; }
                        while (dragAcc <= -8) { turn(drag.id, -1); dragAcc += 8; dragMoved = true; }
                    }
                    break;
                case SDL_MOUSEBUTTONUP:
                    if (e.button.button == SDL_BUTTON_RIGHT) {
                        if (drag.t == Panel::Hit::Enc) sim.ui.button(drag.id == E_MASTER ? B_MASTER : drag.id, false);
                        drag = {};
                        break;
                    }
                    if (drag.t == Panel::Hit::Btn) setHeld(drag.id, false);
                    if (drag.t == Panel::Hit::Enc && !dragMoved) {
                        int b = drag.id == E_MASTER ? B_MASTER : drag.id;
                        sim.ui.button(b, true);
                        sim.ui.button(b, false);
                    }
                    drag = {};
                    break;
                case SDL_KEYDOWN:
                case SDL_KEYUP: {
                    bool down = e.type == SDL_KEYDOWN;
                    if (e.key.repeat) break;
                    switch (e.key.keysym.sym) {
                        case SDLK_LSHIFT: case SDLK_RSHIFT: setHeld(B_SHIFT, down); break;
                        case SDLK_a: setHeld(B_AUX, down); break;
                        case SDLK_f: setHeld(B_FX1, down); break;
                        case SDLK_g: setHeld(B_FX2, down); break;
                        case SDLK_q: sim.ui.button(B_MUTE1, down); break;
                        case SDLK_w: sim.ui.button(B_MUTE1 + 1, down); break;
                        case SDLK_e: sim.ui.button(B_MUTE1 + 2, down); break;
                        case SDLK_r: sim.ui.button(B_MUTE1 + 3, down); break;
                        case SDLK_RETURN: sim.ui.button(B_MASTER, down); break;
                        case SDLK_UP: if (down) turn(E_MASTER, 1); break;
                        case SDLK_DOWN: if (down) turn(E_MASTER, -1); break;
                        case SDLK_o: if (down) sim.monitor = (sim.monitor + 1) % 3; break;
                        case SDLK_SPACE: if (down) sim.paused = !sim.paused; break;
                        case SDLK_p:
                            if (down) {
                                char f[32];
                                snprintf(f, sizeof f, "screen-%02d.png", shotN++);
                                writePng(f, sim.display, DISPLAY_W, DISPLAY_H);
                                printf("saved %s\n", f);
                            }
                            break;
                        case SDLK_ESCAPE: running = false; break;
                        default: break;
                    }
                    break;
                }
            }
        }
        // a script in GUI mode runs on the real clock
        while (scriptPos < lines.size() && sim.hal.millis() >= scriptWaitUntil) {
            std::istringstream in(lines[scriptPos]);
            std::string cmd;
            in >> cmd;
            if (cmd == "wait") { int ms; in >> ms; scriptWaitUntil = sim.hal.millis() + ms; scriptPos++; break; }
            if (!runScriptLine(sim, lines[scriptPos++], &panel, latched, ang)) { running = false; break; }
        }
        sim.ui.tick();
        sim.ui.render(sim.disp);
        drawPanel(sim, panel, latched, ang);
        SDL_UpdateTexture(tex, nullptr, panelBuf, WIN_W * 2);
        SDL_RenderClear(ren);
        SDL_RenderCopy(ren, tex, nullptr, nullptr);
        SDL_RenderPresent(ren);
    }
    if (dev) SDL_CloseAudioDevice(dev);
    if (sim.recorder.active()) sim.recorder.stop();
    sim.closeOutWav();
    SDL_Quit();
    return 0;
}
