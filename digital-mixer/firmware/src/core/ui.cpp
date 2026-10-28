// SPDX-License-Identifier: GPL-3.0-or-later
#include "ui.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "fx.h"
#include "hal.h"
#include "mixer.h"
#include "recorder.h"

using dsp::clampf;

enum MenuId {
    M_EXIT, M_LOAD, M_SAVE, M_MODE1, M_MODE4 = M_MODE1 + 3, M_WIDTH1, M_WIDTH4 = M_WIDTH1 + 3,
    M_PHONES, M_TEMPO, M_TAP, M_CLOCK, M_LIMITER, M_USBVOL, M_USBSEND, M_TUNER, M_REC,
    M_MIDICH, M_CTRL, M_BRIGHT, M_ENCDIR, M_SHIFTMODE, M_FADERCAL, M_BATT, M_ABOUT, M_COUNT
};
static const int MENU_ROWS = 8;

static uint16_t paramColor(int id) {
    switch (id) {
        case P_SEND_AUX: return col::CYAN;
        case P_SEND_FX1: return col::MAGENTA;
        case P_SEND_FX2: return col::ORANGE;
        case P_GAIN: return col::YELLOW;
        case P_PAN: return col::GREEN;
        case P_FILTER: return col::BLUE;
        case P_COMP: return col::RED;
        default: return col::WHITE;
    }
}

void Ui::init(Hal* hal, Mixer* mixer, Scene* scene, Live* live, Settings* settings, Recorder* rec) {
    hal_ = hal;
    mix_ = mixer;
    scene_ = scene;
    live_ = live;
    settings_ = settings;
    rec_ = rec;
}

void Ui::begin() {
    Settings st;
    if (hal_->load(9, &st, sizeof st) && st.valid()) *settings_ = st;
    else { *settings_ = Settings(); settings_->seal(); }
    Scene s;
    if (hal_->load(0, &s, sizeof s) && s.valid()) *scene_ = s;
    else scene_->defaults();
    shadow_ = *scene_;
    for (int c = 0; c < NCH; c++) sentGain_[c] = 99;
    sentBright_ = -1;
    tick();
}

// FX send rows are labelled with the engine of their bus (REVERB, DELAY ...), the rest by the parameter
const char* Ui::rowLabel(int id) const {
    if (id == P_SEND_FX1 || id == P_SEND_FX2) return fxName((FxType)scene_->fx[id == P_SEND_FX2].type);
    return paramDesc(id).name;
}

int Ui::rowParam(int ch, int row) const {
    if (shiftOn()) return row == 0 ? P_GAIN : row == 1 ? P_PAN : (compRow_[ch] ? P_COMP : P_FILTER);
    if (row == 0) return auxLayer_ ? P_SEND_AUX : P_EQ_HI;
    if (row == 1) return fxLayer_[0] ? P_SEND_FX1 : P_EQ_MID;
    return fxLayer_[1] ? P_SEND_FX2 : P_EQ_LO;
}

int Ui::fxHeld() const {
    uint32_t now = hal_->millis();
    for (int k = 0; k < NFX; k++) {
        int b = B_FX1 + k;
        if (down_[b] && (used_[b] || now - downAt_[b] > 300)) return k;
    }
    return -1;
}

// Linear 3.3..4.2 V (VSYS / 2 on A14); a LiPo discharge curve is a later refinement (06-firmware, p. 7).
int Ui::batteryPercent() {
    float v = hal_->batteryVolts();
    if (v <= 0) return -1;
    return (int)clampf((v - 3.3f) / (4.2f - 3.3f) * 100.f, 0, 100);
}

void Ui::changed() {
    dirty_ = true;
    dirtyAt_ = hal_->millis();
}

// ------------------------------------------------------------------ parameters
void Ui::setParam(int ch, int id, float v, bool fromMidi) {
    Scene& s = fromMidi ? *scene_ : ed();
    paramSet(s, *live_, ch, id, v);
    if (settings_->ctrlMode && !fromMidi) sendCC(ch, id);
    changed();
    if (isGlobal(id) && !fromMidi) {
        char val[16];
        paramFormat(id, paramGet(s, *live_, ch, id), val, sizeof val);
        const char* name = paramDesc(id).name;
        if (id >= P_FX1_TYPE) {
            static char nm[16];
            int k = id >= P_FX2_TYPE ? 1 : 0, j = id - (k ? P_FX2_TYPE : P_FX1_TYPE);
            FxType t = (FxType)s.fx[k].type;
            snprintf(nm, sizeof nm, "FX%d %s", k + 1, j == 0 ? "" : j == 4 ? "RET" : fxParamName(t, j - 1));
            name = nm;
        }
        toast(name, val);
    }
}

