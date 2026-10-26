# Бібліотека KiCad

Власні футпринти генерує [gen_footprints.py](gen_footprints.py) з розмірів креслень у
[docs/datasheets](../../docs/datasheets/README.md); джерело вказано в `descr` кожного футпринта.
Перегенерувати: `python3 hw/lib/gen_footprints.py`. Перевірка: `kicad-cli fp export svg` читає всі файли.

## Власні футпринти (`diy-mixer.pretty`)

| Футпринт | Компонент | Джерело | Що лишається звірити |
|---|---|---|---|
| `Alps_RS451121400A_Fader_Dual_45mm` | фейдери ×7 | Alps RS 2026, кресл. 20; координати pad — mixerli v2.0.1 (виготовлялась) | — |
| `Alps_RK14K12D_Vertical_Volume` | send ×4, навушники | Alps RK14K с. 326 (кресл. 1), виводи с. 327 «Without tap for volume» | — |
| `Alps_RK14K124_Vertical_Tone` | pan ×4 (RK14K124003H) | те саме, виводи «For tone (15C)»: **окремі землі секцій** | — |
| `CTS_204-125ST_DIP_SPDT_5pos_SMD` | моно/стерео | CTS 204 rev D, рис. 2, 4 | **призначення 4 pad кожного перемикача (SPDT) у datasheet не підписане — перевірити продзвонкою**; нумерація позиційна |
| `ESP32-C3_SuperMini_2x8_P2.54` | MCU | datasheet SuperMini: ряди 15,24, плата 18 × 22,52 | зсув гребінки вздовж плати не задано — контур `ОРІЄНТИР` |
| `OLED_0.96in_128x64_I2C_4pin` | OLED | креслення Rajguru | звірити з купленим модулем |
| `CP_Nichicon_UEP_D5.0_L11.0_P2.00_Horizontal` | вхідні 10 µF (D44) | Nichicon UEP | — |
| `CP_Nichicon_UEP_D6.3_L11.0_P2.50_Horizontal` | вихідні 47 µF | Nichicon UEP | — |
| `CUI_SJ-43514-SMT_TRRS_Horizontal` | усі джеки (D50) | те саме креслення CUI, без площадок 5/6 | — |
| `L_Sumida_CLS62` | дросель −12 V | Sumida CLS62: land pattern, схема виводів (вид знизу) | фазування з LT1931 |
| `Alps_EC12D_Switch` | енкодер | Alps EC12D, кресл. 5 | ряди A/B/C ±4,15 — з симетрії, звірити з деталлю |
| `SW_Slide_SPDT_SHOUHAN_MSK12C02_RightAngle` | вимикач живлення (D51) | креслення MSK12C02 (2024-12-14): посадкове місце й вид зверху | спільний вивід 2 — за схемою контактів, перевірити продзвонкою; край плати — лінія Dwgs.User |
| `MountingHole_2.2mm_M2_Pad_Standoff_2Side` | отвори кріплення H1–H4 (D57) | KiCad `MountingHole_2.2mm_M2_Pad` (свердло 2,2, площадка 4,4) | courtyard r 2,45 з обох боків: друкована стійка Ø ≤ 4,8, гайка M2 (4 мм) або головка гвинта |

## Стандартні футпринти KiCad 10 — звірка з datasheet

| Футпринт KiCad | Компонент | Звірка |
|---|---|---|
| `Inductor_SMD:L_Bourns-SRN4018` | SRN4018-4R7M | pad 1,5 × 3,6 при ±1,525; у тексті «Recommended Layout» Bourns є 3,6 і 1,5, але креслення в PDF не рендериться — проміжок між pad не звірено ⚠️ |
| `Package_TO_SOT_SMD:SOT-583-8` | TPS62933O | посилання на datasheet TI у descr; розміри pad ще не звіряв |
| `LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount` | RGB LED | розташування = вид знизу OPSCO (стандартні символ і футпринт узгоджені: 1 VSS, 2 DIN, 3 VDD, 4 DOUT); pad коротші за OPSCO заради зазору до вирізу 3,4 × 3,0 ✅ |
| `Button_Switch_Keyboard:SW_Cherry_MX_1.00u_PCB` | Mute ×6 | у datasheet MX2A креслення немає; footprint за каталогом Cherry MX (посилання в descr) |
| `Connector_USB:USB_C_Receptacle_GCT_USB4085` | USB-C (повністю THT, USB 2.0) | кроки 0,85 / 1,35, пази корпусу 8,65 × 3,38 збігаються з GCT ✅; лінія «PCB Edge» на y 6,1 |
| `Package_SO:SOIC-16_3.9x9.9mm_P1.27mm` | DG413 ×6 | стандартний SOIC |
| `Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm` | MCP23017 | стандартний |
| `Package_SO:SOIC-14_3.9x8.7mm_P1.27mm` | TL064 ×6 | стандартний |
| `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` | OPA1678 ×12, CH340N | стандартний |
| `Package_SO:TSSOP-16_4.4x5mm_P0.65mm` | ADS7828 | стандартний |
| `Package_TO_SOT_SMD:SOT-23-5` | LT1930, LT1931, 74AHCT1G125 | стандартний |
| `Package_TO_SOT_SMD:SOT-23` | AO3401A (1 G, 2 S, 3 D — збігається з datasheet AOS) | стандартний ✅ |
| `Diode_SMD:D_SOD-123` | MBR0530, 1N4148W | стандартний |

## Ще не зроблено

- Футпринт вимикача живлення — модель не обрана.
