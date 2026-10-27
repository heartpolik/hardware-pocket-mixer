# common — спільні скрипти обох підпроєктів

Інструменти, якими користуються і [analog-mixer](../analog-mixer/README.md), і
[digital-mixer](../digital-mixer/README.md). Своє в кожного підпроєкту лишається в ньому: деталі
(footprint, моделі з кресленнями), схеми, розстановка, параметри (бібліотека, класи кіл, шари).

| Файл | Що робить | Хто викликає |
|---|---|---|
| `kisch.py` | пише схему KiCad (`.kicad_sch`), проєкт, правила, класи кіл (ширина доріжок, мінімуми плати, рівні перевірок DRC — параметри підпроєкту) | `hw/sch/project.py` обох підпроєктів задає бібліотеку й силові кола |
| `pcbkit.py` | список з'єднань зі схеми, завантаження footprint, розстановка за зв'язками | `digital-mixer/hw/pcb/build_pcb.py` (`use_project`) |
| `route_pcb.py` | трасування Freerouting, 2 або 4 шари; заливки GND; `--hole-keep` — заборонні зони навколо неметалізованих отворів | напряму (цифровий) або через `analog-mixer/hw/pcb/route_pcb.py` (заборони над перетворювачами) |
| `fix_pcb.py` | очищення після автороутера, зшивка GND | `route_pcb.py`; окремо — з `--edge-keep` (Rev A: 1,0 мм через V-cut) |
| `patch_route.py` | закриває один розрив пошуком A* | вручну, шари — за платою |
| `rip_near.py` | знімає доріжки одного кола біля точки, щоб провести їх заново (`patch_route.py --width`) | вручну |
| `fpgen.py` | клас `FP`: запис `.kicad_mod` | `hw/lib/gen_footprints.py` обох підпроєктів |
| `cq3d.py` | CadQuery-хелпери (коробка, циліндр, вивід, збереження STEP) | `hw/lib/gen_3d.py` обох підпроєктів |
| `tools/` | Freerouting 2.4.1 (`freerouting-2.4.1.jar`, у git не кладемо, 64 МБ: [реліз](https://github.com/freerouting/freerouting/releases/tag/v2.4.1)) | `route_pcb.py` |

Запуск — з теки підпроєкту, як описано в його документації; Python KiCad для `pcbnew`
(`/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3`),
CadQuery — з `.venv-cq` у корені репозиторію:

```sh
python3.12 -m venv .venv-cq && .venv-cq/bin/pip install cadquery==2.6.1
```