void Ui::stepParam(int ch, int id, int delta) {
    const ParamDesc& d = paramDesc(id);
    float v = paramGet(ed(), *live_, ch, id);
    if (d.kind == K_ENUM) {
        int n = (int)(d.max - d.min) + 1;
        int i = ((int)v - (int)d.min + delta) % n;
        if (i < 0) i += n;
        setParam(ch, id, d.min + i);
        return;
    }
    if (d.min <= -59.f) {                              // volumes: -60 = OFF, finer steps near 0 dB
        if (v <= d.min + 0.01f && delta > 0) { setParam(ch, id, -48.f + 3.f * (delta - 1)); return; }
        for (int i = 0, n = delta > 0 ? delta : -delta; i < n; i++) {
            float st = v < -30.f ? 3.f : v < -12.f ? 1.f : d.step;
            v += delta > 0 ? st : -st;
            if (v < -48.f && delta < 0) v = d.min;        // below -48 dB: OFF
        }
        setParam(ch, id, v);
        return;
    }
    setParam(ch, id, v + d.step * delta);
}

void Ui::sendCC(int ch, int id) {
    const ParamDesc& d = paramDesc(id);
    if (!d.cc) return;
    int slot = isGlobal(id) ? 4 : ch;
    uint8_t mch = (uint8_t)((settings_->midiCh + slot) & 15);
    uint8_t val = (uint8_t)lroundf(paramNorm(id, paramGet(ed(), *live_, ch, id)) * 127.f);
    if (lastCC_[slot][d.cc] == val + 1) return;
    lastCC_[slot][d.cc] = val + 1;
    uint8_t msg[3] = {(uint8_t)(0xB0 | mch), d.cc, val};
    hal_->midiOut(msg, 3);
}

void Ui::toast(const char* label, const char* value) {
    snprintf(toastL_, sizeof toastL_, "%s", label);
    snprintf(toastV_, sizeof toastV_, "%s", value);
    toastUntil_ = hal_->millis() + 1200;
}

// ------------------------------------------------------------------ input events
void Ui::encoder(int id, int delta) {
    if (id < 0 || id >= E_COUNT || !delta) return;
    if (settings_->encInvert) delta = -delta;
    uint32_t now = hal_->millis();
    uint32_t dt = encSeen_[id] ? now - encAt_[id] : 1000;
    encAt_[id] = now;
    encSeen_[id] = true;
    if (page_ == HOME) delta *= dt < 25 ? 4 : dt < 60 ? 2 : 1;      // acceleration (not in the menu)

    if (id == E_MASTER) {
        if (page_ == MENU) { menuTurn(delta); return; }
        if (page_ == TUNER) { tunerCh_ = (tunerCh_ + delta % NCH + NCH) % NCH; return; }
        for (int k = 0; k < NFX; k++)
            if (down_[B_FX1 + k]) {
                used_[B_FX1 + k] = true;
                stepParam(-1, k ? P_FX2_TYPE : P_FX1_TYPE, delta > 0 ? 1 : -1);
                return;
            }
        if (down_[B_AUX]) { used_[B_AUX] = true; stepParam(-1, P_AUX, delta); return; }
        if (shiftOn()) { used_[B_SHIFT] = true; stepParam(-1, P_PHONES, delta); return; }
        if (auxLayer_) { stepParam(-1, P_AUX, delta); return; }      // AUX layer on: MASTER = AUX out
        stepParam(-1, P_MAIN, delta);
        return;
    }
    int ch = id / 3, row = id % 3;
    for (int k = 0; k < NFX; k++)
        if (down_[B_FX1 + k]) {                       // FX edit: columns 1-3 = params, 4 = return
            used_[B_FX1 + k] = true;
            int base = k ? P_FX2_TYPE : P_FX1_TYPE;
            stepParam(-1, ch < 3 ? base + 1 + ch : base + 4, delta);
            return;
        }
    if (shiftOn()) used_[B_SHIFT] = true;
    stepParam(ch, rowParam(ch, row), delta);
}

void Ui::button(int id, bool down) {
    if (id < 0 || id >= B_COUNT) return;
    uint32_t now = hal_->millis();
    down_[id] = down;
    if (down) { downAt_[id] = now; used_[id] = false; }
    else {
        if (page_ != HOME) return;
        if (id == B_AUX && !used_[id]) auxLayer_ = !auxLayer_;
        if ((id == B_FX1 || id == B_FX2) && !used_[id] && now - downAt_[id] < 400) {
            int k = id - B_FX1;
            fxLayer_[k] = !fxLayer_[k];
        }
        return;
    }

    if (id == B_SHIFT && settings_->shiftToggle) { shiftLatched_ = !shiftLatched_; return; }
    if (id == B_MASTER) {
        if (page_ == MENU) {
            if (shiftOn()) { used_[B_SHIFT] = true; shiftLatched_ = false; page_ = HOME; menuEdit_ = false; }
            else menuPress();
        } else if (page_ == TUNER) page_ = MENU;
        else if (page_ == FADER_CAL) {
            if (shiftOn()) { used_[B_SHIFT] = true; page_ = MENU; toast("FADER CAL", "CANCELLED"); }
            else faderCalPress();
        } else { page_ = MENU; menuEdit_ = false; }
        return;
    }
    if (id >= B_MUTE1 && id < B_MUTE1 + NCH) {
        int ch = id - B_MUTE1;
        if (shiftOn()) {                               // SHIFT + Mute = Cue (DM28)
            used_[B_SHIFT] = true;
            setParam(ch, P_CUE, ed().ch[ch].cue ? 0.f : 1.f);
        } else setParam(ch, P_MUTE, ed().ch[ch].mute ? 0.f : 1.f);
        return;
    }
    if (id < 12) {                                     // channel encoder push
        int ch = id / 3, row = id % 3;
        for (int k = 0; k < NFX; k++)
            if (down_[B_FX1 + k]) {
                used_[B_FX1 + k] = true;
                int pid = (k ? P_FX2_TYPE : P_FX1_TYPE) + (ch < 3 ? 1 + ch : 4);
                setParam(-1, pid, paramDesc(pid).def);
                return;
            }
        if (shiftOn() && row == 2) {                   // filter <-> compressor on the 3rd row (DM28)
            used_[B_SHIFT] = true;
            compRow_[ch] = !compRow_[ch];
            toast(compRow_[ch] ? "ROW 3" : "ROW 3", compRow_[ch] ? "COMP" : "FILTER");
            return;
        }
        if (shiftOn()) used_[B_SHIFT] = true;
        int pid = rowParam(ch, row);
        setParam(ch, pid, paramDesc(pid).def);
    }
}

