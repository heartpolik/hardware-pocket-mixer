"""Close one unrouted connection on a routed board by a local grid search (A*), without touching
the rest of the routing. For the few connections Freerouting leaves open (docs/14-kicad.md).

Run with KiCad's Python:
  hw/pcb/patch_route.py <board.kicad_pcb> <net> <xa> <ya> <xb> <yb> [--width W] [--margin M] [--dry]
(xa, ya), (xb, yb): a point on each of the two unconnected parts, board mm (page - 20), e.g. from
the DRC report. Routes on F.Cu, In2 and B.Cu (In1 is the GND plane), vias by the net class,
clearance from the board rules, respects track/via keepouts. Refills the zones and saves.
"""
import argparse
import fnmatch
import heapq
import json
import math
from pathlib import Path

import pcbnew

OX = OY = 20.0
RES = 0.05                             # grid, mm
LAYERS = (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
VIA_COST = 3.0                         # mm of track a via is worth


def mm(v):
    return pcbnew.ToMM(v)


def iu(v):
    return pcbnew.FromMM(v)


def poly_of(item, layer, grow=0.0):
    ps = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(ps, layer, iu(grow), iu(0.005), pcbnew.ERROR_OUTSIDE)
    return ps


def net_class(board_path, net):
    """Net class of `net` from the project file next to the board (hw/sch/kisch.py project_files)."""
    pro = json.loads(Path(board_path).with_suffix(".kicad_pro").read_text())["net_settings"]
    name = next((p["netclass"] for p in pro.get("netclass_patterns", []) if fnmatch.fnmatch(net, p["pattern"])),
                "Default")
    return next(c for c in pro["classes"] if c["name"] == name)


def clusters(board, net, win):
    """Copper items of `net` touching the window, grouped by copper contact (tracks, vias, pads;
    zones left out: a part joined to the rest only through a pour is its own group)."""
    items = [t for t in board.GetTracks() if t.GetNetname() == net]
    items += [p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
    items = [it for it in items if it.GetBoundingBox().Intersects(win)]
    polys = {id(it): {L: poly_of(it, L) for L in pcbnew.LSET.AllCuMask().Seq() if it.IsOnLayer(L)} for it in items}
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            b = items[j]
            if not a.GetBoundingBox().Intersects(b.GetBoundingBox()):
                continue
            for L, pa in polys[id(a)].items():
                pb = polys[id(b)].get(L)
                if pb is not None:
                    x = pa.CloneDropTriangulation()
                    x.BooleanIntersection(pb)
                    if not x.IsEmpty():
                        parent[find(i)] = find(j)
                        break
    groups = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    return list(groups.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("net")
    ap.add_argument("coords", type=float, nargs=4)
    ap.add_argument("--width", type=float, default=None)
    ap.add_argument("--margin", type=float, default=6.0)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--avoid", default="", help="REF[,REF...]:mm - keep B.Cu / In2 tracks this far from "
                    "these parts (e.g. the converter inductors: L1,L2,L3:3)")
    a = ap.parse_args()
    board = pcbnew.LoadBoard(a.board)
    net = a.net if a.net.startswith("/") else "/" + a.net
    ni = board.FindNet(net)
    nc = net_class(a.board, net)
    clr = nc["clearance"] + 0.01
    w = a.width or nc["track_width"]
    vd, vdr = nc["via_diameter"], nc["via_drill"]
    xa, ya, xb, yb = a.coords
    x0, y0 = min(xa, xb) - a.margin, min(ya, yb) - a.margin
    x1, y1 = max(xa, xb) + a.margin, max(ya, yb) + a.margin
    nx, ny = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
    win = pcbnew.BOX2I(pcbnew.VECTOR2I(iu(x0 + OX), iu(y0 + OY)), pcbnew.VECTOR2I(iu(x1 - x0), iu(y1 - y0)))

    def cells(ps, inside=True):
        """Grid cells covered by `ps` (bounding box scan + Contains)."""
        out = set()
        ps.BuildBBoxCaches()
        bb = ps.BBox()
        i0 = max(0, int((mm(bb.GetLeft()) - OX - x0) / RES))
        i1 = min(nx - 1, int((mm(bb.GetRight()) - OX - x0) / RES) + 1)
        j0 = max(0, int((mm(bb.GetTop()) - OY - y0) / RES))
        j1 = min(ny - 1, int((mm(bb.GetBottom()) - OY - y0) / RES) + 1)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                p = pcbnew.VECTOR2I(iu(x0 + i * RES + OX), iu(y0 + j * RES + OY))
                if ps.Contains(p, -1, 0, True):
                    out.add((i, j))
        return out

    # blocked cells for a track centre / a via centre, per layer
    block = {L: set() for L in LAYERS}
    vblock = set()
    others = [t for t in board.GetTracks() if t.GetNetname() != net]
    others += [p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname() != net]
    for it in others:
        if not it.GetBoundingBox().Intersects(win):
            continue
        for L in LAYERS:
            if it.IsOnLayer(L):
                block[L] |= cells(poly_of(it, L, clr + w / 2))
        if any(it.IsOnLayer(L) for L in LAYERS):
            vblock |= cells(poly_of(it, next(L for L in LAYERS if it.IsOnLayer(L)), clr + vd / 2))
    for f in board.GetFootprints():                 # holes of own-net pads too: no via in a hole
        for p in f.Pads():
            if p.GetDrillSize().x > 0 and p.GetNetname() == net and p.GetBoundingBox().Intersects(win):
                c = p.GetPosition()
                r = mm(p.GetDrillSize().x) / 2 + vdr / 2 + 0.25
                vblock |= {(i, j) for i in range(max(0, int((mm(c.x) - OX - r - x0) / RES)),
                                                 min(nx, int((mm(c.x) - OX + r - x0) / RES) + 2))
                           for j in range(max(0, int((mm(c.y) - OY - r - y0) / RES)),
                                          min(ny, int((mm(c.y) - OY + r - y0) / RES) + 2))
                           if math.hypot(x0 + i * RES - (mm(c.x) - OX), y0 + j * RES - (mm(c.y) - OY)) < r}
    for z in board.Zones():
        if not z.GetIsRuleArea():
            continue
        for L in LAYERS:
            if z.IsOnLayer(L) and z.GetDoNotAllowTracks():
                ko = z.Outline().CloneDropTriangulation()       # the track edge must stay out too
                ko.Inflate(iu(w / 2 + 0.01), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, iu(0.005))
                block[L] |= cells(ko)
        if z.GetDoNotAllowVias() and any(z.IsOnLayer(L) for L in LAYERS):
            ko = z.Outline().CloneDropTriangulation()
            ko.Inflate(iu(vd / 2 + 0.01), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, iu(0.005))
            vblock |= cells(ko)
    if a.avoid:
        refs, dist = a.avoid.split(":")
        for ref in refs.split(","):
            bb = board.FindFootprintByReference(ref).GetBoundingBox(False)
            ko = pcbnew.SHAPE_POLY_SET()
            ko.NewOutline()
            for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                         (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
                ko.Append(x, y)
            ko.Inflate(iu(float(dist) + w / 2), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, iu(0.005))
            c = cells(ko)
            for L in (pcbnew.B_Cu, pcbnew.In2_Cu):
                block[L] |= c
    edge = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(edge, False)
    inner = edge.CloneDropTriangulation()
    inner.Inflate(-iu(1.0 + w / 2), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, iu(0.005))
    inside = cells(inner)
    for L in LAYERS:
        block[L] |= {(i, j) for i in range(nx) for j in range(ny)} - inside
    for L in LAYERS:
        vblock |= block[L]

    # start / goal: copper of the two parts of the net
    groups = clusters(board, net, win)
    pa = pcbnew.VECTOR2I(iu(xa + OX), iu(ya + OY))
    pb = pcbnew.VECTOR2I(iu(xb + OX), iu(yb + OY))

    def group_at(p):
        best = None
        for g in groups:
            for it in g:
                for L in LAYERS:
                    if it.IsOnLayer(L) and poly_of(it, L, 0.05).Contains(p, -1, 0, True):
                        return g
            d = min((it.GetPosition() - p).EuclideanNorm() for it in g)
            if best is None or d < best[0]:
                best = (d, g)
        return best[1]

    ga, gb = group_at(pa), group_at(pb)
    if ga is gb:
        raise SystemExit("both points are on the same connected part")

    def terminals(g):
        out = set()
        for it in g:
            if not it.GetBoundingBox().Intersects(win):
                continue
            for L in LAYERS:
                if it.IsOnLayer(L):
                    shrink = poly_of(it, L, 0.0)
                    out |= {(L, i, j) for i, j in cells(shrink)}
        return out

    starts, goals = terminals(ga), terminals(gb)
    if not starts or not goals:
        raise SystemExit("a part has no copper in the window: raise --margin")
    gx = sum(i for _, i, _ in goals) / len(goals)
    gy = sum(j for _, _, j in goals) / len(goals)
    h = lambda i, j: math.hypot(i - gx, j - gy) * RES * 0.5
    pq, best, prev = [], {}, {}
    for s in starts:
        best[s] = 0.0
        heapq.heappush(pq, (h(s[1], s[2]), 0.0, s))
    steps = [(di, dj, math.hypot(di, dj) * RES) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj]
    end = None
    while pq:
        _, g, s = heapq.heappop(pq)
        if g > best.get(s, 1e9):
            continue
        if s in goals:
            end = s
            break
        L, i, j = s
        nbrs = []
        for di, dj, c in steps:
            t = (L, i + di, j + dj)
            if 0 <= t[1] < nx and 0 <= t[2] < ny and ((t[1], t[2]) not in block[L] or t in goals or t in starts):
                nbrs.append((t, c))
        if (i, j) not in vblock:
            for L2 in LAYERS:
                if L2 != L:
                    nbrs.append(((L2, i, j), VIA_COST))
        for t, c in nbrs:
            ng = g + c
            if ng < best.get(t, 1e9):
                best[t] = ng
                prev[t] = s
                heapq.heappush(pq, (ng + h(t[1], t[2]), ng, t))
    if end is None:
        raise SystemExit("no path in the window")
    path = [end]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    # drop the part of the path inside the start / goal copper except one cell
    while len(path) > 1 and path[1] in starts:
        path.pop(0)
    while len(path) > 1 and path[-2] in goals:
        path.pop()
    # segments: merge straight runs on one layer, vias at layer changes
    pts = lambda s: pcbnew.VECTOR2I(iu(x0 + s[1] * RES + OX), iu(y0 + s[2] * RES + OY))
    segs, vias = [], []
    run = [path[0]]
    for s in path[1:]:
        if s[0] != run[-1][0]:
            segs.append(run)
            vias.append(s)
            run = [s]
        else:
            run.append(s)
    segs.append(run)
    new = []
    for run in segs:
        if len(run) < 2:
            continue
        L = run[0][0]

        def clear(p, q):                           # straight line p -> q over free cells only
            n = int(max(abs(q[1] - p[1]), abs(q[2] - p[2])) * 2) + 1
            for k in range(n + 1):
                c = (round(p[1] + (q[1] - p[1]) * k / n), round(p[2] + (q[2] - p[2]) * k / n))
                if c in block[L] and (L,) + c not in starts and (L,) + c not in goals:
                    return False
            return True

        corners, k = [run[0]], 0                   # string pulling: farthest visible point
        while k < len(run) - 1:
            m = len(run) - 1
            while m > k + 1 and not clear(run[k], run[m]):
                m -= 1
            corners.append(run[m])
            k = m
        for p, q in zip(corners, corners[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pts(p))
            t.SetEnd(pts(q))
            t.SetWidth(iu(w))
            t.SetLayer(L)
            t.SetNet(ni)
            new.append(t)
    for s in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pts(s))
        v.SetWidth(iu(vd))
        v.SetDrill(iu(vdr))
        v.SetNet(ni)
        new.append(v)
    length = sum(mm(t.GetLength()) for t in new if isinstance(t, pcbnew.PCB_TRACK) and t.GetClass() == "PCB_TRACK")
    print(f"{net}: {len([t for t in new if t.GetClass() == 'PCB_TRACK'])} segments, {len(vias)} vias, "
          f"{length:.1f} mm, layers {sorted({board.GetLayerName(t.GetLayer()) for t in new if t.GetClass() == 'PCB_TRACK'})}")
    if a.dry:
        return
    for t in new:
        board.Add(t)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(a.board)


if __name__ == "__main__":
    main()
