"""Top view and side section of the mixer, iteration 3 (master pair, RET rightmost, Cherry MX mute).

All dimensions in mm. Values marked "orient" are not yet confirmed by drawings.
Run: python3 docs/mech/layout_v3.py  ->  docs/mech/layout-v3.svg
"""
from pathlib import Path

# --- plan (top view) ---------------------------------------------------------
MARGIN = 4.0           # inner wall to first/last column
PITCH = 18.0           # column pitch (channels, CH4 -> M-L, M-R -> RET)
M_PITCH = 11.0         # master L/R faders: body 9 + 2 mm; pads Ø2 at ±3.75 leave ~2 mm
RET_PITCH = 20.5       # M-R -> RET: phones jack footprint 10.2 + 2 x 0.5 between fader bodies
REAR_ZONE = 20.0       # raised strip: digital board (LEDs) above rear jacks
OLED_RAISED = 50.0     # raised zone depth over the master pair (OLED)
ENC_RAISED = 38.0      # raised zone depth over RET (encoder)
STEP_WALL = 2.0
SEND_Y = 30.0          # send rotary row centre
PAN_Y = 49.0           # pan rotary row centre (also phones rotary in RET column)
MUTE_Y = 64.0          # mute row centre: ch1-4, one for the master pair, RET
FADER_Y0 = 72.5        # fader body start (rear end), clears the MX housing
FADER_LEN = 60.0       # RS45 body length
FADER_W = 9.0          # RS451121400A on all 7 faders (D23)
FADER_TRAVEL = 45.0
FRONT_MARGIN = 6.0
RK14_W, RK14_D = 14.0, 11.0     # RK14K body footprint (approx from drawing)
KNOB_D = 13.0                   # rotary knob diameter (orient)
OLED_W, OLED_H = 27.3, 27.3     # module board (Rajguru datasheet, docs/datasheets)
OLED_AA = (21.74, 10.86)        # active area
OLED_Y = 21.0
ENC_W = 12.0                    # EC11-class encoder body (orient)
ENC_Y = 29.0
JACK_W, JACK_D = 6.0, 17.0      # SJ-4351X-SMT: body 6.0 wide, 15.5 + 1.5 nose
JACK_PADS_W = 10.2               # SJ-4351X-SMT footprint width (pads 5.1 each side)
USBC_W, USBC_D = 9.0, 7.5       # orient
USBC_Y = 28.0                   # right side wall, under the digital board, clear of the RET jack
MX_BODY = 15.63                  # Cherry MX housing, MX2A datasheet
MX_TOP = 11.6                    # housing top above PCB: plate top 5 + ~6.6 (orient)
MX_CAP = 15.0                    # printed keycap (orient)

# --- heights (side section), z = 0 is top of analog PCB ----------------------
PCB_T = 1.6
PANEL_T = 2.0
LOW_PANEL_Z = 7.5      # underside of fader/rotary panel (fader mount 7.0, RK14 body 7.5)
BOARD_GAP = 11.0       # PLS + PBS stack, analog top -> digital bottom (orient)
OLED_STACK = 5.0       # digital top -> OLED glass / button cap base (orient)
JACK_H = 5.0           # SJ-4351X-SMT datasheet
FADER_BODY_H = 7.0
FADER_LEVER_TOP = 27.0
RK14_BODY_H, RK14_BUSH_TOP, RK14_SHAFT_TOP = 7.5, 12.5, 22.5
SMD_H, BATT_H, BOTTOM_T = 2.0, 7.0, 2.0

DIG_Z0 = BOARD_GAP
DIG_Z1 = DIG_Z0 + PCB_T
HIGH_PANEL_Z = DIG_Z1 + OLED_STACK

SCALE = 4.0                      # px per mm
COLS = ["CH1", "CH2", "CH3", "CH4", "M-L", "M-R", "RET"]
_x = [MARGIN + PITCH / 2 + PITCH * i for i in range(4)]
_x.append(_x[-1] + PITCH)            # M-L
_x.append(_x[-1] + M_PITCH)          # M-R
_x.append(_x[-1] + RET_PITCH)        # RET (FX return), rightmost
X = dict(zip(COLS, _x))
W = X["RET"] + PITCH / 2 + MARGIN
D = FADER_Y0 + FADER_LEN + FRONT_MARGIN


