// Physical controls: 3 x MCP23017 on Wire2 (12 channel encoders, their pushes, Mute, AUX, FX I,
// FX II), master encoder and SHIFT on Teensy pins, 4 faders. Produces Ui events.
#pragma once
#include <Arduino.h>
#include <Wire.h>

#include "../core/ui.h"
#include "pins.h"

// Quadrature decoder: counts valid Gray-code transitions, emits one step per detent when the
// encoder returns to its rest state (A = B = 1 with pull-ups). EC12SY 24C24P: one cycle per detent.
struct Quad {
    uint8_t prev = 3;
    int8_t acc = 0;
    int step(uint8_t ab) {                     // ab = A << 1 | B
        static const int8_t T[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
        acc += T[prev << 2 | ab];
        prev = ab;
        if (ab == 3) {
            int d = acc >= 2 ? 1 : acc <= -2 ? -1 : 0;
            acc = 0;
            return d;
        }
        return 0;
    }
};

struct Debounce {
    bool state = false, cand = false;
    uint32_t since = 0;
    // returns +1 pressed, -1 released, 0 no change
    int update(bool pressed, uint32_t now) {
        if (pressed != cand) { cand = pressed; since = now; }
        if (cand != state && now - since >= 5) { state = cand; return state ? 1 : -1; }
        return 0;
    }
};

class Controls {
public:
    bool begin(Ui* ui);
    void poll();                                // call from loop()
    static void masterIsr();

private:
    bool mcpWrite(int k, uint8_t reg, uint8_t v);
    bool mcpRead(int k, uint16_t& ab);
    void handleMcp(int k, uint16_t ab, uint32_t now);
    Ui* ui_ = nullptr;
    Quad enc_[12];
    Debounce btn_[B_COUNT];
    uint32_t lastPoll_ = 0, lastFader_ = 0;
    float fader_[4] = {-1, -1, -1, -1}, sent_[4] = {-1, -1, -1, -1};
    static volatile int masterSteps_;
    static Quad masterQuad_;
};
