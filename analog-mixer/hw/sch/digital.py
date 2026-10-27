"""Digital board schematic (hw/digital/digital.kicad_sch).

Sources: docs/06 (GPIO map, I2C-D/I2C-A), 08 (ADC), 12 (parts), 13 (interboard pinout),
D27, D36, D40, D48. Run: python3 hw/sch/digital.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analog import Board, C0805, R0805  # noqa: E402
from project import Sheet, project_files  # noqa: E402

HW = Path(__file__).resolve().parents[1]


def build():
    b = Board()
    b.sh = Sheet("digital", "diy-mixer Rev A — digital board", "A2")
    b.COLS = (25.4, 406.4)
    sh = b.sh

    b.block("ESP32-C3 SuperMini (D27, D40, D59): згори, плоско, USB-C на задньому краї. 5V = VBUS модуля: не підключати USB модуля при увімкненому мікшері", 0)
    b.part("U", "diy-mixer:ESP32-C3_SuperMini", "ESP32-C3 SuperMini", "diy-mixer:ESP32-C3_SuperMini_SMD",
           {"1": "+5V_MCU", "2": "GND", "3": "+3V3",
            "4": "I2C_D_SDA", "5": "INT_N", "6": None, "7": "ENC_B", "8": "ENC_A",
            "9": "I2C_D_SCL", "10": "I2C_A_SDA", "11": "I2C_A_SCL", "12": None,
            "13": "ENC_SW", "14": "LED_DATA_3V3", "15": "UART_RX", "16": "UART_TX"}, w=50)
    # D59: the module's USB-C is reachable now. Its VBUS feeds the 5V pin through the module's own
    # diode; this one keeps a plugged-in USB from feeding our +5V (and, through the high-side FET of
    # TPS62933, VSW and the +-12 V converters) while the mixer is off. Same MBR0530 as the converters.
    b.part("D", "Diode:MBR0530", "MBR0530", "Diode_SMD:D_SOD-123", {"A": "+5V", "K": "+5V_MCU"}, w=12)
    b.c("10u", "+5V", "GND", "Capacitor_SMD:C_1206_3216Metric")
    b.c("10u", "+3V3", "GND", "Capacitor_SMD:C_1206_3216Metric")
    for n in ("I2C_D_SDA", "I2C_D_SCL", "I2C_A_SDA", "I2C_A_SCL"):
        b.r("4.7k", "+3V3", n)

    b.newrow()
    b.part("J", "Connector_Generic:Conn_02x12_Odd_Even", "PLS-24 до аналогової плати",
           "Connector_PinHeader_2.54mm:PinHeader_2x12_P2.54mm_Vertical",
           {"1": "+5V", "2": "+5V", "3": "GND", "4": "GND", "5": "+3V3", "6": "GND",
            "7": "I2C_A_SDA", "8": "GND", "9": "I2C_A_SCL", "10": "INT_N", "11": "UART_TX",
            "12": "UART_RX", "13": "GND", "14": "GND", "15": "MTR_CH1", "16": "MTR_CH2",
            "17": "MTR_CH3", "18": "MTR_CH4", "19": "MTR_RET", "20": "MTR_ML", "21": "MTR_MR",
            "22": "VBAT_SENSE", "23": "GND", "24": "GND"}, w=40)

    b.block("АЦП метрів ADS7828 (08): I²C-D, адреса 0x48, внутрішня опора 2,5 V", 0)
    b.part("U", "Analog_ADC:ADS7828", "ADS7828", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
           {"CH0": "MTR_CH1", "CH1": "MTR_CH2", "CH2": "MTR_CH3", "CH3": "MTR_CH4",
            "CH4": "MTR_RET", "CH5": "MTR_ML", "CH6": "MTR_MR", "CH7": "VBAT_SENSE",
            "GND": "GND", "REF": "ADC_REF", "COM": "GND", "A0": "GND", "A1": "GND",
            "SCL": "I2C_D_SCL", "SDA": "I2C_D_SDA", "VDD": "+3V3"}, w=40)
    b.c("1u", "ADC_REF", "GND")
    b.c("1u", "+3V3", "GND")
    b.decouple("+3V3")
    for n in ("MTR_CH1", "MTR_CH2", "MTR_CH3", "MTR_CH4", "MTR_RET", "MTR_ML", "MTR_MR", "VBAT_SENSE"):
        b.c("10n", n, "GND")

    b.block("OLED SSD1306 (I²C-D) і енкодер EC12D (кнопка = GPIO9/BOOT, D40)", 0)
    b.part("DS", "diy-mixer:OLED_128x64_I2C", "OLED 0.96 128x64", "diy-mixer:OLED_0.96in_128x64_I2C_4pin",
           {"1": "+3V3", "2": "GND", "3": "I2C_D_SCL", "4": "I2C_D_SDA"}, w=30)
    b.decouple("+3V3")
    # EC12D footprint: not made yet - drawing 5 to be re-read / measured (docs/12)
    b.part("SW", "Device:RotaryEncoder_Switch", "EC12D (30/15) з кнопкою", "diy-mixer:Alps_EC12D_Switch",
           {"A": "ENC_A", "B": "ENC_B", "C": "GND", "S1": "ENC_SW", "S2": "GND"}, w=30)
    b.r("10k", "+3V3", "ENC_A")
    b.r("10k", "+3V3", "ENC_B")
    b.c("10n", "ENC_A", "GND")
    b.c("10n", "ENC_B", "GND")

    b.block("RGB LED ×5 SK6812MINI-E (D36), перетворювач рівня 74AHCT1G125, монтаж знизу через виріз", 0)
    b.part("U", "74xGxx:74AHCT1G125", "SN74AHCT1G125DBV", "Package_TO_SOT_SMD:SOT-23-5",
           {"1": "GND", "2": "LED_DATA_3V3", "4": "LED_DATA_5V", "5": "+5V", "3": "GND"}, w=30)
    b.decouple("+5V")
    b.r("330", "LED_DATA_5V", "LED_D1")
    for i in range(1, 6):
        b.part("LED", "LED:SK6812MINI-E", "SK6812MINI-E",
               "LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount",
               {"VDD": "+5V", "VSS": "GND", "DIN": f"LED_D{i}", "DOUT": f"LED_D{i + 1}" if i < 5 else None},
               w=25)
        b.decouple("+5V")
    b.c("47u", "+5V", "GND", "Capacitor_SMD:C_1206_3216Metric")
    b.newrow()
    for n in ("GND", "+5V", "+5V_MCU"):   # +3V3 is driven by the SuperMini LDO (power_out)
        b.part("#FLG", "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, w=12)
    b.finish()
    return sh


def main():
    sh = build()
    out = HW / "digital" / "digital.kicad_sch"
    project_files(out.parent, "digital")
    sh.write(out)
    print(out, len(sh.parts), "parts,", len(sh.nets()), "nets")


if __name__ == "__main__":
    main()
