// SPDX-License-Identifier: GPL-3.0-or-later
// Mixer state: a Scene (everything saved in a scene slot), live values that are not saved
// (fader positions), device settings, and the parameter table used by encoders, MIDI and the UI.
#pragma once
#include <stddef.h>
#include <stdint.h>

constexpr int NCH = 4;          // stereo input channels (DM3)
constexpr int NFX = 2;          // FX I, FX II
constexpr int NSCENES = 8;      // 01-spec 3.6

enum class FxType : uint8_t { Reverb, Delay, Chorus, Filter, Dist, Tape, Freeze, Count };
const char* fxName(FxType t);
const char* fxShortName(FxType t);      // 3 letters for the row labels
const char* fxParamName(FxType t, int i);

enum class PhonesSrc : uint8_t { Auto, Main, Cue, Count };

struct ChannelParams {
    float gainDb = 0;           // PCM1865 PGA, -12..+32 dB (hardware)
    float pan = 0;              // -1..1: pan for mono, balance for stereo
    float width = 1;            // 0..1 stereo width (stereo only)
    float filter = 0;           // -1 lowpass .. 0 off .. +1 highpass
    float eq[3] = {0, 0, 0};    // hi, mid, lo, dB
    float comp = 0;             // 0..1
    float sendAux = 0;          // post-fader sends, 0..1
    float sendFx[NFX] = {0, 0};
    uint8_t mute = 0, cue = 0, stereo = 1, pad = 0;
};

struct FxParams {
    uint8_t type = 0;           // FxType
    uint8_t pad[3] = {};
    float p[3] = {0.5f, 0.5f, 0.5f};
    float ret = 0.5f;           // return level into MAIN, 0..1
};

struct Scene {
    uint32_t magic = MAGIC;
    ChannelParams ch[NCH];
    FxParams fx[NFX];
    float mainDb = -6, auxDb = 0, phonesDb = -12, usbDb = -6;  // -60 = off
    float bpm = 120;
    uint8_t phonesSrc = 0;      // PhonesSrc
    uint8_t limiter = 1;
    uint8_t pad[2] = {};
    uint32_t crc = 0;

    static constexpr uint32_t MAGIC = 0x4D584331;   // "MXC1": bump when the layout changes
    void defaults();
    void seal();                 // compute crc
    bool valid() const;
};

struct Settings {
    uint32_t magic = MAGIC;
    uint8_t brightness = 80;    // %
    uint8_t midiCh = 0;         // 0..15: channel of mixer channel 1; channels 2..4 and master follow
    uint8_t ctrlMode = 0;       // 1: controls send CC to the DAW instead of changing the mix
    uint8_t clockOut = 0;       // MIDI clock out on TRS and USB
    uint8_t usbSend = 0;        // stereo USB build: 0 = MAIN, 1..4 = input channel
    uint8_t lastScene = 0;
    uint8_t encInvert = 0;      // encoder direction (EC12SY A/B order - check on the sample)
    uint8_t shiftToggle = 0;    // 0: SHIFT works while held, 1: a press latches it on / off
    // fader calibration (menu FADER CAL): raw ADC position x 65535 at the bottom and at the top;
    // top < bottom = the fader is wired the other way round
    uint16_t fadLo[NCH] = {0, 0, 0, 0};
    uint16_t fadHi[NCH] = {65535, 65535, 65535, 65535};
    uint8_t recSource = 2;      // Recorder::Source: 0 MAIN, 1 inputs, 2 inputs + MAIN
    uint8_t recBits = 24;       // 16 or 24
    uint8_t pad2[2] = {};
    uint32_t crc = 0;
    static constexpr uint32_t MAGIC = 0x4D585333;
    void seal();
    bool valid() const;
};

// Values that change continuously and are not part of a scene.
struct Live {
    volatile float fader[NCH] = {0.75f, 0.75f, 0.75f, 0.75f};   // 0..1 position
};

// ------------------------------------------------------------------ parameter table
enum ParamId : uint8_t {
    // per channel
    P_GAIN, P_PAN, P_WIDTH, P_FILTER, P_EQ_HI, P_EQ_MID, P_EQ_LO, P_COMP, P_SEND_AUX, P_SEND_FX1, P_SEND_FX2,
    P_LEVEL, P_MUTE, P_CUE,
    P_CH_COUNT,
    // global
    P_MAIN = P_CH_COUNT, P_AUX, P_PHONES, P_USB, P_BPM,
    P_FX1_TYPE, P_FX1_P1, P_FX1_P2, P_FX1_P3, P_FX1_RET,
    P_FX2_TYPE, P_FX2_P1, P_FX2_P2, P_FX2_P3, P_FX2_RET,
    P_COUNT
};

struct ParamDesc {
    const char* name;           // short, upper case (display font has no lower case)
    float min, max, def;
    float step;                 // per encoder detent
    uint8_t cc;                 // MIDI CC (0 = none); channel params on channel base+ch, global on base+4
    uint8_t kind;               // K_*
};
enum : uint8_t { K_DB, K_BIPOLAR, K_UNIT, K_BOOL, K_ENUM, K_BPM, K_GAIN };

const ParamDesc& paramDesc(int id);
// Pointer to the value of a parameter (ch ignored for globals). Bool params are stored as uint8_t
// in the scene, so get/set go through these helpers.
float paramGet(const Scene& s, const Live& l, int ch, int id);
void paramSet(Scene& s, Live& l, int ch, int id, float v);   // clamps
float paramNorm(int id, float v);                             // -> 0..1 for MIDI
float paramFromNorm(int id, float n);
int paramFromCC(uint8_t cc, bool global);                     // -> id or -1
void paramFormat(int id, float v, char* out, size_t n);       // "+3.5", "L20", "OFF" ...

// Fader position 0..1 -> gain (dB); 0.75 = 0 dB, top = +6 dB.
float faderDb(float pos);
inline bool isGlobal(int id) { return id >= P_CH_COUNT; }

uint32_t crc32(const void* data, size_t n);
