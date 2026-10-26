"""Power budget and runtime of the digital mixer on one Li-ion cell (1S).

  python3 digital-mixer/docs/calc/power.py

Chain (docs/02-components.md, p. 4): cell / USB -> load sharing -> buck-boost TPS63802 -> RAIL;
RAIL feeds Teensy VIN (its own 3.3 V regulator also feeds the digital supplies), a low-noise LDO
LP5907 3.3 V for the analog supplies of the codecs, the LEDs and the headphone amp.
Currents: datasheets in docs/datasheets unless marked ESTIMATE.
"""
RAIL = 4.2                 # V, buck-boost output (TPS63802 module, fixed 3.3/4.2/5.0 variants)
EFF = 0.90                 # buck-boost efficiency at ~0.35 A, Vin ~ Vout - ESTIMATE (datasheet curve p. 1)
E_CELL_USABLE = 0.90       # share of nominal energy down to cut-off - ESTIMATE
V_NOM = 3.7

teensy_vin = 100           # mA at 600 MHz (PJRC)
dig_3v3 = {                # from the Teensy 3.3 V pin (max 250 mA, third-party spec tables)
    "PCM1865 IOVDD x2": 2 * 10,        # pcm1865.pdf p. 14, 4-ch active
    "PCM5102A DVDD x3": 3 * 8,         # pcm5102a.pdf p. 10: 99 mW - 22 mA * 3.3 V -> ~8 mA
    "OLED 0.96": 15,                   # analog-mixer 12-parts: 12/20 mA
}
ana_3v3 = {                # LP5907 3.3 V (max 250 mA, dropout <= 250 mV @ 250 mA SOT-23)
    "PCM1865 AVDD x2": 2 * 31,         # pcm1865.pdf p. 14
    "PCM5102A AVDD+CPVDD x3": 3 * 22,  # pcm5102a.pdf p. 10
}
rail_other = {"headphone amp": 20, "SK6812 x8, dim": 40}   # ESTIMATE

i_rail = teensy_vin + sum(dig_3v3.values()) + sum(ana_3v3.values()) + sum(rail_other.values())
p_rail = i_rail / 1000 * RAIL
p_batt = p_rail / EFF
print(f"Teensy 3.3 V pin: {sum(dig_3v3.values())} mA of 250; LP5907: {sum(ana_3v3.values())} mA of 250")
print(f"Rail {RAIL} V: {i_rail} mA = {p_rail:.2f} W; from the cell {p_batt:.2f} W "
      f"({p_batt / V_NOM * 1000:.0f} mA at {V_NOM} V)")
print("\n| Cell, mAh | Energy, Wh | Runtime, h |\n|---|---|---|")
for mah in (2000, 2500, 3000, 4000):
    wh = mah / 1000 * V_NOM
    print(f"| {mah} | {wh:.1f} | {wh * E_CELL_USABLE / p_batt:.1f} |")
need = p_batt * 6 / E_CELL_USABLE / V_NOM * 1000
print(f"\n6 h needs >= {need:.0f} mAh")

# USB: system from VBUS through a Schottky + charging current (TP4056, RPROG)
for prog_k, i_chg in ((2.4, 500), (1.2, 1000)):
    i_sys = p_batt / 4.7 * 1000                   # VBUS 5 V - 0.3 V Schottky
    print(f"RPROG {prog_k}k: charge {i_chg} mA + system {i_sys:.0f} mA = {i_chg + i_sys:.0f} mA from USB; "
          f"3000 mAh in ~{3000 / i_chg * 1.2:.1f} h (CC + CV ~ x1.2, ESTIMATE)")
