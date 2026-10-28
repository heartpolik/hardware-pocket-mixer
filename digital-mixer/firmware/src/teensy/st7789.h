// SPDX-License-Identifier: GPL-3.0-or-later
// GMT147SPI (ST7789V, 172 x 320) in landscape over SPI. Commands: docs/datasheets/st7789v.pdf
// (Sitronix ST7789V v1.3, 2014/03; kept local, not in git): SWRESET 01h, SLPOUT 11h, INVON 21h, DISPON 29h, CASET 2Ah, RASET 2Bh,
// RAMWR 2Ch, MADCTL 36h, COLMOD 3Ah. Only rows whose content changed are sent (row hashes), a few
// rows per call so the main loop keeps polling the controls.
#pragma once
#include <Arduino.h>
#include <SPI.h>

#include "../core/ui.h"
#include "pins.h"

class St7789 {
public:
    // Serial write clock: tSCYCW >= 66 ns in the datasheet (~15 MHz); faster may work - check on the sample.
    static constexpr uint32_t SPI_HZ = 15000000;
    // MADCTL for landscape: MV = 1 (row/column exchange) + MX or MY for the mounting orientation, and
    // the 172-pixel side sits at offset 34 in the 240-line controller RAM - both `ПЕРЕВІРИТИ` on the sample.
    static constexpr uint8_t MADCTL = 0xA0;     // MY | MV, RGB order: checked on the module (0x60 = upside down)
    static constexpr int OFFSET_Y = 34, OFFSET_X = 0;

    void begin() {
        pinMode(pin::LCD_CS, OUTPUT);
        pinMode(pin::LCD_DC, OUTPUT);
        pinMode(pin::LCD_RST, OUTPUT);
        digitalWriteFast(pin::LCD_CS, HIGH);
        SPI.begin();
        digitalWriteFast(pin::LCD_RST, LOW);
        delay(10);
        digitalWriteFast(pin::LCD_RST, HIGH);
        delay(120);
        cmd(0x01); delay(150);                  // SWRESET
        cmd(0x11); delay(120);                  // SLPOUT
        cmd(0x3A, 0x55);                        // COLMOD: 16 bit/pixel (RGB565)
        cmd(0x36, MADCTL);
        cmd(0x21);                              // INVON: IPS panels of this type need inversion - check
        cmd(0x13);                              // NORON
        cmd(0x29);                              // DISPON
        for (int y = 0; y < DISPLAY_H; y++) { hash_[y] = 0; dirty_[y] = true; }
    }

    // compare a freshly rendered frame with what is on the panel
    void frame(const uint16_t* fb) {
        for (int y = 0; y < DISPLAY_H; y++) {
            const uint32_t* p = (const uint32_t*)(fb + y * DISPLAY_W);
            uint32_t h = 2166136261u;
            for (int i = 0; i < DISPLAY_W / 2; i++) h = (h ^ p[i]) * 16777619u;
            if (h != hash_[y]) { hash_[y] = h; dirty_[y] = true; }
        }
    }

    // send up to maxRows changed rows; returns true while rows are pending
    bool service(const uint16_t* fb, int maxRows = 6) {
        int y = 0;
        while (y < DISPLAY_H && !dirty_[y]) y++;
        if (y == DISPLAY_H) return false;
        int y1 = y;
        while (y1 + 1 < DISPLAY_H && dirty_[y1 + 1] && y1 + 1 - y < maxRows) y1++;
        window(0, y, DISPLAY_W - 1, y1);
        SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE0));
        digitalWriteFast(pin::LCD_CS, LOW);
        digitalWriteFast(pin::LCD_DC, LOW);
        SPI.transfer(0x2C);                          // RAMWR, pixels follow in the same CS frame
        digitalWriteFast(pin::LCD_DC, HIGH);
        for (int r = y; r <= y1; r++) {
            const uint16_t* src = fb + r * DISPLAY_W;
            for (int i = 0; i < DISPLAY_W; i++) line_[i] = (uint16_t)(src[i] << 8 | src[i] >> 8);   // big-endian
            SPI.transfer(line_, nullptr, sizeof line_);
            dirty_[r] = false;
        }
        digitalWriteFast(pin::LCD_CS, HIGH);
        SPI.endTransaction();
        return true;
    }

    bool pending() const {
        for (int y = 0; y < DISPLAY_H; y++) if (dirty_[y]) return true;
        return false;
    }

private:
    void cmd(uint8_t c, int arg = -1) {
        SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE0));
        digitalWriteFast(pin::LCD_CS, LOW);
        digitalWriteFast(pin::LCD_DC, LOW);
        SPI.transfer(c);
        if (arg >= 0) { digitalWriteFast(pin::LCD_DC, HIGH); SPI.transfer((uint8_t)arg); }
        digitalWriteFast(pin::LCD_CS, HIGH);
        SPI.endTransaction();
    }
    void cmd4(uint8_t c, uint16_t a, uint16_t b) {
        SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE0));
        digitalWriteFast(pin::LCD_CS, LOW);
        digitalWriteFast(pin::LCD_DC, LOW);
        SPI.transfer(c);
        digitalWriteFast(pin::LCD_DC, HIGH);
        SPI.transfer16(a);
        SPI.transfer16(b);
        digitalWriteFast(pin::LCD_CS, HIGH);
        SPI.endTransaction();
    }
    void window(int x0, int y0, int x1, int y1) {
        cmd4(0x2A, x0 + OFFSET_X, x1 + OFFSET_X);    // CASET
        cmd4(0x2B, y0 + OFFSET_Y, y1 + OFFSET_Y);    // RASET
    }

    uint32_t hash_[DISPLAY_H];
    bool dirty_[DISPLAY_H];
    uint16_t line_[DISPLAY_W];
};
