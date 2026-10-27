"""Route a Rev A board with the shared Freerouting script (common/route_pcb.py), 4 copper layers,
plus the converter keepouts of the analog board.

Run with KiCad's Python after build_pcb.py:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      hw/pcb/route_pcb.py analog [--passes N] [--resume]

Stack-up (docs/14-kicad.md): F.Cu signal / In1.Cu GND plane / In2.Cu signal + power /
B.Cu signal (SMD side). Output: <board>_routed.kicad_pcb next to the input - the placed board from
build_pcb.py stays untouched; manual correction happens on the routed copy. After the import the
result is cleaned up and GND-stitched by common/fix_pcb.py (vias 1.0 from the edge: V-cut keepout).

--resume starts from <board>_routed.kicad_pcb and keeps its tracks: Freerouting only routes what is
still open (the pours and stitching vias are rebuilt afterwards).
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parents[1]
COMMON = HW.parents[1] / "common"
sys.path.insert(0, str(COMMON))
import fix_pcb  # noqa: E402

_spec = importlib.util.spec_from_file_location("common_route_pcb", COMMON / "route_pcb.py")
R = importlib.util.module_from_spec(_spec)          # same file name as this wrapper
_spec.loader.exec_module(R)
mm = R.mm

SWITCH_NETS = ("/SW_P", "/SW_N", "/SW_5", "/BST_5", "/N_N")   # switching nodes of the converters
KEEPOUT_NAME = "audio: no tracks over converter"


def converter_keepouts(board, margin=1.0):
    """The converters sit on B.Cu and In2 has no plane between it and B.Cu (docs/14-kicad.md, 4.1):
    no tracks on In2 over each converter (every part on its switching nodes + `margin`), so the
    switching nodes stay on B.Cu with In1 GND right above them; no tracks on F.Cu over the block
    either. Vias stay allowed (GND of the converter ICs). Kept on the board, so DRC also holds
    manual edits to it. Returns the rule areas."""
    groups = []                                      # footprints sharing switching nodes
    for f in board.GetFootprints():
        nets = {p.GetNetname() for p in f.Pads()} & set(SWITCH_NETS)
        if not nets:
            continue
        hit = [g for g in groups if g[0] & nets]
        merged = [nets, [f]]
        for g in hit:
            merged[0] |= g[0]
            merged[1] += g[1]
            groups.remove(g)
        groups.append(merged)

    def area(layer, bb, grow):
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetZoneName(KEEPOUT_NAME)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetDoNotAllowZoneFills(False)
        z.SetLayer(layer)
        ol = z.Outline()
        ol.NewOutline()
        g = mm(grow)
        for x, y in ((bb.GetLeft() - g, bb.GetTop() - g), (bb.GetRight() + g, bb.GetTop() - g),
                     (bb.GetRight() + g, bb.GetBottom() + g), (bb.GetLeft() - g, bb.GetBottom() + g)):
            ol.Append(x, y)
        board.Add(z)
        return z

    areas = []
    for nets, fps in groups:
        bb = fps[0].GetBoundingBox(False)
        for f in fps[1:]:
            bb.Merge(f.GetBoundingBox(False))
        areas.append(area(pcbnew.In2_Cu, bb, margin))
        areas.append(area(pcbnew.F_Cu, bb, 0.5))     # In1 alone is a thin shield at 1-2 MHz
    return areas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=("analog", "digital"))
    ap.add_argument("--passes", type=int, default=40)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    fix_pcb.EDGE_KEEP = 1.0                          # V-cut keepout 0.5 (panel.py) + via radius 0.3 + 0.2

    def setup(board):
        if a.board == "analog" and not any(z.GetZoneName() == KEEPOUT_NAME for z in board.Zones()):
            print("converter keepouts:", len(converter_keepouts(board)))

    R.route(HW / a.board / f"{a.board}.kicad_pcb", a.layers, a.passes, a.resume, outline=1.0, setup=setup)


if __name__ == "__main__":
    main()
