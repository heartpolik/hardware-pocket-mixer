// Simulator input sources: looped WAV files or built-in demo parts (drums, bass, pad, lead at
// 120 BPM) so the mixer has something to mix without any files.
#pragma once
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <string>
#include <vector>

struct WavData {
    std::vector<float> l, r;
    bool load(const char* path, float fs) {
        FILE* f = fopen(path, "rb");
        if (!f) return false;
        std::vector<uint8_t> d;
        uint8_t buf[65536];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0) d.insert(d.end(), buf, buf + n);
        fclose(f);
        if (d.size() < 12 || memcmp(d.data(), "RIFF", 4) || memcmp(d.data() + 8, "WAVE", 4)) return false;
        int fmt = 0, ch = 0, bits = 0;
        uint32_t rate = 0;
        const uint8_t* data = nullptr;
        uint32_t dataLen = 0;
        auto u16 = [&](size_t at) { return (uint32_t)(d[at] | d[at + 1] << 8); };
        auto u32 = [&](size_t at) { return u16(at) | u16(at + 2) << 16; };
        for (size_t p = 12; p + 8 <= d.size();) {
            uint32_t len = u32(p + 4);
            if (!memcmp(&d[p], "fmt ", 4)) {
                fmt = (int)u16(p + 8); ch = (int)u16(p + 10); rate = u32(p + 12); bits = (int)u16(p + 22);
                if (fmt == 0xFFFE && len >= 26) fmt = (int)u16(p + 32);       // WAVE_FORMAT_EXTENSIBLE
            } else if (!memcmp(&d[p], "data", 4)) {
                data = &d[p + 8];
                dataLen = (uint32_t)(len < d.size() - p - 8 ? len : d.size() - p - 8);
            }
            p += 8 + len + (len & 1);
        }
        if (!data || !ch || !rate || !(fmt == 1 || fmt == 3)) return false;
        int bps = bits / 8;
        size_t frames = dataLen / (bps * ch);
        std::vector<float> L(frames), R(frames);
        for (size_t i = 0; i < frames; i++)
            for (int c = 0; c < (ch > 1 ? 2 : 1); c++) {
                const uint8_t* s = data + (i * ch + c) * bps;
                float v = 0;
                if (fmt == 3 && bits == 32) memcpy(&v, s, 4);
                else if (bits == 16) v = (int16_t)(s[0] | s[1] << 8) / 32768.f;
                else if (bits == 24) v = (int32_t)((uint32_t)(s[0] << 8 | s[1] << 16 | s[2] << 24)) / 2147483648.f;
                else if (bits == 32) v = (int32_t)(s[0] | s[1] << 8 | s[2] << 16 | (uint32_t)s[3] << 24) / 2147483648.f;
                (c ? R : L)[i] = v;
                if (ch == 1) R[i] = v;
            }
        // linear resampling to the mixer rate
        double ratio = rate / (double)fs;
        size_t out = (size_t)(frames / ratio);
        l.resize(out); r.resize(out);
        for (size_t i = 0; i < out; i++) {
            double x = i * ratio;
            size_t k = (size_t)x;
            float t = (float)(x - k);
            size_t k1 = k + 1 < frames ? k + 1 : k;
            l[i] = L[k] * (1 - t) + L[k1] * t;
            r[i] = R[k] * (1 - t) + R[k1] * t;
        }
        return !l.empty();
    }
};

class Source {
public:
    enum Kind { Drums, Bass, Pad, Lead, File, Silence };
    Kind kind = Silence;
    WavData wav;
    std::string name;

    void setDemo(int ch) {
        static const char* const N[] = {"DRUMS", "BASS", "PAD", "LEAD"};
        kind = (Kind)(ch % 4);
        name = N[ch % 4];
    }
    bool setFile(const char* path, float fs) {
        if (!wav.load(path, fs)) return false;
        kind = File;
        name = path;
        return true;
    }

