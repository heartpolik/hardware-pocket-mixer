"""Placement of the digital mixer main board, layout C (DM25), drawn to docs/mech/layout.svg and
imported by hw/pcb/build_pcb.py.

  python3 digital-mixer/docs/mech/layout.py

Sizes (mm): EC12SY land pattern 18 x 20 and body 12.5 x 13.2 (seller drawing, DM26), PTA2043 courtyard
(KiCad), TSF-1266 with legs, latch switch 5.8 mm SMD pads 9.3 tip to tip (seller drawing, DM27),
GMT147SPI 44 x 20.96 landscape, SJ-43514 body, Teensy 4.1 (PJRC), USB-C courtyard. Columns: jack,
3 encoders, fader and Mute of a channel share one axis; top row ON / display / MASTER on one axis;
right column AUX, FX I, FX II on the encoder rows, SHIFT on the Mute row (DM28).
"""
from pathlib import Path

OUT = Path(__file__).with_name("layout.svg")
S = 4.0
M = 6.0
GAP = 4.0                                  # finger gap between control rows (DM19)
CLR = 1.5                                  # pad-to-part clearance where the bodies are smaller than the pads

ENC = (18.0, 20.0)                         # EC12SY SMD land pattern: 18 across the side lugs, 20 S1/S2 to A/C/B
ENC_BODY = (12.5, 13.2)
P = ENC[0] + 1.0                           # channel pitch: 1 mm between the side lugs of neighbours
FADER = (10.0, 36.0)                       # PTA2043 courtyard, long side front-back
TACT = (9.0, 7.0)
CAP = (8.0, 8.0)
LATCH = (6.0, 9.3)                         # SMD self-locking DPDT, pads 9.3 tip to tip
LCD = (44.0, 20.96)                        # GMT147SPI landscape
JACK = (17.6, 10.8)                        # SJ-43514 body length x width
TEENSY = (17.78, 60.96)
USBC = (13.4, 8.94)                        # GCT USB4110 courtyard (KiCad, after the GCT drawing)
BATT = (60.0, 50.0)                        # 3000 mAh pouch ~8 x 50 x 60 - ОРІЄНТИР, not chosen yet
CORNER = 4.0

xs = [M + P / 2 + i * P for i in range(4)]
X_LCD = (xs[0] + xs[-1]) / 2
Y_TOP = 2.0 + LCD[1] / 2                   # one row: ON, display, MASTER
y0 = Y_TOP + LCD[1] / 2 + CLR
y_enc = [y0 + ENC[1] / 2 + k * (ENC[1] + 0.5) for k in range(3)]
y_fader = y_enc[-1] + ENC[1] / 2 + CLR + FADER[1] / 2
y_mute = y_fader + FADER[1] / 2 + GAP + TACT[1] / 2
D = y_mute + TACT[1] / 2 + 2.5
x_r0 = xs[-1] + ENC[0] / 2
W = x_r0 + 1.0 + ENC[0] + CORNER
xr = W - CORNER - ENC[0] / 2               # MASTER and the button column
X_ON = CORNER + LATCH[0] / 2               # rear-left corner
Y_BTN = [*y_enc, y_mute]                   # AUX, FX I, FX II on the encoder rows; SHIFT on the Mute row (cue = SHIFT + Mute)
T_EDGE = 6.5                               # Teensy off the right edge: routing room + the corner hole
T_X = W - T_EDGE - TEENSY[0] / 2
T_Y = D - TEENSY[1] / 2                    # microSD in the front wall
# rear wall under MASTER (DM25): USB4110 is all SMD; 1.6 left of the MASTER axis its two locating
# holes (d0.65, 6.3 from the edge) miss the S1 / S2 pads on top, and the courtyard clears the corner hole
USB_X = xr - 1.6
OUT_P = 14.0                               # 3.2 mm between the output jacks
# right-wall jacks start behind the MASTER pads: their plastic pegs (d1.7 NPTH on the jack axis) clear
# the A / C / B pads and the lugs on top
OUT_Y0 = Y_TOP + ENC[1] / 2 + 0.85 + 0.3
y_out = [OUT_Y0 + i * OUT_P for i in range(4)]
BATT_C = (M + BATT[0] / 2, y_enc[-1] + ENC[1] / 2 - BATT[1] / 2)   # under the encoders (SMD: nothing comes through)
# toward the faders: the band behind it takes the input RC and the power parts
HOLES = [(3.0, 3.0), (3.0, D - 3.0), (W - 3.0, 3.0), (W - 3.0, D - 3.0)]

