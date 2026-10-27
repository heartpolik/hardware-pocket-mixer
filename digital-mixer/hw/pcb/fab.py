"""Fabrication outputs of the main board (hw/main/main_routed.kicad_pcb), docs/05-fab.md:

  python3 hw/pcb/fab.py            (plain Python 3; calls kicad-cli and KiCad's Python for the iBOM)

Writes hw/fab/:
  gerber/, main-gerber.zip   Gerber (4 copper layers, Protel extensions) + Excellon drill (PTH / NPTH)
  bom.csv                    every part, grouped by value + footprint: part number, LCSC, who mounts it
  jlc/bom-jlc.csv            JLCPCB PCBA BOM - only the parts JLCPCB places (Comment, Designator, ...)
  jlc/cpl-jlc.csv            JLCPCB placement file for the same parts
and docs/ibom/ibom.html - InteractiveHtmlBom (as mixerli documentation/ibom/ibom.html), with the part
number, LCSC code and the mounting column. InteractiveHtmlBom: common/tools/ibom (pip --target, see
common/README.md).

Part numbers / LCSC codes: only those checked on lcsc.com / jlcpcb.com (27.10.2026, links in
docs/05-fab.md); the rest is ПЕРЕВІРИТИ, generic passives are left to JLCPCB's BOM matching.
"""
import csv
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

HW = Path(__file__).resolve().parents[1]
ROOT = HW.parents[1]
FAB = HW / "fab"
PCB = HW / "main" / "main_routed.kicad_pcb"
SCH = HW / "main" / "main.kicad_sch"
IBOM_DIR = HW.parent / "docs" / "ibom"
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
KICAD_PY = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3"
IBOM = ROOT / "common" / "tools" / "ibom"
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Paste", "B.Paste",
          "F.Silkscreen", "B.Silkscreen", "Edge.Cuts"]

# value -> (manufacturer part number, LCSC code)
PARTS = {
    "PCM1865": ("PCM1865DBTR", "C181312"),        # LCSC: not recommended for new designs; alt PCM1865QDBTRQ1 C2667266
    "PCM5102A": ("PCM5102APWR", "C107671"),
    "TPA6132A2": ("TPA6132A2RTER", "C69901"),
    "TPS63802": ("TPS63802DLAR", "ПЕРЕВІРИТИ"),
    "TP4056": ("TP4056-42-ESOP8", "C16581"),
    "LP5907MFX-3.3": ("LP5907MFX-3.3/NOPB", "C80670"),
    "MCP23017-E/SO": ("MCP23017-E/SO", "C47023"),
    "USBLC6-2SC6": ("USBLC6-2SC6 (ST)", "C7519"),
    "AO3401A": ("AO3401A (AOS)", "C15127"),
    "MBR0530": ("MBR0530 (JSCJ)", "C77336"),
    "0.47u XFL4015-471ME": ("XFL4015-471MEC", "C18221164"),
    "GCT USB4110-GF-A": ("USB4110-GF-A", "ПЕРЕВІРИТИ"),
    "LiPo 1S 3000 mAh (з платою захисту)": ("S2B-PH-SM4-TB(LF)(SN)", "C295747"),
}
JACK = ("SJ-43514-SMT-TR", "C4992301 — ПЕРЕВІРИТИ (запас малий)")

# who mounts it: JLCPCB places every SMD part of the bottom side except these (by footprint)
HAND = {
    "Teensy41_SMD": "вручну: модуль Teensy 4.1 (DM12), після перевірки живлення",
    "PTA2043": "вручну: THT, фейдер",
    "LCD_GMT147SPI": "вручну: THT, гребінка дисплея",
    "EC12SY": "вручну: верхній бік, AliExpress (DM26)",
    "TSF-1266": "вручну: верхній бік",
    "Latching": "вручну: верхній бік (DM27)",
    "SJ-43514": "вручну: джек (у LCSC мало) — або JLCPCB, якщо є",
    "MountingHole": "—",
}


