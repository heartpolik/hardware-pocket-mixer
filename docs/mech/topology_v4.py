"""Topology v4 of the analog board: where the big bipolar capacitors go (hw/pcb/build_pcb.py
uep_plan) against the real courtyards of the placed mechanical parts, with the audio paths
jack -> capacitor -> DIP / fader. Writes docs/mech/topology-v4.svg and prints the checks.

Run with KiCad's Python (reads hw/analog/analog.kicad_pcb and the schematic netlist):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      docs/mech/topology_v4.py
"""
import math
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hw" / "pcb"))
import build_pcb as bp  # noqa: E402

UEP = {"10u": (5.0, 2.0), "47u": (6.3, 2.5)}          # body d, lead pitch (gen_footprints.py)
BODY0, BODY1 = 1.5, 14.0                               # body along the direction, from the leads
PAD_R = 0.8
SCALE = 5.0
COLORS = {"IN1": "#d33", "IN2": "#e80", "IN3": "#2a2", "IN4": "#28c", "RET": "#a3c",
          "MAIN": "#555", "SEND": "#963", "MASTER": "#088"}
# current routed lengths of the jack->cap nets (hw/analog/route/analog_routed_fixed1, 25.10.2026)


def mmv(v):
    return pcbnew.ToMM(v)


def courtyards(board):
    """[(ref, side, (x0, y0, x1, y1))] in board mm, for the parts that stay where they are."""
    out = []
    for f in board.GetFootprints():
        fid = f.GetFPIDAsString()
        if "UEP" in fid:
            continue
        smd = f.GetAttributes() & pcbnew.FP_SMD
        keep = not smd or any(k in fid for k in ("CTS_204", "SJ-43514", "MSK12C02", "USB4085"))
        if not keep:
            continue
        side = "B" if f.IsFlipped() else "F"
        bb = f.GetCourtyard(pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd).BBox()
        r = tuple(mmv(v) - o for v, o in ((bb.GetLeft(), bp.OX), (bb.GetTop(), bp.OY),
                                          (bb.GetRight(), bp.OX), (bb.GetBottom(), bp.OY)))
        out.append((f.GetReference(), side, r, bool(smd)))
    return out


def cap_geometry(x, y, direction, d, pitch):
    """Body rectangle (with the 0.25 courtyard margin) and the two lead pad centres."""
    w = d / 2 + 0.25
    a, b = BODY0, BODY1
    if direction == "-x":
        body = (x - b, y - w, x - a, y + w)
        pads = [(x, y - pitch / 2), (x, y + pitch / 2)]
    elif direction == "+x":
        body = (x + a, y - w, x + b, y + w)
        pads = [(x, y - pitch / 2), (x, y + pitch / 2)]
    elif direction == "+y":
        body = (x - w, y + a, x + w, y + b)
        pads = [(x - pitch / 2, y), (x + pitch / 2, y)]
    else:
        body = (x - w, y - b, x + w, y - a)
        pads = [(x - pitch / 2, y), (x + pitch / 2, y)]
    return body, pads


def overlap(r, s):
    return r[0] < s[2] and r[2] > s[0] and r[1] < s[3] and r[3] > s[1]


def channel(nets):
    for ch in ("IN1", "IN2", "IN3", "IN4", "RET", "MAIN", "SEND"):
        if any(n.startswith(ch + "_") for n in nets):
            return ch
    return "MASTER"


def pads_of(board, net):
    n = board.FindNet("/" + net)
    return [p for p in board.GetPads() if n and p.GetNetCode() == n.GetNetCode()]


def xy(p):
    q = p.GetPosition()
    return mmv(q.x) - bp.OX, mmv(q.y) - bp.OY