def col_x(i):
    return _x[i]


def rect(x, y, w, h, cls, label=None):
    s = f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}"/>'
    if label:
        s += f'<text x="{x + w / 2}" y="{y + h / 2 + 1.2}">{label}</text>'
    return s


def circle(cx, cy, r, cls):
    return f'<circle class="{cls}" cx="{cx}" cy="{cy}" r="{r}"/>'


def text(x, y, s, cls=None):
    c = f' class="{cls}"' if cls else ""
    return f'<text{c} x="{x}" y="{y}">{s}</text>'


def top_view():
    el = [rect(0, 0, W, D, "case")]
    xm = (X["M-L"] + X["M-R"]) / 2
    x_oled0 = X["CH4"] + PITCH / 2
    x_enc0 = X["RET"] - PITCH / 2
    # raised zone: rear strip + OLED over the master pair + encoder over RET
    el.append(f'<path class="raised" d="M0 0 H{W} V{ENC_RAISED} H{x_enc0} V{OLED_RAISED} '
              f'H{x_oled0} V{REAR_ZONE} H0 Z"/>')
    # rear jacks (under digital board): inputs on their columns, outputs between
    rear = [(X[f"CH{i}"], f"IN{i}") for i in range(1, 5)]
    rear += [(xm, "MAIN"), ((xm + X["RET"]) / 2, "SEND"), (X["RET"], "RET")]
    for x, name in rear:
        el.append(rect(x - JACK_PADS_W / 2, 0, JACK_PADS_W, JACK_D, "pads"))
        el.append(rect(x - JACK_W / 2, 0, JACK_W, JACK_D, "jack", name))
    # USB-C on the right side wall
    el.append(rect(W - USBC_D, USBC_Y - USBC_W / 2, USBC_D, USBC_W, "jack", "USB"))
    # LEDs on digital board: ch1-4 + RET (master state is on the OLED)
    for name in ("CH1", "CH2", "CH3", "CH4", "RET"):
        el.append(circle(X[name], 6, 1.6, "led"))
    # OLED over the master pair, encoder over RET
    ox = xm - OLED_W / 2
    el.append(rect(ox, OLED_Y, OLED_W, OLED_H, "oled"))
    el.append(rect(xm - OLED_AA[0] / 2, OLED_Y + 8, *OLED_AA, "oledaa", "OLED"))
    ex = X["RET"]
    el.append(rect(ex - ENC_W / 2, ENC_Y - ENC_W / 2, ENC_W, ENC_W, "pot"))
    el.append(circle(ex, ENC_Y, 5, "enc"))
    el.append(text(ex, ENC_Y + 1.2, "ENC"))
    # rotaries on analog board: send, pan ch1-4; phones under the encoder
    pots = [(col_x(i), y, n) for y, n in ((SEND_Y, "SND"), (PAN_Y, "PAN")) for i in range(4)]
    pots.append((ex, PAN_Y, "PHN"))
    for cx, cy, name in pots:
        el.append(rect(cx - RK14_W / 2, cy - RK14_D / 2, RK14_W, RK14_D, "pot"))
        el.append(circle(cx, cy, KNOB_D / 2, "knob"))
        el.append(text(cx, cy + 1.2, name))
    # phones jack: front edge, between M-R and RET faders
    jx = (X["M-R"] + X["RET"]) / 2
    el.append(rect(jx - JACK_PADS_W / 2, D - JACK_D, JACK_PADS_W, JACK_D, "pads"))
    el.append(rect(jx - JACK_W / 2, D - JACK_D, JACK_W, JACK_D, "jack", "PH"))
    # mute buttons (analog board, via GPIO expander) + faders
    for name in COLS:
        cx = X[name]
        el.append(rect(cx - FADER_W / 2, FADER_Y0, FADER_W, FADER_LEN, "fader"))
        t0 = FADER_Y0 + (FADER_LEN - FADER_TRAVEL) / 2
        el.append(f'<line class="travel" x1="{cx}" y1="{t0}" x2="{cx}" y2="{t0 + FADER_TRAVEL}"/>')
        el.append(text(cx, FADER_Y0 + FADER_LEN + 4, name))
    for cx in (X["CH1"], X["CH2"], X["CH3"], X["CH4"], xm, X["RET"]):
        el.append(rect(cx - MX_BODY / 2, MUTE_Y - MX_BODY / 2, MX_BODY, MX_BODY, "pot"))
        el.append(rect(cx - MX_CAP / 2, MUTE_Y - MX_CAP / 2, MX_CAP, MX_CAP, "btn", "MUTE"))
    # section line through CH1
    cx = X["CH1"]
    el.append(f'<line class="cut" x1="{cx}" y1="-3" x2="{cx}" y2="{D + 3}"/>')
    el.append(text(cx + 2.5, D + 3, "A"))
    el.append(text(W / 2, D + 7, f"{W:.0f} mm", "dim"))
    el.append(f'<text class="dim" x="{W + 8}" y="{D / 2}" '
              f'transform="rotate(90 {W + 8} {D / 2})">{D:.0f} mm</text>')
    el.append(text(0, -4, "TOP VIEW v3. REAR. Blue = raised zone (digital board), "
                   "dashed = under it. Not confirmed.", "note"))
    el.append(text(0, D + 13, "FRONT (phones)", "note"))
    return el


