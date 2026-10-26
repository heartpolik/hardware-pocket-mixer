"""Post-route cleanup of a Freerouting result (hw/pcb/route_pcb.py output), in place.

Copied from analog-mixer/hw/pcb/fix_pcb.py; on this 2-layer board "the plane" is the GND pour of
the other side: stitching vias go where both pours have room.
Run with KiCad's Python (from digital-mixer/):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      hw/pcb/fix_pcb.py

1. Dangling vias (copper on one layer only) and the track stubs left behind are removed.
2. Tracks thinner than the board minimum (Freerouting neck-downs) are widened to it.
3. GND stitching: every GND pour fragment on F.Cu / In2.Sig / B.Cu without a via or THT pad to
   the In1 plane gets a via, plus a stitching grid where the pours of all four layers overlap.
4. Zones are refilled and the board is saved over <board>_routed.kicad_pcb.
"""
import argparse
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parents[1]
MIN_TRACK = 0.15                     # = min_track_width, hw/sch/kisch.py project_files
VIA_D, VIA_DRILL = 0.6, 0.3          # Default net class
STITCH_PITCH = 5.0                   # mm, stitching grid
STITCH_MIN_DIST = 2.0                # mm to the nearest existing GND via / THT pad
EDGE_KEEP = 0.8                      # via centre to the board edge: via radius 0.3 + 0.5
TOL = pcbnew.FromMM(0.005)


def mm(v):
    return pcbnew.FromMM(v)


def close(a, b):
    return abs(a.x - b.x) <= TOL and abs(a.y - b.y) <= TOL


def key(net, layer, pos):
    return net, layer, round(pos.x / TOL), round(pos.y / TOL)


