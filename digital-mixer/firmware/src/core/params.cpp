// SPDX-License-Identifier: GPL-3.0-or-later
#include "params.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "dsp.h"

static const char* const FX_NAMES[] = {"REVERB", "DELAY", "CHORUS", "FILTER", "DIST", "TAPE", "FREEZE"};
static const char* const FX_PARAMS[][3] = {
    {"SIZE", "DAMP", "PRE"},      // reverb
    {"TIME", "FDBK", "TONE"},     // delay (time in beat divisions)
    {"RATE", "DEPTH", "FDBK"},    // chorus
    {"FREQ", "RESO", "LFO"},      // filter
    {"DRIVE", "TONE", "CRUSH"},   // distortion
    {"TIME", "FDBK", "WOW"},      // tape echo
    {"LEN", "HOLD", "SPEED"},     // freeze
};

const char* fxName(FxType t) { return FX_NAMES[(int)t % (int)FxType::Count]; }
const char* fxParamName(FxType t, int i) { return FX_PARAMS[(int)t % (int)FxType::Count][i % 3]; }

// MIDI CC: channel params on MIDI channel (base + ch), TX-6 numbers where 00-research p. 9 lists
// them (7-9 level/pan/gain, 74 filter, 85-87 EQ, 93 compressor); the rest are ours.
static const ParamDesc TABLE[P_COUNT] = {
    {"GAIN", -12, 32, 0, 0.5f, 9, K_GAIN},
    {"PAN", -1, 1, 0, 0.05f, 8, K_BIPOLAR},
    {"WIDTH", 0, 1, 1, 0.05f, 10, K_UNIT},
    {"FILT", -1, 1, 0, 0.025f, 74, K_BIPOLAR},
    {"HI", -15, 15, 0, 0.5f, 85, K_DB},
    {"MID", -15, 15, 0, 0.5f, 86, K_DB},
    {"LO", -15, 15, 0, 0.5f, 87, K_DB},
    {"COMP", 0, 1, 0, 0.025f, 93, K_UNIT},
    {"AUX", 0, 1, 0, 0.025f, 102, K_UNIT},
    {"FX1", 0, 1, 0, 0.025f, 103, K_UNIT},
    {"FX2", 0, 1, 0, 0.025f, 104, K_UNIT},
    {"LEVEL", 0, 1, 0.75f, 0.01f, 7, K_UNIT},
    {"MUTE", 0, 1, 0, 1, 110, K_BOOL},
    {"CUE", 0, 1, 0, 1, 111, K_BOOL},
    // global, MIDI channel base + 4
    {"MAIN", -60, 6, -6, 0.5f, 7, K_DB},
    {"AUX", -60, 6, 0, 0.5f, 8, K_DB},
    {"PHONES", -60, 6, -12, 0.5f, 9, K_DB},
    {"USB", -60, 6, -6, 0.5f, 10, K_DB},
    {"BPM", 40, 240, 120, 1, 11, K_BPM},
    {"FX1", 0, (float)FxType::Count - 1, 0, 1, 20, K_ENUM},
    {"P1", 0, 1, 0.5f, 0.02f, 21, K_UNIT},
    {"P2", 0, 1, 0.5f, 0.02f, 22, K_UNIT},
    {"P3", 0, 1, 0.5f, 0.02f, 23, K_UNIT},
    {"RET", 0, 1, 0.5f, 0.02f, 24, K_UNIT},
    {"FX2", 0, (float)FxType::Count - 1, 1, 1, 25, K_ENUM},
    {"P1", 0, 1, 0.5f, 0.02f, 26, K_UNIT},
    {"P2", 0, 1, 0.5f, 0.02f, 27, K_UNIT},
    {"P3", 0, 1, 0.5f, 0.02f, 28, K_UNIT},
    {"RET", 0, 1, 0.5f, 0.02f, 29, K_UNIT},
};

const ParamDesc& paramDesc(int id) { return TABLE[id < 0 || id >= P_COUNT ? 0 : id]; }

static float* fxSlot(Scene& s, int id, int& fx) {
    fx = id >= P_FX2_TYPE ? 1 : 0;
    int k = id - (fx ? P_FX2_TYPE : P_FX1_TYPE);
    if (k >= 1 && k <= 3) return &s.fx[fx].p[k - 1];
    if (k == 4) return &s.fx[fx].ret;
    return nullptr;                 // type
}

float paramGet(const Scene& cs, const Live& l, int ch, int id) {
    Scene& s = const_cast<Scene&>(cs);
    const ChannelParams& c = s.ch[ch < 0 ? 0 : ch % NCH];
    switch (id) {
        case P_GAIN: return c.gainDb;
        case P_PAN: return c.pan;
        case P_WIDTH: return c.width;
        case P_FILTER: return c.filter;
        case P_EQ_HI: return c.eq[0];
        case P_EQ_MID: return c.eq[1];
        case P_EQ_LO: return c.eq[2];
        case P_COMP: return c.comp;
        case P_SEND_AUX: return c.sendAux;
        case P_SEND_FX1: return c.sendFx[0];
        case P_SEND_FX2: return c.sendFx[1];
        case P_LEVEL: return l.fader[ch % NCH];
        case P_MUTE: return c.mute;
        case P_CUE: return c.cue;
        case P_MAIN: return s.mainDb;
        case P_AUX: return s.auxDb;
        case P_PHONES: return s.phonesDb;
        case P_USB: return s.usbDb;
        case P_BPM: return s.bpm;
        default: break;
    }
    if (id >= P_FX1_TYPE && id < P_COUNT) {
        int fx;
        float* p = fxSlot(s, id, fx);
        return p ? *p : (float)s.fx[fx].type;
    }
    return 0;
}