// raw -> 0..1 by the stored end points, with 2 % dead zones so the ends are solid OFF / +6 dB
float Ui::calibrated(int ch, float raw) const {
    float lo = settings_->fadLo[ch] / 65535.f, hi = settings_->fadHi[ch] / 65535.f;
    float x = fabsf(hi - lo) < 0.05f ? raw : (raw - lo) / (hi - lo);
    return clampf((x - 0.02f) / 0.96f, 0, 1);
}

void Ui::fader(int ch, float raw) {
    if (ch < 0 || ch >= NCH) return;
    lastRaw_[ch] = clampf(raw, 0, 1);
    if (page_ == FADER_CAL) return;                    // the mix keeps the last positions meanwhile
    float pos = calibrated(ch, lastRaw_[ch]);
    if (settings_->ctrlMode) {
        uint8_t mch = (uint8_t)((settings_->midiCh + ch) & 15);
        uint8_t val = (uint8_t)lroundf(pos * 127.f);
        if (lastCC_[ch][7] != val + 1) {
            lastCC_[ch][7] = val + 1;
            uint8_t msg[3] = {(uint8_t)(0xB0 | mch), 7, val};
            hal_->midiOut(msg, 3);
        }
        return;
    }
    live_->fader[ch] = pos;
}

void Ui::midiIn(const uint8_t* msg, int n) {
    if (n < 1) return;
    uint8_t st = msg[0];
    if (st == 0xF8) {                                  // MIDI clock, 24 ppqn
        uint32_t us = hal_->micros();
        if (extTickUs_) {
            float iv = (float)(us - extTickUs_);
            extTickAvg_ = extTickAvg_ > 0 ? extTickAvg_ * 0.9f + iv * 0.1f : iv;
            if (++extTicks_ % 24 == 0 && extTickAvg_ > 0) {
                float bpm = roundf(60e6f / (extTickAvg_ * 24.f) * 10.f) / 10.f;
                scene_->bpm = clampf(bpm, 20, 300);
            }
        }
        extTickUs_ = us;
        extClockAt_ = hal_->millis();
        return;
    }
    uint8_t type = st & 0xF0;
    int rel = ((st & 0x0F) - settings_->midiCh + 16) & 15;
    if (type == 0xB0 && n >= 3 && rel <= 4) {
        int id = paramFromCC(msg[1], rel == 4);
        if (id < 0) return;
        float v = paramDesc(id).kind == K_BOOL ? (msg[2] >= 64 ? 1.f : 0.f) : paramFromNorm(id, msg[2] / 127.f);
        setParam(rel == 4 ? -1 : rel, id, v, true);
    } else if (type == 0xC0 && n >= 2 && rel == 4) {
        loadScene(msg[1] % NSCENES + 1);               // program change on the master channel
    }
}

// ------------------------------------------------------------------ scenes, tempo, recorder
void Ui::loadScene(int slot) {
    Scene s;
    char v[8];
    snprintf(v, sizeof v, "%d", slot);
    if (hal_->load(slot, &s, sizeof s) && s.valid()) {
        *scene_ = s;
        shadow_ = s;
        settings_->lastScene = (uint8_t)slot;
        settingsDirty_ = true;
        changed();
        toast("LOADED", v);
    } else toast("EMPTY", v);
}

void Ui::saveScene(int slot) {
    Scene s = *scene_;
    s.seal();
    char v[8];
    snprintf(v, sizeof v, "%d", slot);
    toast(hal_->save(slot, &s, sizeof s) ? "SAVED" : "SAVE ERR", v);
    settings_->lastScene = (uint8_t)slot;
    settingsDirty_ = true;
}

void Ui::tap() {
    uint32_t now = hal_->millis();
    if (tapN_ && now - taps_[(tapN_ - 1) % 4] > 2000) tapN_ = 0;
    taps_[tapN_ % 4] = now;
    tapN_++;
    if (tapN_ >= 2) {
        int k = tapN_ > 4 ? 3 : (int)tapN_ - 1;
        uint32_t span = taps_[(tapN_ - 1) % 4] - taps_[(tapN_ - 1 - k) % 4];
        if (span > 0) setParam(-1, P_BPM, roundf(60000.f * k / span));
    }
}

