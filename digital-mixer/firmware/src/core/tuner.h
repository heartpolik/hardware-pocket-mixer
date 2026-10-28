// Tuner (01-spec 3.3): YIN pitch detection (de Cheveigne & Kawahara, JASA 2002) on the ring the
// mixer fills at fs/2. Runs in the main loop, a few times per second.
#pragma once
#include <math.h>
#include <stdint.h>
#include <stdio.h>

struct TunerResult {
    bool valid = false;
    float hz = 0, cents = 0;
    char note[4] = "--";
};

inline TunerResult tunerAnalyze(const float* ring, uint32_t write, int ringLen, float rate) {
    constexpr int W = 1024, TMAX = W / 2;
    static float x[W], d[TMAX];
    TunerResult r;
    float rms = 0;
    for (int i = 0; i < W; i++) {
        x[i] = ring[(write + ringLen - W + i) % ringLen];
        rms += x[i] * x[i];
    }
    if (sqrtf(rms / W) < 0.003f) return r;
    d[0] = 1;
    float run = 0;
    int tau = -1;
    for (int t = 1; t < TMAX; t++) {
        float s = 0;
        for (int i = 0; i < W - TMAX; i++) { float e = x[i] - x[i + t]; s += e * e; }
        run += s;
        d[t] = run > 0 ? s * t / run : 1;
    }
    for (int t = 2; t < TMAX - 1; t++)
        if (d[t] < 0.15f) {
            while (t + 1 < TMAX - 1 && d[t + 1] < d[t]) t++;
            tau = t;
            break;
        }
    if (tau < 0) return r;
    float a = d[tau - 1], b = d[tau], c = d[tau + 1];
    float den = a - 2 * b + c;
    float ft = tau + (den != 0 ? 0.5f * (a - c) / den : 0.f);
    r.hz = rate / ft;
    float midi = 69.f + 12.f * log2f(r.hz / 440.f);
    int m = (int)lroundf(midi);
    r.cents = (midi - m) * 100.f;
    static const char* const N[] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
    snprintf(r.note, sizeof r.note, "%s%d", N[((m % 12) + 12) % 12], m / 12 - 1);
    r.valid = true;
    return r;
}
