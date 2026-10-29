"""Main board schematic of the digital mixer (hw/main/main.kicad_sch).

Sources: docs/01-spec.md, 02-components.md, decisions DM1-DM29, datasheets in docs/datasheets
(typical applications: PCM186x fig. 66, PCM510xA fig. 33, TPA6132A2 fig. 27, TPS63802 sect. 10).
Run from digital-mixer/:  python3 hw/sch/main.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from project import Part, Sheet, pins_of, project_files  # noqa: E402

HW = Path(__file__).resolve().parents[1]
R0805 = "Resistor_SMD:R_0805_2012Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
CP_IN = "Capacitor_SMD:CP_Elec_4x5.4"
JACK = "pocket-digital:Jack_3.5mm_PJ-327A_SMT_Horizontal"    # DM38 (was CUI SJ-43514-SMT)
JACK_SYM = "pocket-digital:AudioJack_Stereo_PJ-327A"
FADER = "pocket-digital:Potentiometer_Alps_RS20111_Single_Slide"   # Alps RS201111J011 (DM39, was Bourns PTA2043)
ENC = "pocket-digital:RotaryEncoder_EC12SY_SMD"                # EC12SY SMD with push switch (DM26)
TACT = "pocket-digital:SW_TSF-1266_6x6mm_SMD"                  # 6 x 6 x 5 SMT tact (DM16), drawing / sample TBD
LATCH = "pocket-digital:SW_Push_Latching_DPDT_5.8mm_SMD"       # self-locking 5.8 mm DPDT SMD (DM27)

A3 = "+3V3A"          # LP5907: analog supplies of the codecs
D3 = "+3V3"           # Teensy 3.3 V pin: digital supplies, display, pull-ups
RAIL = "+4V2"         # TPS63802 output


class Board:
    """Same placement helper as analog-mixer/hw/sch/analog.py (Board), trimmed."""
    COLS = (63.5, 609.6, 1155.7)

    def __init__(self):
        self.sh = Sheet("main", "hardware-pocket-mixer digital — main board", "User")
        self.count = {}
        self.last_ic = None
        self.cursor = {}
        self.col_y = {}
        self.titles = []

    def ref(self, prefix):
        self.count[prefix] = self.count.get(prefix, 0) + 1
        return f"{prefix}{self.count[prefix]}"

    def block(self, name, col):
        if self.cursor:
            c = self.cursor
            self.col_y[c["col"]] = max(c["y"] + 45, c["bottom"] + 30)
        x = self.COLS[col]
        y = self.col_y.get(col, 30)
        self.sh.text(x, y - 10, name, 3)
        self.titles.append((x, name))
        self.cursor = {"x0": x, "x": x, "y": y, "col": col, "bottom": y}

    def finish(self):
        c = self.cursor
        self.col_y[c["col"]] = max(c["y"] + 45, c["bottom"] + 30)
        h = max(self.col_y.values()) + 20
        xs = [x for part in self.sh.parts for (x, _) in part.unit_pos.values()]
        title_end = max(x0 + len(name) * 2.3 for x0, name in self.titles)
        self.sh.paper = (max(1190, round(max(max(xs) + 80, title_end + 30))), max(841, round(h)))

    def _pos(self, n_units=1, w=17.78, top=0.0, low=0.0):
        """Tall symbols hang below the row line so they clear the block title. top / low: pin extent
        above / below the symbol origin (sheet y grows downwards, library y upwards)."""
        c = self.cursor
        pos = []
        for _ in range(n_units):
            if c["x"] - c["x0"] > 330:
                self.newrow()
            y = c["y"] + max(0.0, top - 5)
            pos.append((round(round(c["x"] / 2.54) * 2.54, 2), round(round(y / 2.54) * 2.54, 2)))
            c["bottom"] = max(c["bottom"], y + low)
            c["x"] += w
        return pos

    def part(self, prefix, lib, value, fp, pins, units=(1,), w=17.78, fields=None):
        ref = self.ref(prefix)
        if prefix in ("U", "DS", "LED"):
            self.last_ic = ref
        ys = [y for (_, y, _) in pins_of(lib).values()] or [0.0]
        pos = self._pos(len(units), w, max(ys), -min(ys))
        self.sh.add(Part(ref, lib, value, fp, pins, dict(zip(units, pos)), fields))
        return ref

    def newrow(self):
        c = self.cursor
        c["x"], c["y"] = c["x0"], max(c["y"] + 33.02, c["bottom"] + 15)

    def r(self, val, a, b):
        return self.part("R", "Device:R", val, R0805, {"1": a, "2": b})

    def c(self, val, a, b, fp=C0805, fields=None):
        return self.part("C", "Device:C", val, fp, {"1": a, "2": b}, fields=fields)

    def cp(self, val, plus, minus, fp=CP_IN):
        return self.part("C", "Device:C_Polarized", val, fp, {"1": plus, "2": minus})

    def decouple(self, *nets):
        for n in nets:
            self.c("100n", n, "GND", fields={"Decouples": self.last_ic})


def build():
    b = Board()

    # ================================================================ Teensy 4.1
    b.block("Teensy 4.1 (DM4, DM12, DM35): на гребінках 2 × 24 крізь плату, зазор 2,5 мм під PSRAM; VIN = +4V2; "
            "перемичку VIN–VUSB на модулі РОЗРІЗАТИ, VUSB = VBUS з USB-C; USB device D−/D+ — отвори знизу модуля "
            "(креслення PJRC) → площадки 66/67 під ними, VUSB — дротик (49)", 0)
    b.part("U", "pocket-digital:Teensy4.1", "Teensy 4.1", "pocket-digital:Teensy41_THT", {
        "48": RAIL, "49": "VBUS", "15": D3, "46": D3, "51": D3,
        "1": "GND", "34": "GND", "47": "GND", "52": "GND",
        "66": "USB_DN", "67": "USB_DP",
        # SAI1 -> 3 x PCM5102A (I2S, AudioOutputI2SHex): BCLK1 21, LRCLK1 20, OUT1A 7, OUT1B 32, OUT1C 9
        "43": "DAC_BCK_T", "42": "DAC_LRCK_T", "9": "DAC_MAIN", "24": "DAC_AUX", "11": "DAC_CUE",
        # SAI2 <- 2 x PCM1865 (TDM, 8 slots): BCLK2 4, LRCLK2 3, IN2 5, MCLK2 33
        "6": "ADC_BCK_T", "5": "ADC_LRCK_T", "7": "ADC_DOUT", "25": "ADC_MCLK_T",
        # I2C0: codecs; I2C2: expanders
        "40": "I2C_SDA", "41": "I2C_SCL", "17": "I2C2_SDA", "16": "I2C2_SCL",
        "22": "MCP1_INT", "23": "MCP2_INT", "44": "MCP3_INT",
        # faders A0-A3, battery A14
        "36": "FADER1", "37": "FADER2", "38": "FADER3", "39": "FADER4", "30": "VBAT_SENSE",
        # master encoder, function buttons
        "2": "ENC_M_A", "3": "ENC_M_B", "4": "ENC_M_SW",
        # display GMT147SPI on SPI0: SCK 13, MOSI 11, CS 10, DC 40, RES 41, backlight PWM 28; SHIFT 29
        "35": "LCD_SCK", "13": "LCD_MOSI", "12": "LCD_CS", "32": "LCD_DC", "33": "LCD_RES", "20": "LCD_BLK",
        "21": "BTN_SHIFT",
        # DAC soft mute, headphone enable, MIDI OUT (Serial8 TX = pin 35)
        "28": "DAC_XSMT", "29": "HP_EN", "27": "MIDI_TX",
    }, w=60)
    b.c("10u", RAIL, "GND", C1206)
    b.c("10u", D3, "GND", C1206)
    for n in ("I2C_SDA", "I2C_SCL", "I2C2_SDA", "I2C2_SCL"):
        b.r("4.7k", D3, n)
    for n in ("DAC_BCK", "DAC_LRCK", "ADC_BCK", "ADC_LRCK", "ADC_MCLK"):
        b.r("33", f"{n}_T", n)               # series termination at the source (DM29), next to the Teensy
    b.r("10k", "DAC_XSMT", "GND")            # DACs muted until the firmware is up
    b.r("10k", "HP_EN", "GND")               # headphone amp off until then
    b.r("100k", "VSYS", "VBAT_SENSE")        # 4.7 V max -> 2.35 V at A14
    b.r("100k", "VBAT_SENSE", "GND")
    b.c("100n", "VBAT_SENSE", "GND")

    # ================================================================ USB-C
    b.block("USB-C (GCT USB4110-GF-A, повністю SMD — під MASTER, DM25): аудіо, MIDI, заряд. CC 5,1k — пристрій-споживач; ESD USBLC6", 0)
    b.part("J", "Connector:USB_C_Receptacle_USB2.0_16P", "GCT USB4110-GF-A", "Connector_USB:USB_C_Receptacle_GCT_USB4110",
           {"VBUS": "VBUS", "GND": "GND", "CC1": "CC1", "CC2": "CC2", "D+": "USB_C_DP", "D-": "USB_C_DN",
            "SBU1": None, "SBU2": None, "SHIELD": "GND"}, w=40)
    b.r("5.1k", "CC1", "GND")
    b.r("5.1k", "CC2", "GND")
    b.part("U", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
           {"1": "USB_C_DP", "6": "USB_DP", "3": "USB_C_DN", "4": "USB_DN", "GND": "GND", "VBUS": "VBUS"}, w=30)

    # ================================================================ power
    b.block("Заряд 1S (DM11): TP4056, R_PROG 2,4k → 0,5 A; TEMP на GND — без NTC. CHRG / STDBY — світлодіоди", 1)
    b.part("U", "Battery_Management:TP4056-42-ESOP8", "TP4056", "Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.3mm",
           {"V_{CC}": "VBUS", "CE": "VBUS", "TEMP": "GND", "PROG": "CHG_PROG", "GND": "GND", "EPAD": "GND",
            "BAT": "BAT+", "~{CHRG}": "CHG_LED_R", "~{STDBY}": "CHG_LED_G"}, w=30)
    b.c("10u", "VBUS", "GND", C1206)
    b.c("10u", "BAT+", "GND", C1206)
    b.r("2.4k", "CHG_PROG", "GND")
    b.part("D", "Device:LED", "red", "LED_SMD:LED_0805_2012Metric", {"1": "CHG_LED_R", "2": "CHG_LED_RA"})
    b.r("1k", "VBUS", "CHG_LED_RA")
    b.part("D", "Device:LED", "green", "LED_SMD:LED_0805_2012Metric", {"1": "CHG_LED_G", "2": "CHG_LED_GA"})
    b.r("1k", "VBUS", "CHG_LED_GA")
    b.part("J", "Connector_Generic_MountingPin:Conn_01x02_MountingPin", "LiPo 1S 3000 mAh (з платою захисту)",
           "Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal", {"1": "BAT+", "2": "GND", "MP": "GND"}, w=20)

    b.block("Load sharing (02, п. 4): від USB — через діод, акумулятор відключає P-MOSFET (затвор = VBUS)", 1)
    b.part("D", "Diode:MBR0530", "MBR0530", "Diode_SMD:D_SOD-123", {"A": "VBUS", "K": "VSYS"}, w=12)
    b.part("Q", "Transistor_FET:AO3401A", "AO3401A", "Package_TO_SOT_SMD:SOT-23",
           {"G": "VBUS", "D": "BAT+", "S": "VSYS"}, w=20)
    b.r("100k", "VBUS", "GND")                 # gate pulled low without USB -> FET on
    b.c("10u", "VSYS", "GND", C1206)

    b.block("Buck-boost TPS63802 → +4V2 (DM11). R1/R2 = 665k/91k → 4,15 V (VFB 0,5 V, табл. 10-5); "
            "L 0,47 µH XFL4015; C 10 µF вх., 2×22 µF вих. (>3,6 V). Вимикач — кнопка з фіксацією 5,8 мм на EN (DM27)", 1)
    b.part("U", "pocket-digital:TPS63802", "TPS63802", "pocket-digital:Texas_VSON-HR-10_2x3mm_P0.5mm",
           {"VIN": "VSYS", "EN": "PWR_EN", "MODE": "GND", "L1": "BB_L1", "L2": "BB_L2", "AGND": "GND",
            "GND": "GND", "VOUT": RAIL, "FB": "BB_FB", "PG": None}, w=40)
    b.part("L", "Device:L", "0.47u XFL4015-471ME", "pocket-digital:L_Coilcraft_XFL4015",
           {"1": "BB_L1", "2": "BB_L2"}, w=14)
    b.c("10u", "VSYS", "GND", C1206)
    b.c("22u", RAIL, "GND", C1206)
    b.c("22u", RAIL, "GND", C1206)
    b.r("665k", RAIL, "BB_FB")
    b.r("91k", "BB_FB", "GND")
    # one pole: common 2 -> EN; latched (PUSH) 2-3 -> VSYS, released (FREE) 1-2 -> GND (seller
    # drawing); the second pole is spare
    b.part("SW", "Switch:SW_DPDT_x2", "Power 5.8mm DPDT self-lock SMD", LATCH,
           {"1": "GND", "2": "PWR_EN", "3": "VSYS", "4": None, "5": None, "6": None}, units=(1, 2), w=20)
    b.r("100k", "PWR_EN", "GND")                                 # EN never floats while switching

    b.block("LP5907 3,3 V — аналог кодеків (+3V3A): < 6,5 µVrms, 250 mA; навантаження 128 mA (calc/power.py). "
            "Ємність на всій шині +3V3A — 0,7…10 µF (datasheet, COUT): 2,2 µF тут + 1 µF біля кожного кодека + 100 nF ≈ 8 µF", 1)
    b.part("U", "Regulator_Linear:LP5907MFX-3.3", "LP5907MFX-3.3", "Package_TO_SOT_SMD:SOT-23-5",
           {"IN": RAIL, "EN": RAIL, "GND": "GND", "OUT": A3, "NC": None}, w=30)
    b.c("1u", RAIL, "GND")
    b.c("2.2u", A3, "GND", C1206)          # LP5907: 0.7 <= COUT <= 10 uF over the whole +3V3A rail (SNVS798Q, 5.6 "capacitance for stability")

    # ================================================================ inputs + ADC
    for k, (adr, chs) in enumerate((("GND", (1, 2)), (D3, (3, 4))), start=1):
        b.block(f"АЦП{k} PCM1865 (I²C {'0x94' if adr == 'GND' else '0x96'}): входи IN{chs[0]}, IN{chs[1]}. "
                f"Ведений TDM, слоти {4 * k - 3}–{4 * k}. Вхід: 10k послідовно (−6 dB з 10 kΩ входу) + 10 µF", 2)
        for ch in chs:
            T, R = f"IN{ch}_T", f"IN{ch}_R"
            b.part("J", JACK_SYM, f"IN{ch} PJ-327A", JACK,
                   {"T": T, "TN": None, "R": R, "S": "GND", "S2": "GND"}, w=30)
            for s, n in (("L", T), ("R", R)):
                b.r("100k", n, "GND")                        # defines the cap's jack side
                b.r("10k", n, f"IN{ch}_{s}S")
                b.cp("10u 16V", f"ADC{k}_IN{ch}_{s}", f"IN{ch}_{s}S")   # + to the chip (internal bias)
            b.newrow()
        a, c2 = chs
        b.part("U", "Audio:PCM1864DBT", "PCM1865", "Package_SO:TSSOP-30_4.4x7.8mm_P0.5mm", {
            "VINL1/VIN1P": f"ADC{k}_IN{a}_L", "VINR1/VIN2P": f"ADC{k}_IN{a}_R",
            "VINL2/VIN1M": f"ADC{k}_IN{c2}_L", "VINR2/VIN2M": f"ADC{k}_IN{c2}_R",
            "VINL3/VIN4P": None, "VINR3/VIN3P": None, "VINL4/VIN4M": None, "VINR4/VIN3M": None,
            "Mic_Bias": None, "VREF": f"ADC{k}_VREF", "AGND": "GND", "AVDD": A3, "XO": None, "XI": "GND",
            "LDO": f"ADC{k}_LDO", "DGND": "GND", "DVDD": D3, "IOVDD": D3, "SCKI": "ADC_MCLK",
            "LRCK": "ADC_LRCK", "BCK": "ADC_BCK", "DOUT": f"ADC{k}_DOUT",
            "GPIO3/INTC": None, "GPIO2/INTB/DMCLK": None, "GPIO1/INTA/DMIN": None, "MISO/GPIO0/DMIN2": None,
            "MOSI/SDA": "I2C_SDA", "MC/SCL": "I2C_SCL", "MS/AD": adr, "MD0": "GND"}, w=50)
        b.c("1u", f"ADC{k}_VREF", "GND")
        b.decouple(A3)
        b.c("1u", A3, "GND", C1206)            # not 10 uF: the LP5907 output limit (see the LDO block)
        b.c("100n", f"ADC{k}_LDO", "GND")
        b.c("10u", f"ADC{k}_LDO", "GND", C1206)
        b.decouple(D3, D3)                  # DVDD, IOVDD
        b.c("10u", D3, "GND", C1206)
        b.r("33", f"ADC{k}_DOUT", "ADC_DOUT")  # TDM: both DOUT share one line (Hi-Z outside own slots, p. 59)

    # ================================================================ DACs + outputs
    for name, data in (("MAIN", "DAC_MAIN"), ("AUX", "DAC_AUX"), ("CUE", "DAC_CUE")):
        b.block(f"ЦАП {name} PCM5102A: I²S, BCK PLL (SCK = GND), FMT/FLT/DEMP = GND; вихід 470 Ω + 2,2 nF "
                "(рис. 33). XSMT — спільний з Teensy", 0)
        b.part("U", "Audio:PCM5102A", "PCM5102A", "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm", {
            "CPVDD": A3, "CAPP": f"{name}_CAPP", "CPGND": "GND", "CAPM": f"{name}_CAPM", "VNEG": f"{name}_VNEG",
            "OUTL": f"{name}_OL", "OUTR": f"{name}_OR", "AVDD": A3, "AGND": "GND", "DEMP": "GND", "FLT": "GND",
            "SCK": "GND", "BCK": "DAC_BCK", "DIN": data, "LRCK": "DAC_LRCK", "FMT": "GND", "XSMT": "DAC_XSMT",
            "LDOO": f"{name}_LDOO", "DGND": "GND", "DVDD": D3}, w=50)
        dac = b.last_ic                     # charge-pump caps right at their pins (fig. 33)
        b.c("2.2u", f"{name}_CAPP", f"{name}_CAPM", fields={"Decouples": dac})
        b.c("2.2u", f"{name}_VNEG", "GND", fields={"Decouples": dac})
        b.decouple(A3, A3, D3)              # CPVDD, AVDD, DVDD
        b.c("1u", A3, "GND", C1206)            # not 10 uF: the LP5907 output limit
        b.c("10u", D3, "GND", C1206)
        b.c("100n", f"{name}_LDOO", "GND")
        b.c("10u", f"{name}_LDOO", "GND", C1206)
        b.newrow()
        for s in "LR":
            out = f"{name}_{s}" if name != "CUE" else f"CUE_{s}"
            b.part("R", "Device:R", "470", R0805, {"1": f"{name}_O{s}", "2": out},
                   fields={"Decouples": dac})       # output RC at the DAC pins (fig. 33)
            b.c("2.2n", out, "GND")
        if name != "CUE":
            b.part("J", JACK_SYM, f"{name} OUT PJ-327A", JACK,
                   {"T": f"{name}_L", "TN": None, "R": f"{name}_R", "S": "GND", "S2": "GND"}, w=30)

    b.block("Навушники TPA6132A2 (рис. 27, несиметричний вхід): G0 = G1 = GND → −6 dB (2,1 Vrms ЦАП → ≈1 Vrms); "
            "EN від Teensy. QFN — лише при передзбиранні JLCPCB (DM7)", 0)
    b.part("U", "Amplifier_Audio:TPA6132A2RTE", "TPA6132A2", "Package_DFN_QFN:WQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm", {
        "INL-": "HP_INL", "INL+": "GND", "INR-": "HP_INR", "INR+": "GND", "OUTL": "PH_L", "OUTR": "PH_R",
        "G0": "GND", "G1": "GND", "EN": "HP_EN", "VDD": RAIL, "HPVDD": "HP_HPVDD", "HPVSS": "HP_HPVSS",
        "CPP": "HP_CPP", "CPN": "HP_CPN", "PGND": "GND", "SGND": "GND", "EP": "GND"}, w=40)
    b.c("1u", "CUE_L", "HP_INL")
    b.c("1u", "CUE_R", "HP_INR")
    # supply and charge-pump caps at their pins (fig. 27): placed as decoupling caps of the amp
    tpa = b.last_ic
    b.c("2.2u", RAIL, "GND", fields={"Decouples": tpa})
    b.c("2.2u", "HP_HPVDD", "GND", fields={"Decouples": tpa})
    b.c("1u", "HP_HPVSS", "GND", fields={"Decouples": tpa})
    b.c("1u", "HP_CPP", "HP_CPN", fields={"Decouples": tpa})
    b.part("J", JACK_SYM, "PHONES PJ-327A", JACK,
           {"T": "PH_L", "TN": None, "R": "PH_R", "S": "GND", "S2": "GND"}, w=30)

    b.block("MIDI OUT, TRS Type A (DM20): кінчик = DIN 5 (через RC 10 Ω від UART), кільце = DIN 4 (RA 33 Ω "
            "від +3,3 V), гільза = DIN 2 / GND. Значення для 3,3 V — MIDI 1.0 Electrical Spec Update, рис. 1", 0)
    b.part("J", JACK_SYM, "MIDI OUT PJ-327A", JACK,
           {"T": "MIDI_SINK", "TN": None, "R": "MIDI_SRC", "S": "GND", "S2": "GND"}, w=30)
    b.part("R", "Device:R", "33 0.5W", "Resistor_SMD:R_2010_5025Metric", {"1": D3, "2": "MIDI_SRC"})
    b.part("R", "Device:R", "10 0.25W", "Resistor_SMD:R_1206_3216Metric", {"1": "MIDI_TX", "2": "MIDI_SINK"})

    # ================================================================ controls
    for k in (1, 2):
        chs = (1, 2) if k == 1 else (3, 4)
        b.block(f"MCP23017 #{k} (I²C2, 0x2{k - 1}): енкодери каналів {chs[0]}, {chs[1]} (A/B), Mute; GPx7 вільні; "
                "внутрішні підтяжки 100k, INTA/INTB дзеркальні → один INT", 2)
        spare = {(1, "A"): None, (1, "B"): None, (2, "A"): None, (2, "B"): None}
        pins = {"V_{DD}": D3, "V_{SS}": "GND", "SCK": "I2C2_SCL", "SDA": "I2C2_SDA", "~{RESET}": D3,
                "A0": "GND" if k == 1 else D3, "A1": "GND", "A2": "GND",
                "INTA": f"MCP{k}_INT", "INTB": None, "NC": None}
        for half, ch in zip("AB", chs):
            for e in range(3):
                pins[f"GP{half}{2 * e}"] = f"ENC{ch}_{e + 1}_A"
                pins[f"GP{half}{2 * e + 1}"] = f"ENC{ch}_{e + 1}_B"
            pins[f"GP{half}6"] = f"MUTE{ch}"
            pins[f"GP{half}7"] = spare[(k, half)]
        b.part("U", "Interface_Expansion:MCP23017x-x-SO", "MCP23017-E/SO", "Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm",
               pins, w=50)
        b.decouple(D3)

    b.block("MCP23017 #3 (I²C2, 0x22): кнопки 12 енкодерів каналів (DM28: натискання — фільтр / компресор, "
            "скидання значення) і кнопки AUX, FX I, FX II (GPA6, GPA7, GPB6) — найближчий до правої колонки; GPB7 вільний", 2)
    pins = {"V_{DD}": D3, "V_{SS}": "GND", "SCK": "I2C2_SCL", "SDA": "I2C2_SDA", "~{RESET}": D3,
            "A0": "GND", "A1": D3, "A2": "GND", "INTA": "MCP3_INT", "INTB": None, "NC": None}
    for half, chs in zip("AB", ((1, 2), (3, 4))):
        for i, (ch, e) in enumerate((c, e) for c in chs for e in range(3)):
            pins[f"GP{half}{i}"] = f"ENC{ch}_{e + 1}_SW"
        pins[f"GP{half}6"] = pins[f"GP{half}7"] = None
    pins.update({"GPA6": "BTN_AUX", "GPA7": "BTN_FX1", "GPB6": "BTN_FX2"})
    b.part("U", "Interface_Expansion:MCP23017x-x-SO", "MCP23017-E/SO", "Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm",
           pins, w=50)
    b.decouple(D3)

    for ch in (1, 2, 3, 4):
        b.block(f"Канал {ch}: 3 енкодери EC12SY SMD з кнопкою (шари EQ / посили / канал, DM6, DM26), фейдер 35 мм Alps RS201111J011 (DM8, DM39), "
                "Mute — тактова кнопка TSF-1266 (DM16)", 2)
        for e in range(3):
            b.part("SW", "Device:RotaryEncoder_Switch_MP", f"EC12SY ch{ch}.{e + 1}", ENC,
                   {"A": f"ENC{ch}_{e + 1}_A", "B": f"ENC{ch}_{e + 1}_B", "C": "GND",
                    "S1": f"ENC{ch}_{e + 1}_SW", "S2": "GND", "MP": "GND"}, w=20)
        b.part("RV", "Device:R_Potentiometer", "RS201111J011 10k B", FADER,
               {"1": "GND", "2": f"FADER{ch}", "3": D3}, w=20)
        b.c("100n", f"FADER{ch}", "GND")
        b.part("SW", "Switch:SW_Push", f"Mute {ch} TSF-1266", TACT, {"1": f"MUTE{ch}", "2": "GND"}, w=20)

    b.block("Майстер: енкодер EC12SY з кнопкою, кнопки AUX, FX I, FX II, SHIFT (TSF-1266; CUE = SHIFT + Mute, DM28); "
            "дисплей GMT147SPI 1,47\" 172×320 ST7789P3, SPI, на гребінці (DM18, DM23); виводи — за кресленням продавця", 2)
    b.part("SW", "Device:RotaryEncoder_Switch_MP", "EC12SY master", ENC,
           {"A": "ENC_M_A", "B": "ENC_M_B", "C": "GND", "S1": "ENC_M_SW", "S2": "GND", "MP": "GND"}, w=20)
    for n in ("FX1", "FX2", "AUX", "SHIFT"):
        b.part("SW", "Switch:SW_Push", f"{n} TSF-1266", TACT, {"1": f"BTN_{n}", "2": "GND"}, w=20)
    # pin order from the GMT147SPI seller drawing ("Interface information", docs/datasheets)
    b.part("DS", "Connector_Generic:Conn_01x08", "GMT147SPI 1.47in 172x320", "pocket-digital:LCD_GMT147SPI",
           {"1": "GND", "2": D3, "3": "LCD_SCK", "4": "LCD_MOSI", "5": "LCD_RES", "6": "LCD_DC",
            "7": "LCD_CS", "8": "LCD_BLK"}, w=20)
    b.c("10u", D3, "GND", C1206)

    b.block("Прапорці живлення: шини, які в символах не мають «виходу живлення» (GND, вихід 3,3 V Teensy, VBUS, "
            "внутрішні LDO PCM1865, накачка TPA6132A2, VSYS після діода / ключа)", 0)
    for n in ("GND", D3, "VBUS", "VSYS", "ADC1_LDO", "ADC2_LDO", "HP_HPVDD", "HP_HPVSS"):
        b.part("#FLG", "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, w=12)

    b.finish()
    out = HW / "main"
    b.sh.write(out / "main.kicad_sch")
    project_files(out, "main")
    print(out / "main.kicad_sch", len(b.sh.parts), "parts")


if __name__ == "__main__":
    build()
