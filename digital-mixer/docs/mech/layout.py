"""Approximate placement of the digital mixer main board (docs/mech/layout.svg).

  python3 digital-mixer/docs/mech/layout.py

Sizes (mm): courtyards of the footprints used in hw/sch/main.py (read with KiCad 10), the Kailh
PG1350 drawing (body 15 x 15, keycap pitch 18 x 17, LED window 5 x 3.15 at +4.7 from the stem),
Teensy 4.1 60.96 x 17.78 (electrokit, joy-it). Positions are a first sketch, not a placement.
"""
from pathlib import Path

OUT = Path(__file__).with_name("layout.svg")
S = 4.0                                   # px per mm
M = 3.0                                   # board edge margin
P = 18.0                                  # channel pitch = Choc keycap pitch (Kailh: 18 x 17)

FADER = (10.1, 36.1)                      # PTA2043 courtyard (w, d), long side front-back
ENC = (16.8, 13.8)                        # EC11E courtyard, lugs left/right
CHOC = (15.5, 15.5)                       # Choc courtyard; keycap 17.5 x 16.5
OLED = (27.9, 27.9)
JACK = (10.8, 17.6)                       # SJ-43514, body front-back, plug from the rear
TEENSY = (17.78, 60.96)
USBC = (10.6, 10.3)
MSK = (9.0, 6.1)
BATT = (50.0, 60.0)                       # 3000 mAh pouch ~8 x 50 x 60 - ОРІЄНТИР, not chosen yet

xs = [M + P / 2 + i * P for i in range(4)]          # channel centres
y_enc = [M + 7.5 + k * 15.0 for k in range(3)]       # three encoders, 15 mm pitch
y_mute = y_enc[-1] + 7.5 + 1.0 + 8.5
y_fader = y_mute + 8.5 + 1.5 + FADER[1] / 2
x_m0 = M + 4 * P + 2.0                               # master section
W_M = 36.0
W = x_m0 + W_M + M
D = y_fader + FADER[1] / 2 + M
xm = x_m0 + W_M / 2


# inline styles: some SVG renderers ignore <style>
STYLE = {
    "board": "fill:#eef4ea;stroke:#333;stroke-width:1.5", "enc": "fill:#cfe0f5;stroke:#4a6fa5",
    "cap": "fill:none;stroke:#999;stroke-dasharray:3 2", "choc": "fill:#f6d9b8;stroke:#b07030",
    "led": "fill:#ffef60;stroke:#c90", "fader": "fill:#d8cff0;stroke:#6a55a5", "oled": "fill:#444;stroke:#222",
    "jack": "fill:#cde8d8;stroke:#3a8a5a", "teensy": "fill:#9fd29f;stroke:#2d7a2d",
    "batt": "fill:#ffe9b0;fill-opacity:0.6;stroke:#c90;stroke-dasharray:6 4",
    "zone": "fill:#f2f2f2;stroke:#888;stroke-dasharray:4 3", "edge": "fill:#e8c8c8;stroke:#a55",
}
TXT = "font-family:sans-serif;text-anchor:middle;fill:{c};font-size:{f}px;font-weight:{w}"


def text(x, y, s, f=11, w="normal", c="#222"):
    return f'<text x="{x:.1f}" y="{y:.1f}" style="{TXT.format(c=c, f=f, w=w)}">{s}</text>'


def rect(cx, cy, w, h, cls, label=None, sub=None):
    out = [f'<rect x="{(cx - w / 2) * S:.1f}" y="{(cy - h / 2) * S:.1f}" width="{w * S:.1f}" '
           f'height="{h * S:.1f}" style="{STYLE[cls]}"/>']
    c = "#fff" if cls == "oled" else "#222"
    if label:
        out.append(text(cx * S, (cy + (0 if not sub else -1.2)) * S + 4, label, 11, "bold", c))
    if sub:
        out.append(text(cx * S, (cy + 2.4) * S + 4, sub, 9, "normal", c))
    return out


def top():
    o = []
    for i, x in enumerate(xs, 1):
        for k, y in enumerate(y_enc, 1):
            o += rect(x, y, *ENC, "enc", f"E{i}.{k}")
        o += rect(x, y_mute, 17.5, 16.5, "cap")
        o += rect(x - 1.5, y_mute, *CHOC, "choc", f"M{i}", "mute")
        o += rect(x + 4.7, y_mute, 3.15, 5.0, "led")      # LED window 4.7 mm beside the stem (drawing, side to confirm)
        o += rect(x, y_fader, *FADER, "fader", f"F{i}", "35 мм")
    o += rect(xm, M + OLED[1] / 2, *OLED, "oled", "OLED", "128×64")
    o += rect(xm, y_enc[2], *ENC, "enc", "MASTER", "з кнопкою")
    for (dx, dy), name in zip(((-9, 0), (9, 0), (-9, 17), (9, 17), (-9, 34)), ("FX I", "FX II", "AUX", "CUE", "SHIFT")):
        o += rect(xm + dx, y_mute + dy, 17.5, 16.5, "cap")
        o += rect(xm + dx, y_mute + dy, *CHOC, "choc", name)
    o += rect(W - MSK[1] / 2, y_mute + 34, MSK[1], MSK[0], "edge", "ON")
    return o


def bottom():
    o = []
    names = ["IN1", "IN2", "IN3", "IN4", "MAIN", "AUX", "PH"]
    jx = xs + [x_m0 + 6.0, x_m0 + 18.0, x_m0 + 30.0]
    for x, n in zip(jx, names):
        o += rect(x, JACK[1] / 2, *JACK, "jack", n)
    o += rect(M + TEENSY[0] / 2 + 1, D - TEENSY[1] / 2, *TEENSY, "teensy", "Teensy 4.1", "microSD →")
    o += rect(W - USBC[1] / 2, 31.0, USBC[1], USBC[0], "edge", "USB")
    o += rect(62.0, D - 8 - BATT[1] / 2, *BATT, "batt", "LiPo 1S", "3000 mAh, ~8 мм")
    o += rect(47.0, 30.0, 52.0, 18.0, "zone", "АЦП ×2, ЦАП ×3,", "навушники")
    o += rect(W - 26.0, 31.0, 22.0, 18.0, "zone", "заряд,", "buck-boost, LDO")
    o += rect(W - 26.0, 53.0, 22.0, 18.0, "zone", "MCP23017 ×2")
    return o


def board(ox, title, body):
    g = [f'<g transform="translate({ox * S:.1f},{40:.1f})">',
         f'<rect x="0" y="0" width="{W * S:.1f}" height="{D * S:.1f}" style="{STYLE["board"]}"/>',
         text(W * S / 2, -14, title, 17, "bold"), *body,
         text(W * S / 2, D * S + 24, f"{W:.0f} × {D:.0f} мм — фронт унизу", 14),
         '</g>']
    return g


def main():
    gap = 25.0
    body = board(5, "Згори: керування", top()) + board(5 + W + gap, "Знизу (вид згори, наскрізь): роз'єми, електроніка", bottom())
    w = (W * 2 + gap + 10) * S
    h = D * S + 100

    OUT.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">'
                   '<rect width="100%" height="100%" fill="#fff"/>' + "".join(body) + "</svg>\n")
    print(OUT, f"board {W:.1f} x {D:.1f} mm")


if __name__ == "__main__":
    main()
