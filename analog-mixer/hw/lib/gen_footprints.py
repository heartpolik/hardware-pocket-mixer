"""Generate project footprints (hw/lib/diy-mixer.pretty) from datasheet drawings.

Run: python3 hw/lib/gen_footprints.py
Every footprint lists its source drawing in `descr`. Dimensions in mm, origin and
orientation as noted per footprint. Positional pad numbering is used where the
datasheet does not name terminals.
"""
from pathlib import Path

OUT = Path(__file__).parent / "diy-mixer.pretty"
# 3D models from hw/lib/gen_3d.py; the path works from every project folder in hw/ (analog,
# digital, panel). Footprints not listed use a model of their own name.
MODEL_DIR = "${KIPRJMOD}/../lib/diy-mixer.3dshapes"
MODEL_OF = {"Alps_RK14K12D_Vertical_Volume": "Alps_RK14K_Vertical",
            "Alps_RK14K124_Vertical_Tone": "Alps_RK14K_Vertical",
            "CUI_SJ-4351X-SMT_TRRS_Horizontal": "CUI_SJ-43514-SMT_TRRS_Horizontal"}
SILK, FAB, CRT = 0.12, 0.10, 0.05


def fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


class FP:
    def __init__(self, name, descr, tags, attr="through_hole", model=True, flags=""):
        self.name, self.descr, self.tags, self.attr = name, descr, tags, attr
        self.model, self.flags = model, flags
        self.items = []

    def line(self, x1, y1, x2, y2, layer, w):
        self.items.append(f'\t(fp_line (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)}) '
                          f'(stroke (width {w}) (type solid)) (layer "{layer}"))')

    def rect(self, x1, y1, x2, y2, layer, w):
        self.items.append(f'\t(fp_rect (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)}) '
                          f'(stroke (width {w}) (type solid)) (fill no) (layer "{layer}"))')

    def circle(self, cx, cy, r, layer, w):
        self.items.append(f'\t(fp_circle (center {fmt(cx)} {fmt(cy)}) (end {fmt(cx + r)} {fmt(cy)}) '
                          f'(stroke (width {w}) (type solid)) (fill no) (layer "{layer}"))')

    def text(self, x, y, s, layer, size=1.0):
        self.items.append(f'\t(fp_text user "{s}" (at {fmt(x)} {fmt(y)}) (layer "{layer}") '
                          f'(effects (font (size {size} {size}) (thickness {size * 0.15:.3f}))))')

    def body(self, x1, y1, x2, y2, pad=0.25):
        """Fab outline, silk outline, courtyard around the body."""
        self.rect(x1, y1, x2, y2, "F.Fab", FAB)
        self.rect(x1, y1, x2, y2, "F.SilkS", SILK)
        self.rect(x1 - pad, y1 - pad, x2 + pad, y2 + pad, "F.CrtYd", CRT)

    def tht(self, num, x, y, size, drill, shape="circle"):
        d = f"(drill {fmt(drill)})" if not isinstance(drill, tuple) else \
            f"(drill oval {fmt(drill[0])} {fmt(drill[1])})"
        sz = size if isinstance(size, tuple) else (size, size)
        extra = " (roundrect_rratio 0.25)" if shape == "roundrect" else ""
        self.items.append(f'\t(pad "{num}" thru_hole {shape} (at {fmt(x)} {fmt(y)}) '
                          f'(size {fmt(sz[0])} {fmt(sz[1])}) {d} (layers "*.Cu" "*.Mask"){extra})')

    def npth(self, x, y, drill):
        self.items.append(f'\t(pad "" np_thru_hole circle (at {fmt(x)} {fmt(y)}) '
                          f'(size {fmt(drill)} {fmt(drill)}) (drill {fmt(drill)}) (layers "*.Cu" "*.Mask"))')

    def smd(self, num, x, y, w, h):
        self.items.append(f'\t(pad "{num}" smd roundrect (at {fmt(x)} {fmt(y)}) (size {fmt(w)} {fmt(h)}) '
                          f'(layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.15))')

    def write(self, ref_y, val_y):
        attr = "" if self.attr == "through_hole" else " smd"
        s = [f'(footprint "{self.name}"', '\t(version 20241229)', '\t(generator "diy-mixer-gen")',
             '\t(layer "F.Cu")', f'\t(descr "{self.descr}")', f'\t(tags "{self.tags}")',
             f'\t(property "Reference" "REF**" (at 0 {fmt(ref_y)} 0) (layer "F.SilkS") '
             '(effects (font (size 1 1) (thickness 0.15))))',
             f'\t(property "Value" "{self.name}" (at 0 {fmt(val_y)} 0) (layer "F.Fab") '
             '(effects (font (size 1 1) (thickness 0.15))))',
             f'\t(attr {"through_hole" if self.attr == "through_hole" else "smd"}{self.flags})']
        model = MODEL_OF.get(self.name, self.name)
        s += self.items + ([f'\t(model "{MODEL_DIR}/{model}.step")'] if self.model else []) + [")"]
        OUT.mkdir(exist_ok=True)
        (OUT / f"{self.name}.kicad_mod").write_text("\n".join(s) + "\n")
        return self.name


