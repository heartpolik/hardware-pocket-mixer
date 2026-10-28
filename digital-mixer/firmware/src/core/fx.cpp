// SPDX-License-Identifier: GPL-3.0-or-later
#include "fx.h"

#include <math.h>
#include <string.h>

using namespace dsp;

// Freeverb tunings (Jezar at Dreampoint, public domain), samples at 44.1 kHz
static const int COMB[8] = {1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617};
static const int ALLPASS[4] = {556, 441, 341, 225};
static const int SPREAD = 23;

static const float DELAY_BEATS[] = {0.25f, 1.f / 3, 0.375f, 0.5f, 2.f / 3, 0.75f, 1.f, 1.5f, 2.f, 4.f};
static const char* const DELAY_NAMES[] = {"1/16", "1/8T", "1/16D", "1/8", "1/4T", "1/8D", "1/4", "1/4D", "1/2", "1/1"};
static const float FREEZE_BEATS[] = {0.5f, 1.f, 2.f, 4.f, 8.f};
static const char* const FREEZE_NAMES[] = {"1/8", "1/4", "1/2", "1 BAR", "2 BAR"};

float FxEngine::delayBeats(float p, const char** name) {
    int i = (int)(clampf(p, 0, 1) * 9.999f);
    if (name) *name = DELAY_NAMES[i];
    return DELAY_BEATS[i];
}

float FxEngine::freezeBeats(float p, const char** name) {
    int i = (int)(clampf(p, 0, 1) * 4.999f);
    if (name) *name = FREEZE_NAMES[i];
    return FREEZE_BEATS[i];
}

void FxEngine::init(float fs, int16_t* pool, uint32_t poolSize) {
    fs_ = fs;
    pool_ = pool;
    poolSize_ = poolSize;
    type_ = FxType::Count;
}

DelayLine FxEngine::alloc(uint32_t n) {
    DelayLine d;
    if (used_ + n > poolSize_) n = poolSize_ > used_ ? poolSize_ - used_ : 0;
    d.buf = pool_ + used_;
    d.size = n ? n : 1;
    used_ += n;
    if (!n) d.buf = pool_;            // degenerate, never happens with sane pool sizes
    d.clear();
    return d;
}

void FxEngine::select(FxType t) {
    type_ = t;
    used_ = 0;
    memset(combStore_, 0, sizeof combStore_);
    lfo_ = lfo2_ = 0;
    delaySm_[0] = delaySm_[1] = 0;
    memset(svf_, 0, sizeof svf_);
    bqs_[0].reset(); bqs_[1].reset();
    hold_[0] = hold_[1] = 0;
    holdCount_ = 0;
    frozen_ = false;
    playPos_ = 0;
    tone_[0].y = tone_[1].y = 0;
    float k = fs_ / 44100.f;
    switch (t) {
        case FxType::Reverb:
            for (int i = 0; i < 8; i++) {
                comb_[i] = alloc((uint32_t)(COMB[i] * k));
                comb_[i + 8] = alloc((uint32_t)((COMB[i] + SPREAD) * k));
            }
            for (int i = 0; i < 4; i++) {
                ap_[i] = alloc((uint32_t)(ALLPASS[i] * k));
                ap_[i + 4] = alloc((uint32_t)((ALLPASS[i] + SPREAD) * k));
            }
            line_[0] = alloc((uint32_t)(0.1f * fs_) + 4);      // pre-delay, mono
            break;
        case FxType::Chorus:
            line_[0] = alloc((uint32_t)(0.05f * fs_));
            line_[1] = alloc((uint32_t)(0.05f * fs_));
            break;
        case FxType::Delay:
        case FxType::Tape:
        case FxType::Freeze: {
            uint32_t half = poolSize_ / 2;
            line_[0] = alloc(half);
            line_[1] = alloc(half);
            break;
        }
        default: break;
    }
}