void Ui::toggleRecord() {
    if (!rec_) return;
    if (rec_->active()) { rec_->stop(); toast("REC", "STOPPED"); return; }
    FileSink* sink = hal_->recSink();
    if (!sink) { toast("REC", "NO CARD"); return; }
    char name[32];
    hal_->recFileName(name, sizeof name);
    if (rec_->start(sink, name, hal_->recChannels())) toast("REC", name);
    else toast("REC", "FAILED");
}

// ------------------------------------------------------------------ tick
void Ui::tick() {
    uint32_t now = hal_->millis();
    for (int c = 0; c < NCH; c++)
        if (scene_->ch[c].gainDb != sentGain_[c]) {
            sentGain_[c] = scene_->ch[c].gainDb;
            hal_->setInputGain(c, sentGain_[c]);
        }
    if (settings_->brightness != sentBright_) {
        sentBright_ = settings_->brightness;
        hal_->setBacklight(sentBright_);
    }
    if (dirty_ && now - dirtyAt_ > 3000) {             // autosave: the power switch cuts power at once
        Scene s = *scene_;
        s.seal();
        hal_->save(0, &s, sizeof s);
        dirty_ = false;
    }
    if (settingsDirty_) {
        settings_->seal();
        hal_->save(9, settings_, sizeof *settings_);
        settingsDirty_ = false;
    }
    if (extClockAt_ && now - extClockAt_ > 1000) { extClockAt_ = 0; extTickUs_ = 0; extTickAvg_ = 0; }
    if (settings_->clockOut && !extClockAt_) {
        uint32_t us = hal_->micros();
        uint32_t iv = (uint32_t)(60e6f / (scene_->bpm * 24.f));
        if ((int32_t)(us - clockNextUs_) >= 0) {
            uint8_t m = 0xF8;
            hal_->midiOut(&m, 1);
            clockNextUs_ += iv;
            if ((int32_t)(us - clockNextUs_) > (int32_t)(4 * iv)) clockNextUs_ = us + iv;   // resync
        }
    }
    if (rec_) rec_->service();
    mix_->tunerChannel = page_ == TUNER ? tunerCh_ : -1;
    mix_->usbSend = settings_->usbSend;
    if (page_ == TUNER && now - tunerAt_ > 120) {
        tunerAt_ = now;
        tuner_ = tunerAnalyze(mix_->tunerBuf, mix_->tunerWrite, Mixer::TUNER_LEN, mix_->fs() / 2);
    }
}

// ------------------------------------------------------------------ menu
void Ui::menuItem(int i, char* label, char* value, int n) {
    value[0] = 0;
    char tmp[16];
    if (i >= M_MODE1 && i <= M_MODE4) {
        snprintf(label, n, "IN%d", i - M_MODE1 + 1);
        snprintf(value, n, "%s", scene_->ch[i - M_MODE1].stereo ? "STEREO" : "MONO");
        return;
    }
    if (i >= M_WIDTH1 && i <= M_WIDTH4) {
        int c = i - M_WIDTH1;
        snprintf(label, n, "IN%d WIDTH", c + 1);
        if (scene_->ch[c].stereo) snprintf(value, n, "%d", (int)lroundf(scene_->ch[c].width * 100));
        else snprintf(value, n, "-");
        return;
    }
    switch (i) {
        case M_EXIT: snprintf(label, n, "< BACK"); break;
        case M_LOAD: snprintf(label, n, "LOAD SCENE"); snprintf(value, n, "%d", menuSlot_); break;
        case M_SAVE: snprintf(label, n, "SAVE SCENE"); snprintf(value, n, "%d", menuSlot_); break;
        case M_PHONES: {
            static const char* const S[] = {"AUTO", "MAIN", "CUE"};
            snprintf(label, n, "PHONES SRC");
            snprintf(value, n, "%s", S[scene_->phonesSrc % 3]);
            break;
        }
        case M_TEMPO:
            snprintf(label, n, "TEMPO");
            snprintf(value, n, extClockAt_ ? "EXT %.1f" : "%.0f", (double)scene_->bpm);
            break;
        case M_TAP: snprintf(label, n, "TAP TEMPO"); snprintf(value, n, "PRESS"); break;
        case M_CLOCK: snprintf(label, n, "CLOCK OUT"); snprintf(value, n, settings_->clockOut ? "ON" : "OFF"); break;
        case M_LIMITER: snprintf(label, n, "LIMITER"); snprintf(value, n, scene_->limiter ? "ON" : "OFF"); break;
        case M_USBVOL:
            snprintf(label, n, "USB IN VOL");
            paramFormat(P_USB, scene_->usbDb, value, n);
            break;
        case M_USBSEND:
            snprintf(label, n, "USB SEND");
            if (settings_->usbSend) snprintf(value, n, "IN%d", settings_->usbSend);
            else snprintf(value, n, "MAIN");
            break;
        case M_TUNER: snprintf(label, n, "TUNER"); snprintf(value, n, ">"); break;
        case M_REC:
            snprintf(label, n, "RECORD");
            if (rec_ && rec_->active()) {
                uint32_t s = rec_->seconds();
                snprintf(value, n, "%02u:%02u", (unsigned)(s / 60), (unsigned)(s % 60));
            } else snprintf(value, n, "OFF");
            break;
        case M_MIDICH: snprintf(label, n, "MIDI CH"); snprintf(value, n, "%d-%d", settings_->midiCh + 1, (settings_->midiCh + 4) % 16 + 1); break;
        case M_CTRL: snprintf(label, n, "CONTROLLER"); snprintf(value, n, settings_->ctrlMode ? "ON" : "OFF"); break;
        case M_BRIGHT: snprintf(label, n, "BRIGHTNESS"); snprintf(value, n, "%d", settings_->brightness); break;
        case M_ENCDIR: snprintf(label, n, "ENC DIR"); snprintf(value, n, settings_->encInvert ? "INVERT" : "NORMAL"); break;
        case M_SHIFTMODE: snprintf(label, n, "SHIFT MODE"); snprintf(value, n, settings_->shiftToggle ? "TOGGLE" : "HOLD"); break;
        case M_FADERCAL: snprintf(label, n, "FADER CAL"); snprintf(value, n, ">"); break;
        case M_BATT: {
            int pct = batteryPercent();
            snprintf(label, n, "BATTERY");
            if (pct >= 0) snprintf(value, n, "%d%% %.2fV", pct, (double)hal_->batteryVolts());
            else snprintf(value, n, "-");
            break;
        }
        case M_ABOUT: {
            float cpu = hal_->cpuLoad();
            snprintf(label, n, "FW %s", FW_VERSION);
            if (cpu >= 0) snprintf(tmp, sizeof tmp, "CPU %d%%", (int)cpu); else snprintf(tmp, sizeof tmp, "-");
            snprintf(value, n, "%s", tmp);
            break;
        }
        default: label[0] = 0;
    }
}

