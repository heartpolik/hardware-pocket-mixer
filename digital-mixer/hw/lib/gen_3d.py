"""3D models (STEP) of the project footprints (hw/lib/pocket-digital.pretty) for the KiCad 3D view and
the enclosure. Built from the same drawings as hw/lib/gen_footprints.py; helpers in common/cq3d.py.

Run with CadQuery (not KiCad's Python), from digital-mixer/:
  ../.venv-cq/bin/python hw/lib/gen_3d.py

Every model sits in its footprint's frame (x, -y), z = 0 on the PCB. Envelope dimensions come from
the drawings; heights or positions the drawings do not give are marked ОРІЄНТИР. Stock
footprints use the KiCad models.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))
import cq3d  # noqa: E402
from cq3d import BLACK, DARK, GLASS, METAL, PCB_BLACK, PIN, WHITE, box, cyl, header, union  # noqa: E402

OUT = Path(__file__).parent / "pocket-digital.3dshapes"


def save(name, parts):
    return cq3d.save(OUT, name, parts)


def ec12sy():
    """EC12SY-H6-17.5F5.0 SMD (seller drawing): body 12.5 x 13.2, 6 high (H6); bushing d6.8 to 11
    (body 6 + 5); shaft d6, top at L = 17.5, flat 4.5 over F = 5 at the top; pads / lugs as the
    footprint. Bushing height from the side view (6.0 + 5.0)."""
    body = box(-6.25, -6.6, 6.25, 6.6, 0.0, 6.0)
    bush = cyl(0, 0, 6.8, 6.0, 11.0)
    shaft = cyl(0, 0, 6.0, 11.0, 17.5).cut(box(-3.5, 1.5, 3.5, 3.5, 12.5, 17.6))
    legs = union(*[box(x - 0.5, y - 1.0, x + 0.5, y + 1.0, 0.0, 0.3)
                   for x, y in ((-2.5, -7.4), (2.5, -7.4), (-2.5, 7.4), (0.0, 7.4), (2.5, 7.4))])
    lugs = union(*[box(x - 1.0, -2.0, x + 1.0, 2.0, 0.0, 3.0) for x in (-7.0, 7.0)])
    return save("RotaryEncoder_EC12SY_SMD", [(body, METAL), (bush, DARK), (shaft, DARK), (legs, PIN),
                                             (lugs, METAL)])


def tsf1266():
    """TSF-1266 (seller drawing): body 6 x 6 (5.95 inner), 3.5 high, round cap d5 to 5.0, terminals
    1.4 wide, 6.7 over both."""
    body = box(-3.0, -3.0, 3.0, 3.0, 0.0, 3.5)
    cap = cyl(0, 0, 5.0, 3.5, 5.0)
    legs = union(*[box(x - 0.35, -0.7, x + 0.35, 0.7, 0.0, 0.3) for x in (-3.0, 3.0)])
    return save("SW_TSF-1266_6x6mm_SMD", [(body, BLACK), (cap, DARK), (legs, METAL)])


def latch():
    """5.8 mm self-locking DPDT SMD (seller drawing): body 5.8 x 5.8, 5.2 high on a 0.3 standoff;
    plunger 3.5 x 2.9 to 10.5 (unlatched); legs 0.6 wide, pitch 2.0, to 4.65 from the centre."""
    body = box(-2.9, -2.9, 2.9, 2.9, 0.3, 5.5)
    plunger = box(-1.45, -1.75, 1.45, 1.75, 5.5, 10.5)
    legs = union(*[box(x - 0.3, s * 2.9, x + 0.3, s * 4.65, 0.0, 0.3) for x in (-2.0, 0.0, 2.0) for s in (-1, 1)])
    return save("SW_Push_Latching_DPDT_5.8mm_SMD", [(body, WHITE), (plunger, DARK), (legs, METAL)])


def lcd():
    """GMT147-01M on its 1 x 8 header (plastic 2.5, as Rev A): PCB 20.96 x 44, T 1.2; holes d3.5;
    glass over the active area 17.39 x 32.35 (5.82 from the top edge). Glass outline 19.6 x 37 and
    1.5 thick - ОРІЄНТИР."""
    zb = 2.5
    plastic, pins = header([8.89 - i * 2.54 for i in range(8)], 20.5, zb)
    board = box(-10.48, -22.0, 10.48, 22.0, zb, zb + 1.2)
    for x in (-8.27, 8.27):
        board = board.cut(cyl(x, -22.0 + 2.07, 3.5, zb - 0.1, zb + 1.3))
    glass = box(-9.8, -22.0 + 4.0, 9.8, -22.0 + 41.0, zb + 1.2, zb + 2.7)
    aa = box(-8.7, -22.0 + 5.82, 8.7, -22.0 + 5.82 + 32.35, zb + 2.7, zb + 2.71)
    return save("LCD_GMT147SPI", [(board, PCB_BLACK), (glass, GLASS), (aa, DARK), (plastic, BLACK),
                                  (pins, PIN)])


def teensy():
    """Teensy 4.1 on 2.54 pin headers (DM35), PJRC dimensions_teensy41.png: board 60.96 x 17.78 x 1.57
    on the 2.5 header spacer, micro-USB 7.5 wide, 5.0 long, 0.7 past the USB end (-X). Its parts face
    away from our board. MCU and microSD socket size and position - ОРІЄНТИР."""
    zb = 2.5
    xs = [-29.21 + i * 2.54 for i in range(24)]
    p1, n1 = header(xs, 7.62, zb)
    p2, n2 = header(xs, -7.62, zb)
    board = box(-30.48, -8.89, 30.48, 8.89, zb, zb + 1.57)
    top = zb + 1.57
    usb = box(-31.18, -3.75, -26.18, 3.75, top, top + 2.5)
    mcu = box(-12.0, -5.0, -2.0, 5.0, top, top + 1.2)
    sd = box(18.0, -6.0, 30.48, 6.0, top, top + 1.8)
    return save("Teensy41_THT", [(board, PCB_BLACK), (usb, METAL), (mcu, DARK), (sd, METAL),
                                 (union(p1, p2), BLACK), (union(n1, n2), PIN)])


def xfl4015():
    """Coilcraft XFL4015 (Doc 769-2): 4.0 x 4.0, 1.5 high max."""
    return save("L_Coilcraft_XFL4015", [(box(-2.0, -2.0, 2.0, 2.0, 0.0, 1.5), DARK)])


def vson():
    """TI DLA0010A VSON-HR-10: 2 x 3, 1.0 high max."""
    return save("Texas_VSON-HR-10_2x3mm_P0.5mm", [(box(-1.0, -1.5, 1.0, 1.5, 0.0, 1.0), BLACK)])


def usb4110():
    """GCT USB4110-GF-A, drawing rev. B4 (docs/datasheets/gct-usb4110.pdf), in the frame of the KiCad
    footprint USB_C_Receptacle_GCT_USB4110 (mouth at +Y on the PCB edge line): shell 8.94 x 7.35,
    3.16 high on a 0.10 standoff (3.26 total); opening 8.34 x 2.56, its axis 1.68 below the top;
    side tabs on the 2.18 x 2.00 pads, tails 7.70 long overall. Tongue thickness - ОРІЄНТИР."""
    zc = 3.26 - 1.68
    shell = box(-4.47, -3.675, 4.47, 3.675, 0.10, 3.26).cut(box(-4.17, -2.5, 4.17, 3.8, zc - 1.28, zc + 1.28))
    tongue = box(-3.3, -2.5, 3.3, 3.2, zc - 0.35, zc + 0.35)
    tabs = union(*[box(s * 4.47, y - 1.0, s * 6.2, y + 1.0, 0.0, 0.3) for s in (-1, 1) for y in (-3.105, 0.825)])
    pins = union(*[box(x - 0.15, -3.85, x + 0.15, -3.675, 0.0, 0.2)
                   for x in (-3.2, -2.4, -1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 1.75, 2.4, 3.2)])
    return save("USB_C_Receptacle_GCT_USB4110", [(shell, METAL), (tongue, BLACK), (tabs, METAL), (pins, PIN)])


def alps_rs20111():
    """Alps RS201111J011 (docs/datasheets/alps-rs-super-slide.pdf, p. 387, drawing No. 1): body 35 x 8,
    7 high over the PCB, slot in the top face; lever 5 along the travel x 2, 15 above the body (seller's
    photo - the lever length L1 is an ordering option, ОРІЄНТИР); pins 0.4 x 1, 3.5 below. Footprint frame:
    pins 1 / 3 at x 0 / 25, pin 2 at y -3.75, centre (12.5, -1.875); lever at mid travel."""
    cx, cy = 12.5, -1.875
    body = box(cx - 17.5, cy - 4.0, cx + 17.5, cy + 4.0, 0.0, 7.0).cut(box(cx - 12.5, cy - 0.6, cx + 12.5, cy + 0.6, 6.0, 7.1))
    lever = box(cx - 2.5, cy - 1.0, cx + 2.5, cy + 1.0, 6.0, 22.0)
    pins = union(*[box(x - 0.5, y - 0.2, x + 0.5, y + 0.2, -3.5, 0.0) for x, y in ((0, 0), (0, -3.75), (25, 0))])
    return save("Potentiometer_Alps_RS20111_Single_Slide", [(body, METAL), (lever, DARK), (pins, PIN)])


def jst_ph_sm4():
    """JST S2B-PH-SM4-TB (side entry, SMT) in the frame of the KiCad footprint: body between the
    signal pads (y -1.1) and the mating face (y +5.1, F.Fab), 7.9 wide; height 4.8 - ОРІЄНТИР
    (JST ePH.pdf not in the repo)."""
    body = box(-3.95, -1.1, 3.95, 5.1, 0.0, 4.8).cut(box(-2.9, 1.0, 2.9, 5.2, 0.8, 4.0))
    legs = union(*[box(x - 0.3, -4.0, x + 0.3, -1.1, 0.0, 0.3) for x in (-1.0, 1.0)],
                 *[box(s * 3.95, 1.5, s * 4.0, 4.3, 0.0, 3.0) for s in (-1, 1)])
    return save("JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal", [(body, WHITE), (legs, METAL)])


def pj327a():
    """PJ-327A in the footprint frame (seller's drawing docs/datasheets/pj-327a-seller-drawing.jpg and
    seller's STEP): body 6.0 x 12.3, 4.4 high on the legs; nose d5.0, 2.0 long in front of y = 0, its
    axis 2.3 up (it reaches 0.2 below the seating plane - off the board edge); legs 1.0 wide out to
    x +-4.8 on the pad centres; pegs d0.75, 0.6 below. Axis height - ОРІЄНТИР (seller's STEP)."""
    import cadquery as cq
    body = box(-3.0, 0.0, 3.0, 12.3, 0.1, 4.5)
    nose = cq.Workplane("XZ").center(0, 2.3).circle(2.5).circle(1.8).extrude(-2.0)
    legs = union(*[box(s * 2.35, y - 0.5, s * 4.8, y + 0.5, 0.0, 0.2)
                   for s, y in ((1, 1.7), (1, 5.4), (1, 11.4), (-1, 2.7), (-1, 9.7))])
    pegs = union(*[cyl(0, y, 0.75, -0.6, 0.1) for y in (3.0, 9.0)])
    return save("Jack_3.5mm_PJ-327A_SMT_Horizontal", [(body, BLACK), (nose, BLACK), (legs, METAL), (pegs, BLACK)])


def main():
    print("\n".join([ec12sy(), tsf1266(), latch(), lcd(), teensy(), xfl4015(), vson(), usb4110(), alps_rs20111(), jst_ph_sm4(), pj327a()]))


if __name__ == "__main__":
    main()
