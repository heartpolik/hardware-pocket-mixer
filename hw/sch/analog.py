"""Analog board schematic (hw/analog/analog.kicad_sch).

Sources: docs/06 (signal flow, Mute, control), 07 (values), 08 (meters), 10 (passives),
11 (power), 13 (interboard pinout), decisions D21-D48.
Run: python3 hw/sch/analog.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kisch import Part, Sheet, project_files  # noqa: E402

HW = Path(__file__).resolve().parents[1]
R0805 = "Resistor_SMD:R_0805_2012Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
UEP5 = "diy-mixer:CP_Nichicon_UEP_D5.0_L11.0_P2.00_Horizontal"
UEP63 = "diy-mixer:CP_Nichicon_UEP_D6.3_L11.0_P2.50_Horizontal"
SOIC8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
SOIC14 = "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm"
FADER = "diy-mixer:Alps_RS451121400A_Fader_Dual_45mm"
POT_VOL = "diy-mixer:Alps_RK14K12D_Vertical_Volume"
POT_TONE = "diy-mixer:Alps_RK14K124_Vertical_Tone"
JACK = "diy-mixer:CUI_SJ-43514-SMT_TRRS_Horizontal"   # no pads 5/6 (not on SJ-43514)
MX = "Button_Switch_Keyboard:SW_Cherry_MX_1.00u_PCB"

P12, N12 = "+12VA", "-12VA"


class Board:
    def __init__(self):
        self.sh = Sheet("analog", "diy-mixer Rev A — analog board", "User")
        self.count = {}
        self.last_ic = None
        self.group = None                      # converter block, field "Group" (build_pcb.py place_group)
        self.cursor = {}
        self.col_y = {}

    def ref(self, prefix):
        self.count[prefix] = self.count.get(prefix, 0) + 1
        return f"{prefix}{self.count[prefix]}"

    COLS = (25.4, 508.0, 1143.0)

    def block(self, name, col, _y=None):
        """Start a block in column `col` below the previous block of that column."""
        if self.cursor:
            c = self.cursor
            self.col_y[c["col"]] = c["y"] + 45
        x = self.COLS[col]
        y = self.col_y.get(col, 30)
        self.sh.text(x, y - 10, name, 3)
        self.cursor = {"x0": x, "x": x, "y": y, "col": col}

    def finish(self):
        c = self.cursor
        self.col_y[c["col"]] = c["y"] + 45
        h = max(self.col_y.values()) + 20
        xs = [x for part in self.sh.parts for (x, _) in part.unit_pos.values()]
        self.sh.paper = (max(1190, round(max(xs) + 80)), max(841, round(h)))

    def _pos(self, n_units=1, w=17.78):
        c = self.cursor
        pos = []
        for _ in range(n_units):
            if c["x"] - c["x0"] > 330:
                c["x"], c["y"] = c["x0"], c["y"] + 33.02
            pos.append((round(round(c["x"] / 2.54) * 2.54, 2), round(round(c["y"] / 2.54) * 2.54, 2)))
            c["x"] += w
        return pos

    def part(self, prefix, lib, value, fp, pins, units=(1,), w=17.78, fields=None):
        ref = self.ref(prefix)
        if self.group:
            fields = dict(fields or {}, Group=self.group)
        if prefix in ("U", "DS", "LED"):           # parts with supply pins, for decouple()
            self.last_ic = ref
        pos = self._pos(len(units), w)
        self.sh.add(Part(ref, lib, value, fp, pins, dict(zip(units, pos)), fields))
        return ref

    def newrow(self):
        c = self.cursor
        c["x"], c["y"] = c["x0"], c["y"] + 33.02

    # ------------------------------------------------------------- primitives
    def r(self, val, a, b):
        return self.part("R", "Device:R", val, R0805, {"1": a, "2": b}, w=17.78)

    def c(self, val, a, b, fp=C0805, fields=None):
        return self.part("C", "Device:C", val, fp, {"1": a, "2": b}, w=17.78, fields=fields)

    def decouple(self, *nets):
        """100n per supply net of the IC created last; the field tells build_pcb.py whose pin it serves."""
        for n in nets:
            self.c("100n", n, "GND", fields={"Decouples": self.last_ic})

    def opa(self, a=None, b=None, value="OPA1678", fp=SOIC8, lib="Amplifier_Operational:OPA1678"):
        """a/b = (plus, minus, out) or None (unused half: follower to GND)."""
        pins = {"8": P12, "4": N12}
        for (p, m, o), (pp, mm, oo) in (((a or ("GND", None, None)), ("3", "2", "1")),
                                         ((b or ("GND", None, None)), ("5", "6", "7"))):
            if m is None:                                  # unused: buffer to GND
                pins.update({pp: "GND", mm: None, oo: None})
            else:
                pins.update({pp: p, mm: m, oo: o})
        ref = self.part("U", lib, value, fp, pins, units=(1, 2, 3), w=22.86)
        self.decouple(P12, N12)
        return ref


def build():
    b = Board()
    sh = b.sh

    # ================================================================ inputs x5
    for k in range(1, 6):
        ch = f"IN{k}" if k < 5 else "RET"
        b.block(f"Вхід {ch}: джек → 10 µF → DIP моно/стерео → фейдер → буфер +6 dB → Mute (DG413)",
                0)
        T, R = f"{ch}_T", f"{ch}_R"
        b.part("J", "diy-mixer:AudioJack_TRRS_SJ-43514", "SJ-43514-SMT", JACK,
               {"2": T, "3": R, "4": "GND", "1": "GND"}, w=30)
        b.c("10u BP", T, f"{ch}_TC", UEP5)
        b.c("10u BP", R, f"{ch}_RC", UEP5)
        b.r("1M", T, "GND")
        b.r("1M", R, "GND")
        # DIP SPDT per channel (D55): T1 <- R (stereo), T2 <- T (mono), B1 -> fader R top.
        # ПРИПУЩЕННЯ: pin roles not in the CTS datasheet - verify by continuity (docs/12).
        b.part("SW", "diy-mixer:SW_DIP_SPDT_CTS204_1pos", "CTS 204-121ST",
               "diy-mixer:CTS_204-121ST_DIP_SPDT_1pos_SMD",
               {"4": f"{ch}_RC", "3": f"{ch}_TC", "1": f"{ch}_RTOP", "2": None}, w=15)
        b.part("RV", "Device:R_Potentiometer_Dual_Separate", "RS451121400A 10k B", FADER,
               {"3": f"{ch}_TC", "2": f"{ch}_LW", "1": "GND",
                "6": f"{ch}_RTOP", "5": f"{ch}_RW", "4": "GND"}, units=(1, 2), w=17.78)
        b.newrow()
        b.r("1M", f"{ch}_LW", "GND")
        b.r("1M", f"{ch}_RW", "GND")
        b.opa((f"{ch}_LW", f"{ch}_LFB", f"{ch}_LB"), (f"{ch}_RW", f"{ch}_RFB", f"{ch}_RB"))
        for s in "LR":
            b.r("10k", f"{ch}_{s}B", f"{ch}_{s}FB")
            b.r("10k", f"{ch}_{s}FB", "GND")
        # Mute (D31, D41): SW1/SW4 series (NO), SW2/SW3 shunt (NC); 0 = mute
        mute = f"MUTE_{ch}"
        b.part("U", "Analog_Switch:DG413xY", "DG413", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
               {"1": mute, "3": f"{ch}_LB", "2": f"{ch}_LM",
                "16": mute, "14": "GND", "15": f"{ch}_LM",
                "8": mute, "6": f"{ch}_RB", "7": f"{ch}_RM",
                "9": mute, "11": "GND", "10": f"{ch}_RM",
                "13": P12, "4": N12, "5": "GND", "12": "+5V"}, units=(1, 2, 3, 4, 5), w=17.78)
        b.decouple(P12, N12, "+5V")
        b.r("100k", mute, "GND")
        b.newrow()
        if k < 5:
            # pan (D17, D26): Rs 10k -> node, pot ends L/R, wiper to GND; Rsum 22k
            b.r("10k", f"{ch}_LM", f"{ch}_LP")
            b.r("10k", f"{ch}_RM", f"{ch}_RP")
            b.part("RV", "Device:R_Potentiometer_Dual_Separate", "RK14K124003H 10k B detent",
                   POT_TONE, {"1": f"{ch}_LP", "2": "GND", "3": f"{ch}_RP",
                              "4": None}, units=(1, 2))
            b.r("22k", f"{ch}_LP", "SUM_L_IN")
            b.r("22k", f"{ch}_RP", "SUM_R_IN")
            # send (post-fader, pre-pan): RK14K12D, 20k into send sum
            b.part("RV", "diy-mixer:R_Potentiometer_Dual_CommonEnd", "RK14K12D 50k A", POT_VOL,
                   {"3": f"{ch}_LM", "2": f"{ch}_LS", "1": "GND", "6": f"{ch}_RM", "5": f"{ch}_RS"})
            b.r("20k", f"{ch}_LS", "SEND_L_IN")
            b.r("20k", f"{ch}_RS", "SEND_R_IN")
            b.part("SW", "Switch:SW_Push", "Cherry MX", MX, {"1": f"BTN_{ch}", "2": "GND"})
        else:
            b.r("76.8k", "RET_LM", "SUM_L_IN")
            b.r("76.8k", "RET_RM", "SUM_R_IN")
            b.part("SW", "Switch:SW_Push", "Cherry MX", MX, {"1": "BTN_RET", "2": "GND"})

    # ================================================================ sum, master, outputs
    b.block("Сума L/R (Rf 38,3k ‖ 39 pF), Master L/R (одна секція, D23), DC-блок, Mute Master, буфер, інвертор, MAIN OUT", 1)
    b.opa(("GND", "SUM_L_IN", "SUM_L"), ("GND", "SUM_R_IN", "SUM_R"))
    for s in "LR":
        b.r("38.3k", f"SUM_{s}", f"SUM_{s}_IN")
        b.c("39p C0G", f"SUM_{s}", f"SUM_{s}_IN")
    b.newrow()
    for s, gang in (("L", "ML"), ("R", "MR")):
        b.part("RV", "Device:R_Potentiometer_Dual_Separate", "RS451121400A 10k B", FADER,
               {"3": f"SUM_{s}", "2": f"{gang}_W", "1": "GND", "6": "GND", "5": "GND", "4": "GND"},
               units=(1, 2))
        b.c("10u BP", f"{gang}_W", f"{gang}_C", UEP5)
        b.r("1M", f"{gang}_C", "GND")
    b.part("U", "Analog_Switch:DG413xY", "DG413", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
           {"1": "MUTE_M", "3": "ML_C", "2": "ML_M", "16": "MUTE_M", "14": "GND", "15": "ML_M",
            "8": "MUTE_M", "6": "MR_C", "7": "MR_M", "9": "MUTE_M", "11": "GND", "10": "MR_M",
            "13": P12, "4": N12, "5": "GND", "12": "+5V"}, units=(1, 2, 3, 4, 5))
    b.decouple(P12, N12, "+5V")
    b.r("100k", "MUTE_M", "GND")
    b.part("SW", "Switch:SW_Push", "Cherry MX", MX, {"1": "BTN_M", "2": "GND"})
    b.newrow()
    b.opa(("ML_M", "ML_B", "ML_B"), ("MR_M", "MR_B", "MR_B"))
    b.opa(("GND", "ML_INV", "ML_OUT"), ("GND", "MR_INV", "MR_OUT"))
    b.newrow()
    for s, g in (("L", "ML"), ("R", "MR")):
        b.r("10k", f"{g}_B", f"{g}_INV")
        b.r("10k", f"{g}_INV", f"{g}_OUT")
        b.r("100", f"{g}_OUT", f"{g}_O")
        b.c("47u BP", f"{g}_O", f"MAIN_{s}", UEP63)
        b.r("100k", f"MAIN_{s}", "GND")
    b.part("J", "diy-mixer:AudioJack_TRRS_SJ-43514", "SJ-43514-SMT MAIN", JACK,
           {"2": "MAIN_L", "3": "MAIN_R", "4": "GND", "1": "GND"}, w=30)

    # send bus
    b.block("Send: сума (Rf 10k ‖ 150 pF) → інвертор → 100 Ω → 47 µF → SEND OUT", 1)
    b.opa(("GND", "SEND_L_IN", "SEND_L_S"), ("GND", "SEND_R_IN", "SEND_R_S"))
    b.opa(("GND", "SEND_L_INV", "SEND_L_OUT"), ("GND", "SEND_R_INV", "SEND_R_OUT"))
    b.newrow()
    for s in "LR":
        b.r("10k", f"SEND_{s}_S", f"SEND_{s}_IN")
        b.c("150p C0G", f"SEND_{s}_S", f"SEND_{s}_IN")
        b.r("10k", f"SEND_{s}_S", f"SEND_{s}_INV")
        b.r("10k", f"SEND_{s}_INV", f"SEND_{s}_OUT")
        b.r("100", f"SEND_{s}_OUT", f"SEND_{s}_O")
        b.c("47u BP", f"SEND_{s}_O", f"SEND_{s}", UEP63)
        b.r("100k", f"SEND_{s}", "GND")
    b.part("J", "diy-mixer:AudioJack_TRRS_SJ-43514", "SJ-43514-SMT SEND", JACK,
           {"2": "SEND_L", "3": "SEND_R", "4": "GND", "1": "GND"}, w=30)

    # phones
    b.block("Навушники (D32, D39): ротатор від суми, OPA1678 на канал, половини паралельно через 10 Ω", 1)
    b.part("RV", "diy-mixer:R_Potentiometer_Dual_CommonEnd", "RK14K12D 50k A PHONES", POT_VOL,
           {"3": "SUM_L", "2": "PH_LW", "1": "GND", "6": "SUM_R", "5": "PH_RW"})
    for s in "LR":
        b.opa((f"PH_{s}W", f"PH_{s}A", f"PH_{s}A"), (f"PH_{s}W", f"PH_{s}B", f"PH_{s}B"))
        b.r("10", f"PH_{s}A", f"PH_{s}")
        b.r("10", f"PH_{s}B", f"PH_{s}")
    b.part("J", "diy-mixer:AudioJack_TRRS_SJ-43514", "SJ-43514-SMT PHONES", JACK,
           {"2": "PH_L", "3": "PH_R", "4": "GND", "1": "GND"}, w=30)

    # ================================================================ meters
    b.block("Метри (08): двополуперіодні пік-детектори TL064 → C 0,33 µF → 10k → роз'єм", 1)
    meters = [(f"IN{k}", ["IN%d_LB" % k, "IN%d_RB" % k], f"MTR_CH{k}", "634k") for k in range(1, 5)]
    meters.append(("RET", ["RET_LB", "RET_RB"], "MTR_RET", "634k"))
    tl = []
    for name, srcs, out, rrel in meters:
        units = []
        for src in srcs:
            for pol in "PN":
                d = f"D_{name}_{src[-2]}{pol}"
                if pol == "P":
                    b.r("374k", src, f"{d}_IN")
                    b.r("100k", f"{d}_IN", "GND")
                    units.append((f"{d}_IN", f"{d}_K", f"{d}_O"))
                else:
                    b.r("953k", src, f"{d}_M")
                    b.r("200k", f"{d}_M", f"{d}_K")
                    units.append(("GND", f"{d}_M", f"{d}_O"))
                b.part("D", "Diode:1N4148W", "1N4148W", "Diode_SMD:D_SOD-123",
                       {"A": f"{d}_O", "K": f"{d}_K"}, w=10.16)
                b.r("330", f"{d}_K", f"{out}_H")
        tl.append(units)
        b.c("0.33u", f"{out}_H", "GND")
        b.r(rrel, f"{out}_H", "GND")
        b.r("10k", f"{out}_H", out)
        b.newrow()
    # master: L+, L-, R+, R- on one TL064, two hold caps
    units = []
    for s, out in (("L", "MTR_ML"), ("R", "MTR_MR")):
        for pol in "PN":
            d = f"D_M{s}{pol}"
            if pol == "P":
                b.r("374k", f"SUM_{s}", f"{d}_IN")
                b.r("100k", f"{d}_IN", "GND")
                units.append((f"{d}_IN", f"{d}_K", f"{d}_O"))
            else:
                b.r("953k", f"SUM_{s}", f"{d}_M")
                b.r("200k", f"{d}_M", f"{d}_K")
                units.append(("GND", f"{d}_M", f"{d}_O"))
            b.part("D", "Diode:1N4148W", "1N4148W", "Diode_SMD:D_SOD-123",
                   {"A": f"{d}_O", "K": f"{d}_K"}, w=10.16)
            b.r("330", f"{d}_K", f"{out}_H")
        b.c("0.33u", f"{out}_H", "GND")
        b.r("412k", f"{out}_H", "GND")
        b.r("10k", f"{out}_H", out)
    tl.append(units)
    b.newrow()
    for units in tl:
        pins = {"4": P12, "11": N12}
        for (p, m, o), (pp, mm, oo) in zip(units, (("3", "2", "1"), ("5", "6", "7"),
                                                   ("10", "9", "8"), ("12", "13", "14"))):
            pins.update({pp: p, mm: m, oo: o})
        b.part("U", "Amplifier_Operational:TL064", "TL064AC", SOIC14, pins, units=(1, 2, 3, 4, 5), w=20.32)
        b.decouple(P12, N12)
    b.r("249k", "VSW", "VBAT_SENSE")
    b.r("100k", "VBAT_SENSE", "GND")

    # ================================================================ control
    b.block("Керування (06 п. 4, D42): MCP23017 — Mute ×6 (GPA0–5), кнопки ×6 (GPB0–5), INT", 2)
    b.part("U", "Interface_Expansion:MCP23017x-x-SO", "MCP23017-E/SO", "Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm",
           {"V_{DD}": "+3V3", "V_{SS}": "GND", "SCK": "I2C_A_SCL", "SDA": "I2C_A_SDA",
            "A0": "GND", "A1": "GND", "A2": "GND", "~{RESET}": "MCP_RST", "INTA": "INT_N",
            "INTB": None, "NC": None,
            "GPA0": "MUTE_IN1", "GPA1": "MUTE_IN2", "GPA2": "MUTE_IN3", "GPA3": "MUTE_IN4",
            "GPA4": "MUTE_RET", "GPA5": "MUTE_M", "GPA6": None, "GPA7": None,
            "GPB0": "BTN_IN1", "GPB1": "BTN_IN2", "GPB2": "BTN_IN3", "GPB3": "BTN_IN4",
            "GPB4": "BTN_RET", "GPB5": "BTN_M", "GPB6": None, "GPB7": None}, w=45)
    b.r("10k", "+3V3", "MCP_RST")
    b.decouple("+3V3")

    # interboard connector, D48
    ib = {"1": "+5V", "2": "+5V", "3": "GND", "4": "GND", "5": "+3V3", "6": "GND",
          "7": "I2C_A_SDA", "8": "GND", "9": "I2C_A_SCL", "10": "INT_N", "11": "UART_TX",
          "12": "UART_RX", "13": "GND", "14": "GND", "15": "MTR_CH1", "16": "MTR_CH2",
          "17": "MTR_CH3", "18": "MTR_CH4", "19": "MTR_RET", "20": "MTR_ML", "21": "MTR_MR",
          "22": "VBAT_SENSE", "23": "GND", "24": "GND"}
    b.part("J", "Connector_Generic:Conn_02x12_Odd_Even", "PBS-24 до цифрової плати",
           "Connector_PinSocket_2.54mm:PinSocket_2x12_P2.54mm_Vertical", ib, w=30)

    # USB-C + CH340N (D25, D40)
    b.block("USB-C (GCT USB4085) → VBUS на модуль IP2326; D+/D− → USBLC6 → CH340N → UART0 ESP", 2)
    b.part("J", "Connector:USB_C_Receptacle_USB2.0_16P", "GCT USB4085",
           "Connector_USB:USB_C_Receptacle_GCT_USB4085",
           {"VBUS": "VBUS", "GND": "GND", "CC1": "CC1", "CC2": "CC2", "D+": "USB_DP", "D-": "USB_DN",
            "SBU1": None, "SBU2": None, "SHIELD": "GND"}, w=40)
    b.r("5.1k", "CC1", "GND")
    b.r("5.1k", "CC2", "GND")
    b.part("U", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
           {"I/O1": "USB_DP", "I/O2": "USB_DN", "VBUS": "VBUS", "GND": "GND"}, w=25)
    b.part("U", "Interface_USB:CH340N", "CH340N", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
           {"UD+": "USB_DP", "UD-": "USB_DN", "GND": "GND", "~{RTS}": None, "VCC": "+3V3",
            "V3": "+3V3", "TXD": "UART_RX", "RXD": "UART_TX"}, w=25)
    b.decouple("+3V3")

    # ================================================================ power (11, D16, D18, D22, D46)
    b.block("Живлення: модуль IP2326 + 2S, вимикач, LT1930 +12 V, LT1931 −12 V, RC-фільтри, TPS62933O 5 V", 2)
    b.part("J", "Connector_Generic:Conn_01x04", "Модуль IP2326: VBUS, GND, BAT+, GND",
           "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
           {"1": "VBUS", "2": "GND", "3": "BAT+", "4": "GND"}, w=20)
    # D51: MSK12C02 (12 V 50 mA) only pulls the gate of a P-MOSFET load switch; the battery
    # current (up to ~0.56 A at 6 V, 11-power) goes through AO3401A. 100n G-S = soft turn-on.
    b.part("SW", "Switch:SW_SPDT", "MSK12C02 вимикач живлення",
           "diy-mixer:SW_Slide_SPDT_SHOUHAN_MSK12C02_RightAngle",
           {"B": "PWR_G_SW", "A": "GND", "C": None}, w=20)
    b.r("10k", "PWR_G_SW", "PWR_G")
    b.part("Q", "Transistor_FET:AO3401A", "AO3401A", "Package_TO_SOT_SMD:SOT-23",
           {"S": "BAT+", "D": "VSW", "G": "PWR_G"}, w=20)
    b.r("100k", "BAT+", "PWR_G")
    b.c("100n", "BAT+", "PWR_G")
    b.newrow()
    # +12 V, LT1930 (mixerli v1.0)
    b.group = "P12"
    b.part("U", "diy-mixer:LT1930", "LT1930ES5", "Package_TO_SOT_SMD:SOT-23-5",
           {"5": "VSW", "4": "VSW", "2": "GND", "1": "SW_P", "3": "FB_P"}, w=30)
    # D49: shielded SRN4018-100M instead of unshielded Sumida CR43 (mixerli v1.0)
    b.part("L", "Device:L", "10u SRN4018-100M", "Inductor_SMD:L_Bourns-SRN4018", {"1": "VSW", "2": "SW_P"}, w=12)
    b.part("D", "Diode:MBR0530", "MBR0530", "Diode_SMD:D_SOD-123", {"A": "SW_P", "K": "+12V_P"}, w=12)
    b.r("113k", "+12V_P", "FB_P")
    b.r("13.3k", "FB_P", "GND")
    b.c("10p C0G", "+12V_P", "FB_P")
    b.c("4.7u 25V", "VSW", "GND", C1206)
    b.c("10u 25V", "+12V_P", "GND", C1206)
    b.r("2.2", "+12V_P", P12)
    b.c("22u 25V", P12, "GND", C1206)
    b.newrow()
    # -12 V, LT1931 dual-inductor inverting (mixerli v1.0)
    b.group = "M12"
    b.part("U", "Regulator_Switching:LT1931", "LT1931ES5", "Package_TO_SOT_SMD:SOT-23-5",
           {"VIN": "VSW", "~{SHDN}": "VSW", "GND": "GND", "SW": "SW_N", "NFB": "FB_N"}, w=30)
    b.part("L", "Device:L_Coupled", "2x10u CLS62-100", "diy-mixer:L_Sumida_CLS62",
           {"1": "VSW", "2": "SW_N", "3": "-12V_P", "4": "N_N"}, w=14)   # dots: VIN end, VOUT end (Cuk)
    b.c("1u 25V", "SW_N", "N_N", C0805)
    sh.text(b.cursor["x0"], b.cursor["y"] + 24, "LT1931: точки дроселя на VIN і на -12V (розрахунок для Cuk) - звірити з рис. 1 datasheet", 1.8)
    b.part("D", "Diode:MBR0530", "MBR0530", "Diode_SMD:D_SOD-123", {"A": "N_N", "K": "GND"}, w=12)
    b.r("84.5k", "-12V_P", "FB_N")
    b.r("10k", "FB_N", "GND")
    b.c("4.7u 25V", "VSW", "GND", C1206)
    b.c("10u 25V", "-12V_P", "GND", C1206)
    b.r("2.2", "-12V_P", N12)
    b.c("22u 25V", N12, "GND", C1206)
    b.newrow()
    # +5 V, TPS62933O: PG and RT not used (O version has PG on pin 7, no SS)
    b.group = "P5"
    b.part("U", "Regulator_Switching:TPS62933O", "TPS62933O", "Package_TO_SOT_SMD:SOT-583-8",
           {"VIN": "VSW", "EN": "EN_5", "GND": "GND", "SW": "SW_5", "BST": "BST_5", "FB": "FB_5",
            "RT": None, "PG": None}, w=30)
    b.r("100k", "VSW", "EN_5")
    b.r("100k", "EN_5", "GND")
    b.c("100n", "BST_5", "SW_5")
    b.part("L", "Device:L", "4.7u SRN4018-4R7M", "Inductor_SMD:L_Bourns-SRN4018", {"1": "SW_5", "2": "+5V"}, w=12)
    b.r("53.6k", "+5V", "FB_5")
    b.r("10.2k", "FB_5", "GND")
    b.c("10u 25V", "VSW", "GND", C1206)
    b.c("100n", "VSW", "GND")                 # TI SLUSEA4D 12.1: 0.1 uF right at VIN / GND
    b.c("22u 10V", "+5V", "GND", C1206)
    b.c("22u 10V", "+5V", "GND", C1206)
    b.group = None
    b.newrow()
    for n in ("GND", "VSW", P12, N12, "+5V", "+3V3"):
        b.part("#FLG", "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, w=12)
    b.finish()
    return sh


def main():
    sh = build()
    out = HW / "analog" / "analog.kicad_sch"
    project_files(out.parent, "analog")
    sh.write(out)
    print(out, len(sh.parts), "parts,", len(sh.nets()), "nets")


if __name__ == "__main__":
    main()