def fader_rs451121400a():
    """Alps RS451121400A, catalog 2026 drawing 20; pad coords as mixerli v2.0.1 (manufactured).
    Origin = body centre, slider travel along X. Section A: 1 bottom, 2 wiper, 3 top;
    section B: 4 bottom, 5 wiper, 6 top (Alps 1-2-3 / 1'-2'-3')."""
    f = FP("Alps_RS451121400A_Fader_Dual_45mm",
           "Alps RS451121400A dual slide pot 45 mm, 10k 1B, no mounting plate. "
           "Catalog RS 2026 drawing 20 (6-d1.1, rows 55 mm). Pads per mixerli v2.0.1.",
           "slide potentiometer fader Alps RS45 dual")
    for num, x, y in (("1", -27.5, -1.25), ("2", -27.5, -3.75), ("3", 27.5, -1.25),
                      ("4", -27.5, 3.75), ("5", -27.5, 1.25), ("6", 27.5, 3.75)):
        f.tht(num, x, y, 2.0, 1.1)
    f.body(-30, -4.5, 30, 4.5)
    f.line(-22.5, 0, 22.5, 0, "F.Fab", FAB)          # lever travel 45 mm
    f.text(-27.5, -6, "1", "F.SilkS", 0.8)
    return f.write(-6, 6)


def rk14k(name, pads, descr):
    """Alps RK14K vertical (catalog p.326 drawing 1): 7 x d1 holes, pitch 2, row 11 mm from
    the snap-in tabs; tabs 2 x 2.1 slots, 15.3 mm over outer edges (13.3 c-c).
    Origin = shaft centre = tab line (mixerli v2.0.1). Body 14 wide, -6.7..+9.7."""
    f = FP(name, descr, "potentiometer rotary Alps RK14K dual vertical")
    for num, x in pads:
        f.tht(num, x, 11.0, 1.524, 1.0)
    for x in (-6.65, 6.65):
        f.tht("MP", x, 0.0, (4.0, 4.0), (2.0, 2.1), "roundrect")
    f.rect(-7, -6.7, 7, 9.7, "F.Fab", FAB)
    f.rect(-7, -6.7, 7, 9.7, "F.SilkS", SILK)
    f.rect(-7.25, -6.95, 7.25, 12.0, "F.CrtYd", CRT)
    f.circle(0, 0, 3.0, "F.Fab", FAB)                  # shaft d6
    f.circle(0, 0, 4.5, "F.Fab", FAB)                  # bushing M9
    return f.write(-8, 13.5)


