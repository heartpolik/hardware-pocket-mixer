// SPDX-License-Identifier: GPL-3.0-or-later
// Teensy 4.1 entry point: audio graph (TDM in from 2 x PCM1865, I2S out to 3 x PCM5102A, USB audio
// and MIDI), codecs over I2C, controls, display, EEPROM scenes, microSD recorder.
#include <Arduino.h>
#include <Audio.h>
#include <EEPROM.h>
#include <SD.h>
#include <Wire.h>

#include "../core/gfx.h"
#include "../core/hal.h"
#include "../core/mixer.h"
#include "../core/recorder.h"
#include "../core/ui.h"
#include "controls.h"
#include "pcm1865.h"
#include "pins.h"
#include "st7789.h"

extern "C" uint8_t external_psram_size;        // MB of PSRAM fitted under the Teensy 4.1 (0 = none)

static Scene scene;
static Live live;
static Settings settings;
static Mixer mixer;
static Recorder recorder;
static Ui ui;
static Controls controls;
static St7789 lcd;
static Pcm1865 adc[2];
static uint16_t framebuf[DISPLAY_W * DISPLAY_H];
static Canvas canvas(framebuf, DISPLAY_W, DISPLAY_H);

#ifdef MIXER_USB_OCT
static constexpr int USB_OUT = 8;              // UAC2 core (alex6679 / grrrr teensy-4-usbAudio)
#else
static constexpr int USB_OUT = 2;              // stock Teensy USB audio: stereo, 44.1 kHz
#endif

// ------------------------------------------------------------------ audio node
// 16 TDM inputs (8 slots x high/low 16 bits), 2 USB inputs -> 6 DAC outputs + USB_OUT USB outputs.
class MixerNode : public AudioStream {
public:
    MixerNode() : AudioStream(18, queue_) {}
    void update() override {
        static float in[8][AUDIO_BLOCK_SAMPLES], usbIn[2][AUDIO_BLOCK_SAMPLES];
        static float out[6][AUDIO_BLOCK_SAMPLES], usbOut[8][AUDIO_BLOCK_SAMPLES];
        constexpr float K = 1.f / 2147483648.f;
        for (int s = 0; s < 8; s++) {
            // a 32-bit TDM slot arrives split in two 16-bit channels: high half, low half (input_tdm2.cpp)
            audio_block_t* hi = receiveReadOnly(2 * s);
            audio_block_t* lo = receiveReadOnly(2 * s + 1);
            for (int i = 0; i < AUDIO_BLOCK_SAMPLES; i++) {
                int32_t v = (hi ? (int32_t)hi->data[i] << 16 : 0) | (lo ? (uint16_t)lo->data[i] : 0);
                in[s][i] = v * K;
            }
            if (hi) release(hi);
            if (lo) release(lo);
        }
        AudioIO io;
        for (int k = 0; k < 2; k++) {
            audio_block_t* b = receiveReadOnly(16 + k);
            for (int i = 0; i < AUDIO_BLOCK_SAMPLES; i++) usbIn[k][i] = b ? b->data[i] / 32768.f : 0.f;
            if (b) release(b);
            io.usbIn[k] = usbIn[k];
        }
        for (int k = 0; k < 8; k++) { io.in[k] = in[k]; io.usbOut[k] = k < USB_OUT ? usbOut[k] : nullptr; }
        for (int k = 0; k < 6; k++) io.out[k] = out[k];
        io.usbOutChannels = USB_OUT;
        io.n = AUDIO_BLOCK_SAMPLES;
        mixer.process(io);
        for (int k = 0; k < 6 + USB_OUT; k++) {
            audio_block_t* b = allocate();
            if (!b) continue;
            const float* src = k < 6 ? out[k] : usbOut[k - 6];
            for (int i = 0; i < AUDIO_BLOCK_SAMPLES; i++) {
                float x = src[i] * 32767.f;
                b->data[i] = (int16_t)(x > 32767.f ? 32767 : x < -32768.f ? -32768 : (int)lrintf(x));
            }
            transmit(b, k);
            release(b);
        }
    }

private:
    audio_block_t* queue_[18];
};

AudioInputTDM2 tdm;
AudioOutputI2SHex dacs;                        // OUT1A pin 7 = MAIN, OUT1B 32 = AUX, OUT1C 9 = CUE
MixerNode node;
#ifdef MIXER_USB_OCT
AudioInputUSB usbIn;
AudioOutputUSBOct usbOut;                      // `ПЕРЕВІРИТИ` class name in the UAC2 core
#else
AudioInputUSB usbIn;
AudioOutputUSB usbOut;
#endif
AudioConnection* wires[16 + 2 + 6 + USB_OUT];

static void connectAudio() {
    int w = 0;
    for (int i = 0; i < 16; i++) wires[w++] = new AudioConnection(tdm, i, node, i);
    wires[w++] = new AudioConnection(usbIn, 0, node, 16);
    wires[w++] = new AudioConnection(usbIn, 1, node, 17);
    for (int i = 0; i < 6; i++) wires[w++] = new AudioConnection(node, i, dacs, i);
    for (int i = 0; i < USB_OUT; i++) wires[w++] = new AudioConnection(node, 6 + i, usbOut, i);
}

// ------------------------------------------------------------------ platform
class SdSink : public FileSink {
public:
    bool open(const char* name) override { f_ = SD.open(name, FILE_WRITE_BEGIN); return (bool)f_; }
    bool write(const void* d, uint32_t n) override { return f_.write((const uint8_t*)d, n) == n; }
    bool writeAt(uint32_t pos, const void* d, uint32_t n) override {
        uint32_t cur = f_.position();
        f_.seek(pos);
        bool ok = f_.write((const uint8_t*)d, n) == n;
        f_.seek(cur);
        return ok;
    }
    void close() override { f_.close(); }

private:
    File f_;
};