void Ui::faderCalPress() {
    if (calStep_ == 0) {
        for (int c = 0; c < NCH; c++) calLo_[c] = lastRaw_[c];
        calStep_ = 1;
        return;
    }
    for (int c = 0; c < NCH; c++)
        if (lastRaw_[c] < 0 || fabsf(lastRaw_[c] - calLo_[c]) < 0.5f) {   // less than half the scale: not moved
            char v[16];
            snprintf(v, sizeof v, "FADER %d FAIL", c + 1);
            toast("CAL", v);
            page_ = MENU;
            return;
        }
    for (int c = 0; c < NCH; c++) {
        settings_->fadLo[c] = (uint16_t)lroundf(calLo_[c] * 65535.f);
        settings_->fadHi[c] = (uint16_t)lroundf(lastRaw_[c] * 65535.f);
    }
    settingsDirty_ = true;
    toast("FADER CAL", "SAVED");
    page_ = MENU;
    for (int c = 0; c < NCH; c++) fader(c, lastRaw_[c]);           // apply at once
}

void Ui::menuTurn(int d) {
    if (!menuEdit_) {
        menuSel_ = (int)clampf((float)(menuSel_ + d), 0, M_COUNT - 1);
        if (menuSel_ < menuTop_) menuTop_ = menuSel_;
        if (menuSel_ >= menuTop_ + MENU_ROWS) menuTop_ = menuSel_ - MENU_ROWS + 1;
        return;
    }
    int i = menuSel_;
    if (i == M_LOAD || i == M_SAVE) menuSlot_ = (menuSlot_ - 1 + d % NSCENES + NSCENES) % NSCENES + 1;
    else if (i >= M_WIDTH1 && i <= M_WIDTH4) stepParam(i - M_WIDTH1, P_WIDTH, d);
    else if (i == M_TEMPO) stepParam(-1, P_BPM, d);
    else if (i == M_USBVOL) stepParam(-1, P_USB, d);
    else if (i == M_USBSEND) { settings_->usbSend = (uint8_t)((settings_->usbSend + d % 5 + 5) % 5); settingsDirty_ = true; }
    else if (i == M_MIDICH) { settings_->midiCh = (uint8_t)((settings_->midiCh + d % 16 + 16) % 16); settingsDirty_ = true; }
    else if (i == M_BRIGHT) {
        settings_->brightness = (uint8_t)clampf((float)(settings_->brightness + 5 * d), 5, 100);
        settingsDirty_ = true;
    }
}

void Ui::menuPress() {
    int i = menuSel_;
    if (i >= M_MODE1 && i <= M_MODE4) {
        scene_->ch[i - M_MODE1].stereo ^= 1;
        changed();
        return;
    }
    if ((i >= M_WIDTH1 && i <= M_WIDTH4) || i == M_TEMPO || i == M_USBVOL || i == M_USBSEND || i == M_MIDICH ||
        i == M_BRIGHT) {
        menuEdit_ = !menuEdit_;
        return;
    }
    switch (i) {
        case M_EXIT: page_ = HOME; break;
        case M_LOAD:
        case M_SAVE:
            if (!menuEdit_) { menuEdit_ = true; break; }
            menuEdit_ = false;
            if (i == M_LOAD) loadScene(menuSlot_); else saveScene(menuSlot_);
            break;
        case M_PHONES: scene_->phonesSrc = (uint8_t)((scene_->phonesSrc + 1) % 3); changed(); break;
        case M_TAP: tap(); break;
        case M_CLOCK: settings_->clockOut ^= 1; settingsDirty_ = true; clockNextUs_ = hal_->micros(); break;
        case M_LIMITER: scene_->limiter ^= 1; changed(); break;
        case M_TUNER: page_ = TUNER; tuner_ = TunerResult(); break;
        case M_REC: toggleRecord(); break;
        case M_CTRL:
            settings_->ctrlMode ^= 1;
            settingsDirty_ = true;
            shadow_ = *scene_;
            memset(lastCC_, 0, sizeof lastCC_);
            break;
        case M_ENCDIR: settings_->encInvert ^= 1; settingsDirty_ = true; break;
        case M_SHIFTMODE: settings_->shiftToggle ^= 1; shiftLatched_ = false; settingsDirty_ = true; break;
        case M_FADERCAL: page_ = FADER_CAL; calStep_ = 0; break;
        default: break;
    }
}