def cleanup(board, gnd):
    """Remove duplicate segments, dangling vias and the stubs they leave. GND is skipped (the
    pours connect it). Returns the number of removed items."""
    copper = list(board.GetEnabledLayers().CuStack())
    pads = {}
    for p in board.GetPads():
        pads.setdefault(p.GetNetCode(), []).append(p)

    def on_pad(net, layer, pos):
        return any(p.IsOnLayer(layer) and p.HitTest(pos) for p in pads.get(net, ()))

    def on_segment(p, segs):
        """T-junction: `p` lies on another segment (within its half width)."""
        for a, b, hw in segs:
            dx, dy = b.x - a.x, b.y - a.y
            ll = dx * dx + dy * dy
            u = 0 if ll == 0 else max(0.0, min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / ll))
            if (p.x - a.x - u * dx) ** 2 + (p.y - a.y - u * dy) ** 2 <= hw * hw:
                return True
        return False

    removed = 0
    while True:
        items = [t for t in board.GetTracks() if t.GetNetCode() != gnd]
        ends, seen, dead, segs = {}, set(), [], {}
        for t in items:
            uid, net = t.m_Uuid.AsString(), t.GetNetCode()
            if t.GetClass() == "PCB_VIA":
                for l in copper:
                    ends.setdefault(key(net, l, t.GetPosition()), set()).add(uid)
                continue
            seg = (net, t.GetLayer(), *sorted([key(0, 0, t.GetStart())[2:], key(0, 0, t.GetEnd())[2:]]))
            if seg in seen:                      # Freerouting leaves exact duplicates
                dead.append(t)
                continue
            seen.add(seg)
            segs.setdefault((net, t.GetLayer()), []).append(
                (t.GetStart(), t.GetEnd(), t.GetWidth() // 2, t.m_Uuid.AsString()))
            for e in (t.GetStart(), t.GetEnd()):
                ends.setdefault(key(net, t.GetLayer(), e), set()).add(uid)
        gone = {t.m_Uuid.AsString() for t in dead}

        def met(t, layer, pos):
            uid = t.m_Uuid.AsString()
            others = ends.get(key(t.GetNetCode(), layer, pos), set()) - {uid} - gone
            if others or on_pad(t.GetNetCode(), layer, pos):
                return True
            return on_segment(pos, [(a, b, w) for a, b, w, u in segs.get((t.GetNetCode(), layer), ())
                                    if u != uid and u not in gone])

        for t in items:
            if t.m_Uuid.AsString() in gone:
                continue
            if t.GetClass() == "PCB_VIA":
                if sum(met(t, l, t.GetPosition()) for l in copper) < 2:
                    dead.append(t)
            elif not (met(t, t.GetLayer(), t.GetStart()) and met(t, t.GetLayer(), t.GetEnd())):
                dead.append(t)
        if not dead:
            return removed
        for t in dead:
            board.Delete(t)
        removed += len(dead)


def widen(board):
    n = 0
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetWidth() < mm(MIN_TRACK):
            t.SetWidth(mm(MIN_TRACK))
            n += 1
    return n


def fill(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def gnd_polys(board, gnd):
    """{layer: SHAPE_POLY_SET} of the filled GND pours."""
    out = {}
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() != gnd:
            continue
        for layer in z.GetLayerSet().CuStack():
            out.setdefault(layer, pcbnew.SHAPE_POLY_SET()).Append(z.GetFilledPolysList(layer))
    return out


def anchors(board, gnd):
    """Points where a GND pour fragment already reaches the In1 plane: GND vias and THT pads."""
    pts = [t.GetPosition() for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gnd]
    pts += [p.GetPosition() for p in board.GetPads()
            if p.GetNetCode() == gnd and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
    return pts


def add_via(board, gnd, pos):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pos)
    v.SetWidth(mm(VIA_D))
    v.SetDrill(mm(VIA_DRILL))
    v.SetNetCode(gnd)
    board.Add(v)


def inside_edges(board):
    """Board outline shrunk by EDGE_KEEP: where a via may go."""
    poly = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(poly, False)
    poly.Inflate(-mm(EDGE_KEEP), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, mm(0.005))
    return poly


def drop_stitching(board, gnd):
    """Remove the stitching vias (GND vias no track ends on): stitch() rebuilds them, so a rerun
    gives the same result instead of a second grid."""
    ends = {(t.GetStart().x, t.GetStart().y) for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"}
    ends |= {(t.GetEnd().x, t.GetEnd().y) for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"}
    dead = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gnd
            and (t.GetPosition().x, t.GetPosition().y) not in ends]
    for t in dead:
        board.Delete(t)
    return len(dead)


def stitch(board, gnd):
    """GND vias where all four pours have room for one; first into every unanchored fragment,
    then on a grid. Holes of other nets are cleared by the pours' own clearance."""
    polys = gnd_polys(board, gnd)
    keep = mm(VIA_D / 2 + 0.05)
    ok = None
    for layer, ps in polys.items():
        d = ps.CloneDropTriangulation()
        d.Inflate(-keep, pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, mm(0.005))
        if ok is None:
            ok = d
        else:
            ok.BooleanIntersection(d)
    if ok is None or ok.IsEmpty():
        return 0, 0
    ok.BooleanIntersection(inside_edges(board))
    ok.BuildBBoxCaches()
    bb = board.GetBoardEdgesBoundingBox()
    step = mm(0.25)
    cand = [pcbnew.VECTOR2I(x, y) for x in range(bb.GetLeft(), bb.GetRight(), step)
            for y in range(bb.GetTop(), bb.GetBottom(), step)]
    cand = [p for p in cand if ok.Contains(p, -1, 0, True)]
    have = anchors(board, gnd)

    def far(p, pts, dist):
        d2 = mm(dist) ** 2
        return all((p.x - q.x) ** 2 + (p.y - q.y) ** 2 >= d2 for q in pts)

    frag = 0
    for layer, ps in polys.items():
        for i in range(ps.OutlineCount()):
            if any(ps.Contains(a, i) for a in have):
                continue
            inside = [p for p in cand if ps.Contains(p, i) and far(p, have, VIA_D + 0.3)]
            if inside:
                c = ps.Outline(i).Centre() if hasattr(ps.Outline(i), "Centre") else inside[0]
                p = min(inside, key=lambda q: (q.x - c.x) ** 2 + (q.y - c.y) ** 2)
                add_via(board, gnd, p)
                have.append(p)
                frag += 1
    grid = 0
    pitch = mm(STITCH_PITCH)
    for x in range(bb.GetLeft(), bb.GetRight(), pitch):
        for y in range(bb.GetTop(), bb.GetBottom(), pitch):
            near = [p for p in cand if abs(p.x - x) <= pitch // 2 and abs(p.y - y) <= pitch // 2]
            near = [p for p in near if far(p, have, STITCH_MIN_DIST)]
            if near:
                p = min(near, key=lambda q: (q.x - x) ** 2 + (q.y - y) ** 2)
                add_via(board, gnd, p)
                have.append(p)
                grid += 1
    return frag, grid


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    path = HW / "main" / "main_routed.kicad_pcb"
    board = pcbnew.LoadBoard(str(path))
    gnd = next(board.FindNet(n) for n in ("/GND", "GND") if board.FindNet(n)).GetNetCode()

    print("stitching vias removed:", drop_stitching(board, gnd))
    print("dangling removed:", cleanup(board, gnd))
    print("widened:", widen(board))
    fill(board)
    print("stitching vias (fragments, grid):", stitch(board, gnd))
    fill(board)
    pcbnew.SaveBoard(str(path), board)
    print("saved", path)


if __name__ == "__main__":
    main()
