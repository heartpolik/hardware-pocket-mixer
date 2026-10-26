"""Power supply: LT1930 (+12 V), LT1931 (-12 V), TPS62933O (5 V) from 2S, and runtime.

Run: python3 docs/calc/power.py  -> markdown tables on stdout.
Sources: docs/datasheets/1930f.pdf, 1931fa.pdf, tps62933o.pdf, esp32-c3_datasheet_en.pdf.
"""
import math

V_BAT = {"6,0 V (розряджена)": 6.0, "7,4 V (номінал)": 7.4, "8,4 V (заряджена)": 8.4}

# --- loads (mA), typ / max: see docs/07-gain-structure.md, docs/08-meter-detector.md -----
OPA1678_PKG = (4.0, 5.0)        # 2 / 2.5 mA per channel
N_OPA1678 = 12                  # 10 audio path + 2 phones
TL064_PKG = (0.8, 1.0)          # 0.2 / 0.25 mA per amplifier
N_TL064 = 6
PHONES_LOAD = (10.0, 30.0)      # average current into headphones, loud listening
I_RAIL = tuple(N_OPA1678 * o + N_TL064 * t + p
               for o, t, p in zip(OPA1678_PKG, TL064_PKG, PHONES_LOAD))

LOADS_5V = {                    # mA, typ / max
    "ESP32-C3, 80 MHz, без радіо (+ flash)": (22, 32),   # datasheet table 5-8 + ~10 mA flash
    "OLED 128×64 SSD1306": (12, 20),                      # module datasheet: 12 typ / 20 max at 3.3 V
    "RGB LED SK6812MINI-E × 5 (спокій 1 mA + низька яскравість)": (10, 25),
    "MCP23017, ADS7828, перетворювач рівня, CH340N (сон)": (2, 4),
}

# --- LT1930 boost, datasheet: VFB 1.240/1.255/1.270 V, switch limit 1 A min ---------------
R1_P, R2_P = 113e3, 13.3e3
L_P, F_SW = 10e-6, 1.2e6       # Sumida CR43-100 (mixerli v1.0), LT1930 1.2 MHz
# --- LT1931 inverting: NFB -1.255 V, NFB current 4 (typ) .. 8 (max) uA -------------------
R1_N, R2_N = 84.5e3, 10e3
I_NFB = (4e-6, 8e-6)
L_N = 10e-6                    # Sumida CLS62-100 coupled (mixerli v1.0)
I_SW_LIM = 1.0
V_DIODE = 0.4
ETA_12 = 0.80                  # estimate
# --- TPS62933O ----------------------------------------------------------------------------
RFBT, RFBB = 53.6e3, 10.2e3    # datasheet table 10-2 for 5 V
L_5, F_5 = 4.7e-6, 500e3       # RT floating = 500 kHz
I_RIPPLE_MIN = 0.3             # >= 10 % of 3 A (datasheet 10.2.2.7)
ETA_5 = 0.88                   # estimate at light load
R_EN_TOP, R_EN_BOT = 100e3, 100e3

BAT_WH = 2 * 3.7 * 1.5         # 2S 1500 mAh
BAT_USABLE = 0.9


