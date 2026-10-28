"""Place the main board (hw/main/main.kicad_pcb) from the schematic, 2 copper layers (DM22).

Run with KiCad's Python (from digital-mixer/); routed on 4 layers by common/route_pcb.py --layers 4 (DM31):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 hw/pcb/build_pcb.py

Mechanical parts at the positions of docs/mech/layout.py (layout C, DM25: top - controls and the
display; bottom - jacks, USB-C, Teensy, electronics, battery zone), ICs by hand next to their
connectors, passives by common/pcbkit.place_near (connectivity, decoupling caps at their IC pins) on
the bottom side outside the battery zone.
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
MODEL_OVERRIDE = {
    "USB_C_Receptacle_GCT_USB4110": "OWN/USB_C_Receptacle_GCT_USB4110.step",
    "Potentiometer_Bourns_PTA2043_Single_Slide": "OWN/Potentiometer_Bourns_PTA2043_Single_Slide.step",
    "JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal": "OWN/JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal.step",
    # TP4056: same SOIC-8 body, only the exposed pad differs
    "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.3mm":
        "${KICAD10_3DMODEL_DIR}/Package_SO.3dshapes/SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.81mm.step",
}
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


def via(pcb, net, x, y, d=0.6, drill=0.3):
    v = pcbnew.PCB_VIA(pcb.board)
    v.SetPosition(K.pt(x, y))
    v.SetWidth(mm(d))
    v.SetDrill(mm(drill))
    v.SetNet(pcb.net(net))
    v.SetLocked(True)
    pcb.board.Add(v)


def usb_pair(pcb, comps):
    """USB D+ / D- from the USBLC6 toward the Teensy wire pads 67 / 66 as a coupled pair (DM25 puts
    them ~75 mm apart): 0.2 tracks, 0.2 gap, on F.Cu over the In1 GND plane (DM31) along the right
    column - between the left lug of MASTER and the S1 pad / the AUX, FX I, FX II pads - down to 2.3 mm
    before the wire pads at the Teensy USB end (DM35). Locked, so Freerouting routes the rest around
    it; the last few mm to the pads (on B.Cu, where they are) are left to the router / patch_route.py.
    Returns keep-out boxes of its vias for the bottom-side placement."""
    esd = next(r for r, c in comps.items() if c["value"] == "USBLC6-2SC6")
    teensy = next(r for r, c in comps.items() if "Teensy41" in c["fp"])
    master = next(r for r, c in comps.items() if "EC12SY" in c["fp"] and "/ENC_M_A" in c["pins"].values())
    btn = [r for r, c in comps.items() if "TSF-1266" in c["fp"] and
           any(v.lstrip("/") in ("BTN_AUX", "BTN_FX1", "BTN_FX2") for v in c["pins"].values())]
    dp_pin = pad_xy(pcb.fps[esd], next(n for n, v in comps[esd]["pins"].items() if v.endswith("USB_DP")))
    dn_pin = pad_xy(pcb.fps[esd], next(n for n, v in comps[esd]["pins"].items() if v.endswith("USB_DN")))
    wire_top = min(pcbnew.ToMM(p.GetBoundingBox().GetTop()) - OY for p in pcb.fps[teensy].Pads()
                   if p.GetNumber() in ("66", "67"))
    lug_r = max(pcbnew.ToMM(p.GetBoundingBox().GetRight()) - OX for p in pcb.fps[master].Pads()
                if p.GetNumber() == "MP" and pcbnew.ToMM(p.GetPosition().x) - OX < L.xr)
    pad_l = min(pcbnew.ToMM(p.GetBoundingBox().GetLeft()) - OX for r in btn for p in pcb.fps[r].Pads())
    h, w = 0.2, 0.2                                    # half pitch, track width: 0.2 gap (90 ohm - ОЦІНКА)
    xc = (lug_r + pad_l) / 2                           # corridor axis
    y_end = wire_top - 2.3                             # stop short of the wire pads
    vx = dp_pin[0] + 1.16                              # vias right of the ESD pins, 0.2 to them and to the USB-C tab
    for net, pin, y_via in (("/USB_DP", dp_pin, dp_pin[1]), ("/USB_DN", dn_pin, dn_pin[1])):
        via(pcb, net, vx, y_via)
        track(pcb, net, [pin, (vx, y_via)], w, pcbnew.B_Cu)
    xs_p, xs_n = xc - h, xc + h
    yfirst = dn_pin[1] + 0.34
    track(pcb, "/USB_DP", [(vx, dp_pin[1]), (xs_p, dp_pin[1]), (xs_p, y_end)], w, pcbnew.F_Cu)
    track(pcb, "/USB_DN", [(vx, dn_pin[1]), (vx + 0.34, yfirst), (xs_n, yfirst), (xs_n, y_end)], w, pcbnew.F_Cu)
    r = 0.3 + 0.4
    return [(vx - r, y - r, vx + r, y + r) for y in (dp_pin[1], dn_pin[1])]


def find_holes(pcb, corners, clear=0.3):
    """Free spot nearest to each corner: hole courtyard r 2.45 + clear from every courtyard (both
    sides: a standoff or screw head sits on each) and from the board edge."""
    boxes, shapes = [], []                            # courtyard bboxes; polygons tested exactly
    for fp in pcb.fps.values():
        fp.BuildCourtyardCaches()
        c = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        (shapes.append((crt_box(fp), c)) if c.OutlineCount() else boxes.append(crt_box(fp)))
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
                if any(x + rr > l and x - rr < r and y + rr > t and y - rr < b and c.Collide(K.pt(x, y), mm(rr))
                       for (l, t, r, b), c in shapes):
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

    # ---------------------------------------------------------------- top: controls (layout C, DM25)
    btn_y = dict(zip(("AUX", "FX1", "FX2", "SHIFT"), L.Y_BTN))
    for ref, c in comps.items():
        fpn, n = c["fp"], nets(ref)
        if "EC12SY" in fpn:
            if "ENC_M_A" in n:
                put_c(ref, L.xr, L.Y_TOP)
            else:                                              # ENC<ch>_<k>_A
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
            else:                                              # signal pad (1) away from the USB pair
                put_c(ref, L.xr, btn_y[b[4:]], 0 if b == "BTN_SHIFT" else 180)
        elif "Latching" in fpn:
            put_c(ref, L.X_ON, L.Y_TOP)
        elif "GMT147" in fpn:
            # landscape; header on the left, its pins between the IN1 and IN2 jacks underneath
            for rot in (90, 270):
                put_c(ref, L.X_LCD, L.Y_TOP, rot)
                if pad_xy(pcb.fps[ref], "1")[0] < L.X_LCD:
                    break

    # ---------------------------------------------------------------- bottom: edges
    outs = {"MAIN_L": 0, "AUX_L": 1, "MIDI_SINK": 2, "PH_L": 3}
    for ref, c in comps.items():
        fpn, p = c["fp"], {k: v.lstrip("/") for k, v in c["pins"].items()}
        if "PJ-327A" in fpn:
            # PJ-327A (DM38): body front on the board edge, the nose (2.0) and courtyard margin past it
            t = p.get("4", "")                      # tip
            if t.startswith("IN"):
                at_edge(pcb, ref, L.xs[int(t[2]) - 1], 0.0, "-y", "1", True, 2.25)
            else:
                at_edge(pcb, ref, L.y_out[outs[t]], W, "+x", "1", True, 2.25)
            placed.add(ref)
        elif "Teensy41" in fpn:
            at_edge(pcb, ref, L.T_X, D, "+y", "25", True, -L.T_BACK)       # microSD end 6 mm off the front (DM35)
            placed.add(ref)
        elif "USB4110" in fpn:
            # GCT USB4110 (all SMD): PCB edge line at local y 3.675 (KiCad footprint), courtyard to
            # 4.18 -> 0.505 past the edge; rear wall under MASTER (DM25)
            pcb.place(ref, 0, 0, 0, True)
            at_edge(pcb, ref, L.USB_X, 0.0, "-y", "A1", True, 0.505, inner=True, long_axis=False)

            placed.add(ref)

    # ---------------------------------------------------------------- mounting holes (reserved first)
    holes = find_holes(pcb, {"H1": (0, 0), "H2": (W, 0), "H3": (0, D), "H4": (W, D)})
    keep = [(x - MOUNT_R - 0.3, y - MOUNT_R - 0.3, x + MOUNT_R + 0.3, y + MOUNT_R + 0.3)
            for _, x, y in filter(None, holes.values())]

    # ---------------------------------------------------------------- bottom: ICs
    # power by the USB-C (rear right), DACs and the headphone amp between the Teensy and the output
    # jacks, ADCs under the faders next to the Teensy, expanders under the Mute row (layout C)
    def put_ic(ref, x, y, rot):
        if not pcb.put_free(ref, x, y, rot, True, placed, extra=[BATT_ZONE] + keep):
            raise RuntimeError(f"no room for {ref} near ({x}, {y})")
        placed.add(ref)

    xp = L.xs[-1] + 2.0                       # the strip right of the battery
    ic_at = {"PCM1865": [], "PCM5102A": [], "MCP23017-E/SO": []}
    for ref, c in comps.items():
        if c["value"] in ic_at:
            ic_at[c["value"]].append(ref)
    yf = L.y_fader
    for ref, x in zip(sorted(ic_at["PCM1865"], key=lambda r: min(n for n in nets(r) if n.startswith("ADC"))),
                      (L.xs[2] - 2.0, L.xs[3] - 1.0)):
        put_ic(ref, x, yf, 0)
    for ref in ic_at["PCM5102A"]:
        name = next(x for x in nets(ref) if x.endswith("_CAPP")).split("_")[0]
        put_ic(ref, xp + 3.0, {"MAIN": 41.0, "AUX": 53.0, "CUE": 65.0}[name], 90)
    # #1, #2 (channel encoders 1-2, 3-4) left to right, #3 (encoder switches, AUX / FX buttons) nearest
    # the right column
    mcp = sorted(ic_at["MCP23017-E/SO"], key=lambda r: next(n for n in nets(r) if n.startswith("MCP")))
    for ref, x in zip(mcp, (L.xs[0] + 6.0, L.xs[1] + 8.0, L.xs[2] + 8.0)):
        put_ic(ref, x, L.y_mute + 1.0, 270)          # pins 1-14 (GPB, SCL / SDA) inward, not at the edge
    for ref, c in comps.items():
        v = c["value"]
        if v == "TPA6132A2":
            # clear of the Teensy end; 180 deg: OUTL / OUTR face the PHONES jack, so they do not cross
            # the supply pin 14 next to them
            put_ic(ref, L.T_X - 8.0, L.y_out[3] + 2.0, 180)
        elif v == "TP4056":
            put_ic(ref, L.USB_X - 13.0, 12.0, 0)
        elif v == "TPS63802":
            put_ic(ref, xp + 0.0, 27.0, 0)
        elif v == "LP5907MFX-3.3":
            put_ic(ref, L.xs[2] + 9.0, yf, 0)
        elif v == "USBLC6-2SC6":
            put_ic(ref, L.USB_X - 7.0, 8.0, 0)
        elif "LiPo" in v:
            put_ic(ref, L.BATT_C[0] + L.BATT[0] / 2 + 4.0, L.BATT_C[1] + 10.0, 90)

    # headphone amp input caps right at its IN- pins (WQFN 0.5 pitch: no room to reach them later)
    tpa = next(r for r, c in comps.items() if c["value"] == "TPA6132A2")
    for ref, c in comps.items():
        hp = next((n for n in nets(ref) if n in ("HP_INL", "HP_INR")), None)
        if hp and ref != tpa:
            x, y = next((x, y) for n, x, y in pcb.pads_of(tpa) if n == hp)
            if not pcb.put_free(ref, x, y, 0, True, placed, extra=[BATT_ZONE] + keep, reach=6.0):
                raise RuntimeError(f"no room for {ref} at the headphone amp")
            placed.add(ref)

    # series resistors of the I2S / TDM clocks right at their Teensy pins (DM29)
    teensy = next(r for r, c in comps.items() if "Teensy41" in c["fp"])
    for ref, c in comps.items():
        ns = nets(ref)
        src = next((n for n in ns if n.endswith("_T") and n[:-2] in ns), None)
        if src:
            x, y = next((x, y) for n, x, y in pcb.pads_of(teensy) if n == src)
            if not pcb.put_free(ref, x, y, 0, True, placed, extra=[BATT_ZONE] + keep, reach=8.0):
                raise RuntimeError(f"no room for {ref} at the Teensy")
            placed.add(ref)

    # ---------------------------------------------------------------- buck-boost block (TI SLVSEU9D 10.2)
    conv = converter_block(pcb, comps, placed)

    # ---------------------------------------------------------------- USB D+ / D- pair, pre-routed
    keep += usb_pair(pcb, comps)

    # ---------------------------------------------------------------- bottom: passives
    rest = [r for r in pcb.fps if r not in placed]
    decap = {r: c["decouples"] for r, c in comps.items() if c.get("decouples") and r in pcb.fps}
    left = pcb.place_near(rest, placed, (1.0, 1.0, W - 1.0, D - 1.0), RAILS, lambda r: (L.xs[-1], D / 2),
                          extra=[BATT_ZONE] + keep, decap=decap)
    if left:
        left = pcb.pack(left, 1.0, 1.0, W - 1.0, D - 1.0, placed | set(rest) - set(left),
                        extra=[BATT_ZONE] + keep)

    # stock footprints whose KiCad model is not shipped: ours (hw/lib/gen_3d.py) or one of the same body
    own = "${KIPRJMOD}/../lib/pocket-digital.3dshapes/"
    for fp in pcb.fps.values():
        name = fp.GetFPID().GetLibItemName().wx_str()
        if name in MODEL_OVERRIDE and fp.Models().size():
            fp.Models()[0].m_Filename = MODEL_OVERRIDE[name].replace("OWN/", own)

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