// ------------------------------------------------------------------ drawing
void Ui::drawBar(Canvas& c, int x, int y, int w, int h, float norm, bool bipolar, uint16_t colr) {
    c.fill(x, y, w, h, col::DARK);
    norm = clampf(norm, 0, 1);
    if (bipolar) {
        int mid = x + w / 2, px = x + (int)lroundf(norm * (w - 1));
        if (px >= mid) c.fill(mid, y, px - mid + 1, h, colr);
        else c.fill(px, y, mid - px, h, colr);
        c.vline(mid, y - 1, h + 2, col::DIM);
    } else c.fill(x, y, (int)lroundf(norm * w), h, colr);
}

void Ui::drawMeter(Canvas& c, int x, int y, int w, int h, float peak, float clip) {
    c.fill(x, y, w, h, col::DARK);
    float db = dsp::linToDb(peak);
    float norm = clampf((db + 60.f) / 60.f, 0, 1);
    int top = y + h - (int)lroundf(norm * h);
    int y12 = y + h - (int)lroundf(48.f / 60.f * h), y3 = y + h - (int)lroundf(57.f / 60.f * h);
    for (int yy = top; yy < y + h; yy++)
        c.hline(x, yy, w, yy < y3 ? col::RED : yy < y12 ? col::YELLOW : col::GREEN);
    if (clip > 0) c.fill(x, y, w, 3, col::RED);
}

void Ui::drawTop(Canvas& c, const char* title, uint16_t colr) {
    c.fill(0, 0, DISPLAY_W, 14, col::DARK);
    uint32_t now = hal_->millis();
    char buf[48];
    int rx = DISPLAY_W - 3;
    auto right = [&](const char* s, uint16_t k) {      // right-aligned status items, right to left
        int x = rx - Canvas::textWidth(s);
        c.text(x, 3, s, k);
        rx = x - 8;
    };
    int pct = batteryPercent();
    if (pct >= 0) {                                    // battery icon: body 16 x 8, tip 2 x 4
        int x = rx - 18, y = 3;
        uint16_t k = pct < 15 ? col::RED : pct < 35 ? col::YELLOW : col::DIM;
        c.rect(x, y, 16, 8, k);
        c.fill(x + 16, y + 2, 2, 4, k);
        c.fill(x + 2, y + 2, (12 * pct + 50) / 100, 4, k);
        rx = x - 8;
    }
    snprintf(buf, sizeof buf, "%s%d", extClockAt_ ? "EXT " : "", (int)lroundf(scene_->bpm));
    right(buf, col::DIM);
    if (settings_->ctrlMode) right("CTRL", col::CYAN);
    if (rec_ && rec_->active()) {
        uint32_t s = rec_->seconds();
        snprintf(buf, sizeof buf, "REC %02u:%02u", (unsigned)(s / 60), (unsigned)(s % 60));
        right(buf, (now / 500) & 1 ? col::RED : col::WHITE);
    }
    if (now < toastUntil_) {
        snprintf(buf, sizeof buf, "%s %s", toastL_, toastV_);
        c.fill(0, 0, rx + 4, 14, col::BLUE);
        c.text(3, 3, buf, col::WHITE);
    } else c.text(3, 3, title, colr);
}

