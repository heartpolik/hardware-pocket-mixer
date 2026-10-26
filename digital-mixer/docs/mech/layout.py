"""Approximate placement of the digital mixer main board (docs/mech/layout.svg).

  python3 digital-mixer/docs/mech/layout.py

Sizes (mm): courtyards of the footprints used in hw/sch/main.py (read with KiCad 10), Teensy 4.1
60.96 x 17.78 (electrokit, joy-it); TSF-1266 6 x 6 body (seller listing), self-locking switch 7 x 7,
display GMT147SPI 20.96 x 44 (seller manual) - their footprints are not drawn yet (ОРІЄНТИР).
Positions are a first sketch, not a placement.
"""
from pathlib import Path

OUT = Path(__file__).with_name("layout.svg")
S = 4.0                                   # px per mm
M = 3.0                                   # board edge margin
P = 18.0                                  # channel pitch: EC11E courtyard 16.8 + gap

FADER = (10.1, 36.1)                      # PTA2043 courtyard (w, d), long side front-back
ENC = (16.8, 13.8)                        # EC11E courtyard, lugs left/right
TACT = (9.0, 7.0)                         # TSF-1266 6 x 6 with SMT legs - ОРІЄНТИР
CAP = (8.0, 8.0)                          # button cap through the panel - ОРІЄНТИР
LATCH = (7.0, 7.0)
LCD = (20.96, 44.0)
JACK = (10.8, 17.6)                       # SJ-43514, body front-back, plug from the rear
TEENSY = (17.78, 60.96)
USBC = (10.6, 10.3)
BATT = (60.0, 50.0)                       # 3000 mAh pouch ~8 x 50 x 60 - ОРІЄНТИР, not chosen yet

xs = [M + P / 2 + i * P for i in range(4)]          # channel centres
y_enc = [M + 7.5 + k * 15.0 for k in range(3)]       # three encoders, 15 mm pitch
y_mute = y_enc[-1] + 7.5 + 1.0 + TACT[1] / 2
y_fader = y_mute + TACT[1] / 2 + 1.5 + FADER[1] / 2
x_m0 = M + 4 * P + 2.0                               # master section
W_M = 28.0
W = x_m0 + W_M + M
D = y_fader + FADER[1] / 2 + M
xm = x_m0 + W_M / 2


# inline styles: some SVG renderers ignore <style>
STYLE = {
    "board": "fill:#eef4ea;stroke:#333;stroke-width:1.5", "enc": "fill:#cfe0f5;stroke:#4a6fa5",
    "cap": "fill:none;stroke:#999;stroke-dasharray:3 2", "choc": "fill:#f6d9b8;stroke:#b07030",
    "fader": "fill:#d8cff0;stroke:#6a55a5", "oled": "fill:#26364f;stroke:#111",
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
        o += rect(x, y_mute, *TACT, "choc")
        o += rect(x, y_mute, *CAP, "cap", f"M{i}")
        o += rect(x, y_fader, *FADER, "fader", f"F{i}", "35 мм")
    y_lcd = M + LCD[1] / 2
    o += rect(xm, y_lcd, *LCD, "oled", "LCD", "1,47″ 172×320")
    y_me = y_lcd + LCD[1] / 2 + 2.0 + ENC[1] / 2
    o += rect(xm, y_me, *ENC, "enc", "MASTER", "з кнопкою")
    y_b = y_me + ENC[1] / 2 + 6.5
    grid = (("FX I", -7, 0), ("FX II", 7, 0), ("AUX", -7, 11), ("CUE", 7, 11), ("SHIFT", -7, 22))
    for name, dx, dy in grid:
        o += rect(xm + dx, y_b + dy, *TACT, "choc")
        o += rect(xm + dx, y_b + dy, *CAP, "cap", name)
    o += rect(xm + 7, y_b + 22, *LATCH, "edge", "ON", "7×7")
    return o


def bottom():
    o = []
    names = ["IN1", "IN2", "IN3", "IN4", "MAIN", "AUX", "PH"]
    jx = [M + 6.5 + 14.5 * i for i in range(7)]          # all on the rear edge, 14.5 mm pitch
    for x, n in zip(jx, names):
        o += rect(x, JACK[1] / 2, *JACK, "jack", n)
    o += rect(M + TEENSY[0] / 2 + 1, D - TEENSY[1] / 2, *TEENSY, "teensy", "Teensy 4.1", "microSD →")
    o += rect(W - USBC[1] / 2, 72.0, USBC[1], USBC[0], "edge", "USB")
    o += rect(56.0, D - 4 - BATT[1] / 2, *BATT, "batt", "LiPo 1S", "3000 mAh, ~8 мм")
    o += rect(52.0, 29.5, 56.0, 15.0, "zone", "АЦП ×2, ЦАП ×3,", "навушники")
    o += rect(W - 12.5, 31.0, 18.0, 18.0, "zone", "заряд,", "BB, LDO")
    o += rect(W - 12.5, 53.0, 18.0, 18.0, "zone", "MCP23017", "×2")
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
