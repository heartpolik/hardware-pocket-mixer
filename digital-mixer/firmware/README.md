# firmware — прошивка цифрового мікшера

Опис, керування, MIDI і що перевірити на залізі — [docs/06-firmware.md](../docs/06-firmware.md).

```sh
make sim test                          # емулятор (потрібен SDL2: brew install sdl2) і перевірки ядра
./build/pocket-mixer-sim               # вікно з дисплеєм і панеллю, звук у колонки
./build/pocket-mixer-sim --headless --script sim/scripts/demo.txt --data build/demo-data
pio run                                # Teensy 4.1 (PlatformIO); pio run -t upload — залити
```

| Тека | Що |
|---|---|
| `src/core/` | спільне ядро: мікс, ефекти, інтерфейс, дисплей, сцени, MIDI, рекордер, тюнер |
| `src/teensy/` | Teensy 4.1: граф Teensy Audio, PCM1865, MCP23017, ST7789, EEPROM, microSD |
| `sim/` | емулятор на SDL2, демо-джерела, сценарії |
| `tests/` | перевірки ядра без заліза |
| `tools/gen_font.py` | шрифт 5 × 7 → `src/core/font5x7.h` |
