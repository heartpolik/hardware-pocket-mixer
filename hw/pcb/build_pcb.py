"""Build draft PCBs (hw/analog/analog.kicad_pcb, hw/digital/digital.kicad_pcb) from the schematics.

Run with KiCad's Python (needs pcbnew):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 hw/pcb/build_pcb.py

Draft only: outline, all footprints with nets, mechanical parts at the positions of
docs/mech/layout_v3.py, the rest packed by block (SMD on the bottom side). No routing.
"""
import math
import re
import subprocess
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parents[1]
KICAD_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
OX, OY = 20.0, 20.0                  # board origin on the KiCad page

# --- mechanics, docs/mech/layout_v3.py (D29, D30, D50) -------------------------------
X = {"IN1": 13.0, "IN2": 31.0, "IN3": 49.0, "IN4": 67.0, "ML": 85.0, "MR": 96.0, "RET": 116.5}
W, D = 130.0, 138.5
SEND_Y, PAN_Y = 30.0, 49.0
# D56: Mute row below the faders; the faders move up to the pan row (fader rear end -> the jacks
# and the DIP is 15.5 mm shorter). Courtyards: pan row ends at 56.0, fader body +-30.3, MX +-6.64.
FADER_C = 87.0
MUTE_Y = 125.0
PH_X = 104.5                           # phones jack at the front edge, between master and RET mutes
MUTE_X_RET = 0.5                       # RET mute shifted right of its column, clear of the phones jack
DIP_Y = 23.9                           # D55: per-channel DIP, bottom, between send-rotary pins and tabs
XM = (X["ML"] + X["MR"]) / 2
IB_X, IB_Y = 77.155, 37.0              # interboard connector pin 1 (D48), under the OLED zone
# D59: ESP32-C3 SuperMini flat on the top of the digital board, USB-C at the rear edge (module edge
# on the board edge), between the LED windows of IN4 and RET; the OLED moves forward to clear it.
MCU_X, MCU_Y = XM, 0.5 + 22.52 / 2     # module centre (gen_footprints.py supermini_smd)
OLED_Y = 37.2                          # was 34.65: courtyard 13.9 below the module courtyard (23.27)
DIG_Y1 = 52.0                          # lower edge of the digital board under the OLED (was 50)
REAR = {"IN1": X["IN1"], "IN2": X["IN2"], "IN3": X["IN3"], "IN4": X["IN4"],
        "MAIN": XM, "SEND": (XM + X["RET"]) / 2, "RET": X["RET"]}


# D57: M2 mounting holes, plated, on GND (hw/lib/gen_footprints.py mounting_hole_m2). The same ref
# on both boards = one 11 mm standoff between them. H1 also takes a standoff to the case bottom
# (analog rear strip, outside the battery zone); H3/H4 fix the analog front corners to the case;
# H2 (digital only, next to the encoder) takes a short standoff up to the top panel.
MOUNT_FP = "diy-mixer:MountingHole_2.2mm_M2_Pad_Standoff_2Side"
MOUNT_R = 2.45                         # courtyard radius of MOUNT_FP
MOUNT_HOLES = {"analog": {"H1": (3.8, 15.8), "H3": (4.4, 134.0), "H4": (125.6, 134.0)},
               "digital": {"H1": (3.8, 15.8), "H2": (126.0, 29.0)}}


# Converter blocks (docs/14-kicad.md, 4.1): the IC at a fixed spot on the bottom, its parts packed
# around it pad-to-pin, switching loop first - LT1930 fig. 6, LT1931 fig. 10, TPS62933 12.1-12.2.
# Spots: bottom areas free of mechanical parts - under the rear end of the RET fader (P5, P12) and
# under the digital board (M12).
CONV_IC = {"P5": (112.0, 70.0), "P12": (122.5, 70.0), "M12": (91.0, 26.5)}
HOT = {"SW_P", "SW_N", "N_N", "SW_5", "BST_5"}
CONV_OUT = {"+12V_P", "-12V_P", "+5V"}


def hole_rects(board):
    return [(x - MOUNT_R, y - MOUNT_R, x + MOUNT_R, y + MOUNT_R) for x, y in MOUNT_HOLES[board].values()]


