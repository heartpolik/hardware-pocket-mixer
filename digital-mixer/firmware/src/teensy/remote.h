// SPDX-License-Identifier: GPL-3.0-or-later
// Remote panel over the USB serial port (desktop: ./build/pocket-mixer-sim --remote): the display rows that
// changed and a status line go to the computer, encoder / button / fader events come back.
//   Teensy -> host: packets A5 5A <type> <len16 LE> <payload>; type 1 = display row (row u8 + 320 x RGB565 LE),
//                   type 2 = status text "key=value key=value ...".
//   host -> Teensy: text lines "E id delta", "B id 0|1", "F ch pos", "R 1" (start, full frame), "R 0" (stop).
#pragma once
#include <Arduino.h>

#include "../core/ui.h"

class Remote {
public:
    bool active = false;
    bool fadersFromHost = false;           // once the host moves a fader, the (floating) ADC inputs are ignored
    uint32_t rowsSent = 0;

    // returns true when a command changed the UI (the caller renders sooner)
    bool poll(Ui& ui) {
        if (active && !Serial.dtr()) stop();
        bool any = false;
        while (Serial.available()) {
            char c = (char)Serial.read();
            if (c == '\n' || c == '\r') {
                line_[len_] = 0;
                if (len_) any |= command(ui);
                len_ = 0;
            } else if (len_ < sizeof line_ - 1) line_[len_++] = c;
        }
        return any;
    }

    // a packet goes out only whole: a full USB buffer would cut it (Serial.write gives up after a timeout) and
    // the row would be lost; a row that did not fit stays changed and goes with the next frame
    void frame(const uint16_t* fb) {
        if (!active) return;
        for (int y = 0; y < DISPLAY_H; y++) {
            const uint16_t* row = fb + y * DISPLAY_W;
            uint32_t h = 2166136261u;
            for (int i = 0; i < DISPLAY_W; i++) h = (h ^ row[i]) * 16777619u;
            if (h == hash_[y]) continue;
            if (Serial.availableForWrite() < 6 + 2 * DISPLAY_W) break;
            hash_[y] = h;
            uint8_t hdr[6] = {0xA5, 0x5A, 1, (uint8_t)((1 + 2 * DISPLAY_W) & 0xFF), (uint8_t)((1 + 2 * DISPLAY_W) >> 8), (uint8_t)y};
            Serial.write(hdr, 6);
            Serial.write((const uint8_t*)row, 2 * DISPLAY_W);
            rowsSent++;
        }
    }

    void status(const char* text) {
        if (!active) return;
        size_t n = strlen(text);
        if (Serial.availableForWrite() < (int)n + 5) return;      // skipped, the next one comes in 250 ms
        uint8_t hdr[5] = {0xA5, 0x5A, 2, (uint8_t)(n & 0xFF), (uint8_t)(n >> 8)};
        Serial.write(hdr, 5);
        Serial.write((const uint8_t*)text, n);
    }

private:
    void stop() { active = false; fadersFromHost = false; }

    bool command(Ui& ui) {
        int a = 0;
        float f = 0;
        switch (line_[0]) {
            case 'E': {
                int d = 0;
                if (sscanf(line_ + 1, "%d %d", &a, &d) == 2) ui.encoder(a, d);
                return true;
            }
            case 'B': {
                int down = 0;
                if (sscanf(line_ + 1, "%d %d", &a, &down) == 2) ui.button(a, down != 0);
                return true;
            }
            case 'F':
                if (sscanf(line_ + 1, "%d %f", &a, &f) == 2) { fadersFromHost = true; ui.fader(a, f); }
                return true;
            case 'R':
                if (sscanf(line_ + 1, "%d", &a) == 1) {
                    if (a) { active = true; rowsSent = 0; memset(hash_, 0, sizeof hash_); } else stop();   // all rows again
                }
                return true;
        }
        return false;
    }

    char line_[48];
    size_t len_ = 0;
    uint32_t hash_[DISPLAY_H] = {};       // FNV-1a of the rows sent; 0 = send again
};
