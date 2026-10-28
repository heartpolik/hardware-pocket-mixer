// SPDX-License-Identifier: GPL-3.0-or-later
// FX bus engines (01-spec 3.2): reverb, delay, chorus, filter, distortion, tape, freeze.
// Each bus owns a memory pool of int16 samples (PSRAM on Teensy if fitted, else RAM2) that the
// current engine carves into delay lines when the engine is selected.
#pragma once
#include <stddef.h>
#include <stdint.h>

#include "dsp.h"
#include "params.h"

// Fixed-point delay line in the pool (int16, +12 dB headroom).
struct DelayLine {
    int16_t* buf = nullptr;
    uint32_t size = 0, w = 0;
    static constexpr float SCALE = 8192.f, INV = 1.f / 8192.f;

    inline void write(float x) {
        float s = dsp::clampf(x * SCALE, -32767.f, 32767.f);
        buf[w] = (int16_t)s;
        if (++w >= size) w = 0;
    }
    // d samples behind the last written sample (d >= 1)
    inline float read(uint32_t d) const {
        uint32_t i = w + size - (d > size ? size : d);
        if (i >= size) i -= size;
        return buf[i] * INV;
    }
    inline float readFrac(float d) const {
        if (d < 1.f) d = 1.f;
        if (d > size - 2) d = (float)(size - 2);
        uint32_t di = (uint32_t)d;
        float f = d - di;
        return read(di) * (1.f - f) + read(di + 1) * f;
    }
    void clear() { for (uint32_t i = 0; i < size; i++) buf[i] = 0; }
};

class FxEngine {
public:
    void init(float fs, int16_t* pool, uint32_t poolSize);
    // in/out: stereo bus, n samples; out = wet signal (return level applied by the mixer)
    void process(const float* inL, const float* inR, float* outL, float* outR, int n, const FxParams& p, float bpm);
    FxType type() const { return type_; }
    float maxDelaySeconds() const { return (float)poolSize_ / 2 / fs_; }

    // Delay division names for the display (delay TIME and freeze LEN)
    static float delayBeats(float p, const char** name = nullptr);
    static float freezeBeats(float p, const char** name = nullptr);

private:
    void select(FxType t);
    DelayLine alloc(uint32_t n);

    void reverb(const float*, const float*, float*, float*, int, const float*);
    void delay(const float*, const float*, float*, float*, int, const float*, float bpm);
    void chorus(const float*, const float*, float*, float*, int, const float*);
    void filter(const float*, const float*, float*, float*, int, const float*, float bpm);
    void dist(const float*, const float*, float*, float*, int, const float*);
    void tape(const float*, const float*, float*, float*, int, const float*);
    void freeze(const float*, const float*, float*, float*, int, const float*, float bpm);

    float fs_ = 48000;
    int16_t* pool_ = nullptr;
    uint32_t poolSize_ = 0, used_ = 0;
    FxType type_ = FxType::Count;

    // engine state (union-like: only the selected engine's members are meaningful)
    DelayLine comb_[16], ap_[8], line_[2];
    float combStore_[16] = {};
    float lfo_ = 0, lfo2_ = 0, delaySm_[2] = {0, 0};
    dsp::OnePole tone_[2];
    dsp::BiquadCoefs bq_;
    dsp::BiquadState bqs_[2];
    float svf_[2][2] = {};
    float hold_[2] = {0, 0};
    float holdCount_ = 0;
    // freeze
    bool frozen_ = false;
    float playPos_ = 0;
    uint32_t loopStart_ = 0, loopLen_ = 0;
};