def rk14k12d():
    # catalog p.327 "Without tap for volume": Dummy, 1 (common to both gangs), 2, (2), 3, (3), Dummy
    return rk14k("Alps_RK14K12D_Vertical_Volume",
                 [("MP", -6), ("1", -4), ("2", -2), ("5", 0), ("3", 2), ("6", 4), ("MP", 6)],
                 "Alps RK14K12D (dual, volume, common ground). Catalog p.326 drawing 1, "
                 "terminal layout p.327. Pads 1 common bottom, 2/3 gang A wiper/top, 5/6 gang B.")


def rk14k124():
    # catalog p.327 "For tone and for volume (15C)": (1), 1, 2, (2), 3, (3), Dummy
    return rk14k("Alps_RK14K124_Vertical_Tone",
                 [("4", -6), ("1", -4), ("2", -2), ("5", 0), ("3", 2), ("6", 4), ("MP", 6)],
                 "Alps RK14K124 (dual, tone, separate grounds), e.g. RK14K124003H. Catalog p.326 "
                 "drawing 1, terminal layout p.327. Gang A 1-2-3, gang B 4-5-6.")


def cts_204(n):
    """CTS 204-12nST SPDT DIP, n positions, rev D 2021, fig. 2 and 4 (A = 7.26 for 1, 27.58 for 5).
    Pads 1.13 x 2.44, pitch 2.54, outer span 11.04, inner gap 6.17 -> centres +-4.305.
    2n pads per row (2 per switch). Positional numbering: 1..2n bottom row left to right,
    2n+1..4n top row right to left. SPDT terminal mapping to be verified by continuity test."""
    length = {1: 7.26, 5: 27.58}[n]
    f = FP(f"CTS_204-12{n}ST_DIP_SPDT_{n}pos_SMD",
           f"CTS 204-12{n}ST, SPDT DIP switch, {n} position(s), SMD. Datasheet Series 204 rev D, fig. 2, 4. "
           "Positional pad numbers; SPDT mapping not stated in datasheet - verify.",
           "DIP switch SPDT CTS 204", attr="smd")
    for i in range(2 * n):
        x = (i - (2 * n - 1) / 2) * 2.54
        f.smd(str(i + 1), x, 4.305, 1.13, 2.44)
        f.smd(str(4 * n - i), x, -4.305, 1.13, 2.44)
    a = length / 2
    f.rect(-a, -9.78 / 2, a, 9.78 / 2, "F.Fab", FAB)
    f.rect(-a, -3.0, a, 3.0, "F.SilkS", SILK)
    f.rect(-a - 0.3, -5.8, a + 0.3, 5.8, "F.CrtYd", CRT)
    for k in range(n):                                   # actuators, "ON" toward the dot side
        x = (2 * k - (n - 1)) * 2.54
        f.rect(x - 1.5, -2.03, x + 1.5, 2.03, "F.Fab", FAB)
    f.text(-a + 1, -2.0, "1", "F.SilkS", 0.8)
    return f.write(-7, 7)


def supermini():
    """ESP32-C3 SuperMini, datasheet: board 18.00 x 22.52, header rows 15.24 apart, pitch 2.54.
    View from component side, USB-C at top. Left column top-down: 5V, GND, 3V3, GPIO4..0
    (pads 1..8); right column top-down: GPIO5..10, 20, 21 (pads 9..16).
    Vertical position of the header relative to the board edge is not dimensioned:
    the 8 pins are centred on the board length (ОРІЄНТИР)."""
    f = FP("ESP32-C3_SuperMini_2x8_P2.54",
           "ESP32-C3 SuperMini module, 2x8 headers 15.24 mm apart. Datasheet (user), pinout image. "
           "Header offset along the board not dimensioned - outline approximate.",
           "ESP32-C3 SuperMini module")
    y0 = -3.5 * 2.54
    for i in range(8):
        f.tht(str(i + 1), -7.62, y0 + i * 2.54, 1.7, 1.0, "rect" if i == 0 else "circle")
        f.tht(str(i + 9), 7.62, y0 + i * 2.54, 1.7, 1.0)
    f.body(-9.0, -11.26, 9.0, 11.26)
    f.rect(-4.5, -11.26 - 1.3, 4.5, -11.26 + 6.0, "F.Fab", FAB)   # USB-C, approx
    f.text(0, -12.8, "USB", "F.Fab", 0.8)
    return f.write(-13.5, 13)