void paramSet(Scene& s, Live& l, int ch, int id, float v) {
    const ParamDesc& d = paramDesc(id);
    v = dsp::clampf(v, d.min, d.max);
    if (d.kind == K_BOOL || d.kind == K_ENUM) v = roundf(v);
    ChannelParams& c = s.ch[ch < 0 ? 0 : ch % NCH];
    switch (id) {
        case P_GAIN: c.gainDb = roundf(v * 2) / 2; return;         // PGA has 0.5 dB steps
        case P_PAN: c.pan = v; return;
        case P_WIDTH: c.width = v; return;
        case P_FILTER: c.filter = v; return;
        case P_EQ_HI: c.eq[0] = v; return;
        case P_EQ_MID: c.eq[1] = v; return;
        case P_EQ_LO: c.eq[2] = v; return;
        case P_COMP: c.comp = v; return;
        case P_SEND_AUX: c.sendAux = v; return;
        case P_SEND_FX1: c.sendFx[0] = v; return;
        case P_SEND_FX2: c.sendFx[1] = v; return;
        case P_LEVEL: l.fader[ch % NCH] = v; return;
        case P_MUTE: c.mute = (uint8_t)v; return;
        case P_CUE: c.cue = (uint8_t)v; return;
        case P_MAIN: s.mainDb = v; return;
        case P_AUX: s.auxDb = v; return;
        case P_PHONES: s.phonesDb = v; return;
        case P_USB: s.usbDb = v; return;
        case P_BPM: s.bpm = v; return;
        default: break;
    }
    if (id >= P_FX1_TYPE && id < P_COUNT) {
        int fx;
        float* p = fxSlot(s, id, fx);
        if (p) *p = v; else s.fx[fx].type = (uint8_t)v;
    }
}

float paramNorm(int id, float v) {
    const ParamDesc& d = paramDesc(id);
    return dsp::clampf((v - d.min) / (d.max - d.min), 0, 1);
}

float paramFromNorm(int id, float n) {
    const ParamDesc& d = paramDesc(id);
    return d.min + dsp::clampf(n, 0, 1) * (d.max - d.min);
}

int paramFromCC(uint8_t cc, bool global) {
    int lo = global ? P_CH_COUNT : 0, hi = global ? P_COUNT : P_CH_COUNT;
    for (int i = lo; i < hi; i++)
        if (TABLE[i].cc == cc) return i;
    return -1;
}

void paramFormat(int id, float v, char* out, size_t n) {
    const ParamDesc& d = paramDesc(id);
    switch (d.kind) {
        case K_DB:
        case K_GAIN:
            if (v <= -59.9f) snprintf(out, n, "OFF");
            else snprintf(out, n, "%+.1f", (double)v);
            break;
        case K_BIPOLAR: {
            int p = (int)lroundf(v * 100);
            if (id == P_FILTER) {
                if (p == 0) snprintf(out, n, "OFF");
                else snprintf(out, n, "%s%d", p < 0 ? "LP" : "HP", p < 0 ? -p : p);
            } else {
                if (p == 0) snprintf(out, n, "C");
                else snprintf(out, n, "%c%d", p < 0 ? 'L' : 'R', p < 0 ? -p : p);
            }
            break;
        }
        case K_UNIT: snprintf(out, n, "%d", (int)lroundf(v * 100)); break;
        case K_BOOL: snprintf(out, n, "%s", v > 0.5f ? "ON" : "OFF"); break;
        case K_ENUM: snprintf(out, n, "%s", fxName((FxType)(int)v)); break;
        case K_BPM: snprintf(out, n, "%d", (int)lroundf(v)); break;
    }
}

float faderDb(float pos) {
    // knots: position -> dB (0.75 = unity, like a console fader)
    static const float P[] = {0.0f, 0.05f, 0.25f, 0.5f, 0.75f, 1.0f};
    static const float D[] = {-90.f, -60.f, -30.f, -12.f, 0.f, 6.f};
    if (pos <= 0.01f) return -90.f;
    for (int i = 1; i < 6; i++)
        if (pos <= P[i]) return D[i - 1] + (D[i] - D[i - 1]) * (pos - P[i - 1]) / (P[i] - P[i - 1]);
    return 6.f;
}

uint32_t crc32(const void* data, size_t n) {
    const uint8_t* p = (const uint8_t*)data;
    uint32_t c = 0xFFFFFFFFu;
    while (n--) {
        c ^= *p++;
        for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1)));
    }
    return ~c;
}

void Scene::defaults() {
    *this = Scene();
    fx[0].type = (uint8_t)FxType::Reverb;
    fx[1].type = (uint8_t)FxType::Delay;
    fx[1].p[0] = 0.55f;             // 1/8 dotted
}
void Scene::seal() { crc = crc32(this, offsetof(Scene, crc)); }
bool Scene::valid() const { return magic == MAGIC && crc == crc32(this, offsetof(Scene, crc)); }
void Settings::seal() { crc = crc32(this, offsetof(Settings, crc)); }
bool Settings::valid() const { return magic == MAGIC && crc == crc32(this, offsetof(Settings, crc)); }

static_assert(sizeof(Scene) <= 400, "scene must fit 10 EEPROM slots on Teensy 4.1");
