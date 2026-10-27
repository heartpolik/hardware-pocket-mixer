"""Autoroute a placed board with Freerouting (Specctra DSN -> SES), 2 or 4 copper layers. Shared
(common/README.md); Rev A wraps it with its converter keepouts (analog-mixer/hw/pcb/route_pcb.py).

Run with KiCad's Python after the board script:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      common/route_pcb.py <board.kicad_pcb> [--layers 2|4] [--passes N] [--resume] [--edge MM]

4 layers: F.Cu signal / In1.Cu GND plane / In2.Cu signal + power / B.Cu signal. The GND plane is a
"power" layer, so Freerouting does not route on it and drops vias into it for GND pads. 2 layers:
both are signal layers. GND pours on the routing layers after routing, stitched by fix_pcb.stitch().
Tracks locked by the board script (pre-routed blocks) stay. Output: <board>_routed.kicad_pcb next
to the input - the placed board stays untouched.

--resume starts from <board>_routed.kicad_pcb and keeps its tracks: Freerouting only routes what is
still open (the pours and stitching vias are rebuilt afterwards).
"""
import argparse
import os
import shutil
import subprocess
from pathlib import Path

import pcbnew

import fix_pcb

JAVA = os.environ.get("JAVA", "/opt/homebrew/opt/openjdk@25/bin/java")
FREEROUTING = os.environ.get("FREEROUTING", str(Path(__file__).resolve().parent / "tools" / "freerouting-2.4.1.jar"))


def mm(v):
    return pcbnew.FromMM(v)


def setup_layers(board):
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(4)
    layers = board.GetEnabledLayers()
    layers.AddLayer(pcbnew.In1_Cu)
    layers.AddLayer(pcbnew.In2_Cu)
    board.SetEnabledLayers(layers)
    board.SetLayerName(pcbnew.In1_Cu, "In1.GND")
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerName(pcbnew.In2_Cu, "In2.Sig")
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_SIGNAL)


def zone(board, layer, net, priority=0, clearance=0.3):
    bb = board.GetBoardEdgesBoundingBox()
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(net))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(mm(clearance))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                 (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
        ol.Append(x, y)
    board.Add(z)
    return z


def edge_keepouts(board, outline=1.0, cutout=0.45):
    """Freerouting ignores KiCad's copper-to-edge rule: fence every Edge.Cuts segment with a
    track/via keepout for the routing run. Board outline: `outline` / 2 inward (Rev A: 0.5 for the
    V-cut of its panel); footprint cut-outs (LED / Teensy windows): 0.225 mm.
    Returns the rule areas."""
    shapes = [(d, outline) for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    for fp in board.GetFootprints():
        shapes += [(g, cutout) for g in fp.GraphicalItems() if g.GetLayer() == pcbnew.Edge_Cuts]
    segs = []
    for s, width in shapes:
        if s.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            segs.append((s.GetStart(), s.GetEnd(), width))
        elif s.GetShape() == pcbnew.SHAPE_T_RECT:
            a, b = s.GetStart(), s.GetEnd()
            c = [pcbnew.VECTOR2I(a.x, a.y), pcbnew.VECTOR2I(b.x, a.y), pcbnew.VECTOR2I(b.x, b.y),
                 pcbnew.VECTOR2I(a.x, b.y)]
            segs += [(p, q, width) for p, q in zip(c, c[1:] + c[:1])]
        elif s.GetShape() == pcbnew.SHAPE_T_ARC:        # rounded corners of the LED cut-outs
            bb = s.GetBoundingBox()
            segs.append((pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop()), pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()), width))
    areas = []
    for a, b, width in segs:
        h = mm(width / 2)
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetDoNotAllowZoneFills(False)
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
        ol = z.Outline()
        ol.NewOutline()
        x0, x1 = min(a.x, b.x) - h, max(a.x, b.x) + h
        y0, y1 = min(a.y, b.y) - h, max(a.y, b.y) + h
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ol.Append(x, y)
        board.Add(z)
        areas.append(z)
    return areas


def gnd_name(board):
    for n in ("/GND", "GND"):
        if board.FindNet(n):
            return n
    raise RuntimeError("no GND net")


def route(src, layers=2, passes=40, resume=False, outline=1.0, setup=None):
    """Route `src` into <src>_routed.kicad_pcb. `setup(board)`: project hook after the layer
    setup (extra rule areas kept on the board)."""
    src = Path(src)
    out = src.with_name(src.stem + "_routed.kicad_pcb")
    work = src.parent / "route"
    work.mkdir(exist_ok=True)
    dsn, ses = work / f"{src.stem}.dsn", work / f"{src.stem}.ses"

    board = pcbnew.LoadBoard(str(out if resume else src))
    gnd = gnd_name(board)
    gcode = board.FindNet(gnd).GetNetCode()
    if resume:
        # keep the routing, drop what fix_pcb.py rebuilds: pours on the routing layers and the
        # stitching vias (GND vias no track ends on)
        ends = {(t.GetStart().x, t.GetStart().y) for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"}
        ends |= {(t.GetEnd().x, t.GetEnd().y) for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"}
        for t in list(board.GetTracks()):
            if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gcode and (t.GetPosition().x, t.GetPosition().y) not in ends:
                board.Delete(t)
        for z in list(board.Zones()):
            if not z.GetIsRuleArea() and not (layers == 4 and z.GetLayer() == pcbnew.In1_Cu):
                board.Delete(z)
    else:
        for t in list(board.GetTracks()):
            if not t.IsLocked():                       # pre-routed blocks of the board script stay
                board.Remove(t)
        for z in list(board.Zones()):
            board.Remove(z)
        if layers == 4:
            setup_layers(board)
            zone(board, pcbnew.In1_Cu, gnd)
    if setup:
        setup(board)
    fences = edge_keepouts(board, outline=outline)
    board.BuildConnectivity()
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise RuntimeError("DSN export failed")

    cmd = [JAVA, "-Duser.language=en", "-jar", FREEROUTING, "-de", str(dsn), "-do", str(ses),
           "-mp", str(passes), "--gui.enabled=false", "--router.fanout.enabled=true",
           "--profile.allow_telemetry=false", "--usage_and_diagnostic_data.disable_analytics=true"]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)

    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise RuntimeError("SES import failed")
    for z in fences:
        board.Remove(z)
    print("dangling removed:", fix_pcb.cleanup(board, gcode), "widened:", fix_pcb.widen(board))
    for layer in ((pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu) if layers == 4 else (pcbnew.F_Cu, pcbnew.B_Cu)):
        zone(board, layer, gnd)
    fix_pcb.fill(board)
    print("stitching vias (fragments, grid):", fix_pcb.stitch(board, gcode))
    fix_pcb.fill(board)
    board.SetFileName(str(out))
    pcbnew.SaveBoard(str(out), board)
    if not resume:
        for ext in (".kicad_pro", ".kicad_dru"):
            shutil.copy(src.with_suffix(ext), out.with_suffix(ext))   # net classes, rules
    print("saved", out, "tracks:", len(board.GetTracks()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", help="placed board, e.g. digital-mixer/hw/main/main.kicad_pcb")
    ap.add_argument("--layers", type=int, default=2, choices=(2, 4))
    ap.add_argument("--passes", type=int, default=40)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--edge", type=float, default=1.0, help="edge fence width, mm (half of it inside)")
    a = ap.parse_args()
    route(a.board, a.layers, a.passes, a.resume, a.edge)


if __name__ == "__main__":
    main()
