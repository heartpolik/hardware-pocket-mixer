"""Generate project symbols (hw/lib/diy-mixer.kicad_sym) for parts missing in KiCad 10.

Run: python3 hw/lib/gen_symbols.py
Pin numbers match the footprints from gen_footprints.py and the cited datasheets.
"""
from pathlib import Path

OUT = Path(__file__).parent / "diy-mixer.kicad_sym"
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
    for side, lst, x, ang in (("L", left, -width / 2 - G, 0), ("R", right, width / 2 + G, 180)):
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


def lt1930():
    # LT1930 datasheet, S5 package: 1 SW, 2 GND, 3 FB, 4 SHDN, 5 VIN
    return box_symbol("LT1930", "U", "Package_TO_SOT_SMD:SOT-23-5", "docs/datasheets/1930f.pdf",
                      "1.2 MHz boost DC/DC, 1 A switch, SOT-23-5",
                      [("5", "VIN", "power_in"), ("4", "~{SHDN}", "input"), ("2", "GND", "power_in")],
                      [("1", "SW", "output"), ("3", "FB", "input"), None], kw="boost regulator")


def supermini():
    left = [("1", "5V", "power_in"), ("2", "GND", "power_in"), ("3", "3V3", "power_out"),
            ("4", "GPIO4", "bidirectional"), ("5", "GPIO3", "bidirectional"),
            ("6", "GPIO2", "bidirectional"), ("7", "GPIO1", "bidirectional"),
            ("8", "GPIO0", "bidirectional")]
    right = [("9", "GPIO5", "bidirectional"), ("10", "GPIO6", "bidirectional"),
             ("11", "GPIO7", "bidirectional"), ("12", "GPIO8", "bidirectional"),
             ("13", "GPIO9", "bidirectional"), ("14", "GPIO10", "bidirectional"),
             ("15", "GPIO20/U0RXD", "bidirectional"), ("16", "GPIO21/U0TXD", "bidirectional")]
    return box_symbol("ESP32-C3_SuperMini", "U", "diy-mixer:ESP32-C3_SuperMini_2x8_P2.54",
                      "docs/datasheets/esp32-c3-supermini.pdf",
                      "ESP32-C3 SuperMini module. Pin 5V = USB VBUS of the module (BAT60J -> ME6211).",
                      left, right, width=27.94, kw="ESP32 module")


def oled():
    return box_symbol("OLED_128x64_I2C", "DS", "diy-mixer:OLED_0.96in_128x64_I2C_4pin",
                      "docs/datasheets/oled-0.96-128x64-4pin.pdf", "0.96in OLED SSD1306, I2C, 4 pins",
                      [("1", "VCC", "power_in"), ("2", "GND", "power_in"),
                       ("3", "SCL", "input"), ("4", "SDA", "bidirectional")], [], kw="OLED display")


def jack():
    return box_symbol("AudioJack_TRRS_SJ-4351X", "J", "diy-mixer:CUI_SJ-4351X-SMT_TRRS_Horizontal",
                      "docs/datasheets/sj-4351x-smt-series.pdf",
                      "3.5 mm TRRS jack, CUI SJ-4351X-SMT. 5/6 switches only on 43515/43516.",
                      [("2", "T", "passive"), ("3", "R1", "passive"), ("4", "R2", "passive"),
                       ("1", "S", "passive")],
                      [("5", "TSW", "passive"), ("6", "RSW", "passive")], kw="audio jack TRRS")


def jack_43514():
    return box_symbol("AudioJack_TRRS_SJ-43514", "J", "diy-mixer:CUI_SJ-43514-SMT_TRRS_Horizontal",
                      "docs/datasheets/sj-4351x-smt-series.pdf", "3.5 mm TRRS jack CUI SJ-43514-SMT (no switches)",
                      [("2", "T", "passive"), ("3", "R1", "passive"), ("4", "R2", "passive"),
                       ("1", "S", "passive")], [], kw="audio jack TRRS")


