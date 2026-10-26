"""Audio routing review of the routed analog board (read-only): what DRC does not check.

Run with KiCad's Python:  hw/pcb/audio_review.py [--board <b>.kicad_pcb] [--json out.json] [--svg map.svg]

1. Audio next to aggressors: switching nodes of the converters and digital lines. Same layer:
   coupled length closer than SAME_GAP. In2 <-> B.Cu (no plane between them, ~0.2 mm apart):
   broadside overlap closer than BROAD_GAP in XY.
2. Audio near the converter magnetics and ICs (radiated field): tracks within MAG_R of them.
3. In1 GND under audio tracks on F.Cu and In2: runs of SLOT mm or more without In1 copper.
4. Op-amp supply pins: distance to the nearest capacitor on the same rail.
5. Track length per audio net, summing-bus length.
"""
import argparse
import json
import math
import re
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parents[1]
OX = OY = 20.0
AUDIO = re.compile(r"^/(IN\d|RET|ML|MR|SUM|MAIN|SEND|PH)_")
METER = re.compile(r"^/D_")
SWITCH = {"/SW_P", "/SW_N", "/SW_5", "/BST_5", "/N_N"}
DIGITAL = re.compile(r"^/(I2C_|UART_|USB_D|INT_N|MCP_RST|BTN_|CC\d)")
SAME_GAP = 1.0          # mm, edge to edge on the same layer
BROAD_GAP = 0.5         # mm, XY distance between centrelines on In2 / B.Cu
MAG_R = 5.0             # mm from the converter parts
STEP = 0.25             # sampling step along tracks, mm
SLOT = 2.0              # mm of a track over no In1 copper in one run = a slot, not a via hole
SUPPLY = {"OPA1678": {"8": "/+12VA", "4": "/-12VA"},
          "TL064AC": {"4": "/+12VA", "11": "/-12VA"},
          "DG413": {"13": "/+12VA", "4": "/-12VA", "12": "/+5V"}}


def mm(v):
    return pcbnew.ToMM(v)


def segs(board):
    out = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        a, b = t.GetStart(), t.GetEnd()
        out.append({"net": t.GetNetname(), "layer": board.GetLayerName(t.GetLayer()),
                    "a": (mm(a.x) - OX, mm(a.y) - OY), "b": (mm(b.x) - OX, mm(b.y) - OY), "w": mm(t.GetWidth())})
    return out


def samples(s):
    (x1, y1), (x2, y2) = s["a"], s["b"]
    n = max(1, int(math.hypot(x2 - x1, y2 - y1) / STEP))
    return [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n + 1)], math.hypot(x2 - x1, y2 - y1) / n


def pdist(p, s):
    (x1, y1), (x2, y2) = s["a"], s["b"]
    dx, dy = x2 - x1, y2 - y1
    t = max(0.0, min(1.0, ((p[0] - x1) * dx + (p[1] - y1) * dy) / (dx * dx + dy * dy + 1e-12)))
    return math.hypot(x1 + t * dx - p[0], y1 + t * dy - p[1])