void Ui::drawStrip(Canvas& c, int ch, int x) {
    const Scene& s = settings_->ctrlMode ? shadow_ : *scene_;
    const ChannelParams& p = s.ch[ch];
    char buf[24];
    c.fill(x, 16, 62, 12, p.mute ? col::RED : col::GREY);
    snprintf(buf, sizeof buf, "IN%d %s", ch + 1, p.stereo ? "ST" : "MO");
    c.text(x + 3, 18, buf, col::WHITE);
    if (p.cue) { c.fill(x + 44, 16, 18, 12, col::YELLOW); c.text(x + 45, 18, "CU", col::BLACK); }
    for (int r = 0; r < 3; r++) {
        int id = rowParam(ch, r), y0 = 32 + r * 26;
        float v = paramGet(s, *live_, ch, id);
        uint16_t colr = paramColor(id);
        c.text(x + 3, y0, rowLabel(id), colr);
        paramFormat(id, v, buf, sizeof buf);
        c.textRight(x + 60, y0, buf, col::WHITE);
        int k = paramDesc(id).kind;
        drawBar(c, x + 3, y0 + 11, 57, 5, paramNorm(id, v), k == K_DB || k == K_BIPOLAR, colr);
    }
    // meters, fader, gain reduction
    int y = 112, h = 56;
    drawMeter(c, x + 4, y, 5, h, mix_->chMeter[ch][0].peak, mix_->chMeter[ch][0].clip);
    drawMeter(c, x + 11, y, 5, h, mix_->chMeter[ch][1].peak, mix_->chMeter[ch][1].clip);
    float pos = live_->fader[ch];
    c.vline(x + 25, y, h, col::GREY);
    int yk = y + (int)lroundf((1.f - pos) * (h - 4));
    c.fill(x + 20, yk, 11, 4, col::WHITE);
    float db = faderDb(pos);
    if (db <= -89.f) snprintf(buf, sizeof buf, "-INF"); else snprintf(buf, sizeof buf, "%+.1f", (double)db);
    c.textRight(x + 61, y + 2, buf, col::WHITE);
    float gr = mix_->chGr[ch];
    if (gr > 0.3f) {
        snprintf(buf, sizeof buf, "-%.0f", (double)gr);
        c.textRight(x + 61, y + 14, "GR", col::RED);
        c.textRight(x + 61, y + 24, buf, col::RED);
    }
    c.vline(x + 63, 16, DISPLAY_H - 16, col::DARK);
}

void Ui::drawMaster(Canvas& c, int x) {
    char buf[16];
    c.fill(x, 16, 64, 12, col::GREY);
    c.text(x + 3, 18, "MASTER", col::WHITE);
    const int ids[3] = {P_MAIN, P_AUX, P_PHONES};
    const char* names[3] = {"MAIN", "AUX", "PHON"};
    const uint16_t cols[3] = {col::WHITE, col::CYAN, col::YELLOW};
    for (int r = 0; r < 3; r++) {
        int y0 = 32 + r * 26;
        float v = paramGet(*scene_, *live_, 0, ids[r]);
        c.text(x + 3, y0, names[r], cols[r]);
        paramFormat(ids[r], v, buf, sizeof buf);
        c.textRight(x + 61, y0, buf, col::WHITE);
        drawBar(c, x + 3, y0 + 11, 58, 5, paramNorm(ids[r], v), false, cols[r]);
    }
    int y = 112, h = 56;
    drawMeter(c, x + 4, y, 5, h, mix_->mainMeter[0].peak, mix_->mainMeter[0].clip);
    drawMeter(c, x + 11, y, 5, h, mix_->mainMeter[1].peak, mix_->mainMeter[1].clip);
    drawMeter(c, x + 21, y, 4, h, mix_->auxMeter[0].peak, mix_->auxMeter[0].clip);
    drawMeter(c, x + 27, y, 4, h, mix_->auxMeter[1].peak, mix_->auxMeter[1].clip);
    bool cue = scene_->phonesSrc == (uint8_t)PhonesSrc::Cue || (scene_->phonesSrc == 0 && mix_->anyCue());
    c.text(x + 35, y + 2, cue ? "CUE" : "", col::YELLOW);
    if (mix_->limGr > 0.3f) {
        snprintf(buf, sizeof buf, "-%.0f", (double)mix_->limGr);
        c.text(x + 35, y + 14, "LIM", col::RED);
        c.text(x + 35, y + 24, buf, col::RED);
    }
}

void Ui::drawHome(Canvas& c) {
    char title[48];
    if (shiftOn()) snprintf(title, sizeof title, shiftLatched_ ? "SHIFT ON: GAIN PAN FILT/COMP" : "SHIFT: GAIN PAN FILT/COMP");
    else snprintf(title, sizeof title, "%s %s %s", auxLayer_ ? "AUX" : "HI", fxLayer_[0] ? rowLabel(P_SEND_FX1) : "MID",
                  fxLayer_[1] ? rowLabel(P_SEND_FX2) : "LO");
    c.clear(col::BLACK);
    drawTop(c, title, shiftOn() ? col::YELLOW : col::WHITE);
    for (int ch = 0; ch < NCH; ch++) drawStrip(c, ch, ch * 64);
    drawMaster(c, 256);
}

void Ui::drawFx(Canvas& c, int k) {
    const FxParams& f = scene_->fx[k];
    FxType t = (FxType)f.type;
    char title[32], buf[16];
    snprintf(title, sizeof title, "FX %s: %s", k ? "II" : "I", fxName(t));
    c.clear(col::BLACK);
    drawTop(c, title, k ? col::ORANGE : col::MAGENTA);
    for (int i = 0; i < 4; i++) {
        int x = i * 80;
        float v = i < 3 ? f.p[i] : f.ret;
        const char* name = i < 3 ? fxParamName(t, i) : "RETURN";
        const char* div = nullptr;
        if (i == 0 && t == FxType::Delay) FxEngine::delayBeats(v, &div);
        if (i == 0 && t == FxType::Freeze) FxEngine::freezeBeats(v, &div);
        if (div) snprintf(buf, sizeof buf, "%s", div);
        else if (i == 1 && t == FxType::Freeze) snprintf(buf, sizeof buf, "%s", v > 0.5f ? "ON" : "OFF");
        else snprintf(buf, sizeof buf, "%d", (int)lroundf(v * 100));
        c.textCentered(x + 40, 24, name, col::DIM);
        c.textCentered(x + 40, 40, buf, col::WHITE, 2);
        c.fill(x + 30, 64, 20, 80, col::DARK);
        int hh = (int)lroundf(v * 80);
        c.fill(x + 30, 144 - hh, 20, hh, i < 3 ? (k ? col::ORANGE : col::MAGENTA) : col::WHITE);
        snprintf(buf, sizeof buf, "IN%d", i + 1);
        c.textCentered(x + 40, 150, buf, col::GREY);
        if (i) c.vline(x, 20, 140, col::DARK);
    }
    c.textCentered(DISPLAY_W / 2, 162, "MASTER = ENGINE", col::GREY);
}

