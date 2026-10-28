// Control surface and display (01-spec 4, DM28): layers of the 12 channel encoders, AUX / FX I /
// FX II / SHIFT buttons, master encoder with menu, MIDI CC in/out, tempo, scenes, recorder, tuner.
#pragma once
#include <stdint.h>

#include "gfx.h"
#include "params.h"
#include "tuner.h"

class Hal;
class Mixer;
class Recorder;

// Encoders: channel ch (0..3), row r (0 = top, next to the display) -> ch * 3 + r; master = 12.
enum : uint8_t { E_MASTER = 12, E_COUNT = 13 };
// Buttons: 0..11 channel encoder pushes, then master push, Mute 1-4, AUX, FX I, FX II, SHIFT.
enum : uint8_t { B_MASTER = 12, B_MUTE1 = 13, B_AUX = 17, B_FX1 = 18, B_FX2 = 19, B_SHIFT = 20, B_COUNT = 21 };

constexpr int DISPLAY_W = 320, DISPLAY_H = 172;     // GMT147SPI landscape (DM18, DM25)
constexpr const char* FW_VERSION = "0.1";

class Ui {
public:
    void init(Hal* hal, Mixer* mixer, Scene* scene, Live* live, Settings* settings, Recorder* rec);
    void begin();                         // load settings + autosaved state, push gains to the codecs

    void encoder(int id, int delta);      // detents, + = clockwise
    void button(int id, bool down);
    void fader(int ch, float pos);        // 0..1, already filtered
    void midiIn(const uint8_t* msg, int n);
    void tick();                          // call from the main loop as often as possible
    void render(Canvas& c);

    // for the simulator panel
    bool layerAux() const { return auxLayer_; }
    bool layerFx(int k) const { return fxLayer_[k]; }
    bool held(int b) const { return down_[b]; }
    int rowParam(int ch, int row) const;

private:
    enum Page : uint8_t { HOME, MENU, TUNER };
    Scene& ed() { return settings_->ctrlMode ? shadow_ : *scene_; }
    int fxHeld() const;                   // -1 or 0/1 while FX I / FX II is held (edit mode)
    void changed();
    void setParam(int ch, int id, float v, bool fromMidi = false);
    void stepParam(int ch, int id, int delta);
    void sendCC(int ch, int id);
    void toast(const char* label, const char* value);
    void loadScene(int slot);
    void saveScene(int slot);
    void tap();
    void toggleRecord();
    // menu
    void menuTurn(int d);
    void menuPress();
    void menuItem(int i, char* label, char* value, int n);
    // drawing
    void drawHome(Canvas& c);
    void drawStrip(Canvas& c, int ch, int x);
    void drawMaster(Canvas& c, int x);
    void drawFx(Canvas& c, int k);
    void drawMenu(Canvas& c);
    void drawTuner(Canvas& c);
    void drawTop(Canvas& c, const char* title, uint16_t colr);
    void drawBar(Canvas& c, int x, int y, int w, int h, float norm, bool bipolar, uint16_t colr);
    void drawMeter(Canvas& c, int x, int y, int w, int h, float peak, float clip);

    Hal* hal_ = nullptr;
    Mixer* mix_ = nullptr;
    Scene* scene_ = nullptr;
    Scene shadow_;
    Live* live_ = nullptr;
    Settings* settings_ = nullptr;
    Recorder* rec_ = nullptr;

    Page page_ = HOME;
    bool down_[B_COUNT] = {};
    uint32_t downAt_[B_COUNT] = {};
    bool used_[B_COUNT] = {};             // a held button was used as a modifier
    bool auxLayer_ = false, fxLayer_[NFX] = {false, false};
    bool compRow_[NCH] = {};              // SHIFT layer, 3rd row: false = filter, true = compressor
    uint32_t encAt_[E_COUNT] = {};
    bool encSeen_[E_COUNT] = {};

    // menu
    int menuSel_ = 0, menuTop_ = 0, menuSlot_ = 1;
    bool menuEdit_ = false;
    int tunerCh_ = 0;
    TunerResult tuner_;
    uint32_t tunerAt_ = 0;

    // toast
    char toastL_[16] = {}, toastV_[16] = {};
    uint32_t toastUntil_ = 0;

    // persistence
    bool dirty_ = false, settingsDirty_ = false;
    uint32_t dirtyAt_ = 0;
    float sentGain_[NCH] = {99, 99, 99, 99};
    int sentBright_ = -1;

    // tempo
    uint32_t taps_[4] = {}, tapN_ = 0;
    uint32_t clockNextUs_ = 0;
    uint32_t extClockAt_ = 0, extTickUs_ = 0, extTicks_ = 0;
    float extTickAvg_ = 0;

    // MIDI CC sent last (controller mode), to avoid floods
    uint8_t lastCC_[5][128] = {};
};
