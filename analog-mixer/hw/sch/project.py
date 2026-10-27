"""Rev A settings for the shared schematic writer common/kisch.py: project library diy-mixer and the
Power net class (battery / converter nets, up to ~0.56 A, 11-power, and the supply rails)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))
import kisch  # noqa: E402
from kisch import Part, Sheet, pins_of  # noqa: E402,F401

kisch.use_library(Path(__file__).resolve().parents[1] / "lib", "diy-mixer")
POWER = ["/BAT+", "/VSW", "/VBUS", "/SW_P", "/SW_N", "/SW_5", "/N_N", "/+12V_P", "/-12V_P",
         "/+12VA", "/-12VA", "/+5V", "/+3V3"]


def project_files(folder, name):
    kisch.project_files(folder, name, POWER)