def pot_common_gnd():
    # Alps RK14K12D, catalog p.327 "Without tap for volume": common bottom terminal
    return box_symbol("R_Potentiometer_Dual_CommonEnd", "RV", "diy-mixer:Alps_RK14K12D_Vertical_Volume",
                      "docs/datasheets/RK14K12-1370745.pdf",
                      "Dual pot with common bottom end (Alps RK14K12D). 1 common, A: 2 wiper 3 top; "
                      "B: 5 wiper 6 top",
                      [("3", "A_TOP", "passive"), ("2", "A_WIPER", "passive"), ("1", "COMMON", "passive")],
                      [("6", "B_TOP", "passive"), ("5", "B_WIPER", "passive"), None], kw="potentiometer dual")


def dip_spdt_cts():
    """CTS 204-125ST: 5 units, positional pads (gen_footprints.cts_204_125st):
    switch k uses bottom pads 2k-1, 2k and top pads 22-2k, 21-2k. Terminal function not stated
    in the datasheet - pin names are positional (B1, B2 bottom row, T1, T2 top row)."""
    units = []
    for k in range(1, 6):
        pins = [pin("passive", -5.08, 1.27, 0, "T1", str(22 - 2 * k)),
                pin("passive", -5.08, -1.27, 0, "T2", str(21 - 2 * k)),
                pin("passive", 5.08, 1.27, 180, "B1", str(2 * k - 1)),
                pin("passive", 5.08, -1.27, 180, "B2", str(2 * k))]
        units.append(f'\t\t(symbol "SW_DIP_SPDT_x05_CTS204_{k}_1"\n' + "\n".join(pins) + '\n\t\t)')
    body = ('\t\t(symbol "SW_DIP_SPDT_x05_CTS204_0_1" (rectangle (start -2.54 2.54) (end 2.54 -2.54) '
            '(stroke (width 0.254) (type default)) (fill (type background))))')
    return "\n".join([
        '\t(symbol "SW_DIP_SPDT_x05_CTS204" (pin_names (offset 0.5)) (exclude_from_sim no) '
        '(in_bom yes) (on_board yes)',
        prop("Reference", "SW", 0, 5.08), prop("Value", "CTS 204-125ST", 0, -5.08),
        prop("Footprint", "diy-mixer:CTS_204-125ST_DIP_SPDT_5pos_SMD", 0, 0, True),
        prop("Datasheet", "docs/datasheets/cts-204.pdf", 0, 0, True),
        prop("Description", "SPDT DIP x5. Positional pins: SPDT mapping TBD by continuity test", 0, 0, True),
        body, *units, '\t)'])


def dip_spdt_cts_1():
    """CTS 204-121ST (D55): one SPDT position, positional pads as gen_footprints.cts_204(1):
    bottom 1, 2; top 4 (above 1), 3 (above 2) - same roles as one unit of the x05 symbol."""
    pins = [pin("passive", -5.08, 1.27, 0, "T1", "4"), pin("passive", -5.08, -1.27, 0, "T2", "3"),
            pin("passive", 5.08, 1.27, 180, "B1", "1"), pin("passive", 5.08, -1.27, 180, "B2", "2")]
    return "\n".join([
        '\t(symbol "SW_DIP_SPDT_CTS204_1pos" (pin_names (offset 0.5)) (exclude_from_sim no) '
        '(in_bom yes) (on_board yes)',
        prop("Reference", "SW", 0, 5.08), prop("Value", "CTS 204-121ST", 0, -5.08),
        prop("Footprint", "diy-mixer:CTS_204-121ST_DIP_SPDT_1pos_SMD", 0, 0, True),
        prop("Datasheet", "docs/datasheets/cts-204.pdf", 0, 0, True),
        prop("Description", "SPDT DIP, 1 position. Positional pins: SPDT mapping TBD by continuity test",
             0, 0, True),
        '\t\t(symbol "SW_DIP_SPDT_CTS204_1pos_0_1" (rectangle (start -2.54 2.54) (end 2.54 -2.54) '
        '(stroke (width 0.254) (type default)) (fill (type background))))',
        '\t\t(symbol "SW_DIP_SPDT_CTS204_1pos_1_1"\n' + "\n".join(pins) + '\n\t\t)', '\t)'])


def main():
    syms = [lt1930(), supermini(), oled(), jack(), jack_43514(), pot_common_gnd(), dip_spdt_cts(),
            dip_spdt_cts_1()]
    OUT.write_text('(kicad_symbol_lib (version 20241209) (generator "diy-mixer-gen") '
                   '(generator_version "1.0")\n' + "\n".join(syms) + "\n)\n")
    print(OUT)


if __name__ == "__main__":
    main()
