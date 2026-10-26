# 03. Принципова схема і макет розташування

> [!NOTE]
> **Статус:** 26.10.2026, перша версія. Схема — `hw/main/main.kicad_sch` (PDF: [hw/main/main.pdf](../hw/main/main.pdf)),
> генерує `python3 hw/sch/main.py` (з теки `digital-mixer/`). **ERC: 0 помилок**; 15 попереджень —
> footprint, яких ще немає (Teensy 4.1 SMD, TPS63802 VSON-HR-10, дросель XFL4015, кнопки TSF-1266,
> кнопка живлення 7 × 7, дисплей GMT147SPI — робимо на кроці плати за кресленнями / зразками).
> Оновлено за DM16–DM18: дисплей замість OLED, тактові кнопки, без адресних LED.

## 1. Структура

```mermaid
flowchart LR
    subgraph PWR["Живлення (DM11)"]
        USB(["USB-C"]) --> CHG["TP4056<br/>0,5 A"] --> BAT[("LiPo 1S")]
        USB --> LS["MBR0530 + AO3401A<br/>load sharing"]
        BAT --> LS --> BB["TPS63802<br/>+4V2"]
        BB --> LDO["LP5907<br/>+3V3A"]
    end
    subgraph AUD["Аудіо"]
        IN(["IN1–IN4"]) --> RC["10k + 10 µF"] --> ADC["PCM1865 ×2"]
        DAC1["PCM5102A MAIN"] --> OM(["MAIN"])
        DAC2["PCM5102A AUX"] --> OA(["AUX"])
        DAC3["PCM5102A CUE"] --> HP["TPA6132A2"] --> OP(["PHONES"])
    end
    T["Teensy 4.1"]
    ADC -->|"SAI2 TDM"| T
    T -->|"SAI1 I²S ×3"| DAC1 & DAC2 & DAC3
    USB <-->|"USBLC6, D+/D−"| T
    T <-->|"I²C2"| MCP["MCP23017 ×2<br/>12 енкодерів, 4 Mute,<br/>FX I, FX II, AUX, CUE"]
    T -->|"SPI"| LCD["GMT147SPI<br/>1,47″ 172×320"]
    T -->|"I²C"| ADC
    FAD["Фейдери ×4"] -->|"A0–A3"| T
    BB --> T
    LDO --> ADC & DAC1 & DAC2 & DAC3
```

## 2. Виводи Teensy 4.1

Номери — за символом [XenGi/teensy_library](https://github.com/XenGi/teensy_library) (MIT, копія в
`hw/lib/third_party/`). Звірити з карткою PJRC перед footprint.