def supermini_smd():
    """ESP32-C3 SuperMini lying flat on the top of the digital board (D59): the module's plated
    holes are soldered onto SMD pads from above (solder fed into the hole), no headers, no cut-out
    (solid GND under the module). Origin = module centre, USB-C toward -Y (board edge).
    Datasheet: board 18.00 x 22.52, rows 15.24 apart, pitch 2.54. Pin offset along the module is
    not dimensioned: the pinout drawing (datasheet p. 2, in scale along the pins) gives the first
    pin 1.5 from the USB edge and the USB-C shell 1.4 past it - ОРІЄНТИР, measure the module.
    Pads in the order of ESP32-C3_SuperMini_2x8_P2.54 (left column 5V, GND, 3V3, GPIO4..0 = 1..8
    from the USB end, right column GPIO5..10, 20, 21 = 9..16)."""
    f = FP("ESP32-C3_SuperMini_SMD",
           "ESP32-C3 SuperMini soldered flat: SMD pads under the module holes (2 x 8, rows 15.24, pitch 2.54). "
           "Board 18.00 x 22.52 (datasheet). Pin offset from the USB edge 1.5 and USB-C overhang 1.4 - from the "
           "pinout drawing, verify on the module.",
           "ESP32-C3 SuperMini module SMD", attr="smd")
    y0 = -11.26 + 1.5
    for i in range(8):
        for num, x in ((str(i + 1), -7.62), (str(i + 9), 7.62)):
            f.items.append(f'\t(pad "{num}" smd circle (at {fmt(x)} {fmt(y0 + i * 2.54)}) (size 1.7 1.7) '
                           '(layers "F.Cu" "F.Mask"))')
    f.rect(-9.0, -11.26, 9.0, 11.26, "F.Fab", FAB)
    f.rect(-4.5, -11.26 - 1.4, 4.5, -11.26 + 6.1, "F.Fab", FAB)            # USB-C, approx
    f.text(0, -12.0, "USB", "F.Fab", 0.8)
    f.line(-9.0, -11.26, 9.0, -11.26, "F.SilkS", SILK)
    f.line(-9.0, 11.26, 9.0, 11.26, "F.SilkS", SILK)
    f.text(-7.62, y0 - 1.6, "5V", "F.SilkS", 0.8)
    f.rect(-9.25, -11.26 - 1.65, 9.25, 11.51, "F.CrtYd", CRT)
    return f.write(-13.6, 12.6)


def oled():
    """0.96in 128x64 SSD1306 I2C module, Rajguru drawing: board 27.3 x 27.3, 4 x d2.5 holes
    20.7 x 23.2 apart (centred), header 4 x 2.54 centred, 1.65 from the top edge.
    Pins: 1 VCC, 2 GND, 3 SCL, 4 SDA. Origin = board centre, header at top."""
    f = FP("OLED_0.96in_128x64_I2C_4pin",
           "0.96in OLED 128x64 SSD1306 I2C module, 4 pins (VCC GND SCL SDA). Rajguru datasheet "
           "outer dimension drawing. Verify against the purchased module.",
           "OLED SSD1306 I2C module")
    yh = -27.3 / 2 + 1.65
    for i in range(4):
        f.tht(str(i + 1), -3.81 + i * 2.54, yh, 1.7, 1.0, "rect" if i == 0 else "circle")
    for x in (-10.35, 10.35):
        for y in (-11.6, 11.6):
            f.npth(x, y, 2.2)                            # M2 standoffs; module PTH is d2.5
    f.body(-13.65, -13.65, 13.65, 13.65)
    f.rect(-10.87, -5.43 + 1.0, 10.87, 5.43 + 1.0, "F.Fab", FAB)   # active area, approx position
    return f.write(-15, 15)