void FxEngine::process(const float* inL, const float* inR, float* outL, float* outR, int n, const FxParams& p,
                       float bpm) {
    FxType t = (FxType)(p.type % (int)FxType::Count);
    if (t != type_) select(t);
    if (bpm < 20) bpm = 20;
    switch (t) {
        case FxType::Reverb: reverb(inL, inR, outL, outR, n, p.p); break;
        case FxType::Delay: delay(inL, inR, outL, outR, n, p.p, bpm); break;
        case FxType::Chorus: chorus(inL, inR, outL, outR, n, p.p); break;
        case FxType::Filter: filter(inL, inR, outL, outR, n, p.p, bpm); break;
        case FxType::Dist: dist(inL, inR, outL, outR, n, p.p); break;
        case FxType::Tape: tape(inL, inR, outL, outR, n, p.p); break;
        case FxType::Freeze: freeze(inL, inR, outL, outR, n, p.p, bpm); break;
        default:
            for (int i = 0; i < n; i++) outL[i] = outR[i] = 0;
    }
}

// ----------------------------------------------------------------------------- reverb
void FxEngine::reverb(const float* inL, const float* inR, float* outL, float* outR, int n, const float* p) {
    const float fb = 0.70f + 0.28f * p[0];          // room size
    const float damp = 0.4f * p[1];
    const float damp1 = 1.f - damp;
    const uint32_t pre = 1 + (uint32_t)(p[2] * 0.1f * fs_);
    for (int i = 0; i < n; i++) {
        line_[0].write((inL[i] + inR[i]) * 0.015f * 2);
        float x = line_[0].read(pre);
        float l = 0, r = 0;
        for (int c = 0; c < 8; c++) {
            DelayLine& a = comb_[c];
            float y = a.read(a.size);
            combStore_[c] = y * damp1 + combStore_[c] * damp;
            a.write(x + combStore_[c] * fb);
            l += y;
            DelayLine& b = comb_[c + 8];
            float z = b.read(b.size);
            combStore_[c + 8] = z * damp1 + combStore_[c + 8] * damp;
            b.write(x + combStore_[c + 8] * fb);
            r += z;
        }
        for (int c = 0; c < 4; c++) {
            DelayLine& a = ap_[c];
            float bl = a.read(a.size);
            a.write(l + bl * 0.5f);
            l = bl - l;
            DelayLine& b = ap_[c + 4];
            float br = b.read(b.size);
            b.write(r + br * 0.5f);
            r = br - r;
        }
        outL[i] = l * 3.f;
        outR[i] = r * 3.f;
    }
}

// ----------------------------------------------------------------------------- ping-pong delay
void FxEngine::delay(const float* inL, const float* inR, float* outL, float* outR, int n, const float* p,
                     float bpm) {
    float target = delayBeats(p[0]) * 60.f / bpm * fs_;
    if (target > line_[0].size - 4) target = (float)(line_[0].size - 4);
    if (delaySm_[0] <= 0) delaySm_[0] = target;
    const float fb = 0.92f * p[1];
    tone_[0].setCutoff(fs_, 600.f * powf(25.f, p[2]));
    tone_[1].a = tone_[0].a;
    for (int i = 0; i < n; i++) {
        delaySm_[0] += 0.0005f * (target - delaySm_[0]);         // slewed time change (tape-like)
        float dl = line_[0].readFrac(delaySm_[0]);
        float dr = line_[1].readFrac(delaySm_[0]);
        line_[0].write((inL[i] + inR[i]) * 0.5f + tone_[1].run(dr) * fb);
        line_[1].write(tone_[0].run(dl) * fb);
        outL[i] = dl;
        outR[i] = dr;
    }
}

