// What the portable core needs from the platform (Teensy 4.1 or the desktop simulator).
#pragma once
#include <stdint.h>

class FileSink;

class Hal {
public:
    virtual ~Hal() {}
    virtual uint32_t millis() = 0;
    virtual uint32_t micros() = 0;
    virtual void setInputGain(int ch, float db) = 0;            // PCM1865 PGA, both sides of channel ch
    virtual void midiOut(const uint8_t* msg, int n) = 0;        // TRS MIDI OUT and USB MIDI
    // slot 0 = autosave of the current state, 1..8 = scenes, 9 = settings
    virtual bool load(int slot, void* data, uint32_t n) = 0;
    virtual bool save(int slot, const void* data, uint32_t n) = 0;
    virtual void setBacklight(int percent) = 0;
    virtual float batteryVolts() = 0;                            // < 0: unknown
    virtual float cpuLoad() { return -1; }                       // audio thread, %
    // recorder
    virtual FileSink* recSink() = 0;                             // nullptr: no card
    virtual void recFileName(char* buf, int n) = 0;              // next free name
    virtual int recChannels() = 0;                               // 10 (8 inputs + MAIN) or 2 (MAIN)
};