def uep_horizontal(d, l_max, pitch, name):
    """Nichicon UEP bi-polar radial, laid flat (D44). Leads at the origin, pitch across Y,
    body along +X from the lead bend (1.5 mm) to L + alpha."""
    f = FP(name, f"Nichicon UEP radial D{d} x L11 (L+a max {l_max}), lead pitch {pitch}, mounted "
           "horizontally. Datasheet nichicon-uep.pdf.", "capacitor electrolytic bipolar horizontal")
    f.tht("1", 0, -pitch / 2, 1.6, 0.8, "circle")
    f.tht("2", 0, pitch / 2, 1.6, 0.8, "circle")
    x0 = 1.5
    f.body(x0, -d / 2 - 0.25, x0 + l_max, d / 2 + 0.25)
    f.text(x0 + l_max / 2, 0, "BP", "F.Fab", 0.8)
    return f.write(-d / 2 - 1.5, d / 2 + 1.5)


def sj_4351x(switch_pads=True):
    """CUI SJ-4351X-SMT (TRRS 3.5 mm), 'Recommended PCB Layout, Top View' (rev 1.03).
    Origin = body edge at the mouth, on the jack axis; the plug enters from -X: sleeve
    contact (pad 1) is next to the mouth, tip (2) and tip switch (5) are at the far end
    (side view: 1.5 mm nose at the mouth side). Mouth face at x = -1.5.
    Pads: 1 sleeve, 2 tip, 3 ring 1, 4 ring 2, 5 tip switch, 6 ring switch
    (5/6 not populated on SJ-43514). Two d1.7 locating pegs at x 4.5 and 11.5."""
    name = "CUI_SJ-4351X-SMT_TRRS_Horizontal" if switch_pads else "CUI_SJ-43514-SMT_TRRS_Horizontal"
    f = FP(name,
           "CUI SJ-4351X-SMT 3.5 mm TRRS jack, horizontal SMD. Datasheet recommended PCB layout. "
           "1 S, 2 T, 3 R1, 4 R2, 5 T-switch, 6 R-switch. Mouth at -X (x=-1.5), body 15.5 + nose 1.5.",
           "audio jack 3.5mm TRRS SMD CUI SJ-43514", attr="smd")
    for num, x, y, w, h in (("1", 0.6, 3.95, 2.0, 2.3), ("4", 3.4, 3.95, 2.2, 2.3),
                            ("2", 12.8, 3.95, 2.8, 2.3), ("6", 2.5, -3.95, 2.0, 2.3),
                            ("3", 5.3, -3.95, 2.2, 2.3), ("5", 16.8, -0.75, 2.6, 2.8)):
        if num in "56" and not switch_pads:
            continue                                     # SJ-43514: terminals 5/6 not present
        f.smd(num, x, y, w, h)
    for x in (4.5, 11.5):
        f.npth(x, 0, 1.7)
    f.rect(0, -3.0, 15.5, 3.0, "F.Fab", FAB)
    f.rect(-1.5, -2.5, 0, 2.5, "F.Fab", FAB)               # nose d5, 1.5 long, at the mouth
    f.line(-1.5, -3.4, -1.5, 3.4, "Dwgs.User", FAB)         # mouth face = board edge reference
    f.rect(-1.75, -5.35, 18.35 if switch_pads else 15.75, 5.35, "F.CrtYd", CRT)
    f.line(6.6, -3.0, 15.5, -3.0, "F.SilkS", SILK)
    f.line(14.4, 3.0, 4.7, 3.0, "F.SilkS", SILK)
    f.text(8.0, 0, "<- PLUG", "F.Fab", 0.8)
    return f.write(-6.5, 6.5)


