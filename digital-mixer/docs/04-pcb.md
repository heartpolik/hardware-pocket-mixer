# 04. Друкована плата — ітерація 2 (компоновка C)

> [!NOTE]
> **Статус:** 27.10.2026. Одна двошарова плата **104,5 × 136,5 мм** (DM22, DM25), розведена:
> **DRC — 0 порушень, 0 нез'єднаних, 0 розбіжностей зі схемою**. Попередження — лише шовкографія
> (накладання підписів) і напрямні отвори під деталями іншого боку (п. 2). Gerber і BOM ще не робили.

![3D](mech/pcb-3d.png)

## 1. Як згенеровано

```mermaid
flowchart LR
    SCH["hw/sch/main.py<br/>(common/kisch.py)"] --> S1["main.kicad_sch<br/>ERC 0"]
    LIB["hw/lib/gen_footprints.py<br/>за кресленнями"] --> FP[("pocket-digital.pretty")]
    G3["hw/lib/gen_3d.py<br/>CadQuery"] --> M3[("pocket-digital.3dshapes")]
    S1 --> B["hw/pcb/build_pcb.py<br/>розстановка (layout.py)"]
    FP --> B
    M3 --> B
    B --> P1["main.kicad_pcb"]
    P1 --> R["common/route_pcb.py<br/>Freerouting, 2 шари"]
    R --> F["common/fix_pcb.py<br/>заливки GND, зшивка"]
    F --> P2["main_routed.kicad_pcb"]
    P2 -->|"common/patch_route.py<br/>common/rip_near.py"| P2
```

```sh
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3
python3 hw/lib/gen_symbols.py && python3 hw/lib/gen_footprints.py && python3 hw/sch/main.py
../.venv-cq/bin/python hw/lib/gen_3d.py      # 3D-моделі (common/README.md — встановлення CadQuery)
$PY hw/pcb/build_pcb.py                      # -> hw/main/main.kicad_pcb
$PY ../common/route_pcb.py hw/main/main.kicad_pcb --layers 2 --edge 0.6 --passes 60 \
    --hole-keep 0.25 --hole-skip USB_C_Receptacle_GCT_USB4110       # ~20 хв -> main_routed.kicad_pcb
$PY ../common/patch_route.py hw/main/main_routed.kicad_pcb NET xa ya xb yb [--width 0.15]
$PY ../common/rip_near.py hw/main/main_routed.kicad_pcb NET x y [--radius R]   # зняти шматок кола
$PY ../common/fix_pcb.py hw/main/main_routed.kicad_pcb --edge-keep 0.8          # перезалити, зшити
```

Інструменти спільні з Rev A — [common/](../../common/README.md).

## 2. Розстановка (DM25)

![Низ](mech/pcb-bottom.png)

*Вид знизу (дзеркально): праворуч на рисунку — лівий край плати.*

- **Згори:** ON, дисплей (альбомно, гребінка між IN1 і IN2), MASTER — на одній осі; 12 енкодерів
  EC12SY, 4 фейдери, Mute — колонками на осях джеків; AUX, FX I, FX II, SHIFT — у правій колонці.
- **Знизу:** джеки IN1–4 на задньому торці; USB-C (USB4110, SMD) під MASTER; MAIN / AUX / MIDI /
  PHONES на правому торці; Teensy у передньому правому куті (microSD у передню стінку); живлення
  (заряд, TPS63802, ESD) біля USB-C; три ЦАП і TPA6132A2 між вихідними джеками й Teensy; два АЦП
  під фейдерами між їхніми виводами; три MCP23017 під Mute (розвернуті: I²C і GPB — усередину);
  зона акумулятора 60 × 50 під енкодерами — порожня.
- **Блок TPS63802** — за прикладом TI (SLVSEU9D, п. 10.2), доріжки блоку зафіксовані; BB_L1 / BB_L2
  по 4,2 мм без переходів.
- **TPA6132A2:** конденсатори живлення й накачки — біля виводів (поле `Decouples`); мікросхема
  розвернута на 180°, щоб виходи OUTL / OUTR дивились на джек PHONES і не перетинали живлення.
- **Отвори M2** — у чотирьох кутах. Контур енкодера хрестоподібний (за площадками), тож отвір біля
  MASTER і ON стає в кут.
- **Попередження `npth_inside_courtyard`** (8): напрямні джеків SJ-43514 під дисплеєм / кнопками і
  напрямні USB4110 під MASTER. За кресленнями вони виходять під корпусом на 0,8 / 0,63 мм і плату
  1,6 мм не проходять — деталям згори не заважають.

## 3. Правила й обмеження

| Що | Значення | Чому |
|---|---|---|
| Доріжки сигналів / живлення | 0,15 / 0,5 мм | 2 шари навколо TSSOP / WQFN з кроком 0,5 мм |
| Зазор | 0,15 мм | як Rev A |
| Мідь — неметалізовані отвори | 0,25 мм заборонними зонами `hole clearance` | мінімум плати знижено до 0,15 лише заради отворів USB4110 (0,175 від власних площадок за кресленням GCT); правила `.kicad_dru` для цього kicad-cli 10 не застосував |
| Тепловий бар'єр | 1 спиця досить | як Rev A (D12); `starved_thermal` — попередження |

## 4. Результат розводки

| Параметр | Значення |
|---|---|
| Доріжки / переходи | 3345 сегментів, 12,2 м; 834 переходи (з них 457 — GND, зшивка) |
| Такти АЦП (BCK / LRCK / MCLK) | 60–73 мм, 2–4 переходи, через 33 Ω біля Teensy (DM29); було ≈ 110 мм |
| Такти ЦАП (BCK / LRCK) | 63–66 мм, 4–5 переходів, через 33 Ω |
| Вхід → АЦП | джек → RC: до 87 мм; RC → АЦП: 6–22 мм |
| USB-C → USBLC6 | 14–17 мм |
| USBLC6 → Teensy (D+ / D−) | **84 / 100 мм**, 1 / 3 переходи — див. п. 5 |
| SPI дисплея (SCK) | 150 мм |

## 5. Що покращити до замовлення

1. **USB D+ / D− до Teensy — 84 / 100 мм, різниця 17 мм, не диференційною парою.** Для 480 Мбіт/с
   краще вести пару поруч, однакової довжини, без зайвих переходів: розвести її вручну (USB-C ззаду, а
   USB-площадки Teensy — на його задньому кінці, відстань по прямій ≈ 70 мм).
2. **Шовкографія:** прибрати накладання підписів (косметика).
3. **Звірити на зразках:** отвори напрямних EC12SY, ніжки кнопки живлення, гребінку й отвори
   GMT147SPI, положення USB-площадок під Teensy (вікно 1,5–5,5 мм від торця).
4. **Gerber, BOM** — після п. 1–3; наявність у LCSC — [03](03-schematic.md), п. 5.
