"""Fabrication outputs: Gerber + Excellon zip per board and for the panel, and the BOM.

  python3 hw/pcb/fab.py            (plain Python 3; calls kicad-cli)

Writes hw/fab/:
  <name>/            Gerber (Protel extensions) + drill (mm, PTH and NPTH separate)
  <name>-gerber.zip  the same, ready for upload (JLCPCB)
  bom-<board>.csv    grouped by value + footprint, from the schematic
  bom.csv            both boards in one table (one order of parts)
for name in analog, digital, panel. The panel's V-cut line (User.1, hw/pcb/panel.py) is merged into
its outline Gerber, because JLCPCB reads V-cuts only from the outline layer.
"""
import csv
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

HW = Path(__file__).resolve().parents[1]
FAB = HW / "fab"
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
BOARDS = {"analog": HW / "analog" / "analog_routed.kicad_pcb",
          "digital": HW / "digital" / "digital_routed.kicad_pcb",
          "panel": HW / "panel" / "panel.kicad_pcb"}
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Paste", "B.Paste",
          "F.Silkscreen", "B.Silkscreen", "Edge.Cuts"]
VCUT_LAYER = "User.1"

# Ceramic capacitors without a voltage in the value: dielectric from docs/10-passives.md p. 1,
# voltage = highest rail on the board with margin for X7R DC bias (recommendation, not from a datasheet)
CERAMIC_V = {"analog": "25 V (шини ±12 V)", "digital": "10 V (шини ≤ 5 V)"}
UEP = {"10u BP": "Nichicon UEP1E100MDD, 25 V (D44)", "47u BP": "Nichicon UEP1E470MED, 25 V (10-passives)"}


def cli(*args):
    r = subprocess.run([KICAD_CLI, *map(str, args)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"kicad-cli {' '.join(map(str, args[:3]))}: {r.stderr.strip()}")


def gerbers(name, pcb):
    out = FAB / name
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    cli("pcb", "export", "gerbers", "-o", out, "-l", ",".join(LAYERS), "--subtract-soldermask", pcb)
    if name == "panel":
        with tempfile.TemporaryDirectory() as tmp:
            cli("pcb", "export", "gerbers", "-o", tmp, "-l", "Edge.Cuts", "--cl", VCUT_LAYER, pcb)
            edge = next(Path(tmp).glob("*.gm1"))
            shutil.copy(edge, out / edge.name)
    # no drill maps: they carry a second full outline (without the V-cut), and JLCPCB's viewer may take
    # it for the board outline; JLCPCB wants a single outline layer
    cli("pcb", "export", "drill", "-o", out, "--excellon-units", "mm", "--excellon-separate-th", pcb)
    for p in out.iterdir():                  # analog_routed-F_Cu.gtl -> analog-F_Cu.gtl
        if p.suffix == ".gbrjob":
            p.write_text(p.read_text(encoding="utf-8").replace(f'"{pcb.stem}', f'"{name}'), encoding="utf-8")
        p.rename(out / p.name.replace(pcb.stem, name, 1))
    files = sorted(p for p in out.iterdir() if p.is_file())
    with zipfile.ZipFile(FAB / f"{name}-gerber.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.name)
    return files


def spec(board, value, footprint):
    ref_fp = footprint.split(":")[-1]
    if value in UEP:
        return UEP[value]
    if ref_fp.startswith("R_"):
        return "товстоплівковий 1 %, E96"
    if ref_fp.startswith("C_"):
        if "C0G" in value:
            return "C0G"
        return "X7R" + ("" if "V" in value else f", ≥ {CERAMIC_V[board]}")
    return ""


def bom(board):
    sch = HW / board / f"{board}.kicad_sch"
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "bom.csv"
        cli("sch", "export", "bom", "-o", raw, "--fields", "Reference,Value,Footprint,${QUANTITY}",
            "--labels", "Refs,Value,Footprint,Qty", "--group-by", "Value,Footprint",
            "--ref-range-delimiter", "", "--exclude-dnp", sch)
        rows = list(csv.DictReader(raw.open(encoding="utf-8")))
    out = []
    for r in rows:
        out.append({"Плата": board, "К-сть": int(r["Qty"]), "Номінал": r["Value"],
                    "Footprint": r["Footprint"], "Тип": spec(board, r["Value"], r["Footprint"]),
                    "Позначення": r["Refs"]})
    return out


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    FAB.mkdir(exist_ok=True)
    for name, pcb in BOARDS.items():
        files = gerbers(name, pcb)
        print(f"{name}: {len(files)} files -> hw/fab/{name}-gerber.zip")
    total = []
    for board in ("analog", "digital"):
        rows = bom(board)
        write_csv(FAB / f"bom-{board}.csv", rows)
        total += rows
        print(f"bom-{board}.csv: {len(rows)} lines, {sum(r['К-сть'] for r in rows)} parts")
    write_csv(FAB / "bom.csv", total)


if __name__ == "__main__":
    main()