def main():
    print("## ±12 V\n")
    vp = [1.240 * (1 + R1_P / R2_P), 1.255 * (1 + R1_P / R2_P), 1.270 * (1 + R1_P / R2_P)]
    vn = [1.255 + R1_N * (1.255 / R2_N + i) for i in I_NFB]
    print(f"- +12 V (LT1930, {R1_P / 1e3:.0f}k / {R2_P / 1e3:.1f}k): {vp[0]:.2f} … {vp[1]:.2f} … {vp[2]:.2f} V")
    print(f"- −12 V (LT1931, {R1_N / 1e3:.1f}k / {R2_N / 1e3:.0f}k, NFB 4…8 µA): "
          f"−{vn[0]:.2f} … −{vn[1]:.2f} V")
    print(f"- Струм на шину: {I_RAIL[0]:.0f} mA тип., {I_RAIL[1]:.0f} mA макс.\n")
    vout_p, vout_n, i_load = vp[1], vn[0], I_RAIL[1] / 1e3
    print("| Vбат | LT1930: D | Iпік ключа | Iвих макс | LT1931: D | Iпік ключа | Iвих макс "
          "| Діод LT1931, зворотна |")
    print("|---|---|---|---|---|---|---|---|")
    for name, vin in V_BAT.items():
        d_p = (vout_p + V_DIODE - vin) / (vout_p + V_DIODE)
        iin_p = vout_p * i_load / (vin * ETA_12)
        ripple_p = vin * d_p / (L_P * F_SW)
        ipk_p = iin_p + ripple_p / 2
        imax_p = (I_SW_LIM - ripple_p / 2) * (1 - d_p) * ETA_12
        d_n = (vout_n + V_DIODE) / (vin + vout_n + V_DIODE)
        iin_n = vout_n * i_load / (vin * ETA_12)
        ripple_n = vin * d_n / (L_N * F_SW)
        ipk_n = iin_n + i_load + ripple_n / 2
        imax_n = 0.75 * (I_SW_LIM - ripple_n / 2) / (1 + vout_n / (vin * ETA_12))
        print(f"| {name} | {d_p * 100:.0f} % | {ipk_p * 1e3:.0f} mA | ~{imax_p * 1e3:.0f} mA "
              f"| {d_n * 100:.0f} % | {ipk_n * 1e3:.0f} mA | ~{imax_n * 1e3:.0f} mA | {vin + vout_n:.1f} V |")

    print("\n## 5 V (TPS62933O)\n")
    vout5 = 0.8 * (1 + RFBT / RFBB)
    i5 = [sum(v[k] for v in LOADS_5V.values()) for k in (0, 1)]
    print(f"- Vout = 0,8 × (1 + {RFBT / 1e3:.1f}k / {RFBB / 1e3:.1f}k) = {vout5:.2f} V")
    print(f"- Навантаження: {i5[0]} mA тип., {i5[1]} mA макс.")
    print(f"- EN: дільник {R_EN_TOP / 1e3:.0f}k / {R_EN_BOT / 1e3:.0f}k → "
          + ", ".join(f"{v * R_EN_BOT / (R_EN_TOP + R_EN_BOT):.1f} V" for v in V_BAT.values())
          + " (поріг 1,21 V, abs max 6 V)")
    print("- Soft-start: у TPS62933O виводу SS немає (вивід 7 = PG), старт внутрішній\n")
    print("| Vбат | D | Пульсації струму дроселя | Iпік при макс. навантаженні | ≥ 0,3 A? |")
    print("|---|---|---|---|---|")
    for name, vin in V_BAT.items():
        ripple = (vin - vout5) * vout5 / (vin * F_5 * L_5)
        ipk = i5[1] / 1e3 + ripple / 2
        print(f"| {name} | {vout5 / vin * 100:.0f} % | {ripple:.2f} A | {ipk:.2f} A | "
              f"{'✅' if ripple >= I_RIPPLE_MIN else '⚠️'} |")

    print("\n## Батарея й час роботи\n")
    print("| Режим | ±12 V | 5 V | З батареї | Час роботи (2S 1500 mAh, 90 %) |")
    print("|---|---|---|---|---|")
    for k, name in ((0, "тип."), (1, "макс.")):
        p12 = (vp[1] + vn[0]) * I_RAIL[k] / 1e3 / ETA_12
        p5 = 5.0 * i5[k] / 1e3 / ETA_5
        p = p12 + p5
        print(f"| {name} | {p12:.2f} W | {p5:.2f} W | **{p:.2f} W** | **{BAT_WH * BAT_USABLE / p:.1f} год** |")


if __name__ == "__main__":
    main()