| Функція | Виводи Teensy | Куди |
|---|---|---|
| SAI1, I²S → ЦАП | 21 BCLK1, 20 LRCLK1, 7 OUT1A, 32 OUT1B, 9 OUT1C | PCM5102A MAIN, AUX, CUE (`AudioOutputI2SHex`) |
| SAI2, TDM ← АЦП | 4 BCLK2, 3 LRCLK2, 5 IN2, 33 MCLK2 | 2 × PCM1865, слоти 1–4 і 5–8 |
| I²C (Wire) | 18 SDA, 19 SCL | PCM1865 0x94 / 0x96 |
| I²C2 (Wire2) | 25 SDA2, 24 SCL2 | MCP23017 0x20 / 0x21 |
| INT розширювачів | 30, 31 | MCP23017 #1, #2 |
| Фейдери | 14–17 (A0–A3) | PTA2043, 100 nF на повзунку |
| Батарея | 38 (A14) | VSYS / 2 |
| Майстер-енкодер | 0 A, 1 B, 2 кнопка | EC11 з кнопкою |
| Дисплей (SPI) | 13 SCK, 11 MOSI, 10 CS, 40 DC, 41 RES, 28 BLK (ШІМ — `ПЕРЕВІРИТИ`) | GMT147SPI |
| Кнопки | 29 SHIFT; FX I, FX II, AUX, CUE — на вільних GPA7 / GPB7 обох MCP23017 | TSF-1266 |
| MIDI OUT | 35 (Serial8 TX) | джек TRS Type A |
| Керування | 36 XSMT (м'ют ЦАП), 37 EN навушників | 10k на GND — тиша до старту прошивки |
| Живлення | VIN = +4V2, VUSB = VBUS, 3V3 — вихід на цифру | **перемичку VIN–VUSB розрізати** |
| USB | площадки D+ / D− знизу (66 / 67 символу) | USB-C через USBLC6 |

`ПЕРЕВІРИТИ` на макеті: SAI1 (I²S, 64 fs) і SAI2 (TDM, 256 fs) одночасно в бібліотеці Teensy Audio;
обидва порти тактуються від одного аудіо-PLL.

## 3. Вузли — звідки значення

| Вузол | Що на схемі | Джерело |
|---|---|---|
| PCM1865 | I²C (MD0 = GND), адреса MS/AD; VREF 1 µF; AVDD, DVDD, LDO — 0,1 + 10 µF; XI на GND, SCKI = MCLK2; DOUT обох через 33 Ω на одну лінію (поза своїми слотами Hi-Z) | [datasheet](datasheets/pcm1865.pdf), табл. виводів с. 11, TDM с. 58–59, рис. 66 |
| Вхід | джек → 100k на GND → 10k послідовно (з 10 kΩ входу — −6 dB, вхід до +14,6 dBu) → 10 µF електроліт (+ до мікросхеми) | с. 13 (вхідний опір 10 kΩ), [ТЗ](01-spec.md) |
| PCM5102A | SCK = GND (PLL від BCK), FMT / FLT / DEMP = GND; CAPP–CAPM і VNEG 2,2 µF; LDOO 0,1 + 10 µF; вихід 470 Ω + 2,2 nF | [datasheet](datasheets/pcm5102a.pdf), рис. 33 |
| TPA6132A2 | несиметричний вхід 1 µF на IN−, IN+ на GND; G0 = G1 = GND → −6 dB (2,1 Vrms ЦАП → ≈ 1 Vrms); VDD і HPVDD 2,2 µF, HPVSS і накачка 1 µF | [datasheet](datasheets/tpa6132a2.pdf), рис. 27, табл. підсилення |
| TPS63802 | 665k / 91k → 4,15 V; L 0,47 µH XFL4015-471ME; 10 µF вх., 2 × 22 µF вих.; MODE = GND (енергозбереження); EN — з вимикача MSK12C02 + 100k на GND | [datasheet](datasheets/tps63802.pdf), табл. 10-2, 10-5, розд. 10.2.2 |
| TP4056 | R_PROG 2,4k → 500 mA; TEMP на GND; CHRG / STDBY — червоний / зелений LED від VBUS | [datasheet](datasheets/tp4056.pdf) |
| Кнопки | TSF-1266, 6 × 6 × 5 мм SMT, на GND, внутрішні підтяжки MCP23017 / Teensy | [оголошення](https://parts4laptops.eu/en/microbuttons/3291-microbutton-tact-switch-tsf-1266-6x6x5mm-smt-mounting.html); креслення — `ПЕРЕВІРИТИ` |
| Живлення | кнопка з фіксацією 7 × 7, DPDT: одна група — EN = VSYS / GND, друга вільна; струм лише EN | рейтинги в продавців 50–100 mA ([Swiclick](https://www.swiclick.com/product/dpdt-77mm-self-locking-tactile-pushbutton-switch/)) |
| MIDI OUT | TRS Type A: кінчик = DIN 5 через 10 Ω від TX, кільце = DIN 4 через 33 Ω від +3,3 V, гільза = GND; для 3,3 V — 33 Ω 0,5 W і 10 Ω 0,25 W | [MIDI 1.0 Electrical Spec Update](datasheets/midi-electrical-spec-update.pdf), рис. 1; розводка TRS — [MIDI Association](https://midi.org/specification-for-use-of-trs-connectors-with-midi-devices) |
| Дисплей | GMT147SPI: ST7789, SPI, живлення 3,3 V від Teensy; порядок 8 виводів — як у DFR0995, `ПЕРЕВІРИТИ` на зразку | [DFRobot](https://wiki.dfrobot.com/dfr0995/), [jence](https://jence.com/index.php?route=product%2Fproduct&product_id=1303) |

## 4. Макет розташування

![Макет](mech/layout.svg)

Ескіз — `docs/mech/layout.py`, розміри з footprint і креслень (не розстановка).

- **Згори** — лише керування: 4 смуги по 18 мм: 3 енкодери EC11, фейдер 35 мм і під ним Mute
  (TSF-1266) біля переднього краю; між рядами 4 мм для пальців (DM19). Праворуч вертикальний дисплей 21 × 44 мм, майстер-енкодер, кнопки FX I, FX II, AUX,
  CUE, SHIFT і кнопка живлення 7 × 7 поруч з ними.
- **Знизу (компоновка A, DM24)** — 7 джеків (IN1–4, MAIN, AUX, MIDI OUT) у смузі ≈ 19 мм уздовж заднього
  краю з кроком 14 мм: виводи енкодерів і фейдерів проходять крізь плату, тому під ними джеків немає.
  PHONES — на передньому торці, як у Rev A,
  Teensy 4.1 уздовж переднього краю під кнопками Mute, microSD — у лівий торець (DM12); USB-C на правому
  торці; кодеки, живлення, MCP23017 — під правою колонкою (там згори лише SMD-кнопки й дисплей);
  акумулятор 3000 mAh — під каналами, на прокладці над виводами.
- **Розмір — ≈ 114 × 128 мм**: смуга джеків + 3 енкодери + фейдер + кнопка + смуга Teensy, поля 6 мм
  під отвори M2 у кутах. Скоротити: 2 енкодери на канал (−18 мм) — `ВІДКРИТО`.
- Висота (`ОЦІНКА`): знизу джеки ~5 мм і акумулятор ~8 мм, згори — фейдер і EC11 з валом; кнопки
  5 мм і дисплей 2,8 мм нижчі — корпус ≈ 25 мм.

## 5. Що далі

1. Footprint: Teensy 4.1 SMD (креслення PJRC), TPS63802 VSON-HR-10, XFL4015 — за кресленнями
   виробників; TSF-1266, кнопка 7 × 7 і GMT147SPI — за кресленням продавця або виміром зразків.
2. Наявність у LCSC: TPS63802, TPA6132A2, PCM1865 / PCM5102A, тактові кнопки 6 × 6.
3. Розстановка й розведення 4-шарової плати.
