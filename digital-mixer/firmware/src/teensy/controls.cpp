// SPDX-License-Identifier: GPL-3.0-or-later
#include "controls.h"

// MCP23017 registers, IOCON.BANK = 0 (docs/datasheets/mcp23017.pdf, DS20001952D, table 3-1)
enum : uint8_t { IODIRA = 0x00, GPINTENA = 0x04, INTCONA = 0x08, IOCON = 0x0A, GPPUA = 0x0C, GPIOA = 0x12 };
constexpr uint8_t IOCON_MIRROR = 0x40;          // INTA = INTB = any change on either port

volatile int Controls::masterSteps_ = 0;
Quad Controls::masterQuad_;

void Controls::masterIsr() {
    uint8_t ab = (uint8_t)(digitalReadFast(pin::ENC_A) << 1 | digitalReadFast(pin::ENC_B));
    masterSteps_ += masterQuad_.step(ab);
}

bool Controls::mcpWrite(int k, uint8_t reg, uint8_t v) {
    Wire2.beginTransmission(MCP_ADDR[k]);
    Wire2.write(reg);
    Wire2.write(v);
    return Wire2.endTransmission() == 0;
}

bool Controls::mcpRead(int k, uint16_t& ab) {
    Wire2.beginTransmission(MCP_ADDR[k]);
    Wire2.write(GPIOA);                          // sequential: GPIOA then GPIOB; reading clears INT
    if (Wire2.endTransmission(false) != 0) return false;
    if (Wire2.requestFrom(MCP_ADDR[k], (uint8_t)2) != 2) return false;
    uint8_t a = Wire2.read(), b = Wire2.read();
    ab = (uint16_t)(a | b << 8);
    return true;
}

bool Controls::begin(Ui* ui) {
    ui_ = ui;
    Wire2.begin();
    Wire2.setClock(400000);
    bool ok = true;
    for (int k = 0; k < 3; k++) {
        pinMode(pin::MCP_INT[k], INPUT);         // push-pull active-low INT
        ok &= mcpWrite(k, IOCON, IOCON_MIRROR);
        for (int p = 0; p < 2; p++) {
            ok &= mcpWrite(k, IODIRA + p, 0xFF);
            ok &= mcpWrite(k, GPPUA + p, 0xFF);    // 100k internal pull-ups, switches to GND
            ok &= mcpWrite(k, INTCONA + p, 0x00);  // interrupt on change from the previous value
            ok &= mcpWrite(k, GPINTENA + p, 0xFF);
        }
        uint16_t ab;
        if (mcpRead(k, ab) && k < 2)
            for (int e = 0; e < 6; e++) {          // start the decoders from the current position
                int half = e / 3, row = e % 3;
                uint8_t bits = (uint8_t)(ab >> (8 * half));
                enc_[(2 * k + half) * 3 + row].prev = (uint8_t)((bits >> (2 * row) & 1) << 1 | (bits >> (2 * row + 1) & 1));
            }
    }
    pinMode(pin::ENC_A, INPUT_PULLUP);
    pinMode(pin::ENC_B, INPUT_PULLUP);
    pinMode(pin::ENC_SW, INPUT_PULLUP);
    pinMode(pin::SHIFT, INPUT_PULLUP);
    masterQuad_.prev = (uint8_t)(digitalReadFast(pin::ENC_A) << 1 | digitalReadFast(pin::ENC_B));
    attachInterrupt(digitalPinToInterrupt(pin::ENC_A), masterIsr, CHANGE);
    attachInterrupt(digitalPinToInterrupt(pin::ENC_B), masterIsr, CHANGE);
    analogReadResolution(12);
    analogReadAveraging(4);
    return ok;
}

static inline bool bitOf(uint16_t ab, int i) { return (ab >> i & 1) != 0; }   // 1 = high = released / open

void Controls::handleMcp(int k, uint16_t ab, uint32_t now) {
    if (k < 2) {
        for (int half = 0; half < 2; half++) {
            int ch = 2 * k + half, base = 8 * half;
            for (int row = 0; row < 3; row++) {
                uint8_t q = (uint8_t)(bitOf(ab, base + 2 * row) << 1 | bitOf(ab, base + 2 * row + 1));
                int d = enc_[ch * 3 + row].step(q);
                if (d) ui_->encoder(ch * 3 + row, d);
            }
            int b = B_MUTE1 + ch, e = btn_[b].update(!bitOf(ab, base + 6), now);
            if (e) ui_->button(b, e > 0);
        }
        return;
    }
    // #3: encoder pushes GPA0-5 (ch 1-2), GPB0-5 (ch 3-4); AUX GPA6, FX I GPA7, FX II GPB6
    for (int i = 0; i < 12; i++) {
        int bitn = i < 6 ? i : 8 + (i - 6);
        int e = btn_[i].update(!bitOf(ab, bitn), now);
        if (e) ui_->button(i, e > 0);
    }
    const int ids[3] = {B_AUX, B_FX1, B_FX2}, bits[3] = {6, 7, 14};
    for (int j = 0; j < 3; j++) {
        int e = btn_[ids[j]].update(!bitOf(ab, bits[j]), now);
        if (e) ui_->button(ids[j], e > 0);
    }
}

void Controls::poll() {
    uint32_t now = millis();
    bool periodic = now - lastPoll_ >= 4;          // debounce needs reads after the last edge too
    if (periodic) lastPoll_ = now;
    for (int k = 0; k < 3; k++)
        if (periodic || digitalReadFast(pin::MCP_INT[k]) == LOW) {
            uint16_t ab;
            if (mcpRead(k, ab)) handleMcp(k, ab, now);
        }

    noInterrupts();
    int steps = masterSteps_;
    masterSteps_ = 0;
    interrupts();
    if (steps) ui_->encoder(E_MASTER, steps);
    int e = btn_[B_MASTER].update(digitalReadFast(pin::ENC_SW) == LOW, now);
    if (e) ui_->button(B_MASTER, e > 0);
    e = btn_[B_SHIFT].update(digitalReadFast(pin::SHIFT) == LOW, now);
    if (e) ui_->button(B_SHIFT, e > 0);

    if (readFaders && now - lastFader_ >= 5) {
        lastFader_ = now;
        for (int ch = 0; ch < 4; ch++) {
            float x = analogRead(pin::FADER[ch]) / 4095.f;      // raw; ends and direction: menu FADER CAL
            fader_[ch] = fader_[ch] < 0 ? x : fader_[ch] + 0.3f * (x - fader_[ch]);
            if (fabsf(fader_[ch] - sent_[ch]) > 0.002f) {        // hysteresis against ADC noise
                sent_[ch] = fader_[ch];
                ui_->fader(ch, fader_[ch]);
            }
        }
    }
}
