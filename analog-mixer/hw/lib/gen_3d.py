"""3D models (STEP) of the project footprints (hw/lib/diy-mixer.pretty) and of Cherry MX, for the
enclosure design. Built from the same datasheet drawings as hw/lib/gen_footprints.py.

Run with CadQuery (not KiCad's Python):
  python3.12 -m venv .venv-cq && .venv-cq/bin/pip install cadquery==2.6.1
  .venv-cq/bin/python hw/lib/gen_3d.py

Every model sits in its footprint's frame: KiCad footprint (x, y) with y down -> model (x, -y);
z = 0 is the top of the PCB. Envelope dimensions (body, shaft, lever, heights) are the datasheet
ones; small details nobody dimensions (terminal shapes, chamfers) are simplified. Values the
drawing does not give are marked ОРІЄНТИР here and in docs/15-3d.md.
"""
import sys
from pathlib import Path

import cadquery as cq

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))
import cq3d  # noqa: E402
from cq3d import (BLACK, BLUE, DARK, GLASS, METAL, PCB_BLACK, PCB_BLUE, PIN, RED, WHITE,  # noqa: E402,F401
                  box, cyl, hcyl, header, pin, union)

OUT = Path(__file__).parent / "diy-mixer.3dshapes"



def save(name, parts):
    return cq3d.save(OUT, name, parts)


def fader_rs45():
    """Alps RS451121400A, catalog 2026 drawing 20 / catalog p.354 No.11: body 60 x 9, mounting
    surface 7 above the PCB, 2 x M2 56 apart; lever type 4, L1 = 20, t 1.2 (base 6.6, blade 5,
    tip 4 -> 3 over the top 8.5); terminals 3.5 below. Lever at mid travel."""
    body = box(-30, -4.5, 30, 4.5, 0, 7.0)
    body = body.cut(box(-24, -0.8, 24, 0.8, 6.0, 7.0))                  # lever slot
    for x in (-28, 28):
        body = body.cut(cyl(x, 0, 1.6, 4.0, 7.0))                       # M2 threads
    lever = union(box(-3.3, -0.6, 3.3, 0.6, 6.5, 8.0),                  # base 6.6 in the slot
                  box(-2.5, -0.6, 2.5, 0.6, 8.0, 18.5),                 # blade 5
                  cq.Workplane("XZ").polyline([(-2, 18.5), (2, 18.5), (1.5, 27), (-1.5, 27)]).close()
                  .extrude(0.6, both=True))                             # tip 4 -> 3, top at 27
    pins = union(*[pin(x, y) for x, y in ((-27.5, -1.25), (-27.5, -3.75), (27.5, -1.25),
                                          (-27.5, 3.75), (-27.5, 1.25), (27.5, 3.75))])
    return save("Alps_RS451121400A_Fader_Dual_45mm", [(body, METAL), (lever, METAL), (pins, PIN)])


def rk14k():
    """Alps RK14K vertical (RK14K12D / RK14K124), catalog p.326 drawing 1: body 14 x 16.4
    (y -6.7..+9.7 about the shaft), 7.5 high; bushing M9 x 5; insulated shaft d6, LM1 22.5 from
    the mounting surface, flat 4.5 over the top 7 mm. Terminals 7 x pitch 2 on the row y 11,
    snap-in tabs on x +-6.65."""
    body = union(box(-7, -6.7, 7, 6.7, 0, 7.5),                         # metal frame + rotor
                 box(-7, 6.7, 7, 9.7, 0, 4.0))                          # terminal block ОРІЄНТИР
    bush = cyl(0, 0, 9.0, 7.5, 12.5)
    shaft = cyl(0, 0, 6.0, 12.5, 22.5).cut(box(-3.5, 2.25, 3.5, 3.5, 15.5, 22.6))
    pins = union(*[pin(x, 11.0, 0.8, 0.3, -3.5, 0.5) for x in range(-6, 7, 2)],
                 *[box(x, 9.7, x + 0.3, 11.15, 0.2, 0.5) for x in range(-6, 7, 2)])
    tabs = union(*[box(x - 0.15, -1.0, x + 0.15, 1.0, -3.2, 3.0) for x in (-6.65, 6.65)])
    return save("Alps_RK14K_Vertical", [(body, METAL), (bush, METAL), (shaft, DARK),
                                         (pins, PIN), (tabs, METAL)])


