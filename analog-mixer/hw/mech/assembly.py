"""Whole-device 3D model for the enclosure design: both routed boards with all parts, stacked
as in docs/05-mechanics.md, in one STEP file (hw/mech/diy-mixer-assembly.step).

Run with CadQuery (see hw/lib/gen_3d.py) after the 3D models are generated:
  .venv-cq/bin/python hw/mech/assembly.py

Frame: KiCad page coordinates of the boards (x right, y = -page y), z = 0 at the underside of
the analog board. Both boards share the page frame (the interboard connector is aligned in XY by
hw/pcb/build_pcb.py); the digital board sits BOARD_GAP above the analog one.
"""
import subprocess
from pathlib import Path

import cadquery as cq
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool

HW = Path(__file__).resolve().parents[1]
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PCB_T = 1.6                 # board thickness (KiCad default stack-up)
BOARD_GAP = 11.0            # analog top -> digital underside: socket 8.5 + header plastic 2.5
OUT = HW / "mech" / "diy-mixer-assembly.step"


def export(board):
    out = HW / "mech" / f"{board}.step"
    subprocess.run([KICAD_CLI, "pcb", "export", "step", "-f", "--user-origin", "0x0mm",
                    "-o", str(out), str(HW / board / f"{board}_routed.kicad_pcb")],
                   check=True, capture_output=True)
    return out


def main():
    # Both boards share part names (CUI_SJ-..., R_0805...), which cq.Assembly refuses: merge them
    # at the XCAF level, as two located components of one top assembly (colours are kept).
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    tops = []
    for board in ("analog", "digital"):
        r = STEPCAFControl_Reader()
        r.SetColorMode(True)
        r.SetNameMode(True)
        if r.ReadFile(str(export(board))) != IFSelect_RetDone or not r.Transfer(doc):
            raise RuntimeError(f"STEP import failed: {board}")
        seq = TDF_LabelSequence()
        tool.GetFreeShapes(seq)
        tops.append(seq.Value(seq.Length()))
    top = tool.NewShape()
    for label, z in zip(tops, (0.0, PCB_T + BOARD_GAP)):
        tool.AddComponent(top, label, cq.Location((0, 0, z)).wrapped)
    tool.UpdateAssemblies()
    w = STEPCAFControl_Writer()
    w.SetColorMode(True)
    w.SetNameMode(True)
    w.Transfer(doc, STEPControl_AsIs)
    w.Write(str(OUT))
    bb = cq.importers.importStep(str(OUT)).val().BoundingBox()
    print(f"{OUT}: x {bb.xmin:.1f}..{bb.xmax:.1f}, y {bb.ymin:.1f}..{bb.ymax:.1f}, "
          f"z {bb.zmin:.1f}..{bb.zmax:.1f} mm")


if __name__ == "__main__":
    main()
