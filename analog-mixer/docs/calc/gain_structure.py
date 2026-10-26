"""Gain structure and headroom of the analog path on +/-12 V.

Run: python3 docs/calc/gain_structure.py  -> markdown tables on stdout.
All values are estimates (see docs/07-gain-structure.md for sources and assumptions).
"""
import math

# --- rails and op-amps --------------------------------------------------------
V_RAIL_MIN = 11.9          # LT1930 +11.9 V; LT1931 gives -12.4 V, so + side limits
# worst-case drop from the rail and voltage noise density, from the datasheets
OPAMPS = {
    "NJM4580": dict(drop=3.0, en=3.3e-9),   # VOM >= +/-12 V at +/-15 V, RL >= 2k; en graph
    "OPA1678": dict(drop=0.8, en=4.5e-9),   # VO = rails -/+ 0.8 V; en 4.5 nV/rtHz at 1 kHz
}
OPAMP = "OPA1678"          # proposal for the audio path (D34)
V_SW_WORST = V_RAIL_MIN - OPAMPS[OPAMP]["drop"]

# --- topology values (proposal) ---------------------------------------------
G_BUF = 2.0                # input buffer +6 dB, as mixerli (10k / 10k)
R_PAN = 10e3               # RK14K124003H, D26
R_S = 10e3                 # series resistor buffer -> pan node
R_SUM = 22e3               # pan node -> virtual ground
N_ARMS = 5                 # ch1-4 + RET
SEND_GAIN = 1.0            # send out / input at send pot max (R_in = 2 * Rf)
PHONES_GAIN = 1.0          # headphone amp gain at pot max
# phones (D39): one OPA1678 per channel, both halves in parallel via 10 ohm each
I_OUT_MAX = 100e-3         # 2 x ISC 50 mA (OPA1678 datasheet)
R_OUT_PH = 5.0             # 10 ohm || 10 ohm
IQ_PKG = 4e-3              # OPA1678 2 mA per channel
THETA_JA = 144.0           # OPA1678 SOIC-8, degC/W
T_AMB = 40.0               # inside the enclosure (assumption)

K, T, BW = 1.38e-23, 300.0, 20e3
EN_OPAMP = OPAMPS[OPAMP]["en"]


def par(a, b):
    return a * b / (a + b)


def db(x):
    return 20 * math.log10(x)


def dbu(vrms):
    return db(vrms / 0.775)


def pan_gain(x):
    """Voltage at the pan node / buffer output, x = wiper position 0..1 from this side."""
    if x == 0:
        return 0.0
    z = par(x * R_PAN, R_SUM)
    return z / (R_S + z)


def main():
    c, e = pan_gain(0.5), pan_gain(1.0)
    r_f = R_SUM / (G_BUF * c)                 # unity input -> sum at pan centre
    r_ret = G_BUF * r_f                       # RET: no pan, unity
    print("## Номінали суматора\n")
    print("| Величина | Значення |\n|---|---|")
    print(f"| Rf суматора (unity при pan у центрі) | {r_f / 1e3:.1f} k |")
    print(f"| R входу RET (unity) | {r_ret / 1e3:.1f} k |")
    print(f"| Pan law: центр відносно крайнього | {db(c / e):.2f} dB |")
    print(f"| Канал на краю pan відносно unity | +{db(e / c):.2f} dB |")

    # noise at the sum output, all arms connected (muted arms are grounded too)
    arms = [R_SUM + par(R_S, R_PAN / 2)] * (N_ARMS - 1) + [r_ret]
    z_par = 1 / sum(1 / z for z in arms)
    ng = 1 + r_f / z_par
    v2 = 4 * K * T * r_f + sum(4 * K * T * z * (r_f / z) ** 2 for z in arms) + (EN_OPAMP * ng) ** 2
    vn = math.sqrt(v2 * BW)
    print(f"| Noise gain суматора | {ng:.1f} |")
    print(f"| Шум на виході суми ({OPAMP}), 20 Hz–20 kHz | {vn * 1e6:.1f} µVrms ({dbu(vn):.0f} dBu) |")

    print("\n## Запас до кліпінгу\n")
    sw = {n: V_RAIL_MIN - o["drop"] for n, o in OPAMPS.items()}
    print("Межа виходу (гарантовано, від +11,9 V): "
          + ", ".join(f"{n} {v:.1f} Vpk" for n, v in sw.items()) + ".\n")
    print("| Вузол | Рівень відносно входу | "
          + " | ".join(f"Макс. вхід, {n}" for n in sw) + " |")
    print("|---|---|" + "---|" * len(sw))
    rows = [
        ("Вихід вхідного буфера (фейдер max)", G_BUF),
        ("Сума: 1 канал, pan у центрі", 1.0),
        ("Сума: 1 канал, pan на краю", e / c),
        (f"Сума: {N_ARMS} однакових каналів у фазі, pan у центрі", N_ARMS),
        ("MAIN OUT (Master max)", 1.0),
        ("SEND OUT (send max)", SEND_GAIN),
        ("PHONES (гучність max)", PHONES_GAIN),
    ]
    for name, g in rows:
        cells = []
        for v in sw.values():
            vin = v / g / math.sqrt(2)
            cells.append(f"{vin:.2f} Vrms ({dbu(vin):+.1f} dBu)")
        print(f"| {name} | {db(g):+.1f} dB | " + " | ".join(cells) + " |")

    print(f"\n## Типові джерела ({OPAMP})\n")
    print("| Джерело | Vrms | dBu | Запас буфера, dB | Запас суми (5 у фазі), dB |")
    print("|---|---|---|---|---|")
    for name, v in (("Споживчий line −10 dBV", 0.316), ("Pro line +4 dBu", 1.228),
                    ("CD / DAC 2 Vrms", 2.0), ("Eurorack ±5 V", 5 / math.sqrt(2))):
        hb = db(V_SW_WORST / math.sqrt(2) / (v * G_BUF))
        hs = db(V_SW_WORST / math.sqrt(2) / (v * N_ARMS))
        print(f"| {name} | {v:.2f} | {dbu(v):+.1f} | {hb:+.1f} | {hs:+.1f} |")

    print("\n## Навушники: тепло корпусу на каналі (синус)\n")
    print("| Навантаження | Рівень | Струм пік | Потужність у навушниках | Розсіювання корпусу | Tj при 40 °C |")
    print("|---|---|---|---|---|---|")
    for rl in (16, 32, 64):
        for vr in (0.5, 1.0, 2.0):
            ipk = vr * math.sqrt(2) / rl
            if ipk > I_OUT_MAX:
                continue
            p = 24 * IQ_PKG + 2 * V_RAIL_MIN * ipk / math.pi - ipk ** 2 * (rl + R_OUT_PH) / 2
            tj = T_AMB + THETA_JA * p
            mark = "✅" if tj <= 105 else ("⚠️" if tj <= 125 else "❌")
            print(f"| {rl} Ω | {vr:.1f} Vrms | {ipk * 1e3:.0f} mA | {vr ** 2 / rl * 1e3:.0f} mW "
                  f"| {p:.2f} W | {tj:.0f} °C {mark} |")


if __name__ == "__main__":
    main()