def main():
    board = pcbnew.LoadBoard(str(ROOT / "hw" / "analog" / "analog.kicad_pcb"))
    comps = bp.netlist(ROOT / "hw" / "analog" / "analog.kicad_sch")
    plan = bp.uep_plan(comps)
    cys = courtyards(board)

    caps, problems, paths = [], [], []
    for ref, (x, y, direction, bottom) in sorted(plan.items(), key=lambda kv: kv[1]):
        c = comps[ref]
        d, pitch = UEP["47u" if c["value"].startswith("47") else "10u"]
        body, pads = cap_geometry(x, y, direction, d, pitch)
        nets = [c["pins"].get("1", "").lstrip("/"), c["pins"].get("2", "").lstrip("/")]
        side = "B" if bottom else "F"
        ch = channel(nets)
        caps.append((ref, c["value"], side, body, pads, nets, ch))
        # checks: body vs parts on its side; leads (through-hole) vs parts on both sides
        if body[0] < 0.5 or body[2] > bp.W - 0.5 or body[1] < 0.5 or body[3] > bp.D - 0.5:
            problems.append(f"{ref}: body outside the board")
        if bottom and body[3] > bp.BATT_Y0:
            problems.append(f"{ref}: body in the battery zone")
        for oref, oside, r, smd in cys:
            if oside == side and overlap(body, r):
                problems.append(f"{ref}: body over {oref} ({oside})")
            for px, py in pads:
                pr = (px - PAD_R - 0.2, py - PAD_R - 0.2, px + PAD_R + 0.2, py + PAD_R + 0.2)
                if overlap(pr, r) and not (smd and oside != side):
                    problems.append(f"{ref}: lead under {oref} ({oside})")
        for i, (ref2, _, side2, body2, pads2, _, _) in enumerate(caps[:-1]):
            if side2 == side and overlap(body, body2):
                problems.append(f"{ref}: body over {ref2}")
        # audio path: jack-side net to its pads, cap-side net to the DIP / fader / buffer pads
        for k, net in enumerate(nets):
            lead = pads[k]
            for p in pads_of(board, net):
                f = p.GetParentFootprint()
                if f.GetReference() == ref:
                    continue
                if f.GetAttributes() & pcbnew.FP_SMD and "CTS_204" not in f.GetFPIDAsString() \
                        and "SJ-43514" not in f.GetFPIDAsString():
                    continue                    # SMD around the path is re-placed by build_pcb.py
                q = xy(p)
                paths.append((ch, lead, q, math.dist(lead, q),
                              f"{ref}.{k + 1} {net} -> {p.GetParentFootprint().GetReference()}.{p.GetNumber()}"))

    # DIP -> fader B top (the R channel after the mono/stereo switch)
    for f in board.GetFootprints():
        if "CTS_204" not in f.GetFPIDAsString():
            continue
        for p in f.Pads():
            net = p.GetNetname().lstrip("/")
            if not net.endswith("_RTOP"):
                continue
            for q in pads_of(board, net):
                if q.GetParentFootprint().GetReference() != f.GetReference():
                    a, b = xy(p), xy(q)
                    paths.append((net.split("_")[0], a, b, math.dist(a, b),
                                  f"{f.GetReference()}.{p.GetNumber()} {net} -> "
                                  f"{q.GetParentFootprint().GetReference()}.{q.GetNumber()}"))

    svg(board, cys, caps, paths)
    print("\n".join(problems) or "no collisions")
    print("\npath (straight line) per net, mm:")
    for ch, a, b, length, s in sorted(paths, key=lambda t: -t[3]):
        print(f"  {length:6.1f}  {s}")


