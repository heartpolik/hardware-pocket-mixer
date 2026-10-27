"""Board-building helpers (netlist parsing, footprint loading, PCB class with connectivity-driven
placement), extracted from analog-mixer/hw/pcb/build_pcb.py. Shared (common/README.md): a board
script calls use_project() with its hw/ folder and footprint library name first.
"""
import re
import subprocess
from pathlib import Path

import pcbnew

HW = None                            # <subproject>/hw
KICAD_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
OX, OY = 20.0, 20.0                  # board origin on the KiCad page
PROJ_LIB = None                      # project footprint library: HW/lib/<PROJ_LIB>.pretty


def use_project(hw, lib):
    global HW, PROJ_LIB
    HW, PROJ_LIB = Path(hw), lib


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def netlist(sch):
    out = HW / "pcb" / "build" / (Path(sch).stem + ".net")
    out.parent.mkdir(exist_ok=True)
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(sch)],
                   check=True, capture_output=True)
    s = out.read_text()
    comps = {}
    for m in re.finditer(r'\(comp\s*\(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(footprint "([^"]*)"\)', s):
        comps[m.group(1)] = {"value": m.group(2), "fp": m.group(3), "pins": {}}
    for m in re.finditer(r'\(comp\s*\(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(fields', s):
        comps.setdefault(m.group(1), {"value": m.group(2), "fp": "", "pins": {}})
    for blk in re.split(r'\(comp\s*\(ref', s)[1:]:
        ref = re.match(r'\s*"([^"]+)"', blk).group(1)
        ts = re.search(r'\(tstamps "([0-9a-f-]{36})"\)', blk)
        if ref in comps and ts:
            comps[ref]["uuid"] = ts.group(1)
        head = blk.split("(libsource")[0]
        dec = re.search(r'\(name "Decouples"\)\s*"([^"]+)"', head)
        if ref in comps and dec:
            comps[ref]["decouples"] = dec.group(1)          # hw/sch/analog.py decouple()
        grp = re.search(r'\(name "Group"\)\s*"([^"]+)"', head)
        if ref in comps and grp:
            comps[ref]["group"] = grp.group(1)              # converter block, hw/sch/analog.py
    for blk in re.split(r'\(net\s*\(code', s)[1:]:
        name = re.search(r'\(name "([^"]*)"\)', blk).group(1)
        for ref, pin in re.findall(r'\(node\s*\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk):
            if ref in comps:
                comps[ref]["pins"][pin] = name
    return comps


def lib_fp(fpid):
    lib, name = fpid.split(":")
    path = HW / "lib" / f"{PROJ_LIB}.pretty" if lib == PROJ_LIB else KICAD_FP / f"{lib}.pretty"
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        raise RuntimeError(f"footprint not found: {fpid}")
    return fp


def load_fp(fpid):
    lib, name = fpid.split(":")
    fp = lib_fp(fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


class PCB:
    def __init__(self):
        self.board = pcbnew.BOARD()
        self.nets = {}
        self.fps = {}

    def net(self, name):
        if name not in self.nets:
            ni = pcbnew.NETINFO_ITEM(self.board, name)
            self.board.Add(ni)
            self.nets[name] = ni
        return self.nets[name]

    def add(self, ref, comp):
        if not comp["fp"]:
            return None
        fp = load_fp(comp["fp"])
        fp.SetReference(ref)
        if comp.get("uuid"):
            fp.SetPath(pcbnew.KIID_PATH("/" + comp["uuid"]))
        fp.SetValue(comp["value"])
        self.board.Add(fp)
        for pad in fp.Pads():
            n = comp["pins"].get(pad.GetNumber())
            if n:
                pad.SetNet(self.net(n))
        self.fps[ref] = fp
        return fp

    def place(self, ref, x, y, rot=0.0, bottom=False):
        fp = self.fps[ref]
        if bottom and not fp.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pt(x, y))

    def outline(self, pts):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            seg = pcbnew.PCB_SHAPE(self.board)
            seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
            seg.SetStart(pt(x1, y1))
            seg.SetEnd(pt(x2, y2))
            seg.SetLayer(pcbnew.Edge_Cuts)
            seg.SetWidth(mm(0.1))
            self.board.Add(seg)

    def size(self, ref):
        bb = self.fps[ref].GetCourtyard(pcbnew.F_CrtYd).BBox() if self.fps[ref].GetCourtyard(pcbnew.F_CrtYd).OutlineCount() \
            else self.fps[ref].GetBoundingBox(False)
        return pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())

    def rect_of(self, ref):
        bb = self.fps[ref].GetBoundingBox(False)
        return (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)

    def obstacles(self, refs_placed, bottom):
        """Footprints on the same side + every through-hole pad (it occupies both sides)."""
        obs = []
        for ref in refs_placed:
            fp = self.fps[ref]
            if fp.IsFlipped() == bottom:
                obs.append(self.rect_of(ref))
            for pad in fp.Pads():
                if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                    bb = pad.GetBoundingBox()
                    obs.append((pcbnew.ToMM(bb.GetLeft()) - OX - 0.4, pcbnew.ToMM(bb.GetTop()) - OY - 0.4,
                                pcbnew.ToMM(bb.GetRight()) - OX + 0.4, pcbnew.ToMM(bb.GetBottom()) - OY + 0.4))
        return obs

    def pads_of(self, ref):
        """[(net, x, y)] board coordinates."""
        out = []
        for pad in self.fps[ref].Pads():
            n = pad.GetNetname().lstrip("/")
            if n:
                c = pad.GetPosition()
                out.append((n, pcbnew.ToMM(c.x) - OX, pcbnew.ToMM(c.y) - OY))
        return out

    def place_near(self, refs, placed, bounds, rails, fallback, bottom=True, gap=0.4, step=0.5, reach=30.0,
                   extra=(), decap=None):
        """Connectivity-driven placement. Repeatedly takes the part with most signal nets already
        present on the board and puts it at the free spot closest to the centroid of those pads.
        `decap` = {capacitor: IC} (schematic field Decouples): such a capacitor goes right after its
        IC, next to the IC pin on its rail, before other parts take that space. Other parts that only
        touch rails go next to the IC rail pin with fewest caps.
        `rails` = nets ignored for attraction (GND, supplies); `fallback(ref)` = (x, y) target
        for a part with nothing placed yet."""
        B = 5.0
        grid = {}

        def add_obs(o):
            for i in range(int(o[0] // B), int(o[2] // B) + 1):
                for j in range(int(o[1] // B), int(o[3] // B) + 1):
                    grid.setdefault((i, j), []).append(o)

        def free(r):
            for i in range(int(r[0] // B), int(r[2] // B) + 1):
                for j in range(int(r[1] // B), int(r[3] // B) + 1):
                    for o in grid.get((i, j), ()):
                        if r[0] < o[2] and r[2] > o[0] and r[1] < o[3] and r[3] > o[1]:
                            return False
            return True

        for o in list(self.obstacles(placed, bottom)) + list(extra):
            add_obs(o)
        net_xy = {}

        def note(ref):
            for n, x, y in self.pads_of(ref):
                if n not in rails:
                    net_xy.setdefault(n, []).append((x, y))

        for ref in placed:
            note(ref)
        rail_pins = []                               # (net, x, y, [count]) of multi-pin ICs

        def spot(ref, tx, ty, rot, g, st, rch):
            """Free spot nearest to (tx, ty): (distance, x, y, l, t, w, h) or None."""
            self.place(ref, 0, 0, rot, bottom)
            l, t, r, b = self.rect_of(ref)
            w, h = r - l + g, b - t + g
            cands = []
            k = int(rch / st)
            for i in range(-k, k + 1):
                for j in range(-k, k + 1):
                    x, y = tx + i * st - w / 2, ty + j * st - h / 2
                    if bounds[0] <= x and x + w <= bounds[2] and bounds[1] <= y and y + h <= bounds[3]:
                        cands.append(((i * i + j * j) * st * st, x, y))
            cands.sort()
            for d, x, y in cands:
                if free((x, y, x + w, y + h)):
                    return d, x, y, l, t, w, h
            return None

        def commit(ref, rot, found, g):
            _, x, y, l, t, w, h = found
            self.place(ref, 0, 0, rot, bottom)
            self.fps[ref].Move(pcbnew.VECTOR2I(mm(x + g / 2 - l), mm(y + g / 2 - t)))
            add_obs((x, y, x + w, y + h))

        def put_at(ref, tx, ty, rot):
            found = spot(ref, tx, ty, rot, gap, step, reach)
            if found:
                commit(ref, rot, found, gap)
            return bool(found)

        def put_decap(ref, tx, ty):
            """Decoupling cap: tighter gap and grid, the orientation that lands closer to the pin."""
            g = 0.2
            best = min(((f[0], rot, f) for rot in (0, 90) for f in [spot(ref, tx, ty, rot, g, 0.25, 12.0)] if f),
                       default=None, key=lambda v: v[0])
            if best:
                commit(ref, best[1], best[2], g)
            return bool(best)

        todo = set(refs)
        left = []
        done_dec = set()

        def place_decaps(ic):
            for cap in sorted(c for c, i in (decap or {}).items() if i == ic and c in todo):
                rail = next(n for n, _, _ in self.pads_of(cap) if n != "GND")
                pins = [(x, y) for n, x, y in self.pads_of(ic) if n == rail]
                px, py = pins[sum(1 for c, i in decap.items() if i == ic and c in done_dec
                                  and rail in {n for n, _, _ in self.pads_of(c)}) % len(pins)]
                todo.discard(cap)
                if put_decap(cap, px, py):
                    done_dec.add(cap)
                else:
                    left.append(cap)

        for ic in sorted({i for i in (decap or {}).values() if i in placed}):
            place_decaps(ic)                         # parts placed before (modules, LEDs)
        signal = {r: {n for n, _, _ in self.pads_of(r)} - rails for r in refs}
        while todo:
            def score(r):
                return (sum(1 for n in signal[r] if n in net_xy), len(self.fps[r].Pads()))
            ref = max(sorted(todo), key=score)
            todo.discard(ref)
            if not signal[ref]:
                continue                             # rails only: after the ICs
            pts = []
            for n in signal[ref]:
                if n in net_xy:
                    xs = net_xy[n]
                    pts.append((sum(p[0] for p in xs) / len(xs), sum(p[1] for p in xs) / len(xs)))
            if pts:
                tx, ty = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            else:
                tx, ty = fallback(ref)
            rot = 0
            if len(self.fps[ref].Pads()) == 2 and len(pts) == 2:
                rot = 0 if abs(pts[0][0] - pts[1][0]) >= abs(pts[0][1] - pts[1][1]) else 90
            if put_at(ref, tx, ty, rot):
                note(ref)
                place_decaps(ref)
                if len(self.fps[ref].Pads()) >= 5:
                    for n, x, y in self.pads_of(ref):
                        if n in rails and n != "GND":
                            rail_pins.append([n, x, y, 0])
            else:
                left.append(ref)
        for ref in sorted(r for r in refs if not signal[r] and r not in done_dec and r not in left):
            nets = {n for n, _, _ in self.pads_of(ref)} - {"GND"}
            pins = [p for p in rail_pins if p[0] in nets]
            if pins:
                p = min(pins, key=lambda p: p[3])
                p[3] += 1
                tx, ty = p[1], p[2]
            else:
                tx, ty = fallback(ref)
            if not put_at(ref, tx, ty, 0):
                left.append(ref)
        return left

    def pack(self, refs, x0, y0, x1, y1, placed, bottom=True, gap=0.5, step=0.5, extra=()):
        """Greedy first-fit inside a rectangle, avoiding obstacles. Returns refs that did not fit."""
        obs = self.obstacles(placed, bottom) + list(extra)
        left = []
        for ref in refs:
            self.place(ref, 0, 0, 0, bottom)
            l, t, r, btm = self.rect_of(ref)
            w, h = r - l + gap, btm - t + gap
            spot = None
            y = y0
            while y + h <= y1 and spot is None:
                x = x0
                while x + w <= x1:
                    if not any(x < o[2] and x + w > o[0] and y < o[3] and y + h > o[1] for o in obs):
                        spot = (x, y)
                        break
                    x += step
                y += step
            if spot is None:
                left.append(ref)
                continue
            x, y = spot
            self.fps[ref].Move(pcbnew.VECTOR2I(mm(x + gap / 2 - l), mm(y + gap / 2 - t)))
            obs.append((x, y, x + w, y + h))
            placed.add(ref)
        return left

    def put_free(self, ref, tx, ty, rot, bottom, placed, extra=(), gap=0.4, step=0.25, reach=25.0):
        """Free spot nearest to (tx, ty) for the courtyard centre, avoiding parts on the same side,
        every through-hole pad and `extra`. Returns False if none within `reach`."""
        obs = self.obstacles(placed, bottom) + list(extra)
        self.place(ref, 0, 0, rot, bottom)
        l, t, r, b = self.rect_of(ref)
        w, h = r - l + gap, b - t + gap
        k = int(reach / step)
        for _, i, j in sorted((i * i + j * j, i, j) for i in range(-k, k + 1) for j in range(-k, k + 1)):
            x, y = tx + i * step - w / 2, ty + j * step - h / 2
            if x < 0.5 or y < 0.5 or x + w > self.W - 0.5 or y + h > self.D - 0.5:
                continue
            if not any(x < o[2] and x + w > o[0] and y < o[3] and y + h > o[1] for o in obs):
                self.fps[ref].Move(pcbnew.VECTOR2I(mm(x + gap / 2 - l), mm(y + gap / 2 - t)))
                return True
        return False

    def save(self, path):
        ds = self.board.GetDesignSettings()
        ds.SetCopperLayerCount(2)
        ds.m_MinClearance = mm(0.15)            # GCT USB4085 pin rows are 0.15 mm apart (stock footprint)
        ds.m_CopperEdgeClearance = mm(0.2)
        try:
            ds.m_NetSettings.GetDefaultNetclass().SetClearance(mm(0.15))
        except Exception as e:                  # API differs between versions
            print("netclass clearance not set:", e)
        self.board.SetFileName(str(path))
        pcbnew.SaveBoard(str(path), self.board)