def ec12d():
    """Alps EC12D with push switch, catalog p.289 drawing 5: body 12.5 x 11.7, lugs 14.1 over;
    shaft d5.975 with flat 4.475, LM1 17.5 above the mounting surface; d6.8 collar; switch travel
    0.5. Body/collar heights: 5 / 6 from the drawing's '5 (6)' - ОРІЄНТИР."""
    body = box(-6.25, -5.85, 6.25, 5.85, 0, 5.0)
    collar = cyl(0, 0, 6.8, 5.0, 6.0)
    shaft = cyl(0, 0, 5.975, 6.0, 17.5).cut(box(-3.5, 1.49, 3.5, 3.5, 7.5, 17.6))
    pins = union(*[pin(x, y, 0.7, 0.3) for x, y in ((-5.55, -4.15), (5.55, -4.15), (-5.55, 4.15),
                                                    (0.0, -6.85), (5.95, 3.45))])
    lugs = union(*[box(x - 0.15, -1.0, x + 0.15, 1.0, -3.0, 5.0) for x in (-5.625, 5.625)])
    return save("Alps_EC12D_Switch", [(body, METAL), (collar, DARK), (shaft, DARK), (pins, PIN),
                                       (lugs, METAL)])


def cherry_mx():
    """Cherry MX, PCB mount (KiCad SW_Cherry_MX_1.00u_PCB: origin = pin, switch centre at
    (-2.54, 5.08)). MX2A datasheet: housing 15.63 x 15.63, total height 18.5 incl. pins.
    Plate-level split (bottom housing 14 x 14 up to 5.0), housing top 11.6, stem 4 x 4 cross to
    15.2, pins 3.3 below - ОРІЄНТИР (Cherry MX drawing, not in docs/datasheets)."""
    cx, cy = -2.54, 5.08
    bottom = box(cx - 7, cy - 7, cx + 7, cy + 7, 0, 5.0)
    top = (cq.Workplane("XY").rect(15.63, 15.63).workplane(offset=6.6).rect(10.0, 11.0).loft()
           .translate((cx, -cy, 5.0)))
    stem = union(box(cx - 2, cy - 0.65, cx + 2, cy + 0.65, 8.0, 15.2),
                 box(cx - 0.65, cy - 2, cx + 0.65, cy + 2, 8.0, 15.2))
    post = cyl(cx, cy, 3.9, -3.3, 0)
    pegs = union(cyl(-7.62, 5.08, 1.7, -3.3, 0), cyl(2.54, 5.08, 1.7, -3.3, 0))
    pins = union(pin(0, 0, 1.5, 0.3, -3.3, 0), pin(-6.35, 2.54, 1.5, 0.3, -3.3, 0))
    return save("SW_Cherry_MX_1.00u_PCB", [(bottom, DARK), (top, WHITE), (stem, RED),
                                            (union(post, pegs), DARK), (pins, PIN)])


def uep(d, pitch, name):
    """Nichicon UEP radial, laid flat (D44): body d x L 11 along +X from the lead bend at 1.5,
    axis at d/2 above the PCB; leads at the origin, pitch across Y."""
    can = hcyl(1.5, 12.5, 0, d / 2, d)
    leads = union(*[union(cyl(0, y, 0.5, -3.0, d / 2), hcyl(0, 1.5, y, d / 2, 0.5))
                    for y in (-pitch / 2, pitch / 2)])
    return save(name, [(can, BLACK), (leads, METAL)])


