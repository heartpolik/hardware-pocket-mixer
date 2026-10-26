"""Meter detector: full-wave peak detector on TL064, hold capacitor -> ADS7828.

Run: python3 docs/calc/meter_detector.py  -> markdown tables on stdout.
See docs/08-meter-detector.md for the circuit and sources.
"""
import math

# --- fixed by datasheets / earlier decisions ---------------------------------
V_REF = 2.5                # ADS7828 internal reference = full scale
N_BITS = 12
V_ADC_ABS_MAX = 3.3 + 0.2  # ADS7828 absolute input range at VDD = 3.3 V
V_RAIL = 12.4              # largest rail magnitude (LT1931, -12.4 V)
V_CLIP_GUAR = 11.1         # OPA1678 guaranteed peak swing from +11.9 V (07-gain-structure)
VIO_MAX = {"TL064C": 15e-3, "TL064AC": 6e-3}   # TL06x datasheet, 25 degC
I_TL06X = 0.2e-3           # per amplifier, typ.

# --- proposal ----------------------------------------------------------------
R_TOP, R_BOT = 374e3, 100e3   # non-inverting detector: input divider
R_IN, R_FB = 953e3, 200e3     # inverting detector: gain -R_FB/R_IN (high: small leak from C)
R_ATT = 330.0                 # diode cathode -> hold cap (attack); tuned in ngspice
C_HOLD = 0.33e-6
TARGET_R_EQ = 302e3           # total discharge resistance of the hold cap
CLIP_FLAG = 10.0              # firmware near-clip threshold at the node, Vpk
SCAN_HZ = 200                 # firmware ADC scan rate
R_VB_TOP, R_VB_BOT = 249e3, 100e3   # battery divider
V_BAT_MAX = 8.4

# meter -> (non-inverting detectors, inverting detectors) charging one hold cap
METERS = {
    "ch1–ch4 (кожен), RET": (2, 2),   # L+, R+, L-, R-  -> max(|L|, |R|)
    "Master L, Master R (кожен)": (1, 1),
}


def par(*rs):
    return 1 / sum(1 / r for r in rs)


def db(x):
    return 20 * math.log10(x)


def e96(x):
    """Nearest E96 value."""
    dec = 10 ** math.floor(math.log10(x))
    series = [round(10 ** (i / 96), 2) for i in range(96)]
    return min((s * dec for s in series), key=lambda v: abs(math.log(v / x)))


def main():
    k_ni = R_BOT / (R_TOP + R_BOT)
    k_inv = R_FB / R_IN
    k = (k_ni + k_inv) / 2
    lsb = V_REF / 2 ** N_BITS
    print("## Масштаб\n")
    print("| Величина | Значення |\n|---|---|")
    print(f"| k неінвертувального ({R_TOP / 1e3:.0f}k / {R_BOT / 1e3:.0f}k) | {k_ni:.4f} |")
    print(f"| k інвертувального ({R_FB / 1e3:.0f}k / {R_IN / 1e3:.0f}k) | {k_inv:.4f} |")
    print(f"| Розбіжність половин хвилі | {db(k_ni / k_inv):+.2f} dB |")
    print(f"| Повна шкала АЦП відповідає піку у вузлі | {V_REF / k:.2f} Vpk |")
    print(f"| Найбільша напруга на АЦП (вузол на шині {V_RAIL} V) | {V_RAIL * k:.2f} V "
          f"(abs max {V_ADC_ABS_MAX:.1f} V) |")
    print(f"| 1 LSB у вузлі | {lsb / k * 1e3:.2f} mV |")

    print("\n## Утримання й спад\n")
    print("| Метр | Шляхи розряду через інв. детектори | R спаду (E96) | R екв. | τ спаду | τ атаки |")
    print("|---|---|---|---|---|---|")
    for name, (_, n_inv) in METERS.items():
        r_leak = (R_IN + R_FB) / n_inv
        r_rel = e96(1 / (1 / TARGET_R_EQ - 1 / r_leak))
        r_eq = par(r_rel, r_leak)
        print(f"| {name} | {n_inv} × {(R_IN + R_FB) / 1e3:.0f}k | {r_rel / 1e3:.0f}k "
              f"| {r_eq / 1e3:.0f}k | {r_eq * C_HOLD * 1e3:.0f} ms | {R_ATT * C_HOLD * 1e3:.2f} ms |")
    tau = TARGET_R_EQ * C_HOLD
    droop = db(math.exp(-1 / SCAN_HZ / tau))
    print(f"\nЗа один період опитування ({1e3 / SCAN_HZ:.0f} ms) утримання падає на {droop:.2f} dB.")
    i_att = V_REF / R_ATT
    print(f"Найбільший струм заряду (стрибок до повної шкали через {R_ATT:.0f} Ω): {i_att * 1e3:.1f} mA.")

    print("\n## Рівні → коди АЦП\n")
    print("| Сигнал у вузлі (синус) | Vpk | На АЦП | Код | |")
    print("|---|---|---|---|---|")
    levels = [("Межа OPA1678 (гарант.)", V_CLIP_GUAR), ("Поріг CLIP у прошивці", CLIP_FLAG)]
    for dbu in (20, 10, 4, 0, -10, -20, -30, -40):
        levels.append((f"{dbu:+d} dBu", 0.775 * 10 ** (dbu / 20) * math.sqrt(2)))
    for name, vpk in levels:
        va = vpk * k
        code = min(int(va / lsb), 2 ** N_BITS - 1)
        note = "" if code >= 16 else "нижче корисного діапазону"
        print(f"| {name} | {vpk:.3f} | {va * 1e3:.1f} mV | {code} | {note} |")
    print("\nЗміщення TL064 у вузлі (найгірше, 25 °C):")
    for part, vio in VIO_MAX.items():
        v_node = vio / k
        print(f"- {part}: {vio * 1e3:.0f} mV на конденсаторі = {v_node * 1e3:.0f} mV у вузлі "
              f"≈ {db(v_node / math.sqrt(2) / 0.775):.0f} dBu")

    print("\n## Батарея\n")
    kb = R_VB_BOT / (R_VB_TOP + R_VB_BOT)
    for v in (8.4, 7.4, 6.8, 6.4, 6.0):
        print(f"- {v:.1f} V → {v * kb:.3f} V на АЦП, код {int(v * kb / lsb)}")
    print(f"- Струм дільника при 8,4 V: {V_BAT_MAX / (R_VB_TOP + R_VB_BOT) * 1e6:.0f} µA")

    n_amps = sum((a + b) * (5 if "ch1" in n else 2) for n, (a, b) in METERS.items())
    print(f"\n## Струм\n\n{n_amps} підсилювачів = {n_amps // 4} × TL064 → "
          f"{n_amps * I_TL06X * 1e3:.1f} mA на шину (тип.).")

    print("\n## Спад утримання (для графіка)\n")
    ts = list(range(0, 301, 25))
    print("t, ms: " + ", ".join(str(t) for t in ts))
    print("dB: " + ", ".join(f"{db(math.exp(-t / 1e3 / tau)):.1f}" for t in ts))


if __name__ == "__main__":
    main()
