"""Mounting holes (D57) on both routed boards: outlines, courtyards of the mechanical parts, the
battery zone and the M2 holes. Writes docs/mech/mounting.svg.

Run with KiCad's Python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      docs/mech/mounting.py
"""
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hw" / "pcb"))
import build_pcb as bp  # noqa: E402

SCALE = 4.0
GAP = 20.0                             # between the two views, mm
BATT = (2.0, bp.BATT_Y0, bp.W - 2.0, 131.0)   # battery zone minus the front-corner holes (D57)
NOTE = {"H1": "стійка між платами 11 мм + до дна", "H2": "стійка до верхньої панелі",
        "H3": "до дна корпусу", "H4": "до дна корпусу"}


def mmv(v):
    return pcbnew.ToMM(v)


def view(board, ox, title, batt):
    out = [f'<text x="{(ox + bp.W / 2) * SCALE:.0f}" y="{8 * SCALE:.0f}" class="h">{title}</text>']
    labels = []
    oy = 14.0
    edge = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(edge, False)
    for i in range(edge.OutlineCount()):
        o = edge.Outline(i)
        pts = " ".join(f"{(mmv(o.CPoint(k).x) - bp.OX + ox) * SCALE:.1f},{(mmv(o.CPoint(k).y) - bp.OY + oy) * SCALE:.1f}"
                       for k in range(o.PointCount()))
        out.append(f'<polygon points="{pts}" class="board"/>')
    if batt:
        x0, y0, x1, y1 = batt
        out.append(f'<rect x="{(x0 + ox) * SCALE:.1f}" y="{(y0 + oy) * SCALE:.1f}" width="{(x1 - x0) * SCALE:.1f}" '
                   f'height="{(y1 - y0) * SCALE:.1f}" class="batt"/>')
        labels.append(f'<text x="{(ox + bp.W / 2) * SCALE:.0f}" y="{(y0 + oy + 52) * SCALE:.0f}" class="n" '
                      f'text-anchor="middle">зона 2S LiPo знизу: {x1 - x0:.0f} × {y1 - y0:.0f} мм</text>')
    for f in board.GetFootprints():
        if f.GetFPIDAsString() == bp.MOUNT_FP:
            continue
        if f.GetAttributes() & pcbnew.FP_SMD:
            continue
        cy = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
        if not cy.OutlineCount():
            continue
        bb = cy.BBox()
        out.append(f'<rect x="{(mmv(bb.GetLeft()) - bp.OX + ox) * SCALE:.1f}" y="{(mmv(bb.GetTop()) - bp.OY + oy) * SCALE:.1f}" '
                   f'width="{mmv(bb.GetWidth()) * SCALE:.1f}" height="{mmv(bb.GetHeight()) * SCALE:.1f}" class="part"/>')
    for f in board.GetFootprints():
        if f.GetFPIDAsString() != bp.MOUNT_FP:
            continue
        x, y = mmv(f.GetPosition().x) - bp.OX + ox, mmv(f.GetPosition().y) - bp.OY + oy
        ref = f.GetReference()
        out.append(f'<circle cx="{x * SCALE:.1f}" cy="{y * SCALE:.1f}" r="{bp.MOUNT_R * SCALE:.1f}" class="keep"/>')
        out.append(f'<circle cx="{x * SCALE:.1f}" cy="{y * SCALE:.1f}" r="{1.1 * SCALE:.1f}" class="hole"/>')
        dx = 4 if x - ox < bp.W / 2 else -4
        anchor = "start" if dx > 0 else "end"
        labels.append(f'<text x="{(x + dx) * SCALE:.1f}" y="{(y + 1.2) * SCALE:.1f}" class="r" text-anchor="{anchor}">'
                      f'{ref} ({x - ox:.1f}; {y - oy:.1f})</text>')
        labels.append(f'<text x="{(x + dx) * SCALE:.1f}" y="{(y + 5.2) * SCALE:.1f}" class="n" text-anchor="{anchor}">'
                      f'{NOTE[ref]}</text>')
    return out + labels


def main():
    boards = {b: pcbnew.LoadBoard(str(ROOT / "hw" / b / f"{b}_routed.kicad_pcb")) for b in ("analog", "digital")}
    body = view(boards["analog"], 0.0, "Аналогова плата, вид зверху", BATT)
    body += view(boards["digital"], bp.W + GAP, "Цифрова плата, вид зверху (над аналоговою)", None)
    w, h = (2 * bp.W + GAP) * SCALE, (bp.D + 18) * SCALE
    style = """<style>
.board{fill:#f4f8f0;stroke:#333;stroke-width:1.5}.part{fill:#cfd8e6;stroke:#7a8aa6;stroke-width:0.8}
.batt{fill:#ffe9b0;fill-opacity:.55;stroke:#c90;stroke-dasharray:6 4}.keep{fill:#ffb347;fill-opacity:.5;stroke:#d60}
.hole{fill:#fff;stroke:#333;stroke-width:1.2}text{font-family:sans-serif;fill:#222}.h{font-size:18px;text-anchor:middle;font-weight:bold}
.r,.n{paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}.r{font-size:15px;font-weight:bold}.n{font-size:13px}
</style>"""
    out = ROOT / "docs" / "mech" / "mounting.svg"
    out.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">'
                   f'{style}<rect width="100%" height="100%" fill="#fff"/>' + "".join(body) + "</svg>\n")
    print(out)


if __name__ == "__main__":
    main()
