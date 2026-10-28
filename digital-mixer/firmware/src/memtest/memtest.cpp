// SPDX-License-Identifier: GPL-3.0-or-later
// Bench test of the memory chips under the Teensy 4.1 SD socket (pio run -e memtest -t upload, then open
// the serial port): PSRAM on the smaller pads (size detected by the core, write / read patterns over all of
// it) and NOR / NAND flash on the larger pads (LittleFS QSPI drivers: chip name and size).
#include <Arduino.h>
#include <LittleFS.h>

extern "C" uint8_t external_psram_size;

static bool psramTest() {
    const uint32_t bytes = (uint32_t)external_psram_size * 1048576u;
    volatile uint32_t* mem = (volatile uint32_t*)0x70000000;
    const uint32_t n = bytes / 4;
    const uint32_t patterns[] = {0x00000000, 0xFFFFFFFF, 0x55555555, 0xAAAAAAAA, 0x12345678};
    for (uint32_t pat : patterns) {
        uint32_t t0 = millis();
        for (uint32_t i = 0; i < n; i++) mem[i] = pat ^ i;                 // address-dependent: catches stuck address lines
        for (uint32_t i = 0; i < n; i++)
            if (mem[i] != (pat ^ i)) {
                Serial.printf("  FAIL pattern %08lX at offset %lu: read %08lX\n", (unsigned long)pat,
                              (unsigned long)(i * 4), (unsigned long)mem[i]);
                return false;
            }
        Serial.printf("  pattern %08lX ok (%lu ms)\n", (unsigned long)pat, (unsigned long)(millis() - t0));
    }
    return true;
}

static void runTests() {
    Serial.println("\n== Teensy 4.1 memory test ==");
    Serial.printf("PSRAM detected by the core: %u MB\n", external_psram_size);
    if (external_psram_size) Serial.println(psramTest() ? "PSRAM: OK" : "PSRAM: ERRORS");
    else Serial.println("PSRAM: none (a single chip must be on the SMALLER pads)");

    static LittleFS_QSPIFlash nor;
    static LittleFS_QPINAND nand;
    if (nor.begin()) {
        Serial.printf("NOR flash: %s, %llu bytes, used %llu\n", nor.getMediaName(),
                      (unsigned long long)nor.totalSize(), (unsigned long long)nor.usedSize());
    } else if (nand.begin()) {
        Serial.printf("NAND flash: %s, %llu bytes\n", nand.getMediaName(), (unsigned long long)nand.totalSize());
    } else {
        Serial.println("Flash on the larger pads: not found (or not a chip LittleFS knows)");
    }
    Serial.println("== done ==");
}

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 4000) {}
    runTests();
}

void loop() {                               // any character on the serial port runs the tests again
    if (Serial.available()) {
        while (Serial.available()) Serial.read();
        runTests();
    }
}