class TeensyHal : public Hal {
public:
    bool sdOk = false;
    bool psram = false;
    SdSink sink;
    uint32_t millis() override { return ::millis(); }
    uint32_t micros() override { return ::micros(); }
    void setInputGain(int ch, float db) override { adc[ch / 2].setGain(ch % 2, db); }
    void midiOut(const uint8_t* m, int n) override {
        Serial8.write(m, n);                                    // TRS MIDI OUT (DM20)
        if (n == 1) usbMIDI.sendRealTime(m[0]);
        else if (n == 3 && (m[0] & 0xF0) == 0xB0) usbMIDI.sendControlChange(m[1], m[2], (m[0] & 0x0F) + 1);
    }
    // EEPROM emulation: 4284 bytes on Teensy 4.1; 10 slots of 400 bytes
    bool load(int slot, void* d, uint32_t n) override {
        if (n > 400 || slot < 0 || slot > 9) return false;
        uint8_t* p = (uint8_t*)d;
        for (uint32_t i = 0; i < n; i++) p[i] = EEPROM.read(slot * 400 + i);
        return true;
    }
    bool save(int slot, const void* d, uint32_t n) override {
        if (n > 400 || slot < 0 || slot > 9) return false;
        const uint8_t* p = (const uint8_t*)d;
        for (uint32_t i = 0; i < n; i++) EEPROM.update(slot * 400 + i, p[i]);   // writes changed bytes only
        return true;
    }
    void setBacklight(int pct) override { analogWrite(pin::LCD_BLK, pct * 255 / 100); }
    float batteryVolts() override { return analogRead(pin::VBAT) / 4095.f * 3.3f * 2.f; }
    float cpuLoad() override { return AudioProcessorUsage(); }
    FileSink* recSink() override { return sdOk ? &sink : nullptr; }
    void recFileName(char* buf, int n) override {
        for (int i = 1; i < 10000; i++) {
            snprintf(buf, n, "REC%04d.WAV", i);
            if (!SD.exists(buf)) return;
        }
    }
    int recChannels() override { return psram ? 10 : 2; }
};
static TeensyHal hal;

// ------------------------------------------------------------------ setup / loop
static void midiFromUsb() {
    while (usbMIDI.read()) {
        uint8_t type = usbMIDI.getType(), ch = usbMIDI.getChannel();
        uint8_t m[3] = {type, usbMIDI.getData1(), usbMIDI.getData2()};
        if (type < 0xF0) m[0] = (uint8_t)(type | ((ch - 1) & 15));
        ui.midiIn(m, type == 0xC0 ? 2 : (type >= 0xF0 ? 1 : 3));
    }
}

void setup() {
    pinMode(pin::DAC_XSMT, OUTPUT);
    digitalWriteFast(pin::DAC_XSMT, LOW);        // DACs muted until the codecs and the mix are up
    pinMode(pin::HP_EN, OUTPUT);
    digitalWriteFast(pin::HP_EN, LOW);
    pinMode(pin::LCD_BLK, OUTPUT);
    analogWriteFrequency(pin::LCD_BLK, 20000);
    analogWrite(pin::LCD_BLK, 0);
    Serial8.begin(31250);

    // FX memory and recorder ring: PSRAM if fitted (extmem_malloc falls back to the heap in RAM2)
    hal.psram = external_psram_size > 0;
    uint32_t pool = hal.psram ? 480000 : 72000;       // int16 samples per FX bus: 5 s / 0.75 s of stereo delay
    uint32_t ring = hal.psram ? (1u << 21) : (1u << 16);
    int16_t* pools[NFX];
    for (int i = 0; i < NFX; i++) {
        pools[i] = (int16_t*)extmem_malloc(pool * sizeof(int16_t));
        memset(pools[i], 0, pool * sizeof(int16_t));
    }
    recorder.init((uint8_t*)extmem_malloc(ring), ring, AUDIO_SAMPLE_RATE_EXACT);

    mixer.init(AUDIO_SAMPLE_RATE_EXACT, &scene, &live, pools, pool);
    mixer.recorder = &recorder;
    ui.init(&hal, &mixer, &scene, &live, &settings, &recorder);

    AudioMemory(64);
    connectAudio();                               // TDM2 provides MCLK2 to the PCM1865s from here on

    Wire.begin();
    Wire.setClock(400000);
    delay(20);
    adc[0].begin(Wire, ADC_ADDR[0], 1);
    adc[1].begin(Wire, ADC_ADDR[1], 1 + 4 * 32);

    lcd.begin();
    controls.begin(&ui);
    hal.sdOk = SD.begin(BUILTIN_SDCARD);
    ui.begin();                                   // loads the last state, sets PGA gains and backlight

    delay(100);
    digitalWriteFast(pin::DAC_XSMT, HIGH);
    digitalWriteFast(pin::HP_EN, HIGH);
}

void loop() {
    static uint32_t lastFrame = 0;
    controls.poll();
    midiFromUsb();
    ui.tick();
    uint32_t now = millis();
    if (!lcd.pending() && now - lastFrame >= 33) {       // ~30 fps, only changed rows go to the panel
        lastFrame = now;
        ui.render(canvas);
        lcd.frame(framebuf);
    }
    lcd.service(framebuf);
    usbMIDI.send_now();
}