def add_mount_holes(board, which):
    """Put the MOUNT_HOLES of `which` on `board` (replaces earlier ones), pads on GND."""
    for fp in list(board.GetFootprints()):
        if fp.GetFPIDAsString() == MOUNT_FP:
            board.Delete(fp)
    gnd = next(board.FindNet(n) for n in ("/GND", "GND") if board.FindNet(n))
    for ref, (x, y) in MOUNT_HOLES[which].items():
        fp = load_fp(MOUNT_FP)
        fp.SetReference(ref)
        fp.SetValue("M2")
        fp.SetPosition(pt(x, y))
        board.Add(fp)
        for pad in fp.Pads():
            pad.SetNet(gnd)


# --- big bipolar capacitors (Nichicon UEP, lying, D44), docs/mech/topology-v4.svg ----------
# Each cap sits next to the connection it serves: input caps under their own jack (bottom side;
# the battery leaves the rear strip y < BATT_Y0 free), output caps of MAIN/SEND under the digital
# board next to their jacks (top side, 11 mm free). Leads always come up in a spot free on the
# other side too. The master caps (fader wiper -> buffer) stay in the fader gaps at the front end,
# next to the wiper pins. Entry: (lead centre x, y), body direction, side.
BATT_Y0 = 36.0                         # battery zone starts here (bottom side, behind the DIP window)
LEAD_GAP = 7.3                         # input caps: leads between this jack and the next, x = col + 7.3


def uep_plan(comps):
    """{ref: (x, y, direction, bottom)} for every UEP; direction = where the body points from the
    leads ('-x', '+x', '-y', '+y'). Channel and role come from the nets of the capacitor."""
    plan = {}
    for ref, c in comps.items():
        if "UEP" not in c["fp"]:
            continue
        nets = {n.lstrip("/") for n in c["pins"].values()}
        for ch, col in (("IN1", X["IN1"]), ("IN2", X["IN2"]), ("IN3", X["IN3"]),
                        ("IN4", X["IN4"]), ("RET", X["RET"])):
            if f"{ch}_T" in nets or f"{ch}_R" in nets:
                y = 11.5 if f"{ch}_T" in nets else 5.0             # jack: tip pad at the far end
                x = 123.3 if ch == "RET" else col + LEAD_GAP     # RET: strip before the power switch
                plan[ref] = (x, y, "-x", True)                   # body under the jack
        if "MAIN_L" in nets or "MAIN_R" in nets:
            plan[ref] = (83.0 if "MAIN_L" in nets else 91.0, 19.0, "+y", False)
        if "SEND_L" in nets or "SEND_R" in nets:
            plan[ref] = (99.0 if "SEND_L" in nets else 106.5, 19.0, "+y", False)
        if "ML_W" in nets or "MR_W" in nets:                     # wiper (pin 2) is at the front end
            gap = (X["IN4"] + X["ML"]) / 2 if "ML_W" in nets else (X["MR"] + X["RET"]) / 2
            plan[ref] = (gap, FADER_C + 26.0, "-y", False)       # fader gap, body towards the rear
        if ref not in plan:
            raise RuntimeError(f"{ref}: no place planned for nets {sorted(nets)}")
    return plan


def mm(v):
    return pcbnew.FromMM(v)


def place_uep(pcb, ref, x, y, direction, bottom):
    """UEP footprint: leads at the origin, body along local +X. Pick the rotation whose courtyard
    centre lies in `direction` from the leads (on the bottom side the flip mirrors X)."""
    want = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}[direction]
    fp = pcb.fps[ref]
    lay = pcbnew.B_CrtYd if bottom else pcbnew.F_CrtYd
    for rot in (0, 90, 180, 270):
        pcb.place(ref, x, y, rot, bottom)
        fp.BuildCourtyardCaches()
        c = fp.GetCourtyard(lay).BBox().Centre()
        d = (c.x - mm(OX + x), c.y - mm(OY + y))
        if d[0] * want[0] + d[1] * want[1] > mm(5):
            return
    raise RuntimeError(f"{ref}: no rotation points the body {direction}")