def side_view(oy):
    """Section A-A through the CH1 column; horizontal = depth, vertical = z."""
    def r(y, z0, z1, cls, label=None):
        return rect(y[0], oy - z1, y[1] - y[0], z1 - z0, cls, label)

    el = []
    hp0, hp1 = HIGH_PANEL_Z, HIGH_PANEL_Z + PANEL_T
    lp0, lp1 = LOW_PANEL_Z, LOW_PANEL_Z + PANEL_T
    z_bot = -PCB_T - SMD_H - BATT_H - BOTTOM_T
    # enclosure outline (stepped)
    el.append(f'<path class="case" d="M0 {oy - z_bot} V{oy - hp1} H{REAR_ZONE + STEP_WALL} '
              f'V{oy - lp1} H{D} V{oy - z_bot} Z"/>')
    el.append(r((0, D), -PCB_T, 0, "pcb", "analog PCB"))
    el.append(r((4, D - 4), -PCB_T - SMD_H - BATT_H, -PCB_T - SMD_H, "batt", "2S LiPo (orient)"))
    el.append(r((0, JACK_D), 0, JACK_H, "jack", "jack"))
    el.append(r((16.5, 19), 0, DIG_Z0, "hdr"))
    el.append(r((0, REAR_ZONE), DIG_Z0, DIG_Z1, "dig"))
    el.append(r((4.5, 7.5), DIG_Z1, DIG_Z1 + 1, "btn"))
    el.append(r((MUTE_Y - 7, MUTE_Y + 7), 0, MX_TOP, "potside"))
    el.append(r((MUTE_Y - MX_CAP / 2, MUTE_Y + MX_CAP / 2), MX_TOP + 0.5, MX_TOP + 6, "knobside"))
    el.append(r((0, REAR_ZONE + STEP_WALL), hp0, hp1, "panel"))
    el.append(r((REAR_ZONE, REAR_ZONE + STEP_WALL), lp1, hp0, "panel"))
    el.append(r((REAR_ZONE, D), lp0, lp1, "panel"))
    for cy in (SEND_Y, PAN_Y):
        el.append(r((cy - RK14_D / 2, cy + RK14_D / 2), 0, RK14_BODY_H, "potside"))
        el.append(r((cy - 4.5, cy + 4.5), RK14_BODY_H, RK14_BUSH_TOP, "potside"))
        el.append(r((cy - 3, cy + 3), RK14_BUSH_TOP, RK14_SHAFT_TOP, "potside"))
        el.append(r((cy - KNOB_D / 2, cy + KNOB_D / 2), lp1 + 1, RK14_SHAFT_TOP + 1, "knobside"))
    el.append(r((FADER_Y0, FADER_Y0 + FADER_LEN), 0, FADER_BODY_H, "fader", "fader RS45"))
    mid = FADER_Y0 + FADER_LEN / 2
    el.append(r((mid - 0.75, mid + 0.75), FADER_BODY_H, FADER_LEVER_TOP, "lever"))
    # height labels
    for k, (z, s) in enumerate(((0, "0"), (hp1, f"{hp1:g}"), (DIG_Z0, f"{DIG_Z0:g}"),
                 (lp1, f"{lp1:g}"), (FADER_LEVER_TOP, f"{FADER_LEVER_TOP:g}"),
                 (z_bot, f"{z_bot:g}"))):
        el.append(text(D + 3 + 7 * (k % 2), oy - z + 1, s, "zl"))
    el.append(text(0, oy - FADER_LEVER_TOP - 5, "SECTION A-A (CH1 column), z from analog PCB top, mm", "note"))
    return el


