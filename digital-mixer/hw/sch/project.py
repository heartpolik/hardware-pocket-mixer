"""Digital mixer settings for the shared schematic writer common/kisch.py: project library
pocket-digital and the Power net class (up to ~0.45 A from the cell, docs/calc/power.py, and the rails)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))
import kisch  # noqa: E402
from kisch import Part, Sheet, pins_of  # noqa: E402,F401

kisch.use_library(Path(__file__).resolve().parents[1] / "lib", "pocket-digital")
POWER = ["/VBUS", "/VSYS", "/BAT+", "/+4V2", "/BB_L1", "/BB_L2", "/+3V3", "/+3V3A"]


def project_files(folder, name):
    kisch.project_files(folder, name, POWER)