def cls62():
    """Sumida CLS62 2-in-1 coupled inductor, land pattern: 4 pads 1.3 x 1.2, 6.0 x 3.5 c-c.
    Datasheet 'Schematics (Bottom)' for 10-22 uH: winding 2(S)-3 and 1(S)-4. Pads are named
    after the KiCad Device:L_Coupled pins: 1/2 = winding A (CLS 2 start -> 3),
    3/4 = winding B (CLS 1 start -> 4); dots of the symbol = winding starts.
    Top view = bottom view mirrored: CLS 3 (-x,-y), 2 (+x,-y), 4 (-x,+y), 1 (+x,+y)."""
    f = FP("L_Sumida_CLS62", "Sumida CLS62 coupled inductor 2-in-1. Datasheet land pattern 1.3 x 1.2, "
           "6.0 x 3.5. Pads: 1 = CLS pin 2 (start A), 2 = CLS 3, 3 = CLS 1 (start B), 4 = CLS 4.",
           "inductor coupled Sumida CLS62", attr="smd")
    for num, x, y in (("1", 3.0, -1.75), ("2", -3.0, -1.75), ("3", 3.0, 1.75), ("4", -3.0, 1.75)):
        f.smd(num, x, y, 1.3, 1.2)
    f.rect(-3.35, -3.4, 3.35, 3.4, "F.Fab", FAB)
    f.circle(0, 0, 3.0, "F.Fab", FAB)
    f.line(-2.2, -3.4, 2.2, -3.4, "F.SilkS", SILK)
    f.line(-2.2, 3.4, 2.2, 3.4, "F.SilkS", SILK)
    f.rect(-4.0, -3.65, 4.0, 3.65, "F.CrtYd", CRT)
    f.text(4.3, -1.75, "S", "F.SilkS", 0.6)
    f.text(4.3, 1.75, "S", "F.SilkS", 0.6)
    return f.write(-4.6, 4.6)


def ec12d():
    """Alps EC12D with push switch, catalog p.289 drawing 5, 'PC board mounting hole dimensions
    (viewed from mounting side)'. Origin = shaft centre. From the drawing: A-B 11.1, E 6.85 above
    the lug axis, D at x 5.95 / y 3.45, A-C 8.3, lug slots 2.05 x 2.15 over 13.3 outer.
    A/B/C rows at y -4.15 / +4.15: A-C = 8.3 is dimensioned, the split is taken symmetric
    (scaled measurement of the drawing gives -4.19 / +4.12) - verify on the real part.
    Pads: A, B outputs, C common (catalog test circuit), S1 = E, S2 = D (push switch)."""
    f = FP("Alps_EC12D_Switch", "Alps EC12D rotary encoder with push switch, vertical, catalog EC12E/EC12D "
           "drawing 5. 5 x d1.05 + 2 lugs. A/B/C row offset +-4.15 derived (see generator) - verify.",
           "rotary encoder Alps EC12D switch")
    for num, x, y in (("A", -5.55, -4.15), ("B", 5.55, -4.15), ("C", -5.55, 4.15),
                      ("S1", 0.0, -6.85), ("S2", 5.95, 3.45)):
        f.tht(num, x, y, 1.8, 1.05)
    for x in (-5.625, 5.625):
        f.tht("MP", x, 0.0, (2.8, 2.9), (2.05, 2.15), "roundrect")
    f.body(-6.25, -5.85, 6.25, 5.85, pad=0.6)
    f.circle(0, 0, 3.0, "F.Fab", FAB)
    return f.write(-8.5, 7.5)