def main():
    el = top_view()
    oy = D + 20 + FADER_LEVER_TOP + 8
    el += side_view(oy)
    total_h = oy + PCB_T + SMD_H + BATT_H + BOTTOM_T + 6
    style = """
    <style>
      text{font:2.6px sans-serif;text-anchor:middle;fill:#222}
      .note{text-anchor:start;font-size:3px;fill:#555}
      .dim{font-size:3.2px;fill:#a00}
      .zl{text-anchor:start;font-size:2.6px;fill:#a00}
      .case{fill:#fafafa;stroke:#000;stroke-width:0.5}
      .raised{fill:#d8ecff;fill-opacity:0.75;stroke:#2a6;stroke-width:0.3}
      .jack{fill:#bbb;stroke:#555;stroke-width:0.2;stroke-dasharray:0.8 0.4}
      .pads{fill:none;stroke:#c60;stroke-width:0.2;stroke-dasharray:0.4 0.4}
      .btn{fill:#888;fill-opacity:0.8}
      .led{fill:#f60}
      .oled{fill:#334;stroke:#000;stroke-width:0.2}
      .oledaa{fill:#09c}
      .pot{fill:none;stroke:#999;stroke-width:0.2}
      .potside{fill:#ccc;stroke:#555;stroke-width:0.2}
      .knob{fill:#ddd;stroke:#333;stroke-width:0.3;fill-opacity:0.6}
      .knobside{fill:none;stroke:#333;stroke-width:0.3;stroke-dasharray:1 0.6}
      .enc{fill:#cfc;stroke:#363;stroke-width:0.3}
      .fader{fill:#eee;stroke:#333;stroke-width:0.3}
      .lever{fill:#333}
      .travel{stroke:#c00;stroke-width:0.6}
      .cut{stroke:#a00;stroke-width:0.3;stroke-dasharray:3 1 0.6 1}
      .pcb{fill:#6a6;stroke:#353;stroke-width:0.2}
      .dig{fill:#69c;stroke:#246;stroke-width:0.2}
      .hdr{fill:#222}
      .panel{fill:#a87;stroke:#543;stroke-width:0.2}
      .batt{fill:#fd8;stroke:#a80;stroke-width:0.2}
    </style>"""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{(W + 18) * SCALE}" '
           f'height="{(total_h + 8) * SCALE}" viewBox="-4 -8 {W + 18} {total_h + 8}">'
           f'<rect x="-4" y="-8" width="{W + 18}" height="{total_h + 8}" fill="#fff"/>{style}'
           + "".join(el) + "</svg>")
    out = Path(__file__).with_name("layout-v3.svg")
    out.write_text(svg)
    print(f"{out}  {W:.0f} x {D:.0f} mm, panels at {LOW_PANEL_Z + PANEL_T:g} / "
          f"{HIGH_PANEL_Z + PANEL_T:g} mm, overall z {-(PCB_T + SMD_H + BATT_H + BOTTOM_T):g}"
          f"..{HIGH_PANEL_Z + PANEL_T:g}")


if __name__ == "__main__":
    main()
