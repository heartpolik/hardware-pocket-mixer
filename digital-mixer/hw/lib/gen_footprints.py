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


def teensy41_smd():
    """Teensy 4.1 lying flat, its plated holes soldered onto SMD pads from above (as the SuperMini
    in Rev A, D59). PJRC dimensions_teensy41.png: board 60.96 x 17.78, rows 15.24 apart, pitch 2.54,
    first pin 1.27 from the USB end, micro-USB 0.7 past the board. Origin = module centre, USB to -X,
    bottom row (GND, 0..12, 3V3, 24..32 = pads 1..24) at +Y, top row (33..41, GND, 13..23, 3V3, GND,
    VIN = pads 25..48) at -Y - numbering of the XenGi symbol. Placed on the bottom side of the main
    board: the Teensy's own top (SD socket, PJRC card) then faces down and the SD end is put at the
    board edge (DM12). The flat bottom of the Teensy lies on the board: a window under the USB end
    gives access to its USB device pads (VUSB, D-, D+, PJRC card back) and to the VIN/VUSB trace that
    must be cut; pads 49, 66, 67 on the other side of the main board take short wires through it."""
    f = FP("Teensy41_SMD",
           "Teensy 4.1 soldered flat: SMD pads under the module holes (2 x 24, rows 15.24, pitch 2.54, "
           "first pin 1.27 from the USB end) - PJRC dimensions_teensy41.png. Window for wires to the USB "
           "device pads; wire pads VUSB / D- / D+ on the opposite side.",
           "Teensy 4.1 module SMD", attr="smd")
    for i in range(24):
        x = -29.21 + i * 2.54
        f.smd(str(i + 1), x, 7.62, 1.7, 1.7, shape="circle", paste=False)
        f.smd(str(48 - i), x, -7.62, 1.7, 1.7, shape="circle", paste=False)
    # window 1..5 mm from the USB end, where the PJRC card back shows the USB device pads and the
    # VIN/VUSB trace (position from the photo - ОРІЄНТИР); wire pads beside it, over the module
    wx0, wx1 = -30.48 + 1.0, -30.48 + 5.0
    f.rect(wx0, -5.0, wx1, 5.0, "Edge.Cuts", 0.1)
    for num, y, name in (("49", -2.54, "VUSB"), ("66", 0.0, "D-"), ("67", 2.54, "D+")):
        f.smd(num, wx1 + 1.6, y, 1.6, 1.4, side="B", paste=False)
        f.items.append(f'\t(fp_text user "{name}" (at {fmt(wx1 + 4.2)} {fmt(y)}) (layer "B.SilkS") '
                       '(effects (font (size 0.8 0.8) (thickness 0.12)) (justify mirror)))')
    f.rect(-30.48, -8.89, 30.48, 8.89, "F.Fab", FAB)
    f.rect(-30.48 - 0.7, -3.75, -30.48 + 5.0, 3.75, "F.Fab", FAB)   # micro-USB, 7.5 wide (PJRC)
    f.text(25.0, 0, "SD", "F.Fab", 1.0)
    f.line(-30.48, -8.89, 30.48, -8.89, "F.SilkS", SILK)
    f.line(-30.48, 8.89, 30.48, 8.89, "F.SilkS", SILK)
    f.text(-29.21, 5.6, "1", "F.SilkS", 0.8)
    f.rect(-31.43, -9.14, 30.73, 9.14, "F.CrtYd", CRT)
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


def latch_7x7():
    """7 x 7 self-locking DPDT push switch, seller drawing (docs/datasheets/push-latching-dpdt-*):
    6 x d1 holes, 2 rows of 3, pitch 2.0, rows 5.0 apart; body 7 x 7, 12.3 high (latched 11.0). The
    middle pin of each row is the common (filled dot of the circuit diagram): pins 1-2-3 / 4-5-6 =
    A-B-C of Switch:SW_DPDT_x2 per pole, B = common."""
    f = FP("SW_Push_Latching_DPDT_7x7mm", "7x7 self-locking DPDT push switch, 6 pins d1, pitch 2.0, rows 5.0 "
           "(seller drawing); middle pin of each row common", "push switch latching DPDT 7x7")
    for i in range(3):
        f.tht(str(i + 1), -2.0 + i * 2.0, -2.5, 1.6, 1.0, "rect" if i == 0 else "circle")
        f.tht(str(i + 4), -2.0 + i * 2.0, 2.5, 1.6, 1.0)
    f.body(-3.5, -3.5, 3.5, 3.5)
    return f.write(-4.6, 4.6)


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
    print("\n".join([teensy41_smd(), vson_hr10(), xfl4015(), tsf1266(), latch_7x7(), lcd_gmt147(),
                     mounting_hole_m2()]))


if __name__ == "__main__":
    main()
