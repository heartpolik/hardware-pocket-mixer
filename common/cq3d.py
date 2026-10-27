"""CadQuery helpers for the 3D models of the project footprints (common/README.md), used by the
subprojects' hw/lib/gen_3d.py.

Run those with CadQuery (not KiCad's Python), from the repository root:
  python3.12 -m venv .venv-cq && .venv-cq/bin/pip install cadquery==2.6.1

Every model sits in its footprint's frame: KiCad footprint (x, y) with y down -> model (x, -y);
z = 0 is the top of the PCB.
"""
from pathlib import Path

import cadquery as cq

METAL = cq.Color(0.72, 0.72, 0.74)
DARK = cq.Color(0.12, 0.12, 0.13)
BLACK = cq.Color(0.05, 0.05, 0.05)
PIN = cq.Color(0.85, 0.80, 0.55)
WHITE = cq.Color(0.92, 0.92, 0.90)
PCB_BLUE = cq.Color(0.05, 0.20, 0.45)
PCB_BLACK = cq.Color(0.08, 0.08, 0.09)
GLASS = cq.Color(0.10, 0.12, 0.16)
RED = cq.Color(0.80, 0.10, 0.10)
BLUE = cq.Color(0.15, 0.30, 0.70)


def box(x0, y0, x1, y1, z0, z1):
    """Axis-aligned box from footprint coordinates (y down)."""
    xa, xb = sorted((x0, x1))
    ya, yb = sorted((-y0, -y1))
    return cq.Workplane("XY").box(xb - xa, yb - ya, z1 - z0, centered=False).translate((xa, ya, z0))


def cyl(x, y, d, z0, z1):
    """Vertical cylinder at footprint (x, y)."""
    return cq.Workplane("XY").circle(d / 2).extrude(z1 - z0).translate((x, -y, z0))


def hcyl(x0, x1, y, z, d):
    """Cylinder along +X at footprint y, axis height z."""
    return cq.Workplane("YZ").circle(d / 2).extrude(x1 - x0).translate((x0, -y, z))


def pin(x, y, w=0.6, t=0.3, z0=-3.5, z1=0.5):
    return box(x - w / 2, y - t / 2, x + w / 2, y + t / 2, z0, z1)


def save(out, name, parts):
    """[(shape, color)] -> <out>/<name>.step"""
    a = cq.Assembly(name=name)
    for i, (shape, color) in enumerate(parts):
        a.add(shape, name=f"p{i}", color=color)
    Path(out).mkdir(exist_ok=True)
    a.export(str(Path(out) / f"{name}.step"))
    return name


def union(*shapes):
    s = shapes[0]
    for t in shapes[1:]:
        s = s.union(t)
    return s


def header(xs, y, z_board):
    """Pin header under a module: plastic 2.5 from the host PCB, pins through both boards."""
    plastic = union(*[box(x - 1.27, y - 1.27, x + 1.27, y + 1.27, 0, z_board) for x in xs])
    pins = union(*[box(x - 0.32, y - 0.32, x + 0.32, y + 0.32, -3.0, z_board + 1.0 + 1.5) for x in xs])
    return plastic, pins
