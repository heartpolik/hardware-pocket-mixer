// SPDX-License-Identifier: GPL-3.0-or-later
// Teensy 4.1 pins as wired in hw/sch/main.py (symbol pins -> Teensy pins: docs/03-schematic.md, p. 2).
#pragma once
#include <stdint.h>

namespace pin {
// SAI1 I2S -> 3 x PCM5102A: BCLK1 21, LRCLK1 20, OUT1A 7 (MAIN), OUT1B 32 (AUX), OUT1C 9 (CUE) - set by AudioOutputI2SHex
// SAI2 TDM <- 2 x PCM1865: BCLK2 4, LRCLK2 3, IN2 5, MCLK2 33 - set by AudioInputTDM2
// I2C (Wire) 18 SDA / 19 SCL: PCM1865 0x4A / 0x4B. I2C2 (Wire2) 25 SDA2 / 24 SCL2: MCP23017 0x20-0x22
constexpr uint8_t MCP_INT[3] = {30, 31, 22};
constexpr uint8_t FADER[4] = {14, 15, 16, 17};          // A0-A3, PTA2043
constexpr uint8_t VBAT = 38;                            // A14 = VSYS / 2
constexpr uint8_t ENC_A = 0, ENC_B = 1, ENC_SW = 2;     // master encoder EC12SY
constexpr uint8_t LCD_SCK = 13, LCD_MOSI = 11, LCD_CS = 10, LCD_DC = 40, LCD_RST = 41, LCD_BLK = 28;
constexpr uint8_t SHIFT = 29;
constexpr uint8_t DAC_XSMT = 36;                        // PCM5102A soft mute, 10k pull-down
constexpr uint8_t HP_EN = 37;                           // TPA6132A2 enable, 10k pull-down
// MIDI OUT: Serial8 TX = 35
}  // namespace pin

// PCM1865 7-bit I2C addresses: MS/AD = GND -> 0x94 (8-bit) = 0x4A, MS/AD = 3V3 -> 0x96 = 0x4B
constexpr uint8_t ADC_ADDR[2] = {0x4A, 0x4B};
constexpr uint8_t MCP_ADDR[3] = {0x20, 0x21, 0x22};