FADER_PINS = [(y - 1.75, x - 16.5) for x, y in ((0, 0), (0, 3.5), (33, 0), (3.9, 5.95), (5.1, -2.45),
                                                 (27.9, -2.45), (29.1, 5.95))]

STYLE = {
    "board": "fill:#eef4ea;stroke:#333;stroke-width:1.5", "enc": "fill:#cfe0f5;stroke:#4a6fa5",
    "pad": "fill:none;stroke:#4a6fa5;stroke-dasharray:2 2",
    "cap": "fill:none;stroke:#999;stroke-dasharray:3 2", "choc": "fill:#f6d9b8;stroke:#b07030",
    "fader": "fill:#d8cff0;stroke:#6a55a5", "oled": "fill:#26364f;stroke:#111",
    "jack": "fill:#cde8d8;stroke:#3a8a5a", "teensy": "fill:#9fd29f;stroke:#2d7a2d",
    "batt": "fill:#ffe9b0;fill-opacity:0.55;stroke:#c90;stroke-dasharray:6 4",
    "zone": "fill:#f2f2f2;fill-opacity:0.8;stroke:#888;stroke-dasharray:4 3", "edge": "fill:#e8c8c8;stroke:#a55",
    "pin": "fill:#b33;stroke:none", "hole": "fill:#fff;stroke:#555",
    "axis": "stroke:#c33;stroke-width:0.8;stroke-dasharray:2 3",
    "haxis": "stroke:#36c;stroke-width:0.8;stroke-dasharray:2 3",
}
TXT = "font-family:sans-serif;text-anchor:middle;fill:{c};font-size:{f}px;font-weight:{w}"


def text(x, y, s, f=11, w="normal", c="#222"):
    return f'<text x="{x:.1f}" y="{y:.1f}" style="{TXT.format(c=c, f=f, w=w)}">{s}</text>'


def rect(cx, cy, w, h, cls, label=None, sub=None, f=11):
    out = [f'<rect x="{(cx - w / 2) * S:.1f}" y="{(cy - h / 2) * S:.1f}" width="{w * S:.1f}" '
           f'height="{h * S:.1f}" style="{STYLE[cls]}"/>']
    c = "#fff" if cls == "oled" else "#222"
    if label:
        out.append(text(cx * S, (cy + (0 if not sub else -1.2)) * S + 4, label, f, "bold", c))
    if sub:
        out.append(text(cx * S, (cy + 2.4) * S + 4, sub, 9, "normal", c))
    return out


def dot(x, y, r, cls):
    return [f'<circle cx="{x * S:.1f}" cy="{y * S:.1f}" r="{r * S:.1f}" style="{STYLE[cls]}"/>']


def holes():
    return [d for x, y in HOLES for d in dot(x, y, 2.2, "hole")]


def axes():
    o = [f'<line x1="{x * S:.1f}" y1="0" x2="{x * S:.1f}" y2="{D * S:.1f}" style="{STYLE["axis"]}"/>' for x in xs]
    o.append(f'<line x1="0" y1="{Y_TOP * S:.1f}" x2="{W * S:.1f}" y2="{Y_TOP * S:.1f}" style="{STYLE["haxis"]}"/>')
    return o


def enc(x, y, label, sub=None):
    return rect(x, y, *ENC, "pad") + rect(x, y, *ENC_BODY, "enc", label, sub, f=10)


