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

sys.path.insert(0, str(Path(__file__).parent))
import pcbkit as K  # noqa: E402
from pcbkit import OX, OY, mm  # noqa: E402

HW = K.HW
_spec = importlib.util.spec_from_file_location("layout", HW.parent / "docs" / "mech" / "layout.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)
W, D = L.W, L.D

MOUNT_FP = "pocket-digital:MountingHole_2.2mm_M2_Pad_Standoff_2Side"
MOUNT_R = 2.45
BATT_ZONE = (L.M + 47.0 - L.BATT[0] / 2 - 0.5, D - 4 - L.BATT[1] - 0.5, 50.0 + L.BATT[0] / 2 + 0.5, D - 3.5)
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


def at_edge(pcb, ref, along, edge, outward, front_pad, bottom, overhang=0.0):
    """Edge part (jack, USB-C, Teensy): rotation that puts `front_pad` on the side of `outward`
    ('-y' rear, '+y' front, '+x' right) of the courtyard centre, courtyard edge `overhang` past the
    board edge, centred at `along` on the other axis."""
    axis, sign = ("y", -1) if outward == "-y" else ("y", 1) if outward == "+y" else ("x", 1)
    fp = pcb.fps[ref]
    for rot in (0, 90, 180, 270):
        pcb.place(ref, 0, 0, rot, bottom)
        l, t, r, b = crt_box(fp)
        px, py = pad_xy(fp, front_pad)
        c = ((l + r) / 2, (t + b) / 2)
        d = (px - c[0], py - c[1])
        long_ok = (r - l) < (b - t) if axis == "y" else (r - l) > (b - t)
        if long_ok and (d[1] if axis == "y" else d[0]) * sign > 0:
            break
    else:
        raise RuntimeError(f"{ref}: no rotation faces {outward}")
    l, t, r, b = crt_box(fp)
    if axis == "y":
        dy = (-overhang - t) if sign < 0 else (edge + overhang - b)
        fp.Move(pcbnew.VECTOR2I(mm(along - (l + r) / 2), mm(dy)))
    else:
        fp.Move(pcbnew.VECTOR2I(mm(edge + overhang - r), mm(along - (t + b) / 2)))


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
    placed = set()

    def nets(ref):
        return {n.lstrip("/") for n in comps[ref]["pins"].values()}

    def put_c(ref, *a, **k):
        at_center(pcb, ref, *a, **k)
        placed.add(ref)

    # ---------------------------------------------------------------- top: controls
    y_lcd = L.M + L.LCD[1] / 2
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
                put_c(ref, L.xs[int(b[4]) - 1], L.y_mute)
            else:
                put_c(ref, *btn_xy[b[4:]])
        elif "Latching" in fpn:
            put_c(ref, L.xm + 7, y_b + 2 * step)
        elif "GMT147" in fpn:
            put_c(ref, L.xm, y_lcd)

    # ---------------------------------------------------------------- bottom: edges
    rear = ["IN1", "IN2", "IN3", "IN4", "MAIN", "AUX", "MIDI"]
    jx = {name: L.M + 6.5 + 14.5 * i for i, name in enumerate(rear)}
    for ref, c in comps.items():
        fpn, p = c["fp"], {k: v.lstrip("/") for k, v in c["pins"].items()}
        if "SJ-43514" in fpn:
            t = p.get("2", "")
            key = {"IN1_T": "IN1", "IN2_T": "IN2", "IN3_T": "IN3", "IN4_T": "IN4", "MAIN_L": "MAIN",
                   "AUX_L": "AUX", "MIDI_SINK": "MIDI"}.get(t)
            if key:
                at_edge(pcb, ref, jx[key], 0.0, "-y", "1", True, 0.5)
            elif t == "PH_L":
                at_edge(pcb, ref, L.xm, D, "+y", "1", True, 0.5)
            placed.add(ref)
        elif "Teensy41" in fpn:
            at_edge(pcb, ref, L.M + L.TEENSY[0] / 2 + 1, D, "+y", "25", True, 0.0)
            placed.add(ref)
        elif "USB4085" in fpn:
            at_edge(pcb, ref, 29.5, W, "+x", "SH", True, 3.05)     # Rev A: board edge at local y 6.1
            placed.add(ref)

    # ---------------------------------------------------------------- bottom: ICs
    ic_at = {"PCM1865": [], "PCM5102A": [], "MCP23017-E/SO": []}
    for ref, c in comps.items():
        if c["value"] in ic_at:
            ic_at[c["value"]].append(ref)
    adc = sorted(ic_at["PCM1865"], key=lambda r: "IN1_LS" not in str(comps[r]["pins"]))
    for ref, x in zip(sorted(ic_at["PCM1865"], key=lambda r: min(n for n in nets(r) if n.startswith("ADC"))),
                      (jx["IN1"] + 7.25, jx["IN3"] + 7.25)):
        put_c(ref, x, 27.5, 90, True)
    for ref in ic_at["PCM5102A"]:
        name = next(x for x in nets(ref) if x.endswith("_CAPP")).split("_")[0]
        x = {"MAIN": jx["MAIN"], "AUX": jx["AUX"], "CUE": L.xm}[name]
        y = 27.5 if name != "CUE" else D - 30.0
        put_c(ref, x, y, 90, True)
    for ref, y in zip(sorted(ic_at["MCP23017-E/SO"]), (52.0, 76.0)):
        put_c(ref, W - 22.0, y, 0, True)
    for ref, c in comps.items():
        v = c["value"]
        if v == "TPA6132A2":
            put_c(ref, L.xm, D - 22.0, 0, True)
        elif v == "TP4056":
            put_c(ref, W - 10.0, 42.0, 0, True)
        elif v == "TPS63802":
            put_c(ref, W - 9.0, 20.0, 0, True)
        elif v == "LP5907MFX-3.3":
            put_c(ref, W - 18.0, 20.0, 0, True)
        elif v == "USBLC6-2SC6":
            put_c(ref, W - 9.0, 33.0, 0, True)
        elif "LiPo" in v:
            put_c(ref, 50.0, D - 8.0, 0, True)

    # ---------------------------------------------------------------- mounting holes (reserved first)
    holes = find_holes(pcb, {"H1": (0, 0), "H2": (W, 0), "H3": (0, D), "H4": (W, D)})
    keep = [(x - MOUNT_R - 0.3, y - MOUNT_R - 0.3, x + MOUNT_R + 0.3, y + MOUNT_R + 0.3)
            for _, x, y in filter(None, holes.values())]

    # ---------------------------------------------------------------- bottom: passives
    rest = [r for r in pcb.fps if r not in placed]
    decap = {r: c["decouples"] for r, c in comps.items() if c.get("decouples") and r in pcb.fps}
    left = pcb.place_near(rest, placed, (1.0, 1.0, W - 1.0, D - 1.0), RAILS, lambda r: (W - 20.0, 30.0),
                          extra=[BATT_ZONE] + keep, decap=decap)
    if left:
        left = pcb.pack(left, 1.0, 1.0, W - 1.0, D - 1.0, placed | set(rest) - set(left))

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
