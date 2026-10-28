"""Fabrication outputs of the main board (hw/main/main_routed.kicad_pcb) for NextPCB, docs/05-fab.md:

  python3 hw/pcb/fab.py            (plain Python 3; calls kicad-cli and KiCad's Python for the iBOM)

Writes hw/fab/:
  gerber/, main-gerber.zip   Gerber (4 copper layers, Protel extensions) + Excellon drill (PTH / NPTH)
  bom.csv                    every part, grouped by value + footprint: manufacturer, part number, who mounts it
  nextpcb/bom-nextpcb.csv    NextPCB PCBA BOM: Designator, Quantity, Manufacturer, Manufacturer Part
                             Number, Description, Package, Procurement Type (DNP = mounted by hand), Customer Note
  nextpcb/centroid-nextpcb.csv (+ .zip)  pick and place of the parts NextPCB places (mm, Top / Bottom)
  nextpcb/assembly-top.pdf, assembly-bottom.pdf   assembly drawings (fab + silk + outline)
and docs/ibom/ibom.html - InteractiveHtmlBom (as mixerli documentation/ibom/ibom.html). InteractiveHtmlBom:
common/tools/ibom (pip --target, see common/README.md).

Part numbers: only those found on distributor pages (27.10.2026, links in docs/05-fab.md); the rest is
ПЕРЕВІРИТИ with the full specification in Customer Note.
"""
import csv
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

HW = Path(__file__).resolve().parents[1]
ROOT = HW.parents[1]
FAB = HW / "fab"
OUT = FAB / "nextpcb"
PCB = HW / "main" / "main_routed.kicad_pcb"
SCH = HW / "main" / "main.kicad_sch"
IBOM_DIR = HW.parent / "docs" / "ibom"
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
KICAD_PY = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3"
IBOM = ROOT / "common" / "tools" / "ibom"
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Paste", "B.Paste",
          "F.Silkscreen", "B.Silkscreen", "Edge.Cuts"]

# value -> (manufacturer, part number, description)
PARTS = {
    "PCM1865": ("Texas Instruments", "PCM1865DBTR", "ADC 4ch 24 bit TDM, TSSOP-30 (LCSC: NRND; alt. PCM1865QDBTRQ1)"),
    "PCM5102A": ("Texas Instruments", "PCM5102APWR", "DAC stereo 32 bit I2S, TSSOP-20"),
    "TPA6132A2": ("Texas Instruments", "TPA6132A2RTER", "headphone amp DirectPath, WQFN-16 3x3"),
    "TPS63802": ("Texas Instruments", "TPS63802DLAR", "buck-boost 2 A, VSON-HR-10 2x3"),
    "TP4056": ("TOP POWER ASIC", "TP4056-42-ESOP8", "Li-ion charger 1 A, ESOP-8"),
    "LP5907MFX-3.3": ("Texas Instruments", "LP5907MFX-3.3/NOPB", "LDO 3.3 V 250 mA low noise, SOT-23-5"),
    "MCP23017-E/SO": ("Microchip", "MCP23017-E/SO", "I2C 16-bit I/O expander, SOIC-28W"),
    "USBLC6-2SC6": ("STMicroelectronics", "USBLC6-2SC6", "USB ESD protection, SOT-23-6"),
    "AO3401A": ("Alpha & Omega", "AO3401A", "P-MOSFET 30 V 4 A, SOT-23"),
    "MBR0530": ("JSCJ", "MBR0530", "Schottky 30 V 0.5 A, SOD-123"),
    "0.47u XFL4015-471ME": ("Coilcraft", "XFL4015-471MEC", "inductor 0.47 uH 6.6 A, 4x4x1.5"),
    "GCT USB4110-GF-A": ("GCT", "USB4110-GF-A", "USB-C 2.0 receptacle, SMT"),
    "LiPo 1S 3000 mAh (з платою захисту)": ("JST", "S2B-PH-SM4-TB(LF)(SN)", "PH 2-pin side entry, SMT"),
}
JACK = ("Same Sky (CUI)", "SJ-43514-SMT-TR", "3.5 mm TRRS jack, SMT")
# (value, footprint suffix) -> (manufacturer, part number, description)
PASSIVES = {
    ("10u", "C_1206"): ("Samsung", "CL31B106KAHNNNE", "MLCC 10 uF 25 V X7R 1206"),
    ("100n", "C_0805"): ("Samsung", "CL21B104KBCNNNC", "MLCC 100 nF 50 V X7R 0805"),
    ("22u", "C_1206"): ("Samsung", "CL31A226KAHNNNE", "MLCC 22 uF 25 V X5R 1206"),
    ("1u", "C_0805"): ("Samsung", "CL21B105KAFNNNE", "MLCC 1 uF 25 V X7R 0805"),
    ("2.2u", "C_0805"): ("Samsung", "CL21B225KAFNNNE", "MLCC 2.2 uF 25 V X7R 0805"),
    ("2.2n", "C_0805"): ("Samsung", "CL21C222JBFNNNE", "MLCC 2.2 nF 50 V C0G 0805"),
    ("10u 16V", "CP_Elec_4x5.4"): ("Panasonic", "EEE-1CA100SR", "Al electrolytic 10 uF 16 V 4x5.4 SMD"),
    ("red", "LED_0805"): ("Lite-On", "LTST-C171KRKT", "LED red 0805"),
    ("green", "LED_0805"): ("Lite-On", "LTST-C171KGKT", "LED green 0805"),
    ("4.7k", "R_0805"): ("Yageo", "RC0805FR-074K7L", "resistor 4.7 k 1% 0805"),
    ("33", "R_0805"): ("Yageo", "RC0805FR-0733RL", "resistor 33 R 1% 0805"),
    ("10k", "R_0805"): ("Yageo", "RC0805FR-0710KL", "resistor 10 k 1% 0805"),
    ("100k", "R_0805"): ("Yageo", "RC0805FR-07100KL", "resistor 100 k 1% 0805"),
    ("5.1k", "R_0805"): ("Yageo", "RC0805FR-075K1L", "resistor 5.1 k 1% 0805"),
    ("2.4k", "R_0805"): ("Yageo", "RC0805FR-072K4L", "resistor 2.4 k 1% 0805"),
    ("1k", "R_0805"): ("Yageo", "RC0805FR-071KL", "resistor 1 k 1% 0805"),
    ("665k", "R_0805"): ("Yageo", "RC0805FR-07665KL", "resistor 665 k 1% 0805 - ПЕРЕВІРИТИ part number"),
    ("91k", "R_0805"): ("Yageo", "RC0805FR-0791KL", "resistor 91 k 1% 0805"),
    ("470", "R_0805"): ("Yageo", "RC0805FR-07470RL", "resistor 470 R 1% 0805"),
    ("33 0.5W", "R_2010"): ("Yageo", "RC2010FK-0733RL", "resistor 33 R 1% 0.75 W 2010"),
    ("10 0.25W", "R_1206"): ("Yageo", "RC1206FR-0710RL", "resistor 10 R 1% 0.5 W 1206"),
}
# who mounts it: NextPCB places every SMD part of the bottom side; these (by footprint) by hand
HAND = {
    "Teensy41_THT": "вручну: Teensy 4.1 на гребінках 2 × 24 (DM35), PSRAM на ньому — до встановлення; після перевірки живлення",
    "PTA2043": "вручну: THT, фейдер",
    "LCD_GMT147SPI": "вручну: THT, гребінка дисплея",
    "EC12SY": "вручну: верхній бік, AliExpress (DM26)",
    "TSF-1266": "вручну: верхній бік, AliExpress",
    "Latching": "вручну: верхній бік, AliExpress (DM27)",
    "MountingHole": "—",
}


