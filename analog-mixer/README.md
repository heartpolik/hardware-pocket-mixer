# analog-mixer — Rev A

Портативний аналоговий стереомікшер Rev A: 4 стереоканали з pan і FX-петлею
(send/return), Master L/R, вихід на навушники, OLED-метри та Mute/Solo через ESP32-C3,
живлення від 2S LiPo з USB-C.

> [!WARNING]
> Стан: крок E — схеми (ERC чистий) і обидві плати розведено, DRC без розривів і порушень міді;
> Gerber, свердління й BOM — у `hw/fab/` ([14-kicad.md](docs/14-kicad.md), п. 6). Плати ще не
> замовлені й не перевірені в залізі. Команди з документації запускати з теки `analog-mixer/`.

![Компоновка v3](docs/mech/layout-v3.svg)

## Архітектура

```mermaid
flowchart TB
    subgraph DIG["Цифрова плата (верхня, над задніми джеками)"]
        ESP["ESP32-C3 SuperMini<br/>радіо вимкнене"]
        OLED["OLED 128×64<br/>метри, Mute/CLIP Master"]
        ENC["Енкодер"]
        LED["RGB LED ×5"]
        ADC[("АЦП метрів")]
    end
    subgraph ANA["Аналогова плата (нижня)"]
        IN(["IN1–4, RET<br/>задній торець"])
        CTRL["Фейдери ×7, send ×4,<br/>pan ×4, PHONES"]
        AUD["Буфери, суматори,<br/>ключі DG413"]
        MX["Cherry MX ×6<br/>Mute"]
        PWR["2S LiPo → ±12 V, 5 V"]
        OUT(["MAIN, SEND, PHONES"])
    end
    USB(["USB-C<br/>правий торець"]) --> PWR
    USB -.->|"дані: CH340N → UART"| ESP
    IN --> AUD --> OUT
    CTRL --> AUD
    ESP <-->|"I²C-A"| AUD
    MX --> ESP
    AUD -.->|"DC метрів"| ADC --> ESP
    PWR -->|"5 V"| DIG
    ESP --> OLED & LED
    ENC --> ESP
```

## Хід роботи

```mermaid
flowchart LR
    S0["0. Аналоги"]:::done --> SA["A. Фейдери"]:::done --> SB["B. Механіка"]:::done --> SC["C. Схема"]:::done --> SD["D. Pinout між платами"]:::done --> SE["E. KiCad"]:::now
    classDef done fill:#d4edda,stroke:#2a6
    classDef now fill:#ffe9b3,stroke:#b8860b
```

## Документація

| Документ | Зміст |
|---|---|
| [spec-rev-a.md](docs/spec-rev-a.md) | ТЗ |
| [decisions.md](docs/decisions.md) | Журнал рішень D1–D50, має пріоритет над ТЗ |
| [00-prior-art.md](docs/00-prior-art.md) | Аналоги та схожі проєкти |
| [01-faders.md](docs/01-faders.md) | Фейдери Alps RS45 |
| [02-mixerli-analysis.md](docs/02-mixerli-analysis.md) | Розбір mixerli v2.0.1 |
| [03-power-2s.md](docs/03-power-2s.md) | Живлення 2S |
| [04-mixerli-datasheets.md](docs/04-mixerli-datasheets.md) | Висновки з datasheets mixerli |
| [05-mechanics.md](docs/05-mechanics.md) | Механіка, компоновка, висоти |
| [06-signal-flow.md](docs/06-signal-flow.md) | Signal flow, Mute/Solo, метри, керування |
| [07-gain-structure.md](docs/07-gain-structure.md) | Рівні по тракту, запас, шум, вибір op-amp |
| [08-meter-detector.md](docs/08-meter-detector.md) | Детектор метрів і CLIP |
| [09-sourcing.md](docs/09-sourcing.md) | Наявність і ціни ключових компонентів |
| [10-passives.md](docs/10-passives.md) | Пасивні компоненти: правила, перелік, кількості |
| [11-power.md](docs/11-power.md) | Розрахунок живлення ±12 V і 5 V, час роботи |
| [12-parts.md](docs/12-parts.md) | Вибір решти компонентів |
| [13-interboard.md](docs/13-interboard.md) | Крок D: роз'єм і pinout між платами |
| [calc/](docs/calc/), [sim/](docs/sim/) | Скрипти розрахунків (Python) і симуляцій (ngspice) |
| [hw/lib/](hw/lib/README.md) | Бібліотека KiCad: футпринти з креслень |
| [14-kicad.md](docs/14-kicad.md) | Крок E: як згенеровано схеми й плати, стан ERC/DRC |
| [15-3d.md](docs/15-3d.md) | 3D-моделі й збірка |
| [datasheets/](docs/datasheets/README.md) | Усі datasheets проєкту |

## Походження та ліцензія

Проєкт є похідним від **mixerli** (Stahl, 2023):
<https://github.com/stahlnow/mixerli> (базова версія — коміт `18a4a8e`).

SPDX-License-Identifier: CERN-OHL-S-2.0+

This source describes Open Hardware and is licensed under the CERN-OHL-S v2
or any later version. You may redistribute and modify this source and make
products using it under the terms of the CERN-OHL-S v2 or any later version
(https://ohwr.org/cern_ohl_s_v2.txt). This source is distributed WITHOUT ANY
EXPRESS OR IMPLIED WARRANTY, INCLUDING OF MERCHANTABILITY, SATISFACTORY QUALITY
AND FITNESS FOR A PARTICULAR PURPOSE. Please see the CERN-OHL-S v2 for applicable
conditions.

Source location (original): https://github.com/stahlnow/mixerli
Source location (this project): _TBD — указати після публікації репозиторію._

Згідно з розд. 4 CERN-OHL-S v2, на PCB має бути видно source location.
Повний текст ліцензії: [LICENSE](../LICENSE).
