"""Autoroute a placed board with Freerouting (Specctra DSN -> SES), 4 copper layers.

Run with KiCad's Python after build_pcb.py:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      hw/pcb/route_pcb.py analog [--passes N] [--resume]

Stack-up (docs/14-kicad.md): F.Cu signal / In1.Cu GND plane / In2.Cu signal + power /
B.Cu signal (SMD side). The GND plane is a "power" layer, so Freerouting does not route on it
and drops vias into it for GND pads. Output: <board>_routed.kicad_pcb next to the input -
the placed board from build_pcb.py stays untouched; manual correction happens on the routed copy.
After the import the result is cleaned up and GND-stitched by hw/pcb/fix_pcb.py.

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

HW = Path(__file__).resolve().parents[1]
JAVA = os.environ.get("JAVA", "/opt/homebrew/opt/openjdk@25/bin/java")
FREEROUTING = os.environ.get("FREEROUTING", str(HW / "pcb" / "tools" / "freerouting-2.4.1.jar"))


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
    track/via keepout for the routing run. Board outline: 0.5 mm inward (the rear edges become the
    V-cut of the panel, hw/pcb/panel.py); footprint cut-outs (LED windows): 0.225 mm.
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


def gnd_name(board):
    for n in ("/GND", "GND"):
        if board.FindNet(n):
            return n
    raise RuntimeError("no GND net")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=("analog", "digital"))
    ap.add_argument("--passes", type=int, default=40)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()

    src = HW / a.board / f"{a.board}.kicad_pcb"
    out = HW / a.board / f"{a.board}_routed.kicad_pcb"
    work = HW / a.board / "route"
    work.mkdir(exist_ok=True)
    dsn, ses = work / f"{a.board}.dsn", work / f"{a.board}.ses"

    board = pcbnew.LoadBoard(str(out if a.resume else src))
    gnd = gnd_name(board)
    gcode = board.FindNet(gnd).GetNetCode()
    if a.resume:
        # keep the routing, drop what fix_pcb.py rebuilds: pours on the routing layers and the
        # stitching vias (GND vias no track ends on)
        ends = {(t.GetStart().x, t.GetStart().y) for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"}
        ends |= {(t.GetEnd().x, t.GetEnd().y) for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"}
        for t in list(board.GetTracks()):
            if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gcode and (t.GetPosition().x, t.GetPosition().y) not in ends:
                board.Delete(t)
        for z in list(board.Zones()):
            if z.GetLayer() != pcbnew.In1_Cu and not z.GetIsRuleArea():
                board.Delete(z)
    else:
        for t in list(board.GetTracks()):
            board.Remove(t)
        for z in list(board.Zones()):
            board.Remove(z)
        if a.layers == 4:
            setup_layers(board)
            zone(board, pcbnew.In1_Cu, gnd)
    fences = edge_keepouts(board)
    if a.board == "analog" and not any(z.GetZoneName() == KEEPOUT_NAME for z in board.Zones()):
        print("converter keepouts:", len(converter_keepouts(board)))
    board.BuildConnectivity()
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise RuntimeError("DSN export failed")

    cmd = [JAVA, "-Duser.language=en", "-jar", FREEROUTING, "-de", str(dsn), "-do", str(ses),
           "-mp", str(a.passes), "--gui.enabled=false", "--router.fanout.enabled=true",
           "--profile.allow_telemetry=false", "--usage_and_diagnostic_data.disable_analytics=true"]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)

    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise RuntimeError("SES import failed")
    for z in fences:
        board.Remove(z)
    print("dangling removed:", fix_pcb.cleanup(board, gcode), "widened:", fix_pcb.widen(board))
    # GND pours on the routing layers after routing, stitched to In1
    for layer in ((pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu) if a.layers == 4 else (pcbnew.F_Cu, pcbnew.B_Cu)):
        zone(board, layer, gnd)
    fix_pcb.fill(board)
    print("stitching vias (fragments, grid):", fix_pcb.stitch(board, gcode))
    fix_pcb.fill(board)
    board.SetFileName(str(out))
    pcbnew.SaveBoard(str(out), board)
    if not a.resume:
        for ext in (".kicad_pro", ".kicad_dru"):
            shutil.copy(src.with_suffix(ext), out.with_suffix(ext))   # net classes, rules
    print("saved", out, "tracks:", len(board.GetTracks()))


if __name__ == "__main__":
    main()