    void render(float* l, float* r, int n, float fs) {
        for (int i = 0; i < n; i++) {
            float a = 0, b = 0;
            sample(a, b, fs);
            l[i] = a; r[i] = b;
            t_++;
        }
    }

private:
    uint64_t t_ = 0;
    uint32_t noise_ = 22222;
    float ph_[8] = {}, lp_[2] = {}, hp_ = 0;

    float noise() { noise_ = noise_ * 1664525u + 1013904223u; return (int32_t)noise_ / 2147483648.f; }
    static float mtof(float m) { return 440.f * powf(2.f, (m - 69.f) / 12.f); }
    float saw(int k, float f, float fs) { ph_[k] += f / fs; if (ph_[k] >= 1) ph_[k] -= 1; return 2 * ph_[k] - 1; }

    void sample(float& l, float& r, float fs) {
        const double beat = 60.0 / 120.0;
        double t = t_ / (double)fs;
        double inBeat = fmod(t, beat);
        int beatN = (int)(t / beat);
        switch (kind) {
            case Drums: {
                float tb = (float)inBeat;
                if (inBeat * fs < 1.0) ph_[7] = 0;
                ph_[7] += (50.f + 110.f * expf(-tb * 25.f)) / fs;     // pitch-swept sine
                float kick = sinf(2 * 3.14159f * ph_[7]) * expf(-tb * 9.f) * 0.8f;
                double tOff = fmod(t + beat / 2, beat);
                float n = noise();
                float hh = n - hp_; hp_ = n;
                float hat = hh * expf(-(float)tOff * 60.f) * 0.25f;
                float sn = (beatN % 2) ? (noise() * 0.5f + sinf(2 * 3.14159f * 190.f * tb) * 0.3f) * expf(-tb * 18.f) : 0.f;
                l = (kick + hat * 0.8f + sn * 0.9f) * 0.6f;
                r = (kick + hat * 1.2f + sn * 0.9f) * 0.6f;
                break;
            }
            case Bass: {
                static const int NOTES[16] = {33, 33, 45, 33, 31, 31, 43, 31, 29, 29, 41, 29, 31, 31, 43, 36};
                int step = (int)(t / (beat / 2)) % 16;
                double inStep = fmod(t, beat / 2);
                float env = expf(-(float)inStep * 6.f);
                float x = saw(0, mtof((float)NOTES[step]), fs) * env;
                lp_[0] += 0.08f * (x - lp_[0]);
                l = r = lp_[0] * 0.6f;
                break;
            }
            case Pad: {
                static const int CH[4][3] = {{57, 60, 64}, {53, 57, 60}, {48, 52, 55}, {55, 59, 62}};
                int bar = (int)(t / (beat * 8)) % 4;
                float a = 0, b = 0;
                for (int k = 0; k < 3; k++) {
                    float f = mtof((float)CH[bar][k]);
                    a += saw(k, f * 0.997f, fs);
                    b += saw(k + 3, f * 1.003f, fs);
                }
                lp_[0] += 0.03f * (a - lp_[0]);
                lp_[1] += 0.03f * (b - lp_[1]);
                l = lp_[0] * 0.12f; r = lp_[1] * 0.12f;
                break;
            }
            case Lead: {
                static const int ARP[8] = {69, 72, 76, 81, 76, 72, 69, 64};
                int step = (int)(t / (beat / 2)) % 8;
                double inStep = fmod(t, beat / 2);
                float f = mtof((float)ARP[step]);
                ph_[6] += f / fs; if (ph_[6] >= 1) ph_[6] -= 1;
                float tri = 4.f * fabsf(ph_[6] - 0.5f) - 1.f;
                float env = expf(-(float)inStep * 4.f) * 0.35f;
                l = tri * env * 0.7f; r = tri * env;
                break;
            }
            case File: {
                if (wav.l.empty()) { l = r = 0; break; }
                size_t i = (size_t)(t_ % wav.l.size());
                l = wav.l[i]; r = wav.r[i];
                break;
            }
            default: l = r = 0;
        }
    }
};
