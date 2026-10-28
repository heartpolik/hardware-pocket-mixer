// SPDX-License-Identifier: GPL-3.0-or-later
// DSP building blocks shared by the mixer and the FX engines. Portable C++17, no allocation.
#pragma once
#include <math.h>
#include <stdint.h>

namespace dsp {

constexpr float kPi = 3.14159265358979f;

inline float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }
inline float dbToLin(float db) { return db <= -90.f ? 0.f : powf(10.f, db * 0.05f); }
inline float linToDb(float x) { return x > 1e-9f ? 20.f * log10f(x) : -180.f; }

// Fast log2 / exp2 for per-sample gain computers (error < 0.01 dB in the used range).
inline float fastLog2(float x) {
    union { float f; uint32_t i; } v{x};
    float e = (float)(int32_t)((v.i >> 23) & 255) - 128.f;
    v.i = (v.i & 0x007FFFFF) | 0x3F800000;
    return e + (-0.34484843f * v.f + 2.02466578f) * v.f - 0.67487759f;
}
inline float fastExp2(float p) {
    if (p < -126.f) return 0.f;
    float w = floorf(p), z = p - w;
    union { uint32_t i; float f; } v{(uint32_t)((1 << 23) * (p + 121.2740575f + 27.7280233f / (4.84252568f - z) - 1.49012907f * z))};
    return v.f;
}
inline float fastDb(float x) { return 6.0205999f * fastLog2(x + 1e-12f); }
inline float fastDbToLin(float db) { return fastExp2(db * 0.16609640f); }

// Soft clipper: tanh-like, |y| < 1.
inline float softClip(float x) {
    x = clampf(x, -3.f, 3.f);
    return x * (27.f + x * x) / (27.f + 9.f * x * x);
}

// Output safety clipper: transparent below 0.9 (-0.9 dBFS), soft knee above, |y| < 1.
inline float safeClip(float x) {
    float a = fabsf(x);
    if (a <= 0.9f) return x;
    float y = 0.9f + 0.1f * softClip((a - 0.9f) * 10.f);
    return x < 0 ? -y : y;
}

// --------------------------------------------------------------------------------- biquad
// RBJ Audio EQ Cookbook (Robert Bristow-Johnson), transposed direct form II.
struct BiquadCoefs {
    float b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
    bool identity() const { return b0 == 1.f && b1 == 0.f && b2 == 0.f && a1 == 0.f && a2 == 0.f; }

    void set(float nb0, float nb1, float nb2, float na0, float na1, float na2) {
        b0 = nb0 / na0; b1 = nb1 / na0; b2 = nb2 / na0; a1 = na1 / na0; a2 = na2 / na0;
    }
    void lowpass(float fs, float f, float q) {
        float w = 2 * kPi * f / fs, c = cosf(w), al = sinf(w) / (2 * q);
        set((1 - c) / 2, 1 - c, (1 - c) / 2, 1 + al, -2 * c, 1 - al);
    }
    void highpass(float fs, float f, float q) {
        float w = 2 * kPi * f / fs, c = cosf(w), al = sinf(w) / (2 * q);
        set((1 + c) / 2, -(1 + c), (1 + c) / 2, 1 + al, -2 * c, 1 - al);
    }
    void peak(float fs, float f, float q, float db) {
        if (fabsf(db) < 0.05f) { *this = BiquadCoefs(); return; }
        float A = powf(10.f, db / 40.f), w = 2 * kPi * f / fs, c = cosf(w), al = sinf(w) / (2 * q);
        set(1 + al * A, -2 * c, 1 - al * A, 1 + al / A, -2 * c, 1 - al / A);
    }
    void lowShelf(float fs, float f, float db) {
        if (fabsf(db) < 0.05f) { *this = BiquadCoefs(); return; }
        float A = powf(10.f, db / 40.f), w = 2 * kPi * f / fs, c = cosf(w), s = sinf(w);
        float al = s / 2 * sqrtf(2.f), sa = 2 * sqrtf(A) * al;     // shelf slope S = 1
        set(A * ((A + 1) - (A - 1) * c + sa), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - sa),
            (A + 1) + (A - 1) * c + sa, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - sa);
    }
    void highShelf(float fs, float f, float db) {
        if (fabsf(db) < 0.05f) { *this = BiquadCoefs(); return; }
        float A = powf(10.f, db / 40.f), w = 2 * kPi * f / fs, c = cosf(w), s = sinf(w);
        float al = s / 2 * sqrtf(2.f), sa = 2 * sqrtf(A) * al;
        set(A * ((A + 1) + (A - 1) * c + sa), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - sa),
            (A + 1) - (A - 1) * c + sa, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - sa);
    }
};

