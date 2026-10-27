# diy-mixer

Портативний 4-канальний стереомікшер для поля й столу. У репозиторії два підпроєкти:

| Тека | Що це | Стан |
|---|---|---|
| [analog-mixer/](analog-mixer/README.md) | **Rev A, аналоговий**: звук іде крізь фейдери й op-amp, ±12 V від 2S LiPo, ESP32-C3 керує ключами й метрами; дві плати | плати розведено, Gerber і BOM готові |
| [digital-mixer/](digital-mixer/README.md) | **Цифровий**, формфактор і функції на зразок TX-6: АЦП → Teensy 4.1 (мікс, EQ, ефекти) → ЦАП, USB-аудіоінтерфейс 8 каналів, MIDI, рекордер на microSD | плату розставлено й розведено, компоновка переробляється |
| [common/](common/README.md) | спільні скрипти: схема, розстановка, трасування, footprint, 3D | — |

Правила роботи для обох — [CLAUDE.md](CLAUDE.md). Рішення кожного підпроєкту — у його
`docs/decisions.md`.

## Походження та ліцензія

Похідний від **mixerli** (Stahl, 2023): <https://github.com/stahlnow/mixerli>.
Source location: <https://github.com/heartpolik/hardware-pocket-mixer>.
SPDX-License-Identifier: CERN-OHL-S-2.0+ — повний текст у [LICENSE](LICENSE), деталі — в
[analog-mixer/README.md](analog-mixer/README.md#походження-та-ліцензія).