def sj_43514():
    """CUI SJ-43514-SMT, datasheet mechanical drawing (2018): body 15.5 long, 6.0 wide (6.7 over
    the tabs), 5.0 high incl. 0.1 standoff; nose d5 x 1.5 at the mouth (x -1.5..0); plug bore
    d3.6, axis 2.5 above the PCB; plug d3.5 x 14 enters from -X."""
    body = box(0, -3.0, 15.5, 3.0, 0.1, 5.0)
    nose = hcyl(-1.5, 0, 0, 2.5, 5.0)
    bore = hcyl(-1.6, 14.0, 0, 2.5, 3.6)
    shell = union(body, nose).cut(bore)
    tabs = union(*[box(x - w / 2, 3.95 - 1.0 if y > 0 else -3.95 - 1.0, x + w / 2,
                       3.95 + 1.0 if y > 0 else -3.95 + 1.0, 0, 0.2)
                   for x, y, w in ((0.6, 1, 0.8), (3.4, 1, 1.0), (12.8, 1, 1.5), (5.3, -1, 1.0))])
    return save("CUI_SJ-43514-SMT_TRRS_Horizontal", [(shell, BLACK), (tabs, METAL)])


def cts_204(n):
    """CTS 204-12nST, rev D fig. 2: length 7.26 (1 position) / 27.58 (5), height over the PCB
    9.12 incl. actuators 0.89 above the body, standoff 0.38, leads 10.40 tip-to-tip (rows 7.62).
    Body width 7.62 and actuator size 1.2 x 1.5 - ОРІЄНТИР. Actuators drawn in the 'ON' position
    (toward the dot side, -Y). Mounted on the bottom side (KiCad flips the model)."""
    a = {1: 7.26, 5: 27.58}[n] / 2
    body = box(-a, -3.81, a, 3.81, 0.38, 8.23)
    acts = union(*[box((2 * k - (n - 1)) * 2.54 - 0.6, -2.03, (2 * k - (n - 1)) * 2.54 + 0.6, -0.53,
                       8.23, 9.12) for k in range(n)])
    leads = union(*[box((i - (2 * n - 1) / 2) * 2.54 - 0.24, s * 3.81,
                        (i - (2 * n - 1) / 2) * 2.54 + 0.24, s * 5.2, 0, 0.25)
                    for i in range(2 * n) for s in (-1, 1)])
    return save(f"CTS_204-12{n}ST_DIP_SPDT_{n}pos_SMD", [(body, BLACK), (acts, WHITE), (leads, METAL)])


def cls62():
    """Sumida CLS62: 6.6 x 6.8 (7.3 x 7.1 max), 2.5 max high."""
    body = box(-3.3, -3.4, 3.3, 3.4, 0, 2.5).edges("|Z").fillet(0.8)
    pads = union(*[box(x - 0.6, y - 0.5, x + 0.6, y + 0.5, 0, 0.3)
                   for x in (-3.0, 3.0) for y in (-1.75, 1.75)])
    return save("L_Sumida_CLS62", [(body, DARK), (pads, METAL)])


def msk12c02():
    """SHOU HAN MSK12C02 (spec drawing 2024-12-14): body 6.75 x 2.8 x 1.4; actuator 1.3 wide,
    1.45 out of the face toward -Y, drawn in the position at pad 3; actuator height 0.3..1.1 -
    ОРІЄНТИР. Terminals 3/2/1 toward +Y, cover tabs on the short sides."""
    body = box(-3.375, -1.4, 3.375, 1.4, 0, 1.4)
    act = box(-1.45, -2.85, -0.15, -1.4, 0.3, 1.1)
    legs = union(*[box(x - 0.2, 1.4, x + 0.2, 2.5, 0, 0.15) for x in (-2.25, -0.75, 2.25)],
                 *[box(x - 0.45, y - 0.3, x + 0.45, y + 0.3, 0, 0.15)
                   for x in (-3.6, 3.6) for y in (-1.1, 1.1)])
    return save("SW_Slide_SPDT_SHOUHAN_MSK12C02_RightAngle", [(body, METAL), (act, BLACK), (legs, METAL)])


