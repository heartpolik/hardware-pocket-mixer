"""Digital mixer settings for the shared schematic writer common/kisch.py: project library
pocket-digital and the Power net class (up to ~0.45 A from the cell, docs/calc/power.py, and the rails)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))
import kisch  # noqa: E402
from kisch import Part, Sheet, pins_of  # noqa: E402,F401

kisch.use_library(Path(__file__).resolve().parents[1] / "lib", "pocket-digital")
POWER = ["/VBUS", "/VSYS", "/BAT+", "/+4V2", "/BB_L1", "/BB_L2", "/+3V3", "/+3V3A"]
# GCT USB4110 (drawing rev. B4, docs/datasheets/gct-usb4110.pdf, recommended PCB layout = the stock
# footprint): its d0.65 locating holes are 0.175 from its own pads, by design of the part. The board
# minimum goes down to 0.15 for that; every other NPTH hole keeps 0.25 by copper keepouts that
# common/route_pcb.py --hole-keep 0.25 puts on the board (KiCad 10 kicad-cli did not apply hole /
# track rules from .kicad_dru here - checked 27.10.2026).
BOARD_RULES = {"min_hole_clearance": 0.15}
RULES = ""
# signals 0.2 (power 0.5), as Rev A: 4 layers (DM31) leave room around the 0.5-pitch packages
TRACK = 0.2
SEVERITIES = {
    # locating pegs under parts of the other side: PJ-327A pegs reach 0.6 below the jack (seller's
    # STEP), USB4110 pegs 0.63 - neither comes through the 1.6 board (checked per case, 04-pcb.md)
    "npth_inside_courtyard": "warning",
    # one thermal spoke is enough (the .kicad_dru rule of common/kisch.py; hand soldering, D12) -
    # also a warning: with a second rule in the .kicad_dru kicad-cli stopped applying it (27.10.2026)
    "starved_thermal": "warning",
}


def project_files(folder, name):
    kisch.project_files(folder, name, POWER, RULES, BOARD_RULES, SEVERITIES, TRACK)