struct BiquadState {
    float z1 = 0, z2 = 0;
    inline float run(const BiquadCoefs& k, float x) {
        float y = k.b0 * x + z1;
        z1 = k.b1 * x - k.a1 * y + z2;
        z2 = k.b2 * x - k.a2 * y;
        return y;
    }
    void reset() { z1 = z2 = 0; }
};

// --------------------------------------------------------------------------------- one-pole
struct OnePole {                   // lowpass y += a (x - y)
    float a = 1, y = 0;
    void setCutoff(float fs, float f) { a = 1.f - expf(-2 * kPi * f / fs); }
    inline float run(float x) { return y += a * (x - y); }
};

inline float timeCoef(float fs, float ms) { return ms <= 0 ? 1.f : 1.f - expf(-1000.f / (ms * fs)); }

// --------------------------------------------------------------------------------- dynamics
// One-knob compressor: amount 0..1 sets threshold, ratio and make-up together (01-spec 3.1).
struct Compressor {
    float env = 0, atk = 0, rel = 0, thr = 0, slope = 0, makeup = 1;
    float grDb = 0;                       // last gain reduction, for the display
    void setup(float fs) { atk = timeCoef(fs, 5.f); rel = timeCoef(fs, 120.f); }
    void setAmount(float a) {
        thr = -30.f * a;                                  // dBFS
        float ratio = 1.f + 7.f * a;
        slope = 1.f - 1.f / ratio;
        makeup = dbToLin(-thr * slope * 0.5f);            // half of the static reduction at 0 dBFS
    }
    inline void run(float& l, float& r) {
        if (slope <= 0.f) { grDb = 0; return; }
        float x = fmaxf(fabsf(l), fabsf(r));
        env += (x > env ? atk : rel) * (x - env);
        float over = fastDb(env) - thr;
        float g = makeup;
        if (over > 0) { grDb = over * slope; g *= fastDbToLin(-grDb); } else grDb = 0;
        l *= g; r *= g;
    }
};

// Look-ahead peak limiter for MAIN: never exceeds `ceiling` (final hard clip as a safety net).
struct Limiter {
    static constexpr int LA = 48;          // 1 ms at 48 kHz
    float bufL[LA] = {}, bufR[LA] = {};
    int pos = 0;
    float gain = 1, rel = 0, atk = 0, ceiling = 0.966f, grDb = 0;   // -0.3 dBFS
    void setup(float fs) { rel = timeCoef(fs, 80.f); atk = timeCoef(fs, 0.25f); }
    inline void run(float& l, float& r) {
        float pk = fmaxf(fabsf(l), fabsf(r));
        float need = pk > ceiling ? ceiling / pk : 1.f;
        // track the minimum required gain over the look-ahead window
        if (need < gain) gain += atk * 4.f * (need - gain);
        else gain += rel * (need - gain);
        if (need < gain) gain = gain * 0.5f + need * 0.5f;
        float dl = bufL[pos], dr = bufR[pos];
        bufL[pos] = l; bufR[pos] = r;
        pos = (pos + 1) % LA;
        l = clampf(dl * gain, -ceiling, ceiling);
        r = clampf(dr * gain, -ceiling, ceiling);
        grDb = -linToDbApprox(gain);
    }
    static float linToDbApprox(float g) { return 6.0206f * fastLog2(g + 1e-9f); }
};

// Peak meter with hold and fall (values read by the UI thread; single float writes are atomic).
struct Meter {
    volatile float peak = 0;               // 0..1+, decays
    volatile float clip = 0;               // seconds of clip indicator left
    float fall = 0.f;
    void setup(float fs, int block) { fall = powf(10.f, -20.f / 20.f * block / fs); }   // 20 dB/s
    inline void block(float pk, float dt) { block(pk, dt, pk >= 0.99f); }
    // `clipped`: where the clip mark comes from (the channel meters take it from the ADC input)
    inline void block(float pk, float dt, bool clipped) {
        float p = peak * fall;
        peak = pk > p ? pk : p;
        if (clipped) clip = 1.0f; else if (clip > 0) clip = clip - dt;
    }
};

}  // namespace dsp