def supermini():
    """ESP32-C3 SuperMini on 2 x 8 headers (plastic 2.5): board 18.00 x 22.52 (datasheet),
    1.0 thick, USB-C 9.0 x 7.4 x 3.2 overhanging the top edge by 1.3, ESP32-C3 4 x 4 x 0.9 -
    thickness and parts ОРІЄНТИР. Mounted on the bottom of the digital board (flipped by KiCad)."""
    zb = 2.5
    plastic, pins = [], []
    for x in (-7.62, 7.62):
        for i in range(8):
            p, q = header([x], -8.89 + i * 2.54, zb)
            plastic.append(p)
            pins.append(q)
    board = box(-9.0, -11.26, 9.0, 11.26, zb, zb + 1.0)
    usb = box(-4.5, -11.26 - 1.3, 4.5, -11.26 + 6.1, zb + 1.0, zb + 1.0 + 3.2)
    chip = box(-2, -2, 2, 2, zb + 1.0, zb + 1.9)
    return save("ESP32-C3_SuperMini_2x8_P2.54", [(board, PCB_BLACK), (usb, METAL), (chip, DARK),
                                                  (union(*plastic), BLACK), (union(*pins), PIN)])


def supermini_smd():
    """ESP32-C3 SuperMini soldered flat (D59): as supermini() without headers; pins from 1.5 below
    the USB edge (gen_footprints.py supermini_smd), USB-C overhang 1.4 - ОРІЄНТИР."""
    board = box(-9.0, -11.26, 9.0, 11.26, 0.05, 1.05)
    usb = box(-4.5, -11.26 - 1.4, 4.5, -11.26 + 6.1, 1.05, 1.05 + 3.2)
    chip = box(-2, -2, 2, 2, 1.05, 1.95)
    return save("ESP32-C3_SuperMini_SMD", [(board, PCB_BLACK), (usb, METAL), (chip, DARK)])


def oled():
    """0.96in OLED module (Rajguru outer dimension drawing): board 27.3 x 27.3, board + glass
    2.37; glass 26.7 x 19.26, active area 21.74 x 10.86; 4 x d2.5 holes 20.7 x 23.2 apart;
    header 4 x 2.54, 1.65 from the top edge; on its header (plastic 2.5) above the digital board.
    Board thickness 1.0 and the glass position along Y (active area centre at y +1.0, as the
    footprint) - ОРІЄНТИР, measure on the bought module."""
    zb = 2.5
    yh = -27.3 / 2 + 1.65
    p, q = header([-3.81 + i * 2.54 for i in range(4)], yh, zb)
    board = box(-13.65, -13.65, 13.65, 13.65, zb, zb + 1.0)
    for x in (-10.35, 10.35):
        for y in (-11.6, 11.6):
            board = board.cut(cyl(x, y, 2.5, zb - 0.1, zb + 1.1))
    aa_top = 1.0 - 10.86 / 2
    g0 = aa_top - 3.4
    glass = box(-13.35, g0, 13.35, g0 + 19.26, zb + 1.0, zb + 2.37)
    aa = box(-10.87, aa_top, 10.87, aa_top + 10.86, zb + 2.37, zb + 2.38)
    return save("OLED_0.96in_128x64_I2C_4pin", [(board, PCB_BLUE), (glass, GLASS), (aa, BLUE),
                                                 (p, BLACK), (q, PIN)])


def main():
    names = [fader_rs45(), rk14k(), ec12d(), cherry_mx(), sj_43514(), cts_204(5), cts_204(1), cls62(),
             msk12c02(), supermini(), supermini_smd(), oled(),
             uep(5.0, 2.0, "CP_Nichicon_UEP_D5.0_L11.0_P2.00_Horizontal"),
             uep(6.3, 2.5, "CP_Nichicon_UEP_D6.3_L11.0_P2.50_Horizontal")]
    print("\n".join(names))


if __name__ == "__main__":
    main()