def svg(board, cys, caps, paths):
    W, D = bp.W, bp.D
    gap = 12
    el = []

    def rect(x0, y0, x1, y1, cls, ox=0, style=""):
        el.append(f'<rect class="{cls}" x="{x0 + ox:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" '
                  f'height="{y1 - y0:.2f}" {style}/>')

    def text(x, y, s, cls="t"):
        el.append(f'<text class="{cls}" x="{x:.2f}" y="{y:.2f}">{s}</text>')

    x_oled0, x_enc0 = bp.X["IN4"] + 9.0, bp.X["RET"] - 10.25
    dig = [(0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, 38.0), (x_enc0, 38.0), (x_enc0, 50.0),
           (x_oled0, 50.0), (x_oled0, 20.0), (0.5, 20.0)]
    for side, ox, title in (("F", 0, "ВЕРХ аналогової плати"),
                            ("B", W + gap, "НИЗ (вигляд згори, крізь плату)")):
        rect(0, 0, W, D, "board", ox)
        text(ox, -3, title, "h")
        if side == "F":
            el.append('<polygon class="dig" points="' +
                      " ".join(f"{x + ox:.1f},{y:.1f}" for x, y in dig) + '"/>')
            text(ox + 2, 24, "цифрова плата над (11 мм)", "n")
        else:
            rect(2.0, bp.BATT_Y0, W - 2.0, D - 2.0, "batt", ox)
            text(ox + W / 2, bp.BATT_Y0 + 30, f"2S LiPo: зона від y {bp.BATT_Y0:g} до {D - 2:g} мм", "n")
            text(ox + W / 2, bp.BATT_Y0 + 36, f"({W - 4:.0f} × {D - 2 - bp.BATT_Y0:.0f} мм; "
                 "2 × 1500 mAh вимагають значно менше)", "n")
        for ref, s, r, smd in cys:
            if s == side:
                rect(*r, "part", ox)
                if r[2] - r[0] > 8:
                    text((r[0] + r[2]) / 2 + ox, (r[1] + r[3]) / 2 + 1, ref, "p")
            elif not smd:                       # through-hole parts: their pins come through
                rect(*r, "ghost", ox)
        for ref, value, s, body, pads, nets, ch in caps:
            col = COLORS[ch]
            for px, py in pads:
                el.append(f'<circle class="lead" cx="{px + ox:.2f}" cy="{py:.2f}" r="{PAD_R}" '
                          f'style="fill:{col}"/>')
            if s == side:
                rect(*body, "cap", ox, f'style="fill:{col}"')
                cx, cy = (body[0] + body[2]) / 2, (body[1] + body[3]) / 2
                text(cx + ox, cy + 0.9, ref, "c")
        if True:
            for ch, a, b, length, s in paths:
                el.append(f'<line class="path" x1="{a[0] + ox:.2f}" y1="{a[1]:.2f}" '
                          f'x2="{b[0] + ox:.2f}" y2="{b[1]:.2f}" style="stroke:{COLORS[ch]}"/>')
    lx = 0
    for ch, col in COLORS.items():
        rect(lx, D + 4, lx + 4, D + 7, "cap", 0, f'style="fill:{col}"')
        text(lx + 5, D + 6.6, ch, "l")
        lx += 20
    text(0, D + 13, "Лінії — напрямок кіл до виводів (не доріжки). Контури — courtyard деталей, "
         "що лишаються на місці;", "n")
    text(0, D + 17, "пунктир — THT з іншого боку. Дрібні SMD (резистори, ОП) тут не показані: "
         "build_pcb.py ставить їх поруч із цими виводами.", "n")
    w, h = 2 * W + gap + 8, D + 22
    style = """<style>
      .t,.p,.c,.l,.n,.h{font-family:sans-serif;fill:#222}
      .h{font-size:4px;font-weight:bold} .n{font-size:2.6px;fill:#444} .p{font-size:2.4px;text-anchor:middle;fill:#666}
      .c{font-size:2.2px;text-anchor:middle;fill:#fff;font-weight:bold} .l{font-size:2.8px}
      .board{fill:#f4f8f2;stroke:#363;stroke-width:0.4}
      .dig{fill:#5a8fd8;fill-opacity:0.12;stroke:#36c;stroke-width:0.3;stroke-dasharray:1.5 0.8}
      .batt{fill:#fd8;fill-opacity:0.45;stroke:#a80;stroke-width:0.3}
      .part{fill:#ddd;fill-opacity:0.7;stroke:#777;stroke-width:0.2}
      .ghost{fill:none;stroke:#aaa;stroke-width:0.15;stroke-dasharray:0.6 0.6}
      .cap{fill-opacity:0.85;stroke:#000;stroke-width:0.15} .lead{stroke:#000;stroke-width:0.1}
      .path{stroke-width:0.35;stroke-opacity:0.55}
    </style>"""
    out = Path(__file__).with_name("topology-v4.svg")
    out.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * SCALE:.0f}" '
                   f'height="{(h + 8) * SCALE:.0f}" viewBox="-4 -8 {w} {h + 8}">'
                   f'<rect x="-4" y="-8" width="{w}" height="{h + 8}" fill="#fff"/>{style}'
                   + "".join(el) + "</svg>")
    print("written", out)


if __name__ == "__main__":
    main()