def cli(*args):
    r = subprocess.run([KICAD_CLI, *map(str, args)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"kicad-cli {' '.join(map(str, args[:3]))}: {r.stderr.strip()}")
    return r.stdout


def mount(footprint):
    return next((v for k, v in HAND.items() if k in footprint), "JLCPCB")


def part_of(value, footprint):
    if "SJ-43514" in footprint:
        return JACK
    return PARTS.get(value, ("", ""))


def spec(value, footprint):
    fp = footprint.split(":")[-1]
    if fp.startswith("R_"):
        return "товстоплівковий 1 %" + (", 0,5 W" if "2010" in fp else ", 0,25 W" if "1206" in fp else "")
    if fp.startswith("C_"):
        return "X7R, ≥ 10 V (шини ≤ 5 V)" if not value.endswith("n") else "X7R / C0G, ≥ 10 V"
    if fp.startswith("CP_"):
        return "алюмінієвий SMD 4 × 5,4"
    if fp.startswith("LED_"):
        return "світлодіод 0805"
    return ""


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
        mpn, lcsc = part_of(r["Value"], r["Footprint"])
        out.append({"К-сть": int(r["Qty"]), "Номінал": r["Value"], "Footprint": r["Footprint"],
                    "Тип": spec(r["Value"], r["Footprint"]), "Партномер": mpn, "LCSC": lcsc,
                    "Монтаж": mount(r["Footprint"]), "Позначення": r["Refs"]})
    return out


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def jlc(rows):
    """JLCPCB PCBA files for the parts JLCPCB places (all on the bottom side)."""
    jl = [r for r in rows if r["Монтаж"] == "JLCPCB"]
    refs = {ref for r in jl for ref in r["Позначення"].split(",")}
    write_csv(FAB / "jlc" / "bom-jlc.csv",
              [{"Comment": r["Партномер"] or r["Номінал"], "Designator": r["Позначення"],
                "Footprint": r["Footprint"].split(":")[-1],
                "LCSC Part #": r["LCSC"] if r["LCSC"].startswith("C") else ""} for r in jl])
    with tempfile.TemporaryDirectory() as tmp:
        pos = Path(tmp) / "pos.csv"
        cli("pcb", "export", "pos", "-o", pos, "--format", "csv", "--units", "mm", "--side", "both", PCB)
        cpl = []
        for r in csv.DictReader(pos.open(encoding="utf-8")):
            if r["Ref"] in refs:
                cpl.append({"Designator": r["Ref"], "Mid X": f'{float(r["PosX"]):.4f}mm',
                            "Mid Y": f'{float(r["PosY"]):.4f}mm',
                            "Layer": "Bottom" if r["Side"] == "bottom" else "Top",
                            "Rotation": f'{float(r["Rot"]) % 360:.1f}'})
    write_csv(FAB / "jlc" / "cpl-jlc.csv", cpl)
    return jl, cpl


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
            "        for k in ('Партномер', 'LCSC', 'Монтаж'):\n"
            "            fp.SetField(k, r[k])\n"
            "b.Save(sys.argv[1])\n")
        import json
        data = Path(tmp) / "info.json"
        data.write_text(json.dumps(info, ensure_ascii=False))
        env = dict(os.environ, PYTHONPATH=str(IBOM), INTERACTIVE_HTML_BOM_NO_DISPLAY="1")
        subprocess.run([KICAD_PY, script, board, data], check=True, capture_output=True, env=env)
        IBOM_DIR.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([KICAD_PY, IBOM / "InteractiveHtmlBom" / "generate_interactive_bom.py", board,
                            "--no-browser", "--dest-dir", IBOM_DIR, "--name-format", "ibom",
                            "--layer-view", "FB", "--bom-view", "left-right", "--highlight-pin1", "all",
                            "--checkboxes", "Закуплено,Встановлено", "--show-fields",
                            "Value,Footprint,Партномер,LCSC,Монтаж", "--group-fields", "Value,Footprint",
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
    jl, cpl = jlc(rows)
    print(f"jlc: {len(jl)} BOM lines, {len(cpl)} placements")
    print("ibom:", ibom(rows))


if __name__ == "__main__":
    main()
