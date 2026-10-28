// Audio engine (01-spec 2): 4 stereo channels -> filter, 3-band EQ, compressor, mute, fader, pan ->
// MAIN / AUX / FX I / FX II buses; CUE (pre-fader) for the headphones; USB to/from the DAW.
// Runs in the audio interrupt on Teensy and in the audio callback in the simulator.
#pragma once
#include <stdint.h>

#include "dsp.h"
#include "fx.h"
#include "params.h"

class Recorder;

struct AudioIO {
    const float* in[2 * NCH] = {};    // IN1 L, IN1 R, IN2 L ... after the PGA
    const float* usbIn[2] = {};       // stereo from the DAW (nullptr = silence)
    float* out[6] = {};               // MAIN L/R, AUX L/R, PHONES L/R
    float* usbOut[2 * NCH] = {};      // to the DAW; unused entries nullptr
    int usbOutChannels = 8;           // 8 (UAC2 build) or 2 (stock Teensy USB audio)
    int n = 0;                        // samples, <= Mixer::MAX_BLOCK
};

class Mixer {
public:
    static constexpr int MAX_BLOCK = 128;
    static constexpr int TUNER_LEN = 2048;   // ring at fs/2

    void init(float fs, Scene* scene, Live* live, int16_t* fxPool[NFX], uint32_t fxPoolSize);
    void process(AudioIO& io);
    float fs() const { return fs_; }
    const FxEngine& fx(int i) const { return fx_[i]; }

    // set from the UI thread
    volatile int usbSend = 0;                // stereo USB: 0 = MAIN, 1..4 = channel (pre-processing)
    volatile int tunerChannel = -1;          // -1 = tuner off
    Recorder* recorder = nullptr;

    // read by the UI thread
    dsp::Meter chMeter[NCH][2], mainMeter[2], auxMeter[2], phonesMeter[2];
    volatile float chGr[NCH] = {}, limGr = 0;
    float tunerBuf[TUNER_LEN] = {};
    volatile uint32_t tunerWrite = 0;
    bool anyCue() const;

private:
    struct Channel {
        dsp::BiquadCoefs flt, eq[3];
        dsp::BiquadState fltS[2], eqS[3][2];
        dsp::Compressor comp;
        float cFilter = 99, cEq[3] = {99, 99, 99}, cComp = -1;     // cached params
        float gl = 0, gr = 0;                                        // gains at the end of last block
        float sAux = 0, sFx[NFX] = {0, 0};
    };
    void updateChannel(int c);

    float fs_ = 48000;
    Scene* s_ = nullptr;
    Live* l_ = nullptr;
    Channel ch_[NCH];
    FxEngine fx_[NFX];
    dsp::Limiter lim_;
    float gMain_ = 0, gAux_ = 0, gPh_ = 0, gUsb_ = 0, cueMix_ = 0, fxRet_[NFX] = {0, 0};
    uint32_t tunerDecim_ = 0;
};