// ----------------------------------------------------------------------------- chorus / flanger
void FxEngine::chorus(const float* inL, const float* inR, float* outL, float* outR, int n, const float* p) {
    const float rate = 0.05f * powf(100.f, p[0]);            // 0.05..5 Hz
    const float inc = 2 * kPi * rate / fs_;
    const float base = 0.012f * fs_, depth = 0.006f * fs_ * p[1];
    const float fb = 0.7f * p[2];
    for (int i = 0; i < n; i++) {
        lfo_ += inc;
        if (lfo_ > 2 * kPi) lfo_ -= 2 * kPi;
        float l = line_[0].readFrac(base + depth * sinf(lfo_));
        float r = line_[1].readFrac(base + depth * sinf(lfo_ + kPi / 2));
        line_[0].write(inL[i] + l * fb);
        line_[1].write(inR[i] + r * fb);
        outL[i] = l;
        outR[i] = r;
    }
}

// ----------------------------------------------------------------------------- resonant filter
// TPT state-variable filter (V. Zavalishin, "The Art of VA Filter Design"), lowpass output.
void FxEngine::filter(const float* inL, const float* inR, float* outL, float* outR, int n, const float* p,
                      float bpm) {
    const float rate = bpm / 60.f / 4.f;                     // one LFO cycle per bar
    lfo_ += 2 * kPi * rate * n / fs_;
    if (lfo_ > 2 * kPi) lfo_ -= 2 * kPi;
    float pos = clampf(p[0] + 0.5f * p[2] * sinf(lfo_), 0.f, 1.f);
    float fc = 40.f * powf(400.f, pos);
    if (fc > 0.45f * fs_) fc = 0.45f * fs_;
    const float g = tanf(kPi * fc / fs_), k = 2.f - 1.8f * p[1];       // Q up to 5
    const float a1 = 1.f / (1.f + g * (g + k)), a2 = g * a1, a3 = g * a2;
    const float* in[2] = {inL, inR};
    float* out[2] = {outL, outR};
    for (int c = 0; c < 2; c++) {
        float ic1 = svf_[c][0], ic2 = svf_[c][1];
        for (int i = 0; i < n; i++) {
            float v3 = in[c][i] - ic2;
            float v1 = a1 * ic1 + a2 * v3;
            float v2 = ic2 + a2 * ic1 + a3 * v3;
            ic1 = 2 * v1 - ic1;
            ic2 = 2 * v2 - ic2;
            out[c][i] = v2;
        }
        svf_[c][0] = ic1;
        svf_[c][1] = ic2;
    }
}

// ----------------------------------------------------------------------------- distortion / crusher
void FxEngine::dist(const float* inL, const float* inR, float* outL, float* outR, int n, const float* p) {
    const float drive = 1.f + 60.f * p[0] * p[0];
    const float level = 1.f / (1.f + 0.5f * p[0]);
    tone_[0].setCutoff(fs_, 800.f * powf(20.f, p[1]));
    tone_[1].a = tone_[0].a;
    const float hold = 1.f + floorf(p[2] * p[2] * 31.f);
    const float steps = p[2] > 0.02f ? powf(2.f, 15.f - 11.f * p[2]) : 0.f;
    for (int i = 0; i < n; i++) {
        if (++holdCount_ >= hold) {
            holdCount_ = 0;
            hold_[0] = inL[i];
            hold_[1] = inR[i];
            if (steps > 0) {
                hold_[0] = roundf(hold_[0] * steps) / steps;
                hold_[1] = roundf(hold_[1] * steps) / steps;
            }
        }
        outL[i] = tone_[0].run(softClip(hold_[0] * drive)) * level;
        outR[i] = tone_[1].run(softClip(hold_[1] * drive)) * level;
    }
}

