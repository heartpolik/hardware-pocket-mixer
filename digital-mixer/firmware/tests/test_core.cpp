// Checks of the portable core without hardware: DSP, mixer routing, FX timing, tuner, UI layers.
#include <math.h>
#include <stdio.h>
#include <string.h>

#include <vector>

#include "../src/core/fx.h"
#include "../src/core/hal.h"
#include "../src/core/mixer.h"
#include "../src/core/recorder.h"
#include "../src/core/tuner.h"
#include "../src/core/ui.h"

static int fails = 0, checks = 0;
#define CHECK(cond, ...)                                              \
    do {                                                              \
        checks++;                                                     \
        if (!(cond)) {                                                \
            fails++;                                                  \
            printf("FAIL %s:%d: %s  ", __FILE__, __LINE__, #cond);    \
            printf(__VA_ARGS__);                                      \
            printf("\n");                                             \
        }                                                             \
    } while (0)

static constexpr float FS = 48000.f;
static constexpr int N = Mixer::MAX_BLOCK;

struct Rig {
    Scene scene;
    Live live;
    Mixer mix;
    std::vector<int16_t> pool[NFX];
    float in[8][N] = {}, out[6][N] = {}, usb[8][N] = {};
    Rig() {
        scene.defaults();
        for (auto& r : scene.fx) r.ret = 0;
        int16_t* p[NFX];
        for (int i = 0; i < NFX; i++) { pool[i].assign(96000, 0); p[i] = pool[i].data(); }
        mix.init(FS, &scene, &live, p, 96000);
    }
    // runs `blocks` blocks of a sine on channel ch (both sides), returns MAIN L/R peak of the last block
    void run(int blocks, int ch, float amp, float hz, float* pkL, float* pkR, int out0 = 0) {
        static uint64_t t = 0;
        for (int b = 0; b < blocks; b++) {
            for (int i = 0; i < N; i++, t++) {
                float s = amp * sinf(2 * dsp::kPi * hz * t / FS);
                for (int k = 0; k < 8; k++) in[k][i] = (k / 2 == ch) ? s : 0.f;
            }
            AudioIO io;
            for (int k = 0; k < 8; k++) { io.in[k] = in[k]; io.usbOut[k] = usb[k]; }
            for (int k = 0; k < 6; k++) io.out[k] = out[k];
            io.n = N;
            mix.process(io);
        }
        *pkL = *pkR = 0;
        for (int i = 0; i < N; i++) {
            *pkL = fmaxf(*pkL, fabsf(out[out0][i]));
            *pkR = fmaxf(*pkR, fabsf(out[out0 + 1][i]));
        }
    }
};

static void testBiquad() {
    dsp::BiquadCoefs k;
    k.peak(FS, 1000, 0.7f, 0);
    CHECK(k.identity(), "0 dB peak must be bypassed");
    // +6 dB peak: a 1 kHz sine comes out at +6 dB
    k.peak(FS, 1000, 0.7f, 6);
    dsp::BiquadState s;
    float pk = 0;
    for (int i = 0; i < 48000; i++) {
        float y = s.run(k, sinf(2 * dsp::kPi * 1000 * i / FS));
        if (i > 24000) pk = fmaxf(pk, fabsf(y));
    }
    CHECK(fabsf(dsp::linToDb(pk) - 6.f) < 0.1f, "peak gain %.2f dB", dsp::linToDb(pk));
    // low shelf +10 dB: 30 Hz gets ~+10, 5 kHz ~0
    k.lowShelf(FS, 120, 10);
    for (float f : {30.f, 5000.f}) {
        s.reset(); pk = 0;
        for (int i = 0; i < 96000; i++) {
            float y = s.run(k, sinf(2 * dsp::kPi * f * i / FS));
            if (i > 48000) pk = fmaxf(pk, fabsf(y));
        }
        float want = f < 100 ? 10.f : 0.f;
        CHECK(fabsf(dsp::linToDb(pk) - want) < 0.6f, "shelf at %.0f Hz: %.2f dB", f, dsp::linToDb(pk));
    }
}

static void testFastMath() {
    for (float db = -60; db <= 20; db += 7.3f) {
        float x = dsp::dbToLin(db);
        CHECK(fabsf(dsp::fastDb(x) - db) < 0.05f, "fastDb(%.1f) = %.3f", db, dsp::fastDb(x));
        CHECK(fabsf(dsp::fastDbToLin(db) / x - 1.f) < 0.01f, "fastDbToLin(%.1f)", db);
    }
}

static void testMixer() {
    Rig r;
    float l, rr;
    // mono channel 1, fader at unity, centre pan: -3 dB per side
    r.scene.ch[0].stereo = 0;
    r.live.fader[0] = 0.75f;
    r.scene.mainDb = 0;
    r.scene.limiter = 0;
    r.run(20, 0, 0.5f, 1000, &l, &rr);
    CHECK(fabsf(dsp::linToDb(l) - dsp::linToDb(0.5f * 0.7071f)) < 0.2f, "mono centre L %.2f dB", dsp::linToDb(l));
    CHECK(fabsf(l - rr) < 0.01f, "mono centre L=R");
    // hard left
    r.scene.ch[0].pan = -1;
    r.run(10, 0, 0.5f, 1000, &l, &rr);
    CHECK(rr < 0.001f && fabsf(l - 0.5f) < 0.01f, "hard left: L %.3f R %.3f", l, rr);
    // mute
    r.scene.ch[0].mute = 1;
    r.run(4, 0, 0.5f, 1000, &l, &rr);
    CHECK(l < 1e-4f && rr < 1e-4f, "mute: %.5f", l);
    // cue: phones follow the cued channel even when muted (pre-fader), MAIN stays silent
    r.scene.ch[0].cue = 1;
    r.scene.phonesDb = 0;
    r.run(10, 0, 0.5f, 1000, &l, &rr, 4);
    CHECK(l > 0.3f, "cue in phones: %.3f", l);
    r.run(1, 0, 0.5f, 1000, &l, &rr, 0);
    CHECK(l < 1e-4f, "MAIN silent while muted");
    // aux send post fader
    r.scene.ch[0].mute = 0; r.scene.ch[0].cue = 0; r.scene.ch[0].pan = 0;
    r.scene.ch[0].sendAux = 1; r.scene.auxDb = 0;
    r.run(10, 0, 0.5f, 1000, &l, &rr, 2);
    CHECK(fabsf(l - 0.5f * 0.7071f) < 0.02f, "aux send %.3f", l);
    r.live.fader[0] = 0;
    r.run(10, 0, 0.5f, 1000, &l, &rr, 2);
    CHECK(l < 1e-4f, "aux is post-fader");
    // USB to the DAW carries the raw inputs
    CHECK(fabsf(r.usb[0][5] - r.in[0][5]) < 1e-6f, "usb out = input");
}

static void testLimiter() {
    Rig r;
    float l, rr;
    r.scene.ch[0].stereo = 1;
    r.live.fader[0] = 1.0f;            // +6 dB
    r.scene.mainDb = 6;
    r.scene.limiter = 1;
    r.run(100, 0, 0.9f, 220, &l, &rr);   // ~ +12 dBFS into the limiter
    CHECK(l <= 0.967f && l > 0.8f, "limited peak %.3f", l);
    CHECK(r.mix.limGr > 3, "gain reduction %.1f dB", (double)r.mix.limGr);
}

static void testDelayTiming() {
    std::vector<int16_t> pool(96000);
    FxEngine fx;
    fx.init(FS, pool.data(), (uint32_t)pool.size());
    FxParams p;
    p.type = (uint8_t)FxType::Delay;
    p.p[0] = 0.65f;                   // 1/4 note
    p.p[1] = 0;                       // no feedback
    p.p[2] = 1;
    float bpm = 120;                  // 1/4 = 0.5 s = 24000 samples
    std::vector<float> outL;
    float inL[N], inR[N], oL[N], oR[N];
    for (int b = 0; b < 300; b++) {
        for (int i = 0; i < N; i++) inL[i] = inR[i] = (b == 0 && i == 0) ? 1.f : 0.f;
        fx.process(inL, inR, oL, oR, N, p, bpm);
        outL.insert(outL.end(), oL, oL + N);
    }
    size_t at = 0;
    float best = 0;
    for (size_t i = 0; i < outL.size(); i++) if (fabsf(outL[i]) > best) { best = fabsf(outL[i]); at = i; }
    CHECK(labs((long)at - 24000) <= 2, "echo at %zu (want 24000)", at);
}

static void testFxStability() {
    // every engine at extreme settings stays finite and bounded
    std::vector<int16_t> pool(96000);
    for (int t = 0; t < (int)FxType::Count; t++) {
        FxEngine fx;
        fx.init(FS, pool.data(), (uint32_t)pool.size());
        FxParams p;
        p.type = (uint8_t)t;
        p.p[0] = p.p[1] = p.p[2] = 1.f;
        float inL[N], inR[N], oL[N], oR[N], pk = 0;
        bool finite = true;
        for (int b = 0; b < 2000; b++) {
            for (int i = 0; i < N; i++) inL[i] = inR[i] = 0.5f * sinf(b * N + i);
            fx.process(inL, inR, oL, oR, N, p, 120);
            for (int i = 0; i < N; i++) { finite &= std::isfinite(oL[i]) && std::isfinite(oR[i]); pk = fmaxf(pk, fabsf(oL[i])); }
        }
        CHECK(finite && pk < 8.f, "%s: peak %.2f finite %d", fxName((FxType)t), pk, finite);
    }
}

static void testTuner() {
    static float ring[Mixer::TUNER_LEN];
    float rate = FS / 2;
    for (float hz : {82.41f, 110.f, 440.f, 1046.5f}) {
        for (int i = 0; i < Mixer::TUNER_LEN; i++) ring[i] = 0.3f * sinf(2 * dsp::kPi * hz * i / rate);
        TunerResult r = tunerAnalyze(ring, 0, Mixer::TUNER_LEN, rate);
        CHECK(r.valid && fabsf(1200 * log2f(r.hz / hz)) < 3, "tuner %.2f -> %.2f Hz (%s)", hz, r.hz, r.note);
    }
}

struct FakeHal : Hal {
    uint32_t t = 0;
    std::vector<std::vector<uint8_t>> slots = std::vector<std::vector<uint8_t>>(10);
    std::vector<uint8_t> midi;
    float gain[NCH] = {};
    uint32_t millis() override { return t; }
    uint32_t micros() override { return t * 1000; }
    void setInputGain(int ch, float db) override { gain[ch] = db; }
    void midiOut(const uint8_t* m, int n) override { midi.insert(midi.end(), m, m + n); }
    bool load(int s, void* d, uint32_t n) override {
        if (slots[s].size() != n) return false;
        memcpy(d, slots[s].data(), n);
        return true;
    }
    bool save(int s, const void* d, uint32_t n) override {
        slots[s].assign((const uint8_t*)d, (const uint8_t*)d + n);
        return true;
    }
    void setBacklight(int) override {}
    float batteryVolts() override { return 4.0f; }
    FileSink* recSink() override { return nullptr; }
    void recFileName(char* b, int n) override { snprintf(b, n, "X.WAV"); }
    int recChannels() override { return 2; }
};

static void testUi() {
    Rig r;
    FakeHal hal;
    Settings st;
    Ui ui;
    ui.init(&hal, &r.mix, &r.scene, &r.live, &st, nullptr);
    ui.begin();
    // default layer: row 1 = EQ HI
    ui.encoder(0, 2);
    CHECK(fabsf(r.scene.ch[0].eq[0] - 1.0f) < 1e-4f, "EQ HI step: %.2f", r.scene.ch[0].eq[0]);
    // AUX tap: row 1 becomes the AUX send
    ui.button(B_AUX, true); ui.button(B_AUX, false);
    hal.t += 100;
    ui.encoder(3, 1);
    CHECK(r.scene.ch[1].sendAux > 0.02f, "AUX layer send: %.3f", r.scene.ch[1].sendAux);
    // AUX held + MASTER: AUX volume, and the layer does not toggle back on release
    float aux0 = r.scene.auxDb;
    ui.button(B_AUX, true); ui.encoder(E_MASTER, -4); ui.button(B_AUX, false);
    CHECK(r.scene.auxDb < aux0 && ui.layerAux(), "AUX vol %.1f layer %d", r.scene.auxDb, ui.layerAux());
    // SHIFT: row 1 = gain -> goes to the codec
    ui.button(B_SHIFT, true);
    hal.t += 100;
    ui.encoder(6, 4);
    ui.tick();
    CHECK(fabsf(hal.gain[2] - 2.0f) < 1e-4f, "gain sent: %.2f", hal.gain[2]);
    // SHIFT + Mute = Cue
    ui.button(B_MUTE1 + 2, true); ui.button(B_MUTE1 + 2, false);
    CHECK(r.scene.ch[2].cue == 1 && r.scene.ch[2].mute == 0, "cue %d mute %d", r.scene.ch[2].cue, r.scene.ch[2].mute);
    // SHIFT + push on row 3 toggles filter <-> compressor
    ui.button(8, true); ui.button(8, false);
    CHECK(ui.rowParam(2, 2) == P_COMP, "row 3 = comp");
    ui.button(B_SHIFT, false);
    // FX I held: encoders of channel 1-3 = params, channel 4 = return; MASTER = engine
    ui.button(B_FX1, true);
    ui.encoder(0, 5);
    ui.encoder(9, -10);
    ui.encoder(E_MASTER, 1);
    ui.button(B_FX1, false);
    CHECK(r.scene.fx[0].p[0] > 0.55f && r.scene.fx[0].ret < 0.31f && r.scene.fx[0].type == 1 && !ui.layerFx(0),
          "fx edit p1 %.2f ret %.2f type %d layer %d", r.scene.fx[0].p[0], r.scene.fx[0].ret, r.scene.fx[0].type,
          ui.layerFx(0));
    // encoder push resets
    ui.button(0, true); ui.button(0, false);
    CHECK(r.scene.ch[0].sendAux == 0.f, "push resets the AUX send");
    // autosave after 3 s and restore
    hal.t += 3500;
    ui.tick();
    Scene s2;
    CHECK(hal.load(0, &s2, sizeof s2) && s2.valid() && s2.ch[2].cue == 1, "autosave");
    // MIDI CC in: channel 2 EQ LO (CC 87) on MIDI channel 2
    uint8_t cc[3] = {0xB1, 87, 127};
    ui.midiIn(cc, 3);
    CHECK(fabsf(r.scene.ch[1].eq[2] - 15.f) < 1e-3f, "CC -> EQ LO %.2f", r.scene.ch[1].eq[2]);
    // controller mode: faders send CC 7 and do not move the mix
    st.ctrlMode = 1;
    float f0 = r.live.fader[3];
    ui.fader(3, 0.2f);
    CHECK(r.live.fader[3] == f0 && hal.midi.size() >= 3 && hal.midi[hal.midi.size() - 3] == 0xB3 &&
              hal.midi[hal.midi.size() - 2] == 7, "controller mode fader -> CC");
    // render every page without crashing
    static uint16_t fb[DISPLAY_W * DISPLAY_H];
    Canvas c(fb, DISPLAY_W, DISPLAY_H);
    ui.render(c);
    ui.button(B_MASTER, true); ui.button(B_MASTER, false);
    for (int i = 0; i < 30; i++) { ui.encoder(E_MASTER, 1); ui.render(c); }
    CHECK(true, "pages render");
}

static void testRecorder() {
    struct MemSink : FileSink {
        std::vector<uint8_t> d;
        bool open(const char*) override { d.clear(); return true; }
        bool write(const void* p, uint32_t n) override { d.insert(d.end(), (const uint8_t*)p, (const uint8_t*)p + n); return true; }
        bool writeAt(uint32_t pos, const void* p, uint32_t n) override { memcpy(&d[pos], p, n); return true; }
        void close() override {}
    } sink;
    std::vector<uint8_t> ring(1 << 16);
    Recorder rec;
    rec.init(ring.data(), (uint32_t)ring.size(), FS);
    rec.start(&sink, "x", 2);
    float a[N], b[N];
    for (int i = 0; i < N; i++) { a[i] = 0.5f; b[i] = -0.5f; }
    const float* ch[2] = {a, b};
    for (int k = 0; k < 100; k++) { rec.write(ch, N); rec.service(); }
    rec.stop();
    uint32_t data = sink.d[40] | sink.d[41] << 8 | sink.d[42] << 16 | (uint32_t)sink.d[43] << 24;
    CHECK(data == 100u * N * 6 && sink.d.size() == 44 + data, "wav data %u", data);
    int32_t v = (int32_t)((uint32_t)(sink.d[44] << 8 | sink.d[45] << 16 | sink.d[46] << 24)) >> 8;
    CHECK(abs(v - 4194303) <= 1, "24-bit sample %d", v);
}

int main() {
    testBiquad();
    testFastMath();
    testMixer();
    testLimiter();
    testDelayTiming();
    testFxStability();
    testTuner();
    testUi();
    testRecorder();
    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
