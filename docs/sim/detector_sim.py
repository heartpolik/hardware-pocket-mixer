"""ngspice transient tests of the meter detector (docs/08-meter-detector.md).

Needs: ngspice in PATH, internet once (TI TL064 macromodel, sloj064, is downloaded
to docs/sim/models/ and not committed).
Run:   python3 docs/sim/detector_sim.py   -> markdown table + docs/sim/detector-*.svg
"""
import io
import math
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
MODELS = HERE / "models"
TL064_URL = "https://www.ti.com/lit/zip/sloj064"

# values from docs/calc/meter_detector.py (proposal)
R_TOP, R_BOT = "374k", "100k"
R_IN, R_FB = "953k", "200k"
R_ATT, C_HOLD, R_REL = "330", "0.33u", "634k"
VPOS, VNEG = 11.9, -12.4
K = 0.211

# 1N4148: widely used generic model (not from a vendor datasheet in this repo)
D1N4148 = (".model D1N4148 D(IS=2.52n RS=0.568 N=1.752 CJO=4p M=0.4 TT=20n "
           "BV=100 IBV=100u)")


def tl064_model():
    MODELS.mkdir(exist_ok=True)
    f = MODELS / "TL064.301"
    if not f.exists():
        req = urllib.request.Request(TL064_URL, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            f.write_bytes(z.read("TL064.301"))
    return f


def channel(sig_l, sig_r, tstop, tstep):
    """One channel meter: L+, L-, R+, R- detectors on one hold capacitor."""
    det = []
    for side, src in (("l", sig_l), ("r", sig_r)):
        src_line = (f"B{side} s{side} 0 V = {src[4:]}" if src.startswith("BSRC")
                    else f"V{side} s{side} 0 {src}")
        det.append(f"""
{src_line}
* non-inverting detector
Rt{side} s{side} p{side} {R_TOP}
Rb{side} p{side} 0 {R_BOT}
XP{side} p{side} kp{side} vp vn op{side} TL064
DP{side} op{side} kp{side} D1N4148
RAp{side} kp{side} hold {R_ATT}
* inverting detector
Ri{side} s{side} m{side} {R_IN}
Rf{side} m{side} kn{side} {R_FB}
XN{side} 0 m{side} vp vn on{side} TL064
DN{side} on{side} kn{side} D1N4148
RAn{side} kn{side} hold {R_ATT}""")
    return f"""meter detector
.include {tl064_model()}
{D1N4148}
Vp vp 0 {VPOS}
Vn vn 0 {VNEG}
{''.join(det)}
Chold hold 0 {C_HOLD}
Rrel hold 0 {R_REL}
Rout hold adc 10k
Cadc adc 0 10n
.options method=gear reltol=1e-4
.tran {tstep} {tstop} uic
.control
run
wrdata out.txt v(adc) v(opl) v(sl)
.endc
.end
"""


def run(net):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "t.cir").write_text(net)
        subprocess.run(["ngspice", "-b", "t.cir"], cwd=d, capture_output=True, check=True)
        rows = [list(map(float, ln.split())) for ln in (Path(d) / "out.txt").read_text().splitlines()]
    # wrdata: t v(adc) t v(opl) t v(sl)
    return [(r[0], r[1], r[3], r[5]) for r in rows]


def sine(vpk, f, delay=0.0, cycles=None):
    if cycles is None:
        return f"SIN(0 {vpk} {f} {delay})"
    t_end = delay + cycles / f
    return (f"BSRC(time > {delay} && time < {t_end}) ? "
            f"{vpk} * sin(6.283185 * {f} * (time - {delay})) : 0")


def svg(rows, name, title, t0=0.0):
    w, h, pad = 600, 220, 30
    t1 = rows[-1][0]
    vmax = max(max(r[1] for r in rows), 0.1) * 1.15
    pts = " ".join(f"{pad + (r[0] - t0) / (t1 - t0) * (w - 2 * pad):.1f},"
                   f"{h - pad - r[1] / vmax * (h - 2 * pad):.1f}" for r in rows if r[0] >= t0)
    (HERE / f"detector-{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" fill="#fff"/>'
        f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#999"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" stroke="#999"/>'
        f'<polyline fill="none" stroke="#2a6" stroke-width="1.5" points="{pts}"/>'
        f'<text x="{pad}" y="18" font-family="sans-serif" font-size="12">{title}</text>'
        f'<text x="{w - pad}" y="{h - 8}" font-family="sans-serif" font-size="11" text-anchor="end">'
        f'{(t1 - t0) * 1e3:.0f} ms</text>'
        f'<text x="4" y="{pad + 4}" font-family="sans-serif" font-size="11">{vmax:.2f} V</text></svg>')


def main():
    print("| Тест | Очікувано на АЦП | Симуляція | Похибка |")
    print("|---|---|---|---|")
    tests = [
        ("1 kHz, 10 Vpk (поріг CLIP), L і R", sine(10, 1e3), sine(10, 1e3), 20e-3, 10e-3),
        ("1 kHz, 0,11 Vpk (−20 dBu), лише L", sine(0.11, 1e3), "0", 20e-3, 10e-3),
        ("100 Hz, 0,11 Vpk (−20 dBu), лише L", sine(0.11, 100), "0", 60e-3, 50e-3),
        ("20 kHz, 10 Vpk, лише R", "0", sine(10, 20e3), 5e-3, 3e-3),
        ("Лише від'ємні піки: −8 V імпульси 1 ms", "PULSE(0 -8 2m 10u 10u 1m 10m)", "0", 6e-3, 3.1e-3),
    ]
    for name, sl, sr, tstop, tmeas in tests:
        rows = run(channel(sl, sr, f"{tstop}", "1u"))
        vpk = 8.0 if "−8" in name else (0.11 if "0,11" in name else 10.0)
        expect = vpk * K
        got = max(r[1] for r in rows if r[0] <= tmeas + 1e-3)
        err = 20 * math.log10(got / expect)
        print(f"| {name} | {expect:.3f} V | {got:.3f} V | {err:+.2f} dB |")
        if "CLIP" in name:
            svg(rows, "attack", "Атака: 1 kHz, 10 Vpk → вихід на АЦП")
    # attack of a short burst and release
    rows = run(channel(sine(10, 1e3, 1e-3, 1), "0", "400m", "20u"))
    peak = max(r[1] for r in rows)
    t_pk = next(r[0] for r in rows if r[1] == peak)
    later = next(r[1] for r in rows if r[0] >= t_pk + 0.1)
    print(f"| Один період 1 kHz, 10 Vpk | {10 * K:.3f} V | {peak:.3f} V | "
          f"{20 * math.log10(peak / (10 * K)):+.2f} dB |")
    print(f"\nСпад за 100 ms після піку: {20 * math.log10(later / peak):.1f} dB "
          f"(розрахунок для τ = 100 ms: −8,7 dB).")
    svg(rows, "release", "Один період 1 kHz, 10 Vpk: утримання й спад")
    # oscillation check: high-frequency content on op-amp output while charging
    rows = run(channel(sine(10, 1e3), "0", "3m", "0.1u"))
    seg = [r[2] for r in rows if 0.2e-3 <= r[0] <= 0.3e-3]
    swing = max(seg) - min(seg)
    print(f"Розмах виходу op-amp L+ на фронті заряду (0,2–0,3 ms): {swing:.2f} V.")


if __name__ == "__main__":
    main()
