"""Generate the project symbols (hw/lib/pocket-digital.kicad_sym) for parts missing in KiCad 10.

Run: python3 hw/lib/gen_symbols.py   (from digital-mixer/)
Pin numbers follow the cited datasheets. Teensy 4.1 is taken unchanged from XenGi/teensy_library
(MIT, third_party/LICENSE-teensy_library.txt); the same box style as analog-mixer/hw/lib.
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "pocket-digital.kicad_sym"
G = 2.54
FONT = "(effects (font (size 1.27 1.27)))"
HIDDEN = "(effects (font (size 1.27 1.27)) (hide yes))"


def prop(name, value, x, y, hidden=False):
    return f'\t\t(property "{name}" "{value}" (at {x:.2f} {y:.2f} 0) {HIDDEN if hidden else FONT})'


def pin(kind, x, y, angle, name, num, length=G):
    return (f'\t\t\t(pin {kind} line (at {x:.2f} {y:.2f} {angle}) (length {length}) '
            f'(name "{name}" {FONT}) (number "{num}" {FONT}))')


def box_symbol(name, ref, footprint, datasheet, descr, left, right, width=10.16, kw=""):
    """left/right: lists of (number, name, kind); None leaves an empty row."""
    rows = max(len(left), len(right))
    h = rows * G
    top = (rows - 1) * G / 2
    body = [f'\t\t(symbol "{name}_0_1" (rectangle (start {-width / 2:.2f} {top + G:.2f}) '
            f'(end {width / 2:.2f} {top - h:.2f}) (stroke (width 0.254) (type default)) '
            '(fill (type background))))']
    pins = []
    for lst, x, ang in ((left, -width / 2 - G, 0), (right, width / 2 + G, 180)):
        for i, p in enumerate(lst):
            if p is None:
                continue
            num, pname, kind = p
            pins.append(pin(kind, x, top - i * G, ang, pname, num))
    return "\n".join([
        f'\t(symbol "{name}" (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)',
        prop("Reference", ref, 0, top + G + 1.27),
        prop("Value", name, 0, top - h - 1.27),
        prop("Footprint", footprint, 0, 0, True),
        prop("Datasheet", datasheet, 0, 0, True),
        prop("Description", descr, 0, 0, True),
        prop("ki_keywords", kw, 0, 0, True),
        *body,
        f'\t\t(symbol "{name}_1_1"', *pins, '\t\t)',
        '\t)'])


def tps63802():
    # TPS63802 SLVSEU9D, Pin Functions (VSON-HR-10): 1 EN, 2 MODE, 3 AGND, 4 FB, 5 PG, 6 VOUT,
    # 7 L2, 8 GND, 9 L1, 10 VIN
    return box_symbol("TPS63802", "U", "pocket-digital:Texas_VSON-HR-10_2x3mm_P0.5mm",
                      "docs/datasheets/tps63802.pdf", "Buck-boost 2 A, VIN 1.3-5.5 V, VOUT 1.8-5.2 V, VFB 0.5 V",
                      [("10", "VIN", "power_in"), ("1", "EN", "input"), ("2", "MODE", "input"),
                       ("9", "L1", "passive"), ("3", "AGND", "power_in"), ("8", "GND", "power_in")],
                      [("6", "VOUT", "power_out"), ("4", "FB", "input"), ("5", "PG", "open_collector"),
                       ("7", "L2", "passive"), None, None], width=12.7, kw="buck boost regulator")


def jack_pj327a():
    # PJ-327A 5 legs, numbers and contacts of the seller's drawing (docs/datasheets/pj-327a-seller-drawing.jpg):
    # 4 tip, 5 tip switch (closed to the tip without a plug), 3 ring, 1 and 2 sleeve (DM38)
    return box_symbol("AudioJack_Stereo_PJ-327A", "J", "pocket-digital:Jack_3.5mm_PJ-327A_SMT_Horizontal",
                      "docs/datasheets/pj-327a-seller-drawing.jpg",
                      "3.5 mm stereo jack PJ-327A SMT, tip switch",
                      [("4", "T", "passive"), ("5", "TN", "passive"), ("3", "R", "passive"),
                       ("1", "S", "passive"), ("2", "S2", "passive")], [], kw="audio jack stereo TRS PJ-327A")


# Electrical types normalised for ERC (the upstream symbol mixes them): the three 3V3 pins are one
# regulator output (passive here, the schematic flags the net), every GND is a ground input, VUSB is
# an input (VBUS of our USB-C).
TEENSY_TYPES = {"3V3": "passive", "GND": "power_in", "VUSB": "power_in"}


def teensy41():
    text = (HERE / "third_party" / "teensy41.kicad_sym").read_text().strip()
    pat = re.compile(r'\(pin (\w+) (\w+)(\s*\(at[^)]*\)\s*\(length[^)]*\)\s*(?:\(hide yes\)\s*)?\(name "([^"]*)")')
    text = pat.sub(lambda m: f"(pin {TEENSY_TYPES.get(m.group(4), m.group(1))} {m.group(2)}{m.group(3)}", text)
    return "\t" + text


def main():
    syms = [tps63802(), jack_pj327a(), teensy41()]
    OUT.write_text('(kicad_symbol_lib (version 20241209) (generator "pocket-digital-gen") '
                   '(generator_version "1.0")\n' + "\n".join(syms) + "\n)\n")
    print(OUT)


if __name__ == "__main__":
    main()
