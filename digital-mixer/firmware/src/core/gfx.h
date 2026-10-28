// RGB565 canvas with the primitives the UI needs: rectangles, lines, 5x7 text at integer scale.
#pragma once
#include <stdint.h>

inline constexpr uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) {
    return (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

namespace col {
constexpr uint16_t BLACK = rgb(0, 0, 0), WHITE = rgb(255, 255, 255), GREY = rgb(90, 90, 90),
                   DARK = rgb(35, 35, 40), DIM = rgb(150, 150, 150), RED = rgb(240, 50, 40),
                   ORANGE = rgb(255, 140, 0), YELLOW = rgb(255, 215, 0), GREEN = rgb(60, 220, 90),
                   CYAN = rgb(0, 200, 230), BLUE = rgb(60, 110, 255), MAGENTA = rgb(220, 70, 220);
}

class Canvas {
public:
    Canvas(uint16_t* buf, int w, int h) : buf_(buf), w_(w), h_(h) {}
    int width() const { return w_; }
    int height() const { return h_; }
    uint16_t* data() { return buf_; }
    const uint16_t* data() const { return buf_; }

    void clear(uint16_t c) { fill(0, 0, w_, h_, c); }
    void pixel(int x, int y, uint16_t c) {
        if ((unsigned)x < (unsigned)w_ && (unsigned)y < (unsigned)h_) buf_[y * w_ + x] = c;
    }
    void fill(int x, int y, int w, int h, uint16_t c);
    void rect(int x, int y, int w, int h, uint16_t c);           // outline
    void hline(int x, int y, int w, uint16_t c) { fill(x, y, w, 1, c); }
    void vline(int x, int y, int h, uint16_t c) { fill(x, y, 1, h, c); }
    void line(int x0, int y0, int x1, int y1, uint16_t c);
    void circle(int cx, int cy, int r, uint16_t c, bool filled);

    // Text: 5x7 font in a 6x8 cell times `scale`. Returns the x after the last char.
    int text(int x, int y, const char* s, uint16_t c, int scale = 1);
    static int textWidth(const char* s, int scale = 1);
    int textCentered(int cx, int y, const char* s, uint16_t c, int scale = 1) {
        return text(cx - textWidth(s, scale) / 2, y, s, c, scale);
    }
    int textRight(int rx, int y, const char* s, uint16_t c, int scale = 1) {
        return text(rx - textWidth(s, scale), y, s, c, scale);
    }

private:
    uint16_t* buf_;
    int w_, h_;
};
