// SPDX-License-Identifier: GPL-3.0-or-later
#include "gfx.h"

#include <stdlib.h>
#include <string.h>

#include "font5x7.h"

void Canvas::fill(int x, int y, int w, int h, uint16_t c) {
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > w_) w = w_ - x;
    if (y + h > h_) h = h_ - y;
    if (w <= 0 || h <= 0) return;
    for (int j = 0; j < h; j++) {
        uint16_t* p = buf_ + (y + j) * w_ + x;
        for (int i = 0; i < w; i++) p[i] = c;
    }
}

void Canvas::rect(int x, int y, int w, int h, uint16_t c) {
    hline(x, y, w, c);
    hline(x, y + h - 1, w, c);
    vline(x, y, h, c);
    vline(x + w - 1, y, h, c);
}

void Canvas::line(int x0, int y0, int x1, int y1, uint16_t c) {
    int dx = abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
    int dy = -abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
    int err = dx + dy;
    for (;;) {
        pixel(x0, y0, c);
        if (x0 == x1 && y0 == y1) break;
        int e2 = 2 * err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}

void Canvas::circle(int cx, int cy, int r, uint16_t c, bool filled) {
    for (int y = -r; y <= r; y++)
        for (int x = -r; x <= r; x++) {
            int d = x * x + y * y;
            if (d <= r * r && (filled || d >= (r - 1) * (r - 1))) pixel(cx + x, cy + y, c);
        }
}

static int glyphIndex(char ch) {
    unsigned char u = (unsigned char)ch;
    if (u >= 'a' && u <= 'z') u -= 32;          // the font is upper case only
    if (u < 32 || u > 95) u = '?';
    return u - 32;
}

int Canvas::text(int x, int y, const char* s, uint16_t c, int scale) {
    for (; *s; s++) {
        const uint8_t* g = FONT5X7[glyphIndex(*s)];
        for (int col = 0; col < 5; col++)
            for (int row = 0; row < 7; row++)
                if (g[col] >> row & 1) fill(x + col * scale, y + row * scale, scale, scale, c);
        x += 6 * scale;
    }
    return x;
}

int Canvas::textWidth(const char* s, int scale) {
    int n = (int)strlen(s);
    return n ? (6 * n - 1) * scale : 0;
}
