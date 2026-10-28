// Minimal PNG writer (RGB8, zlib) for screenshots.
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <zlib.h>

#include <vector>

inline bool writePng(const char* path, const uint16_t* rgb565, int w, int h) {
    std::vector<uint8_t> raw;
    raw.reserve((size_t)(w * 3 + 1) * h);
    for (int y = 0; y < h; y++) {
        raw.push_back(0);
        for (int x = 0; x < w; x++) {
            uint16_t p = rgb565[y * w + x];
            uint8_t r = (p >> 11) & 31, g = (p >> 5) & 63, b = p & 31;
            raw.push_back((uint8_t)(r << 3 | r >> 2));
            raw.push_back((uint8_t)(g << 2 | g >> 4));
            raw.push_back((uint8_t)(b << 3 | b >> 2));
        }
    }
    uLongf zn = compressBound((uLong)raw.size());
    std::vector<uint8_t> z(zn);
    if (compress2(z.data(), &zn, raw.data(), (uLong)raw.size(), 9) != Z_OK) return false;
    z.resize(zn);
    static uint32_t table[256];
    if (!table[1])
        for (uint32_t n = 0; n < 256; n++) {
            uint32_t c = n;
            for (int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            table[n] = c;
        }
    FILE* f = fopen(path, "wb");
    if (!f) return false;
    auto chunk = [&](const char* type, const std::vector<uint8_t>& d) {
        uint32_t n = (uint32_t)d.size();
        uint8_t len[4] = {(uint8_t)(n >> 24), (uint8_t)(n >> 16), (uint8_t)(n >> 8), (uint8_t)n};
        fwrite(len, 1, 4, f);
        uint32_t c = 0xFFFFFFFFu;
        auto upd = [&](const uint8_t* p, size_t m) { for (size_t i = 0; i < m; i++) c = table[(c ^ p[i]) & 255] ^ (c >> 8); };
        fwrite(type, 1, 4, f); upd((const uint8_t*)type, 4);
        if (n) { fwrite(d.data(), 1, n, f); upd(d.data(), n); }
        c = ~c;
        uint8_t cc[4] = {(uint8_t)(c >> 24), (uint8_t)(c >> 16), (uint8_t)(c >> 8), (uint8_t)c};
        fwrite(cc, 1, 4, f);
    };
    static const uint8_t sig[8] = {0x89, 'P', 'N', 'G', 13, 10, 26, 10};
    fwrite(sig, 1, 8, f);
    std::vector<uint8_t> ihdr = {(uint8_t)(w >> 24), (uint8_t)(w >> 16), (uint8_t)(w >> 8), (uint8_t)w,
                                 (uint8_t)(h >> 24), (uint8_t)(h >> 16), (uint8_t)(h >> 8), (uint8_t)h,
                                 8, 2, 0, 0, 0};
    chunk("IHDR", ihdr);
    chunk("IDAT", z);
    chunk("IEND", {});
    fclose(f);
    return true;
}