// ----------------------------------------------------------------------------- tape echo
void FxEngine::tape(const float* inL, const float* inR, float* outL, float* outR, int n, const float* p) {
    float target = (0.04f + 0.66f * p[0]) * fs_;
    if (target * 1.03f > line_[0].size - 4 - 0.004f * fs_) target = (line_[0].size - 4 - 0.004f * fs_) / 1.03f;
    if (delaySm_[0] <= 0) delaySm_[0] = target;
    const float fb = 0.9f * p[1];
    const float depth = 0.0025f * fs_ * p[2];
    const float wInc = 2 * kPi * 0.6f / fs_, fInc = 2 * kPi * 7.f / fs_;
    tone_[0].setCutoff(fs_, 4500.f);
    tone_[1].a = tone_[0].a;
    for (int i = 0; i < n; i++) {
        delaySm_[0] += 0.0002f * (target - delaySm_[0]);
        lfo_ += wInc; if (lfo_ > 2 * kPi) lfo_ -= 2 * kPi;
        lfo2_ += fInc; if (lfo2_ > 2 * kPi) lfo2_ -= 2 * kPi;
        float mod = depth * (1.f + 0.8f * sinf(lfo_) + 0.2f * sinf(lfo2_));
        float l = line_[0].readFrac(delaySm_[0] + mod);
        float r = line_[1].readFrac(delaySm_[0] * 1.03f + mod);
        line_[0].write(inL[i] + softClip(tone_[0].run(l) * fb * 1.1f));
        line_[1].write(inR[i] + softClip(tone_[1].run(r) * fb * 1.1f));
        outL[i] = l;
        outR[i] = r;
    }
}

// ----------------------------------------------------------------------------- freeze (looper)
void FxEngine::freeze(const float* inL, const float* inR, float* outL, float* outR, int n, const float* p,
                      float bpm) {
    const bool hold = p[1] > 0.5f;
    const float speed = 0.5f * powf(4.f, p[2]);              // 0.5x .. 2x, 1x at the centre
    const uint32_t xf = (uint32_t)(0.01f * fs_);             // 10 ms crossfade at the loop seam
    DelayLine& L = line_[0];
    DelayLine& R = line_[1];
    if (hold && !frozen_) {
        float len = freezeBeats(p[0]) * 60.f / bpm * fs_;
        if (len > L.size - xf - 8) len = (float)(L.size - xf - 8);
        loopLen_ = (uint32_t)len;
        loopStart_ = (L.w + L.size - loopLen_) % L.size;
        playPos_ = 0;
        frozen_ = true;
    } else if (!hold && frozen_) {
        frozen_ = false;
    }
    auto at = [](const DelayLine& d, float abs) -> float {     // abs: fractional index, may wrap
        while (abs < 0) abs += d.size;
        uint32_t i = (uint32_t)abs;
        float f = abs - i;
        uint32_t i0 = i % d.size, i1 = (i + 1) % d.size;
        return (d.buf[i0] * (1.f - f) + d.buf[i1] * f) * DelayLine::INV;
    };
    for (int i = 0; i < n; i++) {
        float g = holdCount_;                               // reused as output gain smoother
        g += ((frozen_ ? 1.f : 0.f) - g) * 0.002f;
        holdCount_ = g;
        if (!frozen_) {
            L.write(inL[i]);
            R.write(inR[i]);
            outL[i] = outR[i] = 0;
            if (g > 0.001f) {                               // fade out the last loop
                outL[i] = at(L, (float)loopStart_ + playPos_) * g;
                outR[i] = at(R, (float)loopStart_ + playPos_) * g;
            }
            continue;
        }
        float pos = (float)loopStart_ + playPos_;
        float l = at(L, pos), r = at(R, pos);
        float tail = playPos_ - (float)(loopLen_ - xf);
        if (tail > 0) {                                     // blend in audio from before the loop start
            float a = tail / xf;
            float pre = pos - (float)loopLen_;
            l = l * (1.f - a) + at(L, pre) * a;
            r = r * (1.f - a) + at(R, pre) * a;
        }
        playPos_ += speed;
        if (playPos_ >= loopLen_) playPos_ -= loopLen_;
        outL[i] = l * g;
        outR[i] = r * g;
    }
}
