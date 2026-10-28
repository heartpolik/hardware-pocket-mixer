// SPDX-License-Identifier: GPL-3.0-or-later
// microSD recorder (01-spec 3.5): the audio thread packs 24-bit samples into a byte ring, the main
// loop drains it into a WAV file through a FileSink (SdFat on Teensy, stdio in the simulator).
#pragma once
#include <stdint.h>
#include <string.h>

class FileSink {
public:
    virtual ~FileSink() {}
    virtual bool open(const char* name) = 0;
    virtual bool write(const void* data, uint32_t n) = 0;
    virtual bool writeAt(uint32_t pos, const void* data, uint32_t n) = 0;
    virtual void close() = 0;
};

class Recorder {
public:
    // ring: power-of-two size in bytes
    void init(uint8_t* ring, uint32_t size, float fs) {
        ring_ = ring;
        mask_ = size - 1;
        fs_ = (uint32_t)(fs + 0.5f);
    }
    uint32_t ringBytes() const { return mask_ + 1; }

    bool start(FileSink* f, const char* name, int channels) {
        if (active_ || !ring_ || !f || !f->open(name)) return false;
        sink_ = f;
        channels_ = channels;
        head_ = tail_ = 0;
        dataBytes_ = 0;
        overruns = 0;
        uint8_t h[44];
        header(h, 0);
        sink_->write(h, 44);
        active_ = true;
        return true;
    }

    void stop() {
        if (!active_) return;
        active_ = false;
        service();                                   // drain what is left
        uint8_t h[44];
        header(h, dataBytes_);
        sink_->writeAt(0, h, 44);
        sink_->close();
        sink_ = nullptr;
    }

    // audio thread: ch[channels_] pointers, n samples each
    void write(const float* const* ch, int n) {
        if (!active_) return;
        uint32_t need = (uint32_t)(n * channels_ * 3);
        uint32_t used = head_ - tail_;
        if (used + need > mask_ + 1) { overruns = overruns + 1; return; }
        uint32_t h = head_;
        for (int i = 0; i < n; i++)
            for (int c = 0; c < channels_; c++) {
                float x = ch[c] ? ch[c][i] : 0.f;
                x = x > 1.f ? 1.f : (x < -1.f ? -1.f : x);
                int32_t v = (int32_t)(x * 8388607.f);
                ring_[h++ & mask_] = (uint8_t)v;
                ring_[h++ & mask_] = (uint8_t)(v >> 8);
                ring_[h++ & mask_] = (uint8_t)(v >> 16);
            }
        head_ = h;
    }

    // main loop: write whatever is in the ring (in chunks up to `maxChunk`)
    void service(uint32_t maxChunk = 32768) {
        if (!sink_) return;
        for (;;) {
            uint32_t avail = head_ - tail_;
            if (!avail) return;
            uint32_t off = tail_ & mask_;
            uint32_t n = avail;
            if (n > mask_ + 1 - off) n = mask_ + 1 - off;     // up to the ring end
            if (n > maxChunk) n = maxChunk;
            if (active_ && n < 4096 && avail < 4096) return;   // write in bigger pieces while recording
            sink_->write(ring_ + off, n);
            tail_ += n;
            dataBytes_ += n;
        }
    }

    bool active() const { return active_; }
    int channels() const { return channels_; }
    uint32_t seconds() const { return channels_ ? dataBytes_ / (3u * channels_ * fs_) : 0; }
    volatile uint32_t overruns = 0;

private:
    void header(uint8_t* h, uint32_t data) {
        auto u32 = [&](int at, uint32_t v) { h[at] = v; h[at + 1] = v >> 8; h[at + 2] = v >> 16; h[at + 3] = v >> 24; };
        auto u16 = [&](int at, uint32_t v) { h[at] = v; h[at + 1] = v >> 8; };
        memcpy(h, "RIFF", 4); u32(4, 36 + data); memcpy(h + 8, "WAVEfmt ", 8);
        u32(16, 16); u16(20, 1); u16(22, channels_); u32(24, fs_); u32(28, fs_ * 3 * channels_);
        u16(32, 3 * channels_); u16(34, 24);
        memcpy(h + 36, "data", 4); u32(40, data);
    }

    uint8_t* ring_ = nullptr;
    uint32_t mask_ = 0, fs_ = 48000;
    volatile uint32_t head_ = 0, tail_ = 0;
    uint32_t dataBytes_ = 0;
    int channels_ = 2;
    volatile bool active_ = false;
    FileSink* sink_ = nullptr;
};
