"""One-order panel: analog + digital board on one 4-layer panel, separated by mouse bites.

Run with KiCad's Python (KiKit 1.8.1 installed with `pip install --user kikit==1.8.1`):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      hw/pcb/panel.py [--analog hw/analog/analog_routed.kicad_pcb] [--digital hw/digital/digital_routed.kicad_pcb]

Layout (docs/14-kicad.md): analog board at the bottom; the digital board rotated 180 deg above it,
so its straight 129 mm rear edge lies on the rear edge of the analog board. The shared edge is one
straight line across the whole panel -> a single V-cut; copper keeps 0.5 mm off it. The design boards stay separate projects;
the panel is a build product and is regenerated, never edited.
"""
import argparse
import json
import shutil
from pathlib import Path

import pcbnew
from kikit import panelize
from kikit.common import fromMm as mm, fromDegrees
from kikit.defs import Layer

HW = Path(__file__).resolve().parents[1]
GAP = 0.0                            # boards share the V-cut line
VCUT_CLEAR = 1.0                     # copper-free band around the V-cut (0.5 mm each side)


def bbox(path):
    b = pcbnew.LoadBoard(str(path))
    bb = b.GetBoardEdgesBoundingBox()
    return pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())


def fix_project(out):
    """Net classes and rules of the panel = those of the board projects (hw/sch/kisch.py), with the
    net-class patterns rewritten for the renamed nets (AN-..., DIG-...)."""
    src = json.loads((HW / "analog" / "analog.kicad_pro").read_text())
    pro_path = out.with_suffix(".kicad_pro")
    pro = json.loads(pro_path.read_text())
    ns = src["net_settings"]
    pats = []
    for p in ns.get("netclass_patterns", []):
        name = p["pattern"].lstrip("/")
        pats += [{"netclass": p["netclass"], "pattern": f"AN-{name}"},
                 {"netclass": p["netclass"], "pattern": f"DIG-{name}"}]
    pro["net_settings"]["classes"] = ns["classes"]
    pro["net_settings"]["netclass_patterns"] = pats
    pro["board"]["design_settings"]["rules"].update(src["board"]["design_settings"]["rules"])
    pro_path.write_text(json.dumps(pro, indent=2) + "\n")
    shutil.copy(HW / "analog" / "analog.kicad_dru", out.with_suffix(".kicad_dru"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analog", default=str(HW / "analog" / "analog_routed.kicad_pcb"))
    ap.add_argument("--digital", default=str(HW / "digital" / "digital_routed.kicad_pcb"))
    ap.add_argument("--out", default=str(HW / "panel" / "panel.kicad_pcb"))
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(exist_ok=True)

    aw, ah = bbox(a.analog)
    dw, dh = bbox(a.digital)
    panel = panelize.Panel(str(out))
    src = pcbnew.LoadBoard(a.analog)
    panel.inheritDesignSettings(src)
    panel.inheritProperties(src)
    panel.inheritTitleBlock(src)
    panel.inheritCopperLayers(src)
    panel.inheritLayerNames(src)
    panel.inheritEnabledLayers(src)

    # refs and nets of the two boards must not collide in one file
    def refs(prefix):
        return lambda n, ref: f"{prefix}{ref}"

    def nets(prefix):
        return lambda n, net: f"{prefix}-{net.lstrip('/')}" if net else net

    # digital: rotated 180 deg about its centre, rear edge (y min) now at the bottom
    panel.appendBoard(a.digital, pcbnew.VECTOR2I(mm(dw / 2), mm(dh / 2)),
                      origin=panelize.Origin.Center, rotationAngle=fromDegrees(180), tolerance=mm(1),
                      refRenamer=refs("D_"), netRenamer=nets("DIG"), bakeRef=True)
    # the outline line width makes the bounding box 0.1 mm larger than the substrate: butt the
    # analog board against the real substrate edge of the digital one
    dx0, _, _, dy1 = panel.substrates[-1].bounds()
    panel.appendBoard(a.analog, pcbnew.VECTOR2I(int(dx0), int(dy1) + mm(GAP)),
                      origin=panelize.Origin.TopLeft, tolerance=mm(1),
                      refRenamer=refs(""), netRenamer=nets("AN"))

    # KiKit refuses to merge project rules of two boards; both come from hw/sch/kisch.py
    # project_files() and are identical, so the analog project is the single source.
    panel.sourcePaths = {p for p in panel.sourcePaths if "analog" in str(p)}
    panel.vCutSettings.clearance = mm(VCUT_CLEAR)
    # JLCPCB reads V-cuts only from the outline layer (help answer 871). On Edge.Cuts inside KiCad the
    # line breaks the outline (zones stop filling), so it lives on User.1 and fab.py merges User.1 into
    # the outline Gerber.
    panel.vCutSettings.layer = Layer.User_1
    panel.vCutSettings.endProlongation = panel.vCutSettings.textProlongation = 0   # edge to edge, no stubs
    panel.addVCutH(int(dy1) + mm(GAP / 2))
    geoms = getattr(panel.boardSubstrate.substrates, "geoms", [panel.boardSubstrate.substrates])
    if len(geoms) != 1:
        raise RuntimeError(f"panel substrate is not one piece ({len(geoms)}): boards do not touch")
    panel.save(reconstructArcs=False, refillAllZones=True)
    fix_project(out)
    # give the V-cut layer a visible name in KiCad's layer list
    out.write_text(out.read_text().replace('(39 "User.1" user)', '(39 "User.1" user "V-Cut")', 1))
    print("panel:", out, f"{max(aw, dw):.1f} x {ah + GAP + dh:.1f} mm")


if __name__ == "__main__":
    main()
