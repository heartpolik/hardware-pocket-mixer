# Datasheets — цифровий мікшер

Datasheets, на які посилається документація цифрового підпроєкту. Спільні з аналоговим —
у [analog-mixer/docs/datasheets](../../../analog-mixer/docs/datasheets/README.md).

| Файл | Компонент | Де використано | Джерело |
|---|---|---|---|
| [pcm1865.pdf](pcm1865.pdf) | TI PCM186x, SLAS831D, АЦП 4 канали, TSSOP-30 | АЦП входів ([00](../00-research.md), п. 5) | ti.com |
| [pcm5102a.pdf](pcm5102a.pdf) | TI PCM510xA, ЦАП стерео 2,1 Vrms, TSSOP-20 | ЦАП виходів ([00](../00-research.md), п. 5) | ti.com |
| [tps63802.pdf](tps63802.pdf) | TI TPS63802, buck-boost 2 A, VSON-10 | живлення 1S ([02](../02-components.md), п. 4) | ti.com |
| [lp5907.pdf](lp5907.pdf) | TI LP5907, LDO 250 mA, малошумний | 3,3 V аналог кодеків ([02](../02-components.md), п. 4) | ti.com |
| [tp4056.pdf](tp4056.pdf) | NanJing Top Power TP4056, лінійний заряд 1S 1 A | заряд ([02](../02-components.md), п. 4) | sparkfun.com |
| [bourns-pec09.pdf](bourns-pec09.pdf) | Bourns PEC09, енкодер 9 мм, rev. 09/19 | порівняння енкодерів ([02](../02-components.md), п. 3) | bourns.com |
| [tpa6132a2.pdf](tpa6132a2.pdf) | TI TPA6132A2, підсилювач навушників DirectPath, WQFN-16 | навушники ([03](../03-schematic.md)) | ti.com |
| [kailh-choc-pg1350.pdf](kailh-choc-pg1350.pdf) | Kailh PG1350 (CPG135001D01), креслення й характеристики | розглянуто (DM13, скасовано DM16) | adafruit.com (копія Kailh) |
| [midi-electrical-spec-update.pdf](midi-electrical-spec-update.pdf) | MMA CA-033, MIDI 1.0 Electrical Specification Update (2014) | MIDI OUT 3,3 V ([03](../03-schematic.md)) | midi.org |
| [gmt147-01m-drawing.webp](gmt147-01m-drawing.webp) | GMT147-01M (GMT147SPI) 1.47in TFT, креслення продавця: розміри, гребінка 8 × 2,54, отвори | footprint `LCD_GMT147SPI` | від користувача (продавець) |
| [tsf-1266-drawing.png](tsf-1266-drawing.png) | TSF-1266 6 × 6 × 5 SMT tact, креслення й посадкове місце | footprint `SW_TSF-1266_6x6mm_SMD` | від користувача (продавець) |
| [push-latching-dpdt-5.8-7mm-drawing.png](push-latching-dpdt-5.8-7mm-drawing.png), [push-latching-dpdt-7mm-pins.png](push-latching-dpdt-7mm-pins.png) | кнопка з фіксацією DPDT 5,8 / 7 мм, креслення й схема контактів | footprint `SW_Push_Latching_DPDT_7x7mm` | від користувача (продавець) |
| [teensy41-dimensions.png](teensy41-dimensions.png), [teensy41-card-back.png](teensy41-card-back.png) | PJRC Teensy 4.1: розміри, картка виводів (зворот) | footprint `Teensy41_SMD` | pjrc.com |
| [coilcraft-xfl4015.pdf](coilcraft-xfl4015.pdf) | Coilcraft XFL4015, Doc 769, rev. 03/10/26 | дросель TPS63802 | coilcraft.com |