void Ui::drawMenu(Canvas& c) {
    c.clear(col::BLACK);
    drawTop(c, "MENU  (SHIFT+PUSH = EXIT)", col::WHITE);
    char label[24], value[24];
    for (int r = 0; r < MENU_ROWS; r++) {
        int i = menuTop_ + r;
        if (i >= M_COUNT) break;
        int y = 17 + r * 19;
        menuItem(i, label, value, sizeof label);
        bool sel = i == menuSel_;
        if (sel) c.fill(0, y - 1, DISPLAY_W, 18, col::BLUE);
        c.text(6, y + 1, label, col::WHITE, 2);
        int w = Canvas::textWidth(value, 2);
        if (sel && menuEdit_) c.fill(DISPLAY_W - 8 - w, y - 1, w + 6, 18, col::ORANGE);
        c.textRight(DISPLAY_W - 5, y + 1, value, sel && menuEdit_ ? col::BLACK : col::YELLOW, 2);
    }
    // scroll bar
    int h = DISPLAY_H - 16, bh = h * MENU_ROWS / M_COUNT;
    c.fill(DISPLAY_W - 2, 16 + h * menuTop_ / M_COUNT, 2, bh, col::GREY);
}

void Ui::drawTuner(Canvas& c) {
    char buf[48];
    snprintf(buf, sizeof buf, "TUNER IN%d  (MASTER = CHANNEL)", tunerCh_ + 1);
    c.clear(col::BLACK);
    drawTop(c, buf, col::GREEN);
    bool ok = tuner_.valid;
    uint16_t colr = ok && fabsf(tuner_.cents) < 5 ? col::GREEN : col::WHITE;
    c.textCentered(DISPLAY_W / 2, 34, ok ? tuner_.note : "--", colr, 6);
    if (ok) {
        snprintf(buf, sizeof buf, "%.1f HZ  %+.0f CT", (double)tuner_.hz, (double)tuner_.cents);
        c.textCentered(DISPLAY_W / 2, 90, buf, col::DIM, 2);
    }
    int x0 = 20, w = DISPLAY_W - 40, y = 125;
    c.fill(x0, y, w, 24, col::DARK);
    c.vline(x0 + w / 2, y - 4, 32, col::WHITE);
    if (ok) {
        int px = x0 + w / 2 + (int)lroundf(clampf(tuner_.cents, -50, 50) / 50.f * (w / 2 - 4));
        c.fill(px - 3, y + 2, 7, 20, colr);
    }
}

void Ui::drawFaderCal(Canvas& c) {
    char buf[32];
    c.clear(col::BLACK);
    drawTop(c, calStep_ ? "FADER CAL 2/2  (SHIFT+PUSH = CANCEL)" : "FADER CAL 1/2  (SHIFT+PUSH = CANCEL)", col::CYAN);
    c.textCentered(DISPLAY_W / 2, 22, calStep_ ? "ALL FADERS UP" : "ALL FADERS DOWN", col::WHITE, 2);
    c.textCentered(DISPLAY_W / 2, 42, "THEN PUSH MASTER", col::DIM);
    for (int ch = 0; ch < NCH; ch++) {
        int x = 30 + ch * 72, y = 58, h = 92;
        float v = lastRaw_[ch] < 0 ? 0.f : lastRaw_[ch];
        c.fill(x + 16, y, 20, h, col::DARK);
        int hh = (int)lroundf(v * h);
        c.fill(x + 16, y + h - hh, 20, hh, col::CYAN);
        if (calStep_) {                                // the bottom point already taken
            int yl = y + h - (int)lroundf(calLo_[ch] * h);
            c.hline(x + 10, yl, 32, col::YELLOW);
        }
        snprintf(buf, sizeof buf, "%d", (int)lroundf(v * 4095));
        c.textCentered(x + 26, y + h + 4, lastRaw_[ch] < 0 ? "-" : buf, col::WHITE);
        snprintf(buf, sizeof buf, "F%d", ch + 1);
        c.textCentered(x + 26, y + h + 13, buf, col::GREY);
    }
}

void Ui::render(Canvas& c) {
    if (page_ == FADER_CAL) drawFaderCal(c);
    else if (page_ == MENU) drawMenu(c);
    else if (page_ == TUNER) drawTuner(c);
    else {
        int k = fxHeld();
        if (k >= 0) drawFx(c, k); else drawHome(c);
    }
}