def cli(*args):
    r = subprocess.run([KICAD_CLI, *map(str, args)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"kicad-cli {' '.join(map(str, args[:3]))}: {r.stderr.strip()}")
    return r.stdout


def mount(footprint):
    return next((v for k, v in HAND.items() if k in footprint), "NextPCB")


def part_of(value, footprint):
    fp = footprint.split(":")[-1]
    if "SJ-43514" in fp:
        return JACK
    if value in PARTS:
        return PARTS[value]
    return next((v for (val, f), v in PASSIVES.items() if val == value and fp.startswith(f)), ("", "", ""))


def gerbers():
    out = FAB / "gerber"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    cli("pcb", "export", "gerbers", "-o", out, "-l", ",".join(LAYERS), "--subtract-soldermask", PCB)
    cli("pcb", "export", "drill", "-o", out, "--excellon-units", "mm", "--excellon-separate-th", PCB)
    for p in out.iterdir():                  # main_routed-F_Cu.gtl -> main-F_Cu.gtl
        if p.suffix == ".gbrjob":
            p.write_text(p.read_text(encoding="utf-8").replace(f'"{PCB.stem}', '"main'), encoding="utf-8")
        p.rename(out / p.name.replace(PCB.stem, "main", 1))
    files = sorted(p for p in out.iterdir() if p.is_file())
    with zipfile.ZipFile(FAB / "main-gerber.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.name)
    return files


def bom_rows():
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "bom.csv"
        cli("sch", "export", "bom", "-o", raw, "--fields", "Reference,Value,Footprint,${QUANTITY}",
            "--labels", "Refs,Value,Footprint,Qty", "--group-by", "Value,Footprint",
            "--ref-range-delimiter", "", "--exclude-dnp", SCH)
        rows = [r for r in csv.DictReader(raw.open(encoding="utf-8")) if r["Footprint"]]
    out = []
    for r in rows:
        mfr, mpn, desc = part_of(r["Value"], r["Footprint"])
        out.append({"К-сть": int(r["Qty"]), "Номінал": r["Value"], "Footprint": r["Footprint"],
                    "Виробник": mfr, "Партномер": mpn, "Опис": desc,
                    "Монтаж": mount(r["Footprint"]), "Позначення": r["Refs"]})
    return out


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def nextpcb(rows):
    """NextPCB PCBA files: BOM (hand-mounted lines as DNP), centroid of the parts NextPCB places,
    assembly drawings."""
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    bom = []
    for r in rows:
        if r["Монтаж"] == "—":
            continue
        hand = r["Монтаж"] != "NextPCB"
        bom.append({"Designator": r["Позначення"], "Quantity": r["К-сть"], "Manufacturer": r["Виробник"],
                    "Manufacturer Part Number": r["Партномер"], "Description": r["Опис"] or r["Номінал"],
                    "Package": r["Footprint"].split(":")[-1], "Procurement Type": "DNP" if hand else "",
                    "Customer Note": r["Монтаж"] if hand else
                    ("part number to be confirmed, any maker with this description" if "ПЕРЕВІРИТИ" in r["Опис"]
                     else "")})
    write_csv(OUT / "bom-nextpcb.csv", bom)
    refs = {ref for r in rows if r["Монтаж"] == "NextPCB" for ref in r["Позначення"].split(",")}
    with tempfile.TemporaryDirectory() as tmp:
        pos = Path(tmp) / "pos.csv"
        cli("pcb", "export", "pos", "-o", pos, "--format", "csv", "--units", "mm", "--side", "both",
            "--smd-only", PCB)
        cen = []
        for r in csv.DictReader(pos.open(encoding="utf-8")):
            if r["Ref"] in refs:
                cen.append({"Designator": r["Ref"], "Mid X(mm)": f'{float(r["PosX"]):.4f}',
                            "Mid Y(mm)": f'{float(r["PosY"]):.4f}', "Rotation": f'{float(r["Rot"]) % 360:.1f}',
                            "Layer": "Bottom" if r["Side"] == "bottom" else "Top"})
    write_csv(OUT / "centroid-nextpcb.csv", cen)
    with zipfile.ZipFile(OUT / "centroid-nextpcb.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(OUT / "centroid-nextpcb.csv", "centroid-nextpcb.csv")
    cli("pcb", "export", "pdf", "-o", OUT / "assembly-top.pdf", "-l", "F.Fab,F.Silkscreen,Edge.Cuts",
        "--include-border-title", PCB)
    cli("pcb", "export", "pdf", "-o", OUT / "assembly-bottom.pdf", "-l", "B.Fab,B.Silkscreen,Edge.Cuts",
        "--mirror", "--include-border-title", PCB)
    missing = sorted(ref for ref in refs if ref not in {c["Designator"] for c in cen})
    return bom, cen, missing


def ibom(rows):
    """InteractiveHtmlBom on a copy of the board whose footprints carry the BOM columns as fields."""
    info = {ref: r for r in rows for ref in r["Позначення"].split(",")}
    with tempfile.TemporaryDirectory() as tmp:
        board = Path(tmp) / "main.kicad_pcb"
        shutil.copy(PCB, board)
        for ext in (".kicad_pro", ".kicad_dru"):
            shutil.copy(PCB.with_suffix(ext), board.with_suffix(ext))
        script = Path(tmp) / "fields.py"
        script.write_text(
            "import json, sys, pcbnew\n"
            "info = json.load(open(sys.argv[2]))\n"
            "b = pcbnew.LoadBoard(sys.argv[1])\n"
            "for fp in b.GetFootprints():\n"
            "    r = info.get(fp.GetReference())\n"
            "    if r:\n"
            "        for k in ('Виробник', 'Партномер', 'Монтаж'):\n"
            "            fp.SetField(k, r[k])\n"
            "b.Save(sys.argv[1])\n")
        data = Path(tmp) / "info.json"
        data.write_text(json.dumps(info, ensure_ascii=False))
        env = dict(os.environ, PYTHONPATH=str(IBOM), INTERACTIVE_HTML_BOM_NO_DISPLAY="1")
        subprocess.run([KICAD_PY, script, board, data], check=True, capture_output=True, env=env)
        IBOM_DIR.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([KICAD_PY, IBOM / "InteractiveHtmlBom" / "generate_interactive_bom.py", board,
                            "--no-browser", "--dest-dir", IBOM_DIR, "--name-format", "ibom",
                            "--layer-view", "FB", "--bom-view", "left-right", "--highlight-pin1", "all",
                            "--checkboxes", "Закуплено,Встановлено", "--show-fields",
                            "Value,Footprint,Виробник,Партномер,Монтаж", "--group-fields", "Value,Footprint",
                            "--blacklist", "H*", "--include-tracks", "--include-nets"],
                           capture_output=True, text=True, env=env)
        if r.returncode:
            raise RuntimeError(r.stderr[-2000:])
    return IBOM_DIR / "ibom.html"


def main():
    FAB.mkdir(exist_ok=True)
    files = gerbers()
    print(f"gerber: {len(files)} files -> hw/fab/main-gerber.zip")
    rows = bom_rows()
    write_csv(FAB / "bom.csv", rows)
    print(f"bom.csv: {len(rows)} lines, {sum(r['К-сть'] for r in rows)} parts")
    bom, cen, missing = nextpcb(rows)
    print(f"nextpcb: {len(bom)} BOM lines ({sum(1 for b in bom if b['Procurement Type'] == 'DNP')} DNP), "
          f"{len(cen)} placements, not in centroid: {missing}")
    print("ibom:", ibom(rows))


if __name__ == "__main__":
    main()