def top():
    o = axes()
    o += rect(X_ON, Y_TOP, *LATCH, "edge", "ON", f=9)
    o += rect(X_LCD, Y_TOP, *LCD, "oled", "LCD 1,47″", "172×320, альбомно")
    o += enc(xr, Y_TOP, "MASTER", "з кнопкою")
    for i, x in enumerate(xs, 1):
        for k, y in enumerate(y_enc, 1):
            o += enc(x, y, f"E{i}.{k}")
        o += rect(x, y_fader, *FADER, "fader", f"F{i}", "35 мм")
        o += rect(x, y_mute, *TACT, "choc")
        o += rect(x, y_mute, *CAP, "cap", f"M{i}")
    for y, name in zip(Y_BTN, ("AUX", "FX I", "FX II", "SHIFT")):
        o += rect(xr, y, *TACT, "choc")
        o += rect(xr, y, *CAP, "cap", name, f=9)
    return o + holes()


def bottom():
    o = axes()
    for x, n in zip(xs, ("IN1", "IN2", "IN3", "IN4")):
        o += rect(x, JACK[0] / 2 - 0.5, JACK[1], JACK[0], "jack", n)
    for y, n in zip(y_out, ("MAIN", "AUX", "MIDI", "PHONES")):
        o += rect(W - JACK[0] / 2 + 0.5, y, *JACK, "jack", n, f=10)
    o += rect(T_X, T_Y, *TEENSY, "teensy", "Teensy", "↓ microSD", f=10)
    ze = (y_enc[0] - ENC[1] / 2, y_enc[-1] + ENC[1] / 2)
    o += rect(*BATT_C, *BATT, "batt", "LiPo 1S 3000 мАг", "під енкодерами (SMD)")
    px0, px1 = M + BATT[0] + 1.0, T_X - TEENSY[0] / 2 - 0.5
    o += rect((px0 + px1) / 2, sum(ze) / 2, px1 - px0, ze[1] - ze[0], "zone")
    o.append(f'<text transform="translate({(px0 + px1) / 2 * S + 4:.1f},{sum(ze) / 2 * S:.1f}) rotate(-90)" '
             f'style="{TXT.format(c="#222", f=10, w="bold")}">ESD, заряд, BB, LDO</text>')
    yf = (y_fader - 9.0, y_mute + TACT[1] / 2)
    o += rect((M + px1) / 2, sum(yf) / 2, px1 - M, yf[1] - yf[0], "zone",
              "АЦП ×2, ЦАП ×3, TPA6132, MCP23017 ×2", "між виводами фейдерів і під Mute — поруч із Teensy")
    o += [d for x in xs for dx, dy in FADER_PINS for d in dot(x + dx, y_fader + dy, 1.0, "pin")]
    o += rect(USB_X, USBC[1] / 2 - 0.5, *USBC, "edge", "USB-C", f=9)
    for a, b in zip(xs, xs[1:]):
        o += rect((a + b) / 2, 9.0, P - JACK[1] - 1.0, 14.0, "zone")
    o.append(text((xs[0] + xs[1]) / 2 * S, (JACK[0] + 3.5) * S, "вхідні RC між джеками", 9))
    return o + holes()


def board(ox, title, body):
    return [f'<g transform="translate({ox * S:.1f},50)">',
            f'<rect x="0" y="0" width="{W * S:.1f}" height="{D * S:.1f}" style="{STYLE["board"]}"/>',
            text(W * S / 2, -18, title, 17, "bold"), text(W * S / 2, -4, "тил ↑", 11, c="#666"), *body,
            text(W * S / 2, D * S + 24, f"{W:.0f} × {D:.0f} мм — фронт унизу", 14), '</g>']


def main():
    gap = 25.0
    body = board(5, "Згори: керування", top()) + board(5 + W + gap, "Знизу (вид згори, наскрізь)", bottom())
    w = (W * 2 + gap + 10) * S
    h = D * S + 110
    OUT.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">'
                   '<rect width="100%" height="100%" fill="#fff"/>' + "".join(body) + "</svg>\n")
    print(OUT, f"board {W:.1f} x {D:.1f} mm")


if __name__ == "__main__":
    main()