def msk12c02():
    """SHOU HAN MSK12C02 SPDT slide switch, side actuated, SMD; drawing in the specification
    (2024-12-14), '安装参考图' (recommended land pattern) and top view.
    Origin = body centre = line of the two d0.75 locating pegs (NPTH d0.85, 3 apart).
    Actuator toward -Y: 1.3 wide, protrudes 1.45 from the body face (y -1.4 .. -2.85), centre at
    x -0.8 / +0.8 (travel 1.6). Terminals toward +Y: 3 / 2 / 1 at x -2.25 / -0.75 / +2.25,
    pads 0.6 x 1.3, outer edge 2.6 from the peg line. Pad 2 = common (circuit diagram: slider
    bridges 3-2 or 2-1). Four cover tabs (4) 1.05 x 0.7 at x +-3.675, y +-1.1 -> 'MP'.
    The tab pads reach y -1.45, so the board edge goes at y <= -1.65 (0.2 copper-edge rule):
    the actuator then sticks out 1.2 mm past the edge."""
    f = FP("SW_Slide_SPDT_SHOUHAN_MSK12C02_RightAngle",
           "SHOU HAN MSK12C02 SPDT slide switch, side actuated, SMD, 12 V 50 mA. Specification "
           "drawing (2024-12-14). 1/3 = throws, 2 = common, MP = cover tabs. Actuator toward -Y.",
           "switch slide SPDT SMD right angle MSK12C02 MSK-12C02", attr="smd")
    for num, x in (("3", -2.25), ("2", -0.75), ("1", 2.25)):
        f.smd(num, x, 1.95, 0.6, 1.3)
    for x in (-3.675, 3.675):
        for y in (-1.1, 1.1):
            f.smd("MP", x, y, 1.05, 0.7)
    for x in (-1.5, 1.5):
        f.npth(x, 0, 0.85)
    f.rect(-3.375, -1.4, 3.375, 1.4, "F.Fab", FAB)
    f.rect(-1.45, -2.85, -0.15, -1.4, "F.Fab", FAB)         # actuator, position at pad 3 side
    f.rect(0.15, -2.85, 1.45, -1.4, "F.Fab", FAB)           # actuator, other position
    f.line(-4.2, -1.65, 4.2, -1.65, "Dwgs.User", FAB)       # board edge, furthest-in position
    f.line(-2.7, -1.4, 2.7, -1.4, "F.SilkS", SILK)
    f.rect(-4.45, -3.1, 4.45, 2.85, "F.CrtYd", CRT)
    f.text(-2.25, 3.5, "3", "F.SilkS", 0.8)
    f.text(2.25, 3.5, "1", "F.SilkS", 0.8)
    return f.write(-4.0, 4.2)


def mounting_hole_m2():
    """M2 mounting hole for a hex standoff or a screw head on either side (D57). Pad and drill as
    KiCad MountingHole_2.2mm_M2_Pad (drill 2.2, pad 4.4, solid zone connection). Courtyard r 2.45 on
    both sides: M2 hex standoff 4 mm across flats -> 2.31 across corners (ОРІЄНТИР, standoff not
    chosen), M2 nut 4 mm across flats, pan head d 4.0. Board-only, not in the schematic: the pad
    gets the GND net on the board."""
    f = FP("MountingHole_2.2mm_M2_Pad_Standoff_2Side",
           "M2 mounting hole, plated, pad 4.4, drill 2.2 (as KiCad MountingHole_2.2mm_M2_Pad). "
           "Courtyard r 2.45 on F and B for a 4 mm hex standoff, nut or screw head on either side.",
           "mountinghole M2 standoff", model=False, flags=" board_only exclude_from_pos_files exclude_from_bom")
    f.items.append('\t(pad "1" thru_hole circle (at 0 0) (size 4.4 4.4) (drill 2.2) (layers "*.Cu" "*.Mask") '
                   '(zone_connect 2))')
    f.circle(0, 0, 2.2, "Cmts.User", 0.15)
    f.circle(0, 0, 2.45, "F.CrtYd", CRT)
    f.circle(0, 0, 2.45, "B.CrtYd", CRT)
    return f.write(-3.2, 3.2)


def main():
    names = [fader_rs451121400a(), rk14k12d(), rk14k124(), cts_204(5), cts_204(1), supermini(), supermini_smd(), oled(),
             sj_4351x(), sj_4351x(False), cls62(), ec12d(), msk12c02(),
             uep_horizontal(5.0, 12.5, 2.0, "CP_Nichicon_UEP_D5.0_L11.0_P2.00_Horizontal"),
             uep_horizontal(6.3, 12.5, 2.5, "CP_Nichicon_UEP_D6.3_L11.0_P2.50_Horizontal"),
             mounting_hole_m2()]
    print("\n".join(names))


if __name__ == "__main__":
    main()
