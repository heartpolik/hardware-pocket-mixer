"""Refresh the 3D models of the footprints on existing boards from the libraries, without
re-placing anything (the routed boards keep their manual edits).

Run with KiCad's Python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      hw/pcb/set_models.py hw/analog/analog.kicad_pcb hw/analog/analog_routed.kicad_pcb ...
"""
import sys

import pcbnew

from build_pcb import set_models

for path in sys.argv[1:]:
    board = pcbnew.LoadBoard(path)
    for fp in board.GetFootprints():
        set_models(fp, fp.GetFPIDAsString())
    pcbnew.SaveBoard(path, board)
    print("models refreshed:", path)
