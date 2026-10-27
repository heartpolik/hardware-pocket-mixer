"""Footprint writer shared by the subprojects' hw/lib/gen_footprints.py (common/README.md).

A project subclasses FP with its output folder (OUT), generator name and 3D model path; the
footprints themselves - with their drawing sources - stay in the project generators.
"""
from pathlib import Path

SILK, FAB, CRT = 0.12, 0.10, 0.05


def fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


class FP:
    OUT = None                       # <subproject>/hw/lib/<lib>.pretty
    GENERATOR = "fpgen"

    def __init__(self, name, descr, tags, attr="through_hole", flags="", model=None):
        """`model`: full path of the 3D model (KiCad variables allowed) or None."""
        self.name, self.descr, self.tags, self.attr, self.flags = name, descr, tags, attr, flags
        self.model_path = model
        self.items = []

    def line(self, x1, y1, x2, y2, layer, w):
        self.items.append(f'\t(fp_line (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)}) '
                          f'(stroke (width {w}) (type solid)) (layer "{layer}"))')

    def rect(self, x1, y1, x2, y2, layer, w):
        self.items.append(f'\t(fp_rect (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)}) '
                          f'(stroke (width {w}) (type solid)) (fill no) (layer "{layer}"))')

    def circle(self, cx, cy, r, layer, w):
        self.items.append(f'\t(fp_circle (center {fmt(cx)} {fmt(cy)}) (end {fmt(cx + r)} {fmt(cy)}) '
                          f'(stroke (width {w}) (type solid)) (fill no) (layer "{layer}"))')

    def text(self, x, y, s, layer, size=1.0):
        self.items.append(f'\t(fp_text user "{s}" (at {fmt(x)} {fmt(y)}) (layer "{layer}") '
                          f'(effects (font (size {size} {size}) (thickness {size * 0.15:.3f}))))')

    def body(self, x1, y1, x2, y2, pad=0.25):
        """Fab outline, silk outline, courtyard around the body."""
        self.rect(x1, y1, x2, y2, "F.Fab", FAB)
        self.rect(x1, y1, x2, y2, "F.SilkS", SILK)
        self.rect(x1 - pad, y1 - pad, x2 + pad, y2 + pad, "F.CrtYd", CRT)

    def tht(self, num, x, y, size, drill, shape="circle"):
        """`size` and `drill` take a number or a (w, h) tuple (oval drill)."""
        d = f"(drill {fmt(drill)})" if not isinstance(drill, tuple) else \
            f"(drill oval {fmt(drill[0])} {fmt(drill[1])})"
        sz = size if isinstance(size, tuple) else (size, size)
        extra = " (roundrect_rratio 0.25)" if shape == "roundrect" else ""
        self.items.append(f'\t(pad "{num}" thru_hole {shape} (at {fmt(x)} {fmt(y)}) '
                          f'(size {fmt(sz[0])} {fmt(sz[1])}) {d} (layers "*.Cu" "*.Mask"){extra})')

    def npth(self, x, y, drill):
        self.items.append(f'\t(pad "" np_thru_hole circle (at {fmt(x)} {fmt(y)}) '
                          f'(size {fmt(drill)} {fmt(drill)}) (drill {fmt(drill)}) (layers "*.Cu" "*.Mask"))')

    def smd(self, num, x, y, w, h, side="F", shape="roundrect", paste=True):
        layers = f'"{side}.Cu" ' + (f'"{side}.Paste" ' if paste else "") + f'"{side}.Mask"'
        extra = " (roundrect_rratio 0.15)" if shape == "roundrect" else ""
        self.items.append(f'\t(pad "{num}" smd {shape} (at {fmt(x)} {fmt(y)}) (size {fmt(w)} {fmt(h)}) '
                          f'(layers {layers}){extra})')

    def write(self, ref_y, val_y):
        s = [f'(footprint "{self.name}"', '\t(version 20241229)', f'\t(generator "{self.GENERATOR}")',
             '\t(layer "F.Cu")', f'\t(descr "{self.descr}")', f'\t(tags "{self.tags}")',
             f'\t(property "Reference" "REF**" (at 0 {fmt(ref_y)} 0) (layer "F.SilkS") '
             '(effects (font (size 1 1) (thickness 0.15))))',
             f'\t(property "Value" "{self.name}" (at 0 {fmt(val_y)} 0) (layer "F.Fab") '
             '(effects (font (size 1 1) (thickness 0.15))))',
             f'\t(attr {"through_hole" if self.attr == "through_hole" else self.attr}{self.flags})']
        s += self.items + ([f'\t(model "{self.model_path}")'] if self.model_path else []) + [")"]
        Path(self.OUT).mkdir(exist_ok=True)
        (Path(self.OUT) / f"{self.name}.kicad_mod").write_text("\n".join(s) + "\n")
        return self.name
