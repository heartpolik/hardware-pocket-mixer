"""Tiny KiCad schematic writer: symbols from KiCad/project libraries, pins joined by net labels.

A design is a list of parts; every used pin gets a local net label at its end point, unused
pins get a no-connect flag. Single sheet per board. Output opens in KiCad 10 and passes
`kicad-cli sch erc` / `sch export netlist`.
"""
import re
import uuid as _uuid
from pathlib import Path

KICAD_SYM = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols")
PROJ_SYM = Path(__file__).resolve().parents[1] / "lib" / "pocket-digital.kicad_sym"
PROJ_LIB = "pocket-digital"


def uid():
    return str(_uuid.uuid4())


# ---------------------------------------------------------------- s-expressions
TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def parse(text):
    stack, cur = [], []
    for t in TOKEN.findall(text):
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(t)
    return cur


def dump(node, ind=0):
    if not isinstance(node, list):
        return node
    if all(not isinstance(x, list) for x in node):
        return "(" + " ".join(node) + ")"
    pad = "\t" * (ind + 1)
    parts = [node[0]] if node else []
    out = "(" + " ".join(x for x in node if not isinstance(x, list))
    for x in node:
        if isinstance(x, list):
            out += "\n" + pad + dump(x, ind + 1)
    return out + "\n" + "\t" * ind + ")"


def q(s):
    return '"' + str(s).replace('"', '\\"') + '"'


def uq(s):
    return s[1:-1] if s.startswith('"') else s


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


# ---------------------------------------------------------------- libraries
_libs = {}


def lib_symbols(lib):
    if lib not in _libs:
        path = PROJ_SYM if lib == PROJ_LIB else KICAD_SYM / f"{lib}.kicad_sym"
        tree = parse(path.read_text())[0]
        _libs[lib] = {uq(s[1]): s for s in find(tree, "symbol")}
    return _libs[lib]


def flat_symbol(lib_id):
    """Return the symbol s-expr with `extends` resolved, named lib:name."""
    lib, name = lib_id.split(":")
    syms = lib_symbols(lib)
    sym = syms[name]
    ext = find(sym, "extends")
    if ext:
        base = flat_symbol(f"{lib}:{uq(ext[0][1])}")
        base_name = uq(base[1]).split(":")[1]
        props = {uq(p[1]): p for p in find(sym, "property")}
        out = []
        for x in base:
            if isinstance(x, list) and x[0] == "property" and uq(x[1]) in props:
                out.append(props.pop(uq(x[1])))
            elif isinstance(x, list) and x[0] == "symbol":
                y = list(x)
                y[1] = q(uq(x[1]).replace(base_name, name, 1))
                out.append(y)
            else:
                out.append(x)
        out[1] = q(lib_id)
        for p in props.values():
            out.insert(3, p)
        return out
    out = list(sym)
    out[1] = q(lib_id)
    return out


def pins_of(lib_id):
    """{(unit, number): (x, y, angle)} in library coordinates (y up). Unit 0 = all units."""
    sym = flat_symbol(lib_id)
    res = {}
    for sub in find(sym, "symbol"):
        m = re.match(r'.*_(\d+)_(\d+)$', uq(sub[1]))
        unit = int(m.group(1))
        for p in find(sub, "pin"):
            at = find(p, "at")[0]
            num = uq(find(p, "number")[0][1])
            res[(unit, num)] = (float(at[1]), float(at[2]), int(float(at[3])))
    return res


def units_of(lib_id):
    return sorted({u for (u, _) in pins_of(lib_id) if u > 0}) or [1]


def pin_names(lib_id):
    """{pin name: [numbers]}"""
    sym = flat_symbol(lib_id)
    res = {}
    for sub in find(sym, "symbol"):
        for p in find(sub, "pin"):
            res.setdefault(uq(find(p, "name")[0][1]), []).append(uq(find(p, "number")[0][1]))
    return res


def resolve(lib_id, pins):
    """Allow pin names as keys; a name maps to every pin carrying it."""
    nums = {n for (_, n) in pins_of(lib_id)}
    names = pin_names(lib_id)
    out = {}
    for k, net in pins.items():
        if k in nums:
            out[k] = net
        elif k in names:
            for n in names[k]:
                out[n] = net
        else:
            raise KeyError(f"{lib_id}: no pin {k}")
    return out


# ---------------------------------------------------------------- design
class Part:
    def __init__(self, ref, lib_id, value, footprint="", pins=None, unit_pos=None, fields=None):
        self.ref, self.lib_id, self.value, self.footprint = ref, lib_id, value, footprint
        self.pins = pins or {}            # pin number -> net name (None = no connect)
        self.unit_pos = unit_pos or {}    # unit -> (x, y)
        self.fields = fields or {}