class Grid:
    def __init__(self, items, cell=5.0):
        self.cell, self.g = cell, {}
        for it in items:
            (x1, y1), (x2, y2) = it["a"], it["b"]
            for i in range(int(min(x1, x2) // cell) - 1, int(max(x1, x2) // cell) + 2):
                for j in range(int(min(y1, y2) // cell) - 1, int(max(y1, y2) // cell) + 2):
                    self.g.setdefault((i, j), []).append(it)

    def near(self, p):
        return self.g.get((int(p[0] // self.cell), int(p[1] // self.cell)), ())


def coupling(audio, aggr, layers_of, gap_fn):
    """{(audio net, aggressor net, layers): coupled length mm}."""
    grid = Grid(aggr)
    res = {}
    for s in audio:
        pts, dl = samples(s)
        for p in pts:
            hit = {}
            for o in grid.near(p):
                if o["layer"] not in layers_of(s["layer"]):
                    continue
                d = pdist(p, o)
                if d < gap_fn(s, o):
                    hit[(o["net"], o["layer"])] = min(d, hit.get((o["net"], o["layer"]), 99))
            for (net, layer), d in hit.items():
                k = (s["net"], net, f'{s["layer"]}/{layer}')
                r = res.setdefault(k, [0.0, 99.0, []])
                r[0] += dl
                r[1] = min(r[1], d)
                r[2].append(p)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=str(HW / "analog" / "analog_routed.kicad_pcb"))
    ap.add_argument("--json")
    ap.add_argument("--svg", help="map of the findings, e.g. docs/mech/audio-review.svg")
    a = ap.parse_args()
    board = pcbnew.LoadBoard(a.board)
    S = segs(board)
    audio = [s for s in S if AUDIO.match(s["net"])]
    meter = [s for s in S if METER.match(s["net"])]
    sw = [s for s in S if s["net"] in SWITCH]
    dig = [s for s in S if DIGITAL.match(s["net"])]
    report = {}

    same = lambda L: {L}
    broad = lambda L: {"In2.Sig": {"B.Cu"}, "B.Cu": {"In2.Sig"}}.get(L, set())
    edge_gap = lambda s, o: SAME_GAP + (s["w"] + o["w"]) / 2
    xy_gap = lambda s, o: BROAD_GAP + (s["w"] + o["w"]) / 2
    for name, victims, aggr in (("audio_vs_switch", audio, sw), ("audio_vs_digital", audio, dig),
                                ("meter_vs_switch", meter, sw)):
        r = coupling(victims, aggr, same, edge_gap)
        r.update(coupling(victims, aggr, broad, xy_gap))
        report[name] = sorted(([k[0], k[1], k[2], round(v[0], 2), round(v[1], 2),
                                [[round(c, 2) for c in q] for q in v[2][::4]]] for k, v in r.items()),
                              key=lambda x: -x[3])

    # 2. converter parts
    conv = []
    for f in board.GetFootprints():
        v, fid = f.GetValue(), f.GetFPIDAsString()
        if v.startswith(("LT1930", "LT1931", "TPS62933")) or "CLS62" in fid or (f.GetReference().startswith("L")):
            bb = f.GetBoundingBox(False)
            conv.append((f.GetReference(), v, (mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY,
                                               mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY)))
    near = {}
    for s in audio:
        pts, dl = samples(s)
        for p in pts:
            for ref, v, (x0, y0, x1, y1) in conv:
                d = math.hypot(max(x0 - p[0], 0, p[0] - x1), max(y0 - p[1], 0, p[1] - y1))
                if d < MAG_R:
                    k = (s["net"], ref, s["layer"])
                    r = near.setdefault(k, [0.0, 99.0])
                    r[0] += dl
                    r[1] = min(r[1], d)
    report["converter_parts"] = [[r, v, [round(c, 1) for c in box]] for r, v, box in conv]
    report["audio_near_converters"] = sorted(([k[0], k[1], k[2], round(v[0], 2), round(v[1], 2)]
                                             for k, v in near.items()), key=lambda x: x[4])

    # 3. In1 GND under audio on F.Cu / In2
    in1 = pcbnew.SHAPE_POLY_SET()
    for z in board.Zones():
        if z.GetNetname() == "/GND" and z.IsOnLayer(pcbnew.In1_Cu):
            in1.BooleanAdd(z.GetFilledPolysList(pcbnew.In1_Cu))
    in1.BuildBBoxCaches()
    # a short gap is the clearance hole around a via or a pin; a long one is a slot in the plane
    slots = []
    for s in audio:
        if s["layer"] not in ("F.Cu", "In2.Sig"):
            continue
        pts, dl = samples(s)
        run = []
        for p in pts + [None]:
            covered = p is None or in1.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(p[0] + OX), pcbnew.FromMM(p[1] + OY)), -1, 0, True)
            if not covered:
                run.append(p)
            elif run:
                if len(run) * dl >= SLOT:
                    slots.append([s["net"], s["layer"], round(len(run) * dl, 2), [round(run[0][0], 1), round(run[0][1], 1)]])
                run = []
    report["in1_slots"] = sorted(slots, key=lambda x: -x[2])

    # 4. decoupling
    caps = [(f.GetReference(), p) for f in board.GetFootprints() if f.GetReference().startswith("C")
            for p in f.Pads()]
    dec = []
    for f in board.GetFootprints():
        pins = SUPPLY.get(f.GetValue())
        if not pins:
            continue
        for num, rail in pins.items():
            pad = next(p for p in f.Pads() if p.GetNumber() == num)
            best = min(((math.hypot(mm(p.GetPosition().x - pad.GetPosition().x), mm(p.GetPosition().y - pad.GetPosition().y)), r)
                        for r, p in caps if p.GetNetname() == rail), default=(99, "-"))
            cpos = next((p.GetPosition() for r, p in caps if r == best[1] and p.GetNetname() == rail), pad.GetPosition())
            dec.append([f.GetReference(), f.GetValue(), num, rail, best[1], round(best[0], 2),
                        [round(mm(pad.GetPosition().x) - OX, 2), round(mm(pad.GetPosition().y) - OY, 2)],
                        [round(mm(cpos.x) - OX, 2), round(mm(cpos.y) - OY, 2)]])
    report["decoupling"] = sorted(dec, key=lambda x: -x[5])

    # 5. lengths
    ln = {}
    for s in audio:
        ln[s["net"]] = ln.get(s["net"], 0) + math.hypot(s["b"][0] - s["a"][0], s["b"][1] - s["a"][1])
    report["lengths"] = sorted(([n, round(v, 1)] for n, v in ln.items()), key=lambda x: -x[1])

    if a.svg:
        svg(board, report, S, Path(a.svg))
    if a.json:
        Path(a.json).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    for k in ("audio_vs_switch", "meter_vs_switch", "audio_vs_digital", "audio_near_converters", "in1_slots",
              "decoupling", "lengths"):
        rows = report[k]
        print(f"== {k}: {len(rows)}")
        for r in rows[:15]:
            print("  ", r[:5] if k.startswith(("audio_vs", "meter_vs")) else r[:6] if k == "decoupling" else r)


def svg(board, report, S, out, k=5.0):
    """Board map: audio tracks, converter parts, couplings and supply pin -> nearest capacitor."""
    W, D = 130.0, 138.5
    e = []
    P = lambda x, y: f"{x * k:.1f},{y * k:.1f}"
    e.append(f'<rect x="0" y="0" width="{W * k}" height="{D * k}" class="board"/>')
    for s in S:
        if AUDIO.match(s["net"]):
            e.append(f'<polyline points="{P(*s["a"])} {P(*s["b"])}" class="audio"/>')
        elif s["net"] in SWITCH:
            e.append(f'<polyline points="{P(*s["a"])} {P(*s["b"])}" class="sw"/>')
        elif DIGITAL.match(s["net"]):
            e.append(f'<polyline points="{P(*s["a"])} {P(*s["b"])}" class="dig"/>')
    for ref, v, (x0, y0, x1, y1) in report["converter_parts"]:
        e.append(f'<rect x="{(x0 - MAG_R) * k:.1f}" y="{(y0 - MAG_R) * k:.1f}" width="{(x1 - x0 + 2 * MAG_R) * k:.1f}" '
                 f'height="{(y1 - y0 + 2 * MAG_R) * k:.1f}" rx="{MAG_R * k:.0f}" class="halo"/>')
        e.append(f'<rect x="{x0 * k:.1f}" y="{y0 * k:.1f}" width="{(x1 - x0) * k:.1f}" height="{(y1 - y0) * k:.1f}" class="conv"/>')
        e.append(f'<text x="{(x1 + 0.5) * k:.1f}" y="{(y0 - 0.5) * k:.1f}" class="l">{ref} {v}</text>')
    for row in report["decoupling"]:
        d, (px, py), (cx, cy) = row[5], row[6], row[7]
        cls = "ok" if d <= 3 else "warn" if d <= 8 else "bad"
        e.append(f'<line x1="{px * k:.1f}" y1="{py * k:.1f}" x2="{cx * k:.1f}" y2="{cy * k:.1f}" class="dec {cls}"/>')
        e.append(f'<circle cx="{px * k:.1f}" cy="{py * k:.1f}" r="{0.7 * k:.1f}" class="pin {cls}"/>')
    for name, cls in (("audio_vs_switch", "hitsw"), ("audio_vs_digital", "hitdig")):
        for row in report[name]:
            if row[3] < 2.0:
                continue
            for x, y in row[5]:
                e.append(f'<circle cx="{x * k:.1f}" cy="{y * k:.1f}" r="{0.9 * k:.1f}" class="{cls}"/>')
    lg = [("audio", "аудіо"), ("sw", "вузли перемикання SW_P / SW_N / SW_5 / N_N"), ("dig", "цифра: I2C, UART, кнопки")]
    leg = []
    for i, (c, t) in enumerate(lg):
        y = (D + 6 + i * 5) * k
        leg.append(f'<line x1="{2 * k}" y1="{y - 4}" x2="{10 * k}" y2="{y - 4}" class="{c}"/><text x="{12 * k}" y="{y}" class="t">{t}</text>')
    for i, (c, t) in enumerate((("hitsw", "аудіо поруч / над вузлом перемикання"), ("hitdig", "аудіо поруч / над цифрою"))):
        y = (D + 6 + i * 5) * k
        leg.append(f'<circle cx="{84 * k}" cy="{y - 4}" r="{0.9 * k}" class="{c}"/><text x="{87 * k}" y="{y}" class="t">{t}</text>')
    for i, (c, t) in enumerate((("ok", "вивід живлення ОП: 100 nF ≤ 3 мм"), ("warn", "3–8 мм"), ("bad", "> 8 мм (лінія до конденсатора)"))):
        y = (D + 21 + i * 5) * k
        leg.append(f'<circle cx="{4 * k}" cy="{y - 4}" r="{0.7 * k}" class="pin {c}"/><text x="{7 * k}" y="{y}" class="t">{t}</text>')
    leg.append(f'<rect x="{82 * k}" y="{(D + 17) * k}" width="{6 * k}" height="{4 * k}" class="conv"/>'
               f'<text x="{89 * k}" y="{(D + 21) * k}" class="t">перетворювач / дросель, ореол {MAG_R:g} мм</text>')
    style = """<style>.board{fill:#fafaf7;stroke:#333;stroke-width:2}.audio{stroke:#1f6fd1;stroke-width:1.6;fill:none}
.sw{stroke:#e0301e;stroke-width:3;fill:none}.dig{stroke:#2a9d4a;stroke-width:1.6;fill:none;stroke-dasharray:4 2}
.halo{fill:#e0301e;fill-opacity:.06;stroke:#e0301e;stroke-opacity:.4;stroke-dasharray:4 3}.conv{fill:#e0301e;fill-opacity:.35;stroke:#a00}
.dec{stroke-width:1.5}.dec.ok{stroke:#2a9d4a}.dec.warn{stroke:#e8a317}.dec.bad{stroke:#c0392b}
.pin.ok{fill:#2a9d4a}.pin.warn{fill:#e8a317}.pin.bad{fill:#c0392b}
.hitsw{fill:none;stroke:#e0301e;stroke-width:2.5}.hitdig{fill:none;stroke:#2a9d4a;stroke-width:2}
text{font-family:sans-serif;fill:#222}.l{font-size:13px;font-weight:bold;fill:#a00}.t{font-size:15px}</style>"""
    w, h = W * k, (D + 36) * k
    out.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">'
                   f'{style}<rect width="100%" height="100%" fill="#fff"/>' + "".join(e + leg) + "</svg>\n")


if __name__ == "__main__":
    main()
