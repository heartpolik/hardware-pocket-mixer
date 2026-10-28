// PCM1865 in I2C slave mode, 4-channel TDM on a shared DOUT line (docs/datasheets/pcm1865.pdf,
// SLAS831D: register map p. 86-96, TDM p. 58-59).
#pragma once
#include <Wire.h>

class Pcm1865 {
public:
    // txOffset: first BCK of this device's data in the 256-BCK frame. Teensy TDM2 asserts the frame
    // sync one BCK before the data (I2S_RCR4_FSE, output_tdm2.cpp), so ADC1 = 1, ADC2 = 1 + 4 * 32.
    bool begin(TwoWire& w, uint8_t addr, uint8_t txOffset) {
        w_ = &w;
        addr_ = addr;
        bool ok = write(0x00, 0x00);         // page 0
        ok &= write(0x06, 0x41);             // ADC1L <- VINL1 (SE); bit 6 reserved, write 1
        ok &= write(0x07, 0x41);             // ADC1R <- VINR1
        ok &= write(0x08, 0x42);             // ADC2L <- VINL2
        ok &= write(0x09, 0x42);             // ADC2R <- VINR2
        // I2S_FMT: RX_WLEN 24 (unused), TDM_LRCK_MODE = 1 (1/256 duty), TX_WLEN 32 bit, FMT = TDM
        ok &= write(0x0B, 0x40 | 0x10 | 0x00 | 0x03);
        ok &= write(0x0C, 0x01);             // TDM_OSEL: 4 channels ch1 L/R, ch2 L/R
        ok &= write(0x0D, txOffset);         // TX_TDM_OFFSET
        return ok;
    }
    // ch 0 = ADC1 pair (VINL1/VINR1), 1 = ADC2 pair. PGA: 0.5 dB steps, two's complement (p. 89)
    bool setGain(int ch, float db) {
        if (db < -12) db = -12;
        if (db > 32) db = 32;
        int8_t v = (int8_t)lroundf(db * 2);
        uint8_t r = ch ? 0x03 : 0x01;
        return write(r, (uint8_t)v) && write(r + 1, (uint8_t)v);
    }

private:
    bool write(uint8_t reg, uint8_t val) {
        w_->beginTransmission(addr_);
        w_->write(reg);
        w_->write(val);
        return w_->endTransmission() == 0;
    }
    TwoWire* w_ = nullptr;
    uint8_t addr_ = 0;
};