def pt(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


# --- netlist -------------------------------------------------------------------------
def netlist(sch):
    out = Path("/tmp") / (Path(sch).stem + ".net")
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


# KiCad 10 ships no 3D model for these library footprints: use the project ones (hw/lib/gen_3d.py)
MODEL_OVERRIDE = {"Button_Switch_Keyboard:SW_Cherry_MX_1.00u_PCB":
                  "${KIPRJMOD}/../lib/diy-mixer.3dshapes/SW_Cherry_MX_1.00u_PCB.step"}


def lib_fp(fpid):
    lib, name = fpid.split(":")
    path = HW / "lib" / "diy-mixer.pretty" if lib == "diy-mixer" else KICAD_FP / f"{lib}.pretty"
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        raise RuntimeError(f"footprint not found: {fpid}")
    return fp


def set_models(fp, fpid):
    """3D models of `fp` = those of the library footprint (or MODEL_OVERRIDE)."""
    models = fp.Models()
    if fpid in MODEL_OVERRIDE:
        models.clear()
        m = pcbnew.FP_3DMODEL()
        m.m_Filename = MODEL_OVERRIDE[fpid]
        models.push_back(m)
    elif fpid.startswith("diy-mixer:"):
        models.clear()
        for m in lib_fp(fpid).Models():
            models.push_back(m)


def load_fp(fpid):
    lib, name = fpid.split(":")
    fp = lib_fp(fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    set_models(fp, fpid)
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

    def place_group(self, ic, members, placed, extra=(), gap=0.2, step=0.25, reach=12.0):
        """Pack a converter block around its IC (already placed): each part goes where its pads land
        nearest to placed pads of the same nets (GND too: to the IC GND pin and the GND pads placed
        before, so the input loop and the diode-to-output-cap loop close on the spot), trying 4
        rotations. Order (TI SLUSEA4D fig. 12-2, LT1930 fig. 6, LT1931 fig. 10): 0.1 uF at VIN,
        bootstrap cap, input cap, inductor, diode; then output, feedback, the rest."""
        obs = [o for o in self.obstacles(placed | {ic}, True)] + list(extra)

        def free(r):
            return all(not (r[0] < o[2] and r[2] > o[0] and r[1] < o[3] and r[3] > o[1]) for o in obs)

        done = [ic]

        def nets(r):
            return {n for n, _, _ in self.pads_of(r)}

        def prio(r):
            n = nets(r)
            kind = {"L": 0, "D": 1, "C": 2, "R": 3}.get(r.rstrip("0123456789"), 4)
            if n & HOT or n == {"VSW", "GND"}:
                c = r.startswith("C")
                v = self.fps[r].GetValue()
                order = (0 if c and n == {"VSW", "GND"} and v.startswith("100n") else
                         1 if c and "BST_5" in n else
                         2 if c and n == {"VSW", "GND"} else
                         3 if r.startswith("L") else 4 if r.startswith("D") else 5)
                return (0, order)
            if n & CONV_OUT:
                return (1, kind)
            if any(x.startswith("FB_") for x in n):
                return (2, kind)
            return (3, kind)

        for ref in sorted(members, key=lambda r: (prio(r), r)):
            my = nets(ref) - {"GND"}
            my = (my & HOT) or my                    # a switching-node part sits by that node
            targets = [(n, x, y) for d in done for n, x, y in self.pads_of(d) if n in my]
            if not targets:
                targets = [(n, x, y) for n, x, y in self.pads_of(ic)]
            # IC pins first: the loop closes at the IC
            ic_t = [t for t in targets if t in self.pads_of(ic)]
            targets = ic_t or targets
            tgt = {}
            for n, x, y in targets:
                tgt.setdefault(n, []).append((x, y))
            # GND closes the critical loop: buck input cap at the IC GND pin; output caps at the GND
            # pads placed before (diode cathode of the inverter, IC GND), weighted x2
            buck = self.fps[ic].GetValue().startswith("TPS")
            wgnd = 0.0
            if "GND" in nets(ref) and (nets(ref) & CONV_OUT or (buck and nets(ref) == {"VSW", "GND"})):
                tgt["GND"] = [(x, y) for d in done for n, x, y in self.pads_of(d) if n == "GND"]
                cathode = [(x, y) for d in done if d.startswith("D") for n, x, y in self.pads_of(d) if n == "GND"]
                wgnd = 2.0 if nets(ref) & CONV_OUT else 1.0
                if nets(ref) & CONV_OUT and cathode:  # LT1931 fig. 10: D1 current returns to the output cap;
                    tgt["GND"] = cathode              # the output current itself is smooth (2nd winding)
                    wgnd = 4.0
            best = None
            for rot in (0, 90, 180, 270):
                self.place(ref, 0, 0, rot, True)
                l, t, r, b = self.rect_of(ref)
                w, h = r - l + gap, b - t + gap
                rel = [(pn, px - l, py - t) for pn, px, py in self.pads_of(ref) if pn in tgt]
                for n, tx, ty in [(n, x, y) for n, pts in tgt.items() for x, y in pts]:
                    for pn, rx, ry in rel:
                        if pn != n:
                            continue
                        x0, y0 = tx - rx - gap / 2, ty - ry - gap / 2   # this pad on this target
                        k = int(reach / step)
                        for d, i, j in sorted((i * i + j * j, i, j) for i in range(-k, k + 1) for j in range(-k, k + 1)
                                              if i * i + j * j <= k * k):
                            rect = (x0 + i * step, y0 + j * step, x0 + i * step + w, y0 + j * step + h)
                            if rect[0] >= 1.0 and rect[2] <= W - 1.0 and rect[1] >= 1.0 and rect[3] <= D - 1.0 and free(rect):
                                # every pad of the part to its nearest target of the same net
                                cost = sum((wgnd if qn == "GND" else 1.0) *
                                           min(math.hypot(rect[0] + gap / 2 + qx - ax, rect[1] + gap / 2 + qy - ay)
                                               for ax, ay in tgt[qn]) for qn, qx, qy in rel)
                                if best is None or cost < best[0]:
                                    best = (cost, rot, rect, l, t)
                                break
            if not best:
                raise RuntimeError(f"no room for {ref} next to {ic}")
            _, rot, rect, l, t = best
            self.place(ref, 0, 0, rot, True)
            self.fps[ref].Move(pcbnew.VECTOR2I(mm(rect[0] + gap / 2 - l), mm(rect[1] + gap / 2 - t)))
            obs.append(rect)
            done.append(ref)

    def pack(self, refs, x0, y0, x1, y1, placed, bottom=True, gap=0.5, step=0.5):
        """Greedy first-fit inside a rectangle, avoiding obstacles. Returns refs that did not fit."""
        obs = self.obstacles(placed, bottom)
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

    def save(self, path):
        ds = self.board.GetDesignSettings()
        ds.SetCopperLayerCount(2)
        ds.m_MinClearance = mm(0.15)            # GCT USB4085 pin rows are 0.15 mm apart (stock footprint)
        ds.m_CopperEdgeClearance = mm(0.2)      # SK6812MINI-E cut-out: stock footprint pads close to the cut
        try:
            ds.m_NetSettings.GetDefaultNetclass().SetClearance(mm(0.15))
        except Exception as e:                  # API differs between versions
            print("netclass clearance not set:", e)
        self.board.SetFileName(str(path))
        pcbnew.SaveBoard(str(path), self.board)


def nets_of(comp):
    return {n.lstrip("/") for n in comp["pins"].values()}


def analog():
    comps = netlist(HW / "analog" / "analog.kicad_sch")
    pcb = PCB()
    for ref, c in comps.items():
        pcb.add(ref, c)
    pcb.outline([(0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, D - 0.5), (0.5, D - 0.5)])
    placed = set()

    def put(ref, *a, **k):
        pcb.place(ref, *a, **k)
        placed.add(ref)

    for ref, c in comps.items():
        if ref not in pcb.fps:
            continue
        fpn, p = c["fp"], c["pins"]
        if "SJ-43514" in fpn:                         # jacks: mouth at the rear / front edge
            t = p.get("2", "").lstrip("/")
            key = {"IN1_T": "IN1", "IN2_T": "IN2", "IN3_T": "IN3", "IN4_T": "IN4", "RET_T": "RET",
                   "MAIN_L": "MAIN", "SEND_L": "SEND"}.get(t)
            if key:
                put(ref, REAR[key], 1.5, 270)
            elif t == "PH_L":
                put(ref, PH_X, D - 1.5, 90)
        elif "RS451121400A" in fpn:
            top = p.get("3", "").lstrip("/")
            col = {"SUM_L": "ML", "SUM_R": "MR"}.get(top, top.split("_")[0])
            put(ref, X[col], FADER_C, 90)
        elif "RK14K124" in fpn:
            put(ref, X[p["1"].lstrip("/").split("_")[0]], PAN_Y, 180)
        elif "RK14K12D" in fpn:
            top = p.get("3", "").lstrip("/")
            if top == "SUM_L":
                put(ref, X["RET"], PAN_Y, 180)            # phones volume, under the encoder
            else:
                put(ref, X[top.split("_")[0]], SEND_Y, 180)
        elif "Cherry_MX" in fpn:
            col = p["1"].lstrip("/").replace("BTN_", "")
            x = XM if col == "M" else X[col] + (MUTE_X_RET if col == "RET" else 0.0)
            put(ref, x + 2.54, MUTE_Y - 5.08)              # MX footprint origin is a pin, centre at (-2.54, 5.08)
        elif "CTS_204" in fpn:                        # D55: one per channel, window in the case bottom
            ch = p["3"].lstrip("/").split("_")[0]
            put(ref, X[ch] - (1.0 if ch == "RET" else 0.0), DIP_Y, 90, bottom=True)   # RET: clear of USB-C
        elif "PinSocket_2x12" in fpn:
            put(ref, IB_X, IB_Y, 90)                      # pins along +X, rows at y IB_Y and IB_Y-2.54
        elif "USB4085" in fpn:
            put(ref, W - 6.6, 28.0 + 2.975, 90)            # footprint "PCB Edge" line at local y 6.1
        elif "MSK12C02" in fpn:                       # D51: right wall, between RET jack and USB-C
            put(ref, W - 0.5 - 1.65, 10.0, 270)            # actuator to +X, 1.2 mm past the edge
        elif "PinHeader_1x04" in fpn:
            put(ref, W - 4.0, 82.0, 0)

    # big bipolar capacitors (UEP): next to their connection, uep_plan()
    for ref, (x, y, direction, bottom) in uep_plan(comps).items():
        if ref in pcb.fps:
            place_uep(pcb, ref, x, y, direction, bottom)
            placed.add(ref)

    # converter blocks before the other SMD parts
    blocks = {}
    for grp, (gx, gy) in CONV_IC.items():          # all ICs first: each block packs around the others
        refs = [r for r, c in comps.items() if c.get("group") == grp and r in pcb.fps]
        ic = next(r for r in refs if r.startswith("U"))
        put(ic, gx, gy, 0, bottom=True)
        blocks[ic] = [r for r in refs if r != ic]
    for ic, members in blocks.items():
        pcb.place_group(ic, members, placed, extra=hole_rects("analog"))
        placed.update(members)

    # SMD and the rest: bottom side, by block (net prefix)
    rest = [r for r in pcb.fps if r not in placed]
    groups = {k: [] for k in ("IN1", "IN2", "IN3", "IN4", "RET", "MASTER", "POWER")}
    for ref in rest:
        ns = " ".join(sorted(nets_of(comps[ref])))
        g = "MASTER"
        for k in ("IN1", "IN2", "IN3", "IN4", "RET"):
            if re.search(rf"\b(D_)?{k}_|MTR_{'CH' + k[-1] if k.startswith('IN') else 'RET'}\b|MUTE_{k}\b", ns):
                g = k
                break
        if re.search(r"\b(VSW|SW_P|SW_N|N_N|FB_P|FB_N|SW_5|FB_5|BST_5|EN_5|BAT\+|VBUS|CC1|CC2|USB_D[PN])\b", ns):
            g = "POWER"
        groups[g].append(ref)
    regions = {"IN1": (4.5, 36, 21.5, 136), "IN2": (22.5, 36, 39.5, 136), "IN3": (40.5, 36, 57.5, 136),
               "IN4": (58.5, 23, 75.5, 136), "RET": (107, 75, 128.5, 120),
               "MASTER": (76.5, 52, 106.5, 136), "POWER": (107, 3, 128.5, 74)}
    group_of = {r: g for g, refs in groups.items() for r in refs}

    def fallback(ref):
        x0, y0, x1, y1 = regions[group_of[ref]]
        return (x0 + x1) / 2, (y0 + y1) / 2

    rails = {"GND", "+12VA", "-12VA", "+5V", "+3V3", "VSW", "BAT+", "+12V_P", "-12V_P"}
    decap = {r: c["decouples"] for r, c in comps.items() if c.get("decouples") and r in pcb.fps}
    leftovers = pcb.place_near(rest, placed, (1.0, 1.0, W - 1.0, D - 1.0), rails, fallback,
                               extra=hole_rects("analog"), decap=decap)
    if leftovers:
        leftovers = pcb.pack(leftovers, 1.0, 1.0, W - 1.0, D - 1.0, placed)
    add_mount_holes(pcb.board, "analog")
    sock = next(r for r, c in comps.items() if "PinSocket_2x12" in c["fp"])
    for pad in pcb.fps[sock].Pads():
        SOCKET[pad.GetNumber()] = pad_xy(pcb.fps[sock], pad.GetNumber())
    pcb.save(HW / "analog" / "analog.kicad_pcb")
    return len(pcb.fps), leftovers


def pad_xy(fp, num):
    for pad in fp.Pads():
        if pad.GetNumber() == num:
            c = pad.GetPosition()
            return round(pcbnew.ToMM(c.x) - OX, 2), round(pcbnew.ToMM(c.y) - OY, 2)


SOCKET = {}


def match_header(pcb, ref):
    """Place the bottom-side header so that every pin sits over the same pin of the analog socket."""
    fp = pcb.fps[ref]
    for rot in (0, 90, 180, 270):
        pcb.place(ref, 0, 0, rot, bottom=True)
        p1 = pad_xy(fp, "1")
        fp.Move(pcbnew.VECTOR2I(mm(SOCKET["1"][0] - p1[0]), mm(SOCKET["1"][1] - p1[1])))
        if all(abs(pad_xy(fp, n)[0] - xy[0]) < 0.03 and abs(pad_xy(fp, n)[1] - xy[1]) < 0.03
               for n, xy in SOCKET.items()):
            return
    raise RuntimeError("header orientation not found")


def digital():
    comps = netlist(HW / "digital" / "digital.kicad_sch")
    pcb = PCB()
    for ref, c in comps.items():
        pcb.add(ref, c)
    x_oled0, x_enc0 = X["IN4"] + 9.0, X["RET"] - 10.25
    pcb.outline([(0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, 38.0), (x_enc0, 38.0), (x_enc0, DIG_Y1),
                 (x_oled0, DIG_Y1), (x_oled0, 20.0), (0.5, 20.0)])
    placed = set()
    leds = []
    for ref, c in comps.items():
        fpn = c["fp"]
        if "SuperMini" in fpn:
            pcb.place(ref, MCU_X, MCU_Y, 0)              # top, USB-C toward the rear edge (D59)
        elif "OLED" in fpn:
            pcb.place(ref, XM, OLED_Y, 0)
        elif "EC12D" in fpn:
            pcb.place(ref, X["RET"], 29.0, 0)
        elif "PinHeader_2x12" in fpn:
            match_header(pcb, ref)
        elif "SK6812MINI-E" in fpn:
            leds.append(ref)
            continue
        else:
            continue
        placed.add(ref)
    for ref, col in zip(sorted(leds, key=lambda r: int(r[3:])), ("IN1", "IN2", "IN3", "IN4", "RET")):
        pcb.place(ref, X[col], 6.0, 0, bottom=True)        # reverse mount: body in the cut-out, light up
        placed.add(ref)
    rest = [r for r in pcb.fps if r not in placed]
    off_board = [(0, 20.0, x_oled0 + 0.5, DIG_Y1 + 1), (x_enc0 - 0.5, 38.0, W, DIG_Y1 + 1)]   # outside the "L"
    rails = {"GND", "+5V", "+3V3"}
    decap = {r: c["decouples"] for r, c in comps.items() if c.get("decouples") and r in pcb.fps}
    left = pcb.place_near(rest, placed, (1.0, 1.0, W - 1.0, DIG_Y1 - 0.5), rails, lambda r: (90.0, 12.0),
                          extra=off_board + hole_rects("digital"), decap=decap)
    add_mount_holes(pcb.board, "digital")
    pcb.save(HW / "digital" / "digital.kicad_pcb")
    return len(pcb.fps), left


if __name__ == "__main__":
    print("analog:", analog())
    print("digital:", digital())
