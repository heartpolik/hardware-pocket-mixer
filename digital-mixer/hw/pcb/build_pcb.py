"""Place the main board (hw/main/main.kicad_pcb) from the schematic, 2 copper layers (DM22).

Run with KiCad's Python (from digital-mixer/):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 hw/pcb/build_pcb.py

Mechanical parts at the positions of docs/mech/layout.py (top: controls; bottom: jacks, Teensy,
electronics, battery zone), ICs by hand next to their connectors, passives by pcbkit.place_near
(connectivity, decoupling caps at their IC pins) on the bottom side outside the battery zone.
M2 mounting holes (DM23) go to the free spots nearest to the corners. No routing here.
"""
import importlib.util
import math
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))
import pcbkit as K  # noqa: E402
from pcbkit import OX, OY, mm  # noqa: E402

HW = Path(__file__).resolve().parents[1]
K.use_project(HW, "pocket-digital")
_spec = importlib.util.spec_from_file_location("layout", HW.parent / "docs" / "mech" / "layout.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)
W, D = L.W, L.D

MOUNT_FP = "pocket-digital:MountingHole_2.2mm_M2_Pad_Standoff_2Side"
MOUNT_R = 2.45
BATT_ZONE = (L.BATT_C[0] - L.BATT[0] / 2 - 0.5, L.BATT_C[1] - L.BATT[1] / 2 - 0.5,
             L.BATT_C[0] + L.BATT[0] / 2 + 0.5, L.BATT_C[1] + L.BATT[1] / 2 + 0.5)
RAILS = {"GND", "+3V3", "+3V3A", "+4V2", "VSYS", "VBUS", "BAT+"}


def crt_box(fp):
    """Courtyard bbox (board mm) on the footprint's own side."""
    fp.BuildCourtyardCaches()
    lay = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
    c = fp.GetCourtyard(lay)
    bb = c.BBox() if c.OutlineCount() else fp.GetBoundingBox(False)
    return (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
            pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)


def at_center(pcb, ref, cx, cy, rot=0, bottom=False):
    """Courtyard centre at (cx, cy)."""
    pcb.place(ref, 0, 0, rot, bottom)
    l, t, r, b = crt_box(pcb.fps[ref])
    pcb.fps[ref].Move(pcbnew.VECTOR2I(mm(cx - (l + r) / 2), mm(cy - (t + b) / 2)))


def pad_xy(fp, num):
    p = next(p for p in fp.Pads() if p.GetNumber() == num)
    return pcbnew.ToMM(p.GetPosition().x) - OX, pcbnew.ToMM(p.GetPosition().y) - OY


def at_edge(pcb, ref, along, edge, outward, front_pad, bottom, overhang=0.0, inner=False, long_axis=True):
    """Edge part (jack, USB-C, Teensy): rotation that puts `front_pad` on the side of `outward`
    ('-y' rear, '+y' front, '+x' right, '-x' left) of the courtyard centre (`inner`: on the other
    side), courtyard edge `overhang` past the board edge, centred at `along` on the other axis."""
    axis, sign = {"-y": ("y", -1), "+y": ("y", 1), "+x": ("x", 1), "-x": ("x", -1)}[outward]
    fp = pcb.fps[ref]
    for rot in (0, 90, 180, 270):
        pcb.place(ref, 0, 0, rot, bottom)
        l, t, r, b = crt_box(fp)
        px, py = pad_xy(fp, front_pad)
        c = ((l + r) / 2, (t + b) / 2)
        d = (px - c[0], py - c[1])
        long_ok = not long_axis or ((r - l) < (b - t) if axis == "y" else (r - l) > (b - t))
        if not long_axis:                           # square-ish part: the pad row lies across the edge normal
            pads = [pad_xy(fp, p.GetNumber()) for p in fp.Pads() if p.GetNumber().startswith("A")]
            spread = (max(x for x, _ in pads) - min(x for x, _ in pads), max(y for _, y in pads) - min(y for _, y in pads))
            long_ok = spread[1] > spread[0] if axis == "x" else spread[0] > spread[1]
        if long_ok and (d[1] if axis == "y" else d[0]) * sign * (-1 if inner else 1) > 0:
            break
    else:
        raise RuntimeError(f"{ref}: no rotation faces {outward}")
    l, t, r, b = crt_box(fp)
    if axis == "y":
        dy = (-overhang - t) if sign < 0 else (edge + overhang - b)
        fp.Move(pcbnew.VECTOR2I(mm(along - (l + r) / 2), mm(dy)))
    else:
        dx = (-overhang - l) if sign < 0 else (edge + overhang - r)
        fp.Move(pcbnew.VECTOR2I(mm(dx), mm(along - (t + b) / 2)))


def put_pad(pcb, ref, num, x, y, rot, bottom=True):
    """Place `ref` so that its pad `num` lands on (x, y)."""
    pcb.place(ref, 0, 0, rot, bottom)
    px, py = pad_xy(pcb.fps[ref], num)
    pcb.fps[ref].Move(pcbnew.VECTOR2I(mm(x - px), mm(y - py)))


def track(pcb, net, pts, width, layer=pcbnew.B_Cu):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(pcb.board)
        t.SetStart(K.pt(x1, y1))
        t.SetEnd(K.pt(x2, y2))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(pcb.net(net))
        t.SetLocked(True)                    # kept by route_pcb.py, exported to Freerouting as fixed
        pcb.board.Add(t)


def converter_block(pcb, comps, placed):
    """TPS63802 (U, already placed) with L, Cin, 2 x Cout as in the datasheet layout example:
    inductor right of pins 9 (L1) / 7 (L2), input cap at pin 10 (VIN), output caps at pin 6 (VOUT),
    every loop a few mm; the short connections are pre-routed and locked. Returns the refs."""
    u = next(r for r, c in comps.items() if c["value"] == "TPS63802")
    lref = next(r for r, c in comps.items() if c["value"].startswith("0.47u"))
    cin = max((r for r, c in comps.items() if c["value"] == "10u" and
               {n.lstrip("/") for n in c["pins"].values()} == {"VSYS", "GND"}), key=lambda r: int(r[1:]))
    couts = sorted(r for r, c in comps.items() if c["value"] == "22u")
    fp = pcb.fps[u]
    p = {n: pad_xy(fp, n) for n in ("6", "7", "8", "9", "10")}
    xr = p["9"][0] + 0.45                     # right edge of the right pad column
    rx = xr + 0.6                             # risers of L1 / L2, clear of VIN / VOUT going straight out
    # inductor: pads (0.98 x 3.4 rotated) as horizontal strips above / below, right of the risers
    lx = rx + 0.125 + 0.2 + 1.7
    put_pad(pcb, lref, "1", lx, p["9"][1] + 1.2, 90)
    if pad_xy(pcb.fps[lref], "2")[1] > pad_xy(pcb.fps[lref], "1")[1]:
        put_pad(pcb, lref, "1", lx, p["9"][1] + 1.2, 270)
    l1, l2 = pad_xy(pcb.fps[lref], "1"), pad_xy(pcb.fps[lref], "2")
    # input cap below the inductor strip, output caps above
    put_pad(pcb, cin, "1" if comps[cin]["pins"]["1"].endswith("VSYS") else "2", xr - 0.2, l1[1] + 2.4, 0)
    cy = l2[1] - 2.4
    for c in couts:
        put_pad(pcb, c, "1" if comps[c]["pins"]["1"].endswith("+4V2") else "2", xr - 0.2, cy, 0)
        cy -= 2.6
    placed |= {lref, cin, *couts}
    vin = pad_xy(pcb.fps[cin], next(n for n, v in comps[cin]["pins"].items() if v.endswith("VSYS")))
    vo = [pad_xy(pcb.fps[c], next(n for n, v in comps[c]["pins"].items() if v.endswith("+4V2"))) for c in couts]
    track(pcb, "/BB_L1", [p["9"], (rx, p["9"][1]), (rx, l1[1]), (l1[0], l1[1])], 0.25)
    track(pcb, "/BB_L2", [p["7"], (rx, p["7"][1]), (rx, l2[1]), (l2[0], l2[1])], 0.25)
    track(pcb, "/VSYS", [p["10"], (p["10"][0], vin[1])], 0.25)
    track(pcb, "/VSYS", [(p["10"][0], vin[1]), vin], 0.5)
    track(pcb, "/+4V2", [p["6"], (p["6"][0], vo[0][1])], 0.25)
    track(pcb, "/+4V2", [(p["6"][0], vo[0][1]), vo[0], vo[1]], 0.5)
    return [lref, cin, *couts]


def find_holes(pcb, corners, clear=0.3):
    """Free spot nearest to each corner: hole courtyard r 2.45 + clear from every courtyard (both
    sides: a standoff or screw head sits on each) and from the board edge."""
    boxes = [crt_box(fp) for fp in pcb.fps.values()]
    for fp in pcb.fps.values():                       # THT pads poke through to the other side
        for p in fp.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                bb = p.GetBoundingBox()
                boxes.append((pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                              pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY))
    rr = MOUNT_R + clear
    out = {}
    for name, (cx, cy) in corners.items():
        best = None
        for i in range(0, 120):
            for j in range(0, 120):
                x = cx + (i * 0.5 if cx < W / 2 else -i * 0.5)
                y = cy + (j * 0.5 if cy < D / 2 else -j * 0.5)
                if not (rr <= x <= W - rr and rr <= y <= D - rr):
                    continue
                if any(x + rr > l and x - rr < r and y + rr > t and y - rr < b for l, t, r, b in boxes):
                    continue
                d = math.hypot(x - cx, y - cy)
                if best is None or d < best[0]:
                    best = (d, x, y)
        out[name] = best
    return out


def main():
    comps = K.netlist(HW / "main" / "main.kicad_sch")
    pcb = K.PCB()
    for ref, c in comps.items():
        pcb.add(ref, c)
    pcb.outline([(0, 0), (W, 0), (W, D), (0, D)])
    pcb.W, pcb.D = W, D
    placed = set()

    def nets(ref):
        return {n.lstrip("/") for n in comps[ref]["pins"].values()}

    def put_c(ref, *a, **k):
        at_center(pcb, ref, *a, **k)
        placed.add(ref)

    # ---------------------------------------------------------------- top: controls
    y_lcd = L.y0 + L.LCD[1] / 2
    y_me = y_lcd + L.LCD[1] / 2 + L.GAP + L.ENC[1] / 2
    y_b = y_me + L.ENC[1] / 2 + L.GAP + L.CAP[1] / 2
    step = L.CAP[1] + L.GAP
    btn_xy = {"FX1": (L.xm - 7, y_b), "FX2": (L.xm + 7, y_b), "AUX": (L.xm - 7, y_b + step),
              "CUE": (L.xm + 7, y_b + step), "SHIFT": (L.xm - 7, y_b + 2 * step)}
    for ref, c in comps.items():
        fpn, n = c["fp"], nets(ref)
        if "EC11E-Switch" in fpn:
            put_c(ref, L.xm, y_me)
        elif "EC11E" in fpn:                                   # ENC<ch>_<k>_A
            a = next(x for x in n if x.startswith("ENC") and x.endswith("_A"))
            ch, k = int(a[3]), int(a.split("_")[1])
            put_c(ref, L.xs[ch - 1], L.y_enc[k - 1])
        elif "PTA2043" in fpn:
            ch = int(next(x for x in n if x.startswith("FADER"))[5])
            put_c(ref, L.xs[ch - 1], L.y_fader, 90)
        elif "TSF-1266" in fpn:
            b = next(x for x in n if x.startswith(("MUTE", "BTN_")))
            if b.startswith("MUTE"):
                put_c(ref, L.xs[int(b[4]) - 1] + L.MUTE_DX[int(b[4]) - 1], L.y_mute)
            else:
                put_c(ref, *btn_xy[b[4:]])
        elif "Latching" in fpn:
            put_c(ref, *L.LATCH_XY)
        elif "GMT147" in fpn:
            put_c(ref, L.xm, y_lcd)

    # ---------------------------------------------------------------- bottom: edges
    rear = ["IN1", "IN2", "IN3", "IN4", "MAIN", "AUX", "MIDI"]
    jx = dict(zip(rear, L.JX))
    for ref, c in comps.items():
        fpn, p = c["fp"], {k: v.lstrip("/") for k, v in c["pins"].items()}
        if "SJ-43514" in fpn:
            t = p.get("2", "")
            key = {"IN1_T": "IN1", "IN2_T": "IN2", "IN3_T": "IN3", "IN4_T": "IN4", "MAIN_L": "MAIN",
                   "AUX_L": "AUX", "MIDI_SINK": "MIDI"}.get(t)
            if key:
                at_edge(pcb, ref, jx[key], 0.0, "-y", "1", True, 0.5)
            elif t == "PH_L":
                at_edge(pcb, ref, L.PH_X, D, "+y", "1", True, 0.5)          # pegs between Mute 1 and Mute 2
            placed.add(ref)
        elif "Teensy41" in fpn:
            at_edge(pcb, ref, L.T_Y0 + L.TEENSY[0] / 2, W, "+x", "25", True, 0.0)    # microSD end right
            placed.add(ref)
        elif "USB4085" in fpn:
            # GCT USB4085: contact rows at local y 0 / 1.35 inside, PCB edge line at local y 6.1,
            # courtyard to 9.15 -> 3.05 past the edge (as in Rev A)
            pcb.place(ref, 0, 0, 0, True)
            # front edge next to the Teensy USB end (D+/D- short for 480 Mbit/s), left of PHONES
            at_edge(pcb, ref, L.USB_X, D, "+y", "A1", True, 3.05, inner=True, long_axis=False)
            placed.add(ref)

    # ---------------------------------------------------------------- mounting holes (reserved first)
    holes = find_holes(pcb, {"H1": (0, 0), "H2": (W, 0), "H3": (0, D), "H4": (W, D)})
    keep = [(x - MOUNT_R - 0.3, y - MOUNT_R - 0.3, x + MOUNT_R + 0.3, y + MOUNT_R + 0.3)
            for _, x, y in filter(None, holes.values())]

    # ---------------------------------------------------------------- bottom: ICs (right column)
    xm, y0 = L.xm, L.y0

    def put_ic(ref, x, y, rot):
        if not pcb.put_free(ref, x, y, rot, True, placed, extra=[BATT_ZONE] + keep):
            raise RuntimeError(f"no room for {ref} near ({x}, {y})")
        placed.add(ref)

    ic_at = {"PCM1865": [], "PCM5102A": [], "MCP23017-E/SO": []}
    for ref, c in comps.items():
        if c["value"] in ic_at:
            ic_at[c["value"]].append(ref)
    for ref, x in zip(sorted(ic_at["PCM1865"], key=lambda r: min(n for n in nets(r) if n.startswith("ADC"))),
                      (xm - 7.0, xm + 7.0)):
        put_ic(ref, x, y0 + 24.0, 90)
    for ref in ic_at["PCM5102A"]:
        name = next(x for x in nets(ref) if x.endswith("_CAPP")).split("_")[0]
        put_ic(ref, xm + {"MAIN": -9.0, "AUX": 0.0, "CUE": 9.0}[name], y0 + 40.0, 90)
    for ref, y in zip(sorted(ic_at["MCP23017-E/SO"]), (y0 + 56.0, y0 + 70.0)):
        put_ic(ref, xm, y, 0)
    for ref, c in comps.items():
        v = c["value"]
        if v == "TPA6132A2":
            put_ic(ref, xm, D - 24.0, 0)
        elif v == "TP4056":
            put_ic(ref, xm - 6.0, y0 + 9.0, 0)
        elif v == "TPS63802":
            put_ic(ref, xm + 6.0, y0 + 13.5, 0)       # output caps clear of the display standoff holes
        elif v == "LP5907MFX-3.3":
            put_ic(ref, xm - 6.0, y0 + 2.0, 0)
        elif v == "USBLC6-2SC6":
            put_ic(ref, L.USB_X, D - 14.0, 0)
        elif "LiPo" in v:                       # through-hole: clear of the top courtyards as well
            top = [crt_box(pcb.fps[r]) for r in placed if not pcb.fps[r].IsFlipped()]
            if not pcb.put_free(ref, L.BATT_C[0] + L.BATT[0] / 2 + 3.0, L.BATT_C[1], 90, True, placed,
                                extra=[BATT_ZONE] + keep + top):
                raise RuntimeError("no room for the battery connector")
            placed.add(ref)

    # ---------------------------------------------------------------- buck-boost block (TI SLVSEU9D 10.2)
    conv = converter_block(pcb, comps, placed)

    # ---------------------------------------------------------------- bottom: passives
    rest = [r for r in pcb.fps if r not in placed]
    decap = {r: c["decouples"] for r, c in comps.items() if c.get("decouples") and r in pcb.fps}
    left = pcb.place_near(rest, placed, (1.0, 1.0, W - 1.0, D - 1.0), RAILS, lambda r: (L.xm, D / 2),
                          extra=[BATT_ZONE] + keep, decap=decap)
    if left:
        left = pcb.pack(left, 1.0, 1.0, W - 1.0, D - 1.0, placed | set(rest) - set(left),
                        extra=[BATT_ZONE] + keep)

    gnd = pcb.net("/GND")
    for name, spot in holes.items():
        if not spot:
            print(f"{name}: no free spot")
            continue
        fp = K.load_fp(MOUNT_FP)
        fp.SetReference(name)
        fp.SetValue("M2")
        fp.SetPosition(K.pt(spot[1], spot[2]))
        pcb.board.Add(fp)
        for pad in fp.Pads():
            pad.SetNet(gnd)
        print(f"{name}: ({spot[1]:.1f}, {spot[2]:.1f}), {spot[0]:.1f} mm from the corner")

    pcb.save(HW / "main" / "main.kicad_pcb")
    print(f"main.kicad_pcb: {len(pcb.fps)} footprints, {W:.1f} x {D:.1f} mm, not placed: {left}")


if __name__ == "__main__":
    main()
