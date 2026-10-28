"""Generate the project footprints (hw/lib/pocket-digital.pretty).

Run: python3 hw/lib/gen_footprints.py   (from digital-mixer/)
Every footprint names its source in `descr` (drawings in docs/datasheets).
Writer: common/fpgen.py. 3D models of the same names: hw/lib/gen_3d.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))
import fpgen  # noqa: E402
from fpgen import CRT, FAB, SILK, fmt  # noqa: E402,F401

OUT = Path(__file__).parent / "pocket-digital.pretty"
MODEL_DIR = "${KIPRJMOD}/../lib/pocket-digital.3dshapes"


class FP(fpgen.FP):
    OUT = OUT
    GENERATOR = "pocket-digital-gen"

    def __init__(self, name, descr, tags, attr="through_hole", flags="", model=True):
        super().__init__(name, descr, tags, attr, flags, f"{MODEL_DIR}/{name}.step" if model else None)


def teensy41_tht():
    """Teensy 4.1 on standard 2.54 pin headers through our board (DM35): PJRC dimensions_teensy41.png -
    board 60.96 x 17.78, rows 15.24 apart, pitch 2.54, first pin 1.27 from the USB end. Origin = module
    centre, USB to -X, bottom row (GND, 0..12, 3V3, 24..32 = pads 1..24) at +Y, top row (33..41, GND,
    13..23, 3V3, GND, VIN = pads 25..48) at -Y - numbering of the XenGi symbol. Placed on the bottom side
    of the main board, the header spacer (2.5) between the boards: the gap holds PSRAM chips under the SD
    socket (PJRC psram.html). Pins are soldered from the top side. USB device D- / D+ on the Teensy
    bottom: holes 1.78 from the USB end (pin 1 + 0.51), 8.89 / 6.35 from the pin-1 row (bottom view of
    the PJRC drawing), D+ nearer the pin-1 row (PJRC card back): through holes 66 / 67 under them for
    two thin wires soldered from the top of our board (the module pads sit under its micro-USB, so a
    header pin cannot pass through the module).
    VUSB next to them (card photo, no dimension - ОРІЄНТИР): wire pad 49 run out past the module end."""
    f = FP("Teensy41_THT",
           "Teensy 4.1 on 2.54 pin headers (2 x 24, rows 15.24) - PJRC dimensions_teensy41.png; "
           "through holes D- / D+ under the USB device holes of the module (PJRC drawing), wire pad VUSB",
           "Teensy 4.1 module THT header")
    for i in range(24):
        x = -29.21 + i * 2.54
        f.tht(str(i + 1), x, 7.62, 1.7, 1.0, shape="rect" if i == 0 else "circle")
        f.tht(str(48 - i), x, -7.62, 1.7, 1.0)
    # USB device D- / D+: through holes for two wires from the Teensy's own D- / D+ pads;
    # VUSB: wire pad from under the module out past its USB end (no dimension for the Teensy pad)
    x_hole, x_out = -30.48 + 1.78, -30.48 - 0.8
    for num, y, name in (("66", -1.27, "D-"), ("67", 1.27, "D+")):
        f.tht(num, x_hole, y, 1.6, 1.0)
        f.text(x_hole + 2.0, y, name, "F.SilkS", 0.7)
    f.smd("49", (x_hole + 0.5 + x_out) / 2, -3.81, x_hole + 0.5 - x_out, 1.0, paste=False)
    f.text(x_hole + 2.4, -3.81, "VUSB", "F.SilkS", 0.7)
    f.rect(-30.48, -8.89, 30.48, 8.89, "F.Fab", FAB)
    f.rect(-30.48 - 0.7, -3.75, -30.48 + 5.0, 3.75, "F.Fab", FAB)   # micro-USB, 7.5 wide (PJRC)
    f.text(25.0, 0, "SD", "F.Fab", 1.0)
    f.line(-30.48, -8.89, 30.48, -8.89, "F.SilkS", SILK)
    f.line(-30.48, 8.89, 30.48, 8.89, "F.SilkS", SILK)
    f.text(-29.21, 5.6, "1", "F.SilkS", 0.8)
    f.rect(-31.53, -9.14, 30.73, 9.14, "F.CrtYd", CRT)
    return f.write(-10.5, 10.5)


def vson_hr10():
    """TI DLA0010A (TPS63802), EXAMPLE BOARD LAYOUT p. 36: pins 1-5 left, pads 0.6 x 0.25 at
    x -0.9; pins 6, 7, 9, 10 right, 0.9 x 0.25 at x +0.75; pin 8 (GND) 1.3 x 0.25 from x -0.1 to 1.2;
    pitch 0.5, pin 1 and 10 at y -1.0. Origin = package centre."""
    f = FP("Texas_VSON-HR-10_2x3mm_P0.5mm", "TI DLA0010A VSON-HR-10 2 x 3 mm, land pattern example "
           "(TPS63802 SLVSEU9D p. 36)", "VSON-HR DLA0010A TPS63802", attr="smd")
    for i in range(5):
        f.smd(str(i + 1), -0.9, -1.0 + i * 0.5, 0.6, 0.25)
    for num, y in (("10", -1.0), ("9", -0.5), ("7", 0.5), ("6", 1.0)):
        f.smd(num, 0.75, y, 0.9, 0.25)
    f.smd("8", 0.55, 0.0, 1.3, 0.25)
    f.rect(-1.0, -1.5, 1.0, 1.5, "F.Fab", FAB)
    f.circle(-1.45, -1.3, 0.1, "F.SilkS", SILK)
    f.rect(-1.45, -1.75, 1.45, 1.75, "F.CrtYd", CRT)
    return f.write(-2.5, 2.5)


def xfl4015():
    """Coilcraft XFL4015, Document 769-2 rev. 03/10/26, recommended land pattern: two pads
    0.98 x 3.4, 2.37 apart; body 4.0 x 4.0."""
    f = FP("L_Coilcraft_XFL4015", "Coilcraft XFL4015 4 x 4 x 1.5 mm, recommended land pattern (Doc 769-2)",
           "inductor Coilcraft XFL4015", attr="smd")
    for num, x in (("1", -1.675), ("2", 1.675)):
        f.smd(num, x, 0, 0.98, 3.4)
    f.body(-2.0, -2.0, 2.0, 2.0)
    return f.write(-3.2, 3.2)


def tsf1266():
    """TSF-1266 6 x 6 x 5 SMT tact, seller drawing (docs/datasheets/tsf-1266-drawing.png): two
    terminals; P.C.B mounting pattern 2 pads 2 x 2, inner gap 4, overall 8; body 6 x 6 (6.7 with the
    terminals), 5 high."""
    f = FP("SW_TSF-1266_6x6mm_SMD", "TSF-1266 6x6x5 SMT tact switch, 2 terminals; pads 2 x 2 at +-3.0 "
           "(seller drawing, P.C.B mounting pattern)", "tact switch 6x6 SMD TSF-1266", attr="smd")
    for num, x in (("1", -3.0), ("2", 3.0)):
        f.smd(num, x, 0, 2.0, 2.0)
    f.rect(-3.0, -3.0, 3.0, 3.0, "F.Fab", FAB)
    f.line(-1.9, -3.0, 1.9, -3.0, "F.SilkS", SILK)
    f.line(-1.9, 3.0, 1.9, 3.0, "F.SilkS", SILK)
    f.rect(-4.25, -3.25, 4.25, 3.25, "F.CrtYd", CRT)
    return f.write(-4.2, 4.2)


def latch_smd():
    """5.8 x 5.8 self-locking DPDT push switch, SMD, seller drawing
    (docs/datasheets/push-latching-dpdt-5.8mm-smd-drawing.png): body 5.8 x 5.8, 10.5 high (plunger
    3.5 x 2.9, 4.8 above the body); 2 rows of 3 legs, pitch 2.0, leg 0.6 wide, 8.3 / 9.3 tip to tip
    (side / bottom view). Pins top row 3-2-1, bottom row 6-5-4 (left to right, top view); FREE 1-2,
    4-5, PUSH (latched) 2-3, 5-6 - 2 and 5 are the commons. No land pattern on the drawing: pads
    1.0 x 2.0 from the body edge (2.9) to 4.9, past both tip values - ОРІЄНТИР."""
    f = FP("SW_Push_Latching_DPDT_5.8mm_SMD", "5.8x5.8 self-locking DPDT push switch SMD, 2 x 3 legs pitch 2.0 "
           "(seller drawing); 2 and 5 common, latched 2-3 / 5-6; pads 1.0 x 2.0 at +-3.9 - verify",
           "push switch latching DPDT SMD 5.8mm", attr="smd")
    for i, (top, bot) in enumerate((("3", "6"), ("2", "5"), ("1", "4"))):
        f.smd(top, -2.0 + i * 2.0, -3.9, 1.0, 2.0)
        f.smd(bot, -2.0 + i * 2.0, 3.9, 1.0, 2.0)
    f.rect(-2.9, -2.9, 2.9, 2.9, "F.Fab", FAB)
    f.rect(-1.45, -1.75, 1.45, 1.75, "F.Fab", FAB)              # plunger
    for x in (-2.9, 2.9):
        f.line(x, -2.6, x, 2.6, "F.SilkS", SILK)
    f.text(3.6, -3.9, "1", "F.SilkS", 0.6)
    f.rect(-3.15, -5.15, 3.15, 5.15, "F.CrtYd", CRT)
    return f.write(-6.0, 6.0)


def ec12sy_smd():
    """EC12SY-H6-17.5F5.0-24C24P-SMD-612 encoder with push switch, seller drawing
    (docs/datasheets/ec12sy-smd-encoder-drawing.png, "Mounting hole detail"): A / C / B pads
    pitch 2.5 along the bottom, S1 / S2 5.0 apart along the top, 5 pads 1.3 x 3.5, 20.0 over both
    rows; 2 side lugs 3.0 x 5.0, 18.0 over both (pads cut to 6.0..7.95 from the axis: the tabs end at 7.75, 15.5
    over both in the top view - room for the Teensy header next to channel 4, DM35); body 12.5 x 13.2, height 6, shaft d6 (flat),
    17.5 above the PCB (L), bushing d6.8. Locating holes d1.5 and d1.2 on the lug axis at 2.0 left
    and 2.5 right of the centre - the drawing is not to scale and the dimension lines are
    ambiguous: ПЕРЕВІРИТИ on a sample. Lugs centred on the body (drawing: ~0.2 above) - ПРИПУЩЕННЯ.
    Origin = shaft axis, S1 / S2 toward -Y."""
    f = FP("RotaryEncoder_EC12SY_SMD", "EC12SY SMD rotary encoder with switch, 24 detents (seller drawing); "
           "pads 1.3 x 3.5, lugs 1.95 x 5.0; locating holes d1.5 / d1.2 - verify on a sample",
           "rotary encoder SMD EC12 switch", attr="smd")
    for num, x in (("S1", -2.5), ("S2", 2.5)):
        f.smd(num, x, -8.25, 1.3, 3.5)
    for num, x in (("A", -2.5), ("C", 0.0), ("B", 2.5)):
        f.smd(num, x, 8.25, 1.3, 3.5)
    for x in (-6.975, 6.975):                     # lug pads 6.0..7.95: tabs end at 7.75 (15.5 over both)
        f.smd("MP", x, 0.0, 1.95, 5.0)
    f.npth(-2.0, 0.0, 1.5)
    f.npth(2.5, 0.0, 1.2)
    f.rect(-6.25, -6.6, 6.25, 6.6, "F.Fab", FAB)
    f.circle(0, 0, 3.0, "F.Fab", FAB)
    # silk: body outline where it clears the pads by 0.2
    for x in (-6.25, 6.25):
        f.line(x, -6.6, x, -2.7, "F.SilkS", SILK)
        f.line(x, 2.7, x, 6.6, "F.SilkS", SILK)
    for y in (-6.6, 6.6):
        f.line(-5.8, y, -3.35, y, "F.SilkS", SILK)
        f.line(3.35, y, 5.8, y, "F.SilkS", SILK)
    f.text(-4.6, -8.25, "S1", "F.SilkS", 0.6)
    f.text(-4.6, 8.25, "A", "F.SilkS", 0.6)
    # courtyard follows the pads: the corners stay free (M2 hole next to MASTER, DM25)
    q = [(3.4, -10.25), (3.4, -6.85), (6.5, -6.85), (6.5, -2.75), (8.1, -2.75)]   # right half, top
    q += [(x, -y) for x, y in reversed(q)]                                          # right half, bottom
    f.poly(q + [(-x, -y) for x, y in q], "F.CrtYd", CRT)                            # left half
    return f.write(-11.2, 11.2)


def lcd_gmt147():
    """GMT147-01M (GMT147SPI) on its pin header, seller drawing docs/datasheets/gmt147-01m-drawing.webp:
    PCB 20.96 x 44, T 1.2; 8 holes d1.57 at P2.54 (17.78) along the bottom edge - seen from the
    display side BL ... GND left to right, so pin 1 (GND) is at +X; 2 x d3.5 holes 16.54 apart, 2.07
    below the top edge; FPC seat 2.05 high on the back at the top end (stays above our board on the
    header). Header row 1.5 from the bottom edge: scaled from the drawing (no dimension) - ОРІЄНТИР.
    The drawing gives 2.31 from the left edge to the left hole (2.21 if centred) - holes centred here.
    Origin = module centre, display side up, holes toward -Y."""
    f = FP("LCD_GMT147SPI", "GMT147-01M 1.47in 172x320 module on 1x8 P2.54 header (seller drawing); "
           "header row 1.5 from the edge scaled - verify; M2 holes under the module holes d3.5",
           "LCD ST7789 GMT147SPI")
    for i in range(8):
        f.tht(str(i + 1), 8.89 - i * 2.54, 22.0 - 1.5, 1.7, 1.0, "rect" if i == 0 else "circle")
    for x in (-8.27, 8.27):
        f.npth(x, -22.0 + 2.07, 2.2)
    f.body(-10.48, -22.0, 10.48, 22.0)
    f.rect(-8.7, -22.0 + 5.82, 8.7, -22.0 + 5.82 + 32.35, "F.Fab", FAB)     # active area 17.39 x 32.35
    f.text(8.89, 22.0 - 3.2, "GND", "F.SilkS", 0.7)
    return f.write(-23.2, 23.2)


def pj327a():
    """PJ-327A 3.5 mm stereo jack, SMT, 5 legs - the AliExpress seller's drawing (docs/datasheets/
    pj-327a-seller-drawing.jpg, DM38): PCB pads 5 x 2 x 3 (+-0.1), rows 6.8 apart; from the body front
    (plug side) 1 at 1.7, 3 at 5.4, 5 at 11.4 on one side, 2 at 2.7, 4 at 9.7 on the other; pegs d0.75
    at 3 and 9 on the axis (holes d1.30 as the HOOYA drawing - the seller's hole size is not legible);
    1 and 2 sleeve, 3 ring, 4 tip, 5 its normally-closed switch. The seller's STEP has its legs on the
    same centres; HOOYA / XKB / SOFNG (pj-327a-*.pdf) differ by up to 0.4. Frame: plug axis on x = 0,
    body front at y = 0, body towards +y; the nose (2.0) is past the board edge."""
    f = FP("Jack_3.5mm_PJ-327A_SMT_Horizontal", "PJ-327A 3.5 mm stereo jack SMT, 5 legs (seller drawing): "
           "1 / 2 sleeve, 3 ring, 4 tip, 5 tip switch", "audio jack 3.5mm stereo SMT PJ-327A", attr="smd")
    for num, x, y in (("1", 3.4, 1.7), ("3", 3.4, 5.4), ("5", 3.4, 11.4), ("2", -3.4, 2.7), ("4", -3.4, 9.7)):
        f.smd(num, x, y, 3.0, 2.0)
    for y in (3.0, 9.0):
        f.npth(0, y, 1.3)
    f.rect(-3.0, 0.0, 3.0, 12.3, "F.Fab", FAB)
    f.rect(-2.5, -2.0, 2.5, 0.0, "F.Fab", FAB)                  # nose, past the board edge
    f.text(0, 6.0, "PLUG ^", "F.Fab", 0.8)
    f.line(-3.0, 4.0, -3.0, 8.4, "F.SilkS", SILK)
    f.line(3.0, 6.7, 3.0, 10.1, "F.SilkS", SILK)
    f.line(-1.9, 12.3, 1.9, 12.3, "F.SilkS", SILK)
    f.rect(-5.15, -2.25, 5.15, 12.65, "F.CrtYd", CRT)
    return f.write(-3.2, 13.6)


def mounting_hole_m2():
    """As analog-mixer/hw/lib/gen_footprints.py mounting_hole_m2 (D57): KiCad MountingHole_2.2mm_M2_Pad
    pad and drill, courtyard r 2.45 on both sides for a standoff, nut or screw head."""
    f = FP("MountingHole_2.2mm_M2_Pad_Standoff_2Side",
           "M2 mounting hole, plated, pad 4.4, drill 2.2 (as KiCad MountingHole_2.2mm_M2_Pad). "
           "Courtyard r 2.45 on F and B.", "mountinghole M2 standoff",
           flags=" board_only exclude_from_pos_files exclude_from_bom", model=False)
    f.items.append('\t(pad "1" thru_hole circle (at 0 0) (size 4.4 4.4) (drill 2.2) (layers "*.Cu" "*.Mask") '
                   '(zone_connect 2))')
    f.circle(0, 0, 2.45, "F.CrtYd", CRT)
    f.circle(0, 0, 2.45, "B.CrtYd", CRT)
    return f.write(-3.2, 3.2)


def main():
    print("\n".join([teensy41_tht(), vson_hr10(), xfl4015(), tsf1266(), latch_smd(), ec12sy_smd(), lcd_gmt147(),
                     pj327a(), mounting_hole_m2()]))


if __name__ == "__main__":
    main()