class Sheet:
    def __init__(self, project, title, paper="A1"):
        self.project, self.title, self.paper = project, title, paper
        self.parts, self.texts = [], []
        self.root = uid()

    def add(self, part):
        part.pins = resolve(part.lib_id, part.pins)
        self.parts.append(part)
        return part

    def text(self, x, y, s, size=2.5):
        self.texts.append((x, y, s, size))

    def nets(self):
        n = {}
        for p in self.parts:
            for num, net in p.pins.items():
                if net:
                    n.setdefault(net, []).append(f"{p.ref}.{num}")
        return n

    def write(self, path):
        used = sorted({p.lib_id for p in self.parts})
        out = ["(kicad_sch", "\t(version 20250114)", '\t(generator "diy-mixer-kisch")',
               '\t(generator_version "1.0")', f"\t(uuid {q(self.root)})", (f"\t(paper \"User\" {self.paper[0]} {self.paper[1]})" if isinstance(self.paper, tuple) else f"\t(paper {q(self.paper)})"),
               f"\t(title_block (title {q(self.title)}) (rev \"A\") (comment 1 \"Generated by hw/sch — do not edit by hand\"))",
               "\t(lib_symbols"]
        for lid in used:
            out.append("\t\t" + dump(flat_symbol(lid), 2))
        out.append("\t)")
        labels, ncs = [], []
        for p in self.parts:
            pins = pins_of(p.lib_id)
            for unit in units_of(p.lib_id):
                if unit not in p.unit_pos:
                    continue
                sx, sy = p.unit_pos[unit]
                upins = {num: xy for (u, num), xy in pins.items() if u in (0, unit)}
                props = [f'\t\t(property "Reference" {q(p.ref)} (at {sx} {sy - 5} 0) (effects (font (size 1.27 1.27))))',
                         f'\t\t(property "Value" {q(p.value)} (at {sx} {sy + 5} 0) (effects (font (size 1.27 1.27))))',
                         f'\t\t(property "Footprint" {q(p.footprint)} (at {sx} {sy} 0) (effects (font (size 1.27 1.27)) (hide yes)))']
                for k, v in p.fields.items():
                    props.append(f'\t\t(property {q(k)} {q(v)} (at {sx} {sy} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
                out += [f"\t(symbol (lib_id {q(p.lib_id)}) (at {sx} {sy} 0) (unit {unit})",
                        "\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)",
                        f"\t\t(uuid {q(uid())})", *props]
                for num in upins:
                    out.append(f"\t\t(pin {q(num)} (uuid {q(uid())}))")
                out += [f'\t\t(instances (project {q(self.project)} (path {q("/" + self.root)} '
                        f'(reference {q(p.ref)}) (unit {unit}))))', "\t)"]
                for num, (px, py, ang) in upins.items():
                    x, y = round(sx + px, 2), round(sy - py, 2)
                    net = p.pins.get(num)
                    if net:
                        # pin angle points from the connection point into the body
                        la = {0: 180, 180: 0, 90: 270, 270: 90}[ang]
                        just = "right" if la in (180, 270) else "left"
                        labels.append(f'\t(label {q(net)} (at {x} {y} {la}) (fields_autoplaced yes) '
                                      f'(effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid {q(uid())}))')
                    else:
                        ncs.append(f"\t(no_connect (at {x} {y}) (uuid {q(uid())}))")
        out += labels + ncs
        for x, y, s, size in self.texts:
            out.append(f'\t(text {q(s)} (exclude_from_sim no) (at {x} {y} 0) '
                       f'(effects (font (size {size} {size}) (bold yes)) (justify left bottom)) (uuid {q(uid())}))')
        out += [f'\t(sheet_instances (path "/" (page "1")))', ")"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("\n".join(out) + "\n")


def project_files(folder, name):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    pro = folder / f"{name}.kicad_pro"
    import json
    cfg = json.loads(pro.read_text()) if pro.exists() else {}
    cfg.setdefault("meta", {"filename": f"{name}.kicad_pro", "version": 3})
    rules = cfg.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
    rules.update({"min_clearance": 0.15, "min_copper_edge_clearance": 0.2,
                  "min_track_width": 0.15, "min_via_diameter": 0.5, "min_through_hole_diameter": 0.3})
    # Power: battery / converter nets (up to ~0.45 A from the cell, docs/calc/power.py) and the rails
    power = ["/VBUS", "/VSYS", "/BAT+", "/+4V2", "/BB_L1", "/BB_L2", "/+3V3", "/+3V3A"]
    cfg["net_settings"] = {"classes": [
        {"name": "Default", "priority": 2147483647, "clearance": 0.15, "track_width": 0.2,
         "via_diameter": 0.6, "via_drill": 0.3},
        {"name": "Power", "priority": 0, "clearance": 0.15, "track_width": 0.5,
         "via_diameter": 0.8, "via_drill": 0.4}],
        "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in power],
        "meta": {"version": 4}}
    pro.write_text(json.dumps(cfg, indent=2) + "\n")
    rules_file(folder, name)
    for t in ("fp-lib-table", "sym-lib-table"):
        src = Path(__file__).resolve().parents[1] / "lib" / t
        (folder / t).write_text(src.read_text())


# Custom DRC rules (<name>.kicad_dru). Thermal reliefs: GND pads between the tight pins of
# SOIC/TSSOP and of the jacks/USB-C get only one spoke on some layers; each of them also has a
# fanout track/via or the In1 plane on another layer, and one spoke solders easier by hand (D12).
DRU = """(version 1)

(rule "thermal: one spoke is enough"
	(condition "A.Type == 'Pad'")
	(constraint min_resolved_spokes 1))
"""


def rules_file(folder, name):
    (Path(folder) / f"{name}.kicad_dru").write_text(DRU)
