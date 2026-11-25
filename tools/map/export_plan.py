"""Exports the campus plan for the M map (V2-09, docs/DESIGN.md §6) to assets/levels/campus_plan.json.
Reads the level's own numbers, read-only: tools/blender/campus_layout.py (plain math: the real footprints of the south
side) is imported as a module; tools/blender/campus_kb1.py (which needs Blender to import) is only scanned for its
outline constants. Nothing in tools/blender is written. Run from mano-godot/:  python3 tools/map/export_plan.py
Game space: metres, X east along rue Pasteur, Z south; the map draws -Z up (docs/DESIGN.md §6: north is 13.6° clockwise
of page-up)."""
import importlib.util, json, math, os, re, sys

sys.dont_write_bytecode = True   # no __pycache__ written next to campus_layout.py

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
BL = os.path.join(ROOT, "tools", "blender")


def load_layout():
    spec = importlib.util.spec_from_file_location("campus_layout", os.path.join(BL, "campus_layout.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def kb1_numbers():
    """The KB1 outline constants (campus_kb1.py: WX0, WX1 = ..., WZS, WZN = ..., NX0, NX1 = ..., NZN = ...)."""
    src = open(os.path.join(BL, "campus_kb1.py")).read()
    out = {}
    for line in src.splitlines():
        m = re.match(r"^([A-Z0-9_]+(?:\s*,\s*[A-Z0-9_]+)*)\s*=\s*(-?[\d.]+(?:\s*,\s*-?[\d.]+)*)\s*(#.*)?$", line)
        if m:
            names = [n.strip() for n in m.group(1).split(",")]
            vals = [float(v) for v in m.group(2).split(",")]
            if len(names) == len(vals):
                out.update(dict(zip(names, vals)))
    return out


def r(pts):
    return [[round(x, 2), round(z, 2)] for x, z in pts]


def main():
    L = load_layout()
    K = kb1_numbers()
    wx0, wx1, wzs, wzn = K["WX0"], K["WX1"], K["WZS"], K["WZN"]
    nx0, nx1, nzn = K["NX0"], K["NX1"], K["NZN"]
    kb1 = [(wx0, wzs), (wx1, wzs), (wx1, wzn), (nx1, wzn), (nx1, nzn), (nx0, nzn), (nx0, wzn), (wx0, wzn)]
    cafe = [L.cafe_pt(0, 0), L.cafe_pt(L.SE_LEN, 0), L.cafe_pt(L.SE_LEN, L.CAFE_D), L.cafe_pt(0, L.CAFE_D)]
    plan = {
        "version": 1,
        "doc": "Written by tools/map/export_plan.py from tools/blender/campus_layout.py and campus_kb1.py (read only). "
               "Footprints are [x, z] in game metres; the M map (scripts/ui/map_view.gd) bakes them once onto its grid sheet.",
        "bounds": [-55, -50, 110, 115],
        "north_deg": 13.6,
        "carreau_m": 4.0,
        "credit": "map data © OpenStreetMap contributors, ODbL; cadastre, IGN",
        "buildings": [
            {"id": "kb1", "label": "KB1", "hatch": 45, "pts": r(kb1)},
            {"id": "east24", "label": "24 rue Pasteur", "hatch": 30, "pts": r(L.EAST_24)},
            {"id": "paritalie", "label": "Paritalie", "hatch": 30, "pts": r(L.X_PARITALIE)},
            {"id": "south_w", "label": "", "hatch": 30, "pts": r(L.SOUTH_W)},
            {"id": "south_e", "label": "", "hatch": 30, "pts": r(L.SOUTH_E)},
        ],
        "covered": [
            {"id": "passage_n", "pts": r(L.PASSAGE_N)},
            {"id": "passage_s", "pts": r(L.PASSAGE_S)},
        ],
        "court": r(L.COURT),
        "rooms": [
            {"id": "amphi", "label": "Amphi 4", "pts": r([(9.5, 6.0), (28.0, 6.0), (28.0, 18.4), (9.5, 18.4)])},
            {"id": "cafe", "label": "cafet'", "pts": r(cafe)},
            {"id": "under", "label": "l'Under (sous-sol)", "dashed": True, "pts": r([(1.7, 36.0), (28.7, 36.0), (28.7, 52.3), (1.7, 52.3)])},
            {"id": "sm14", "label": "SM14", "floor": 1, "pts": r([(-18.0, -26.0), (-4.0, -26.0), (-4.0, -16.0), (-18.0, -16.0)])},
            {"id": "accueil", "label": "accueil", "pts": r([(-3.8, -26.0), (2.2, -26.0), (2.2, -21.0), (-3.8, -21.0)])},
        ],
        "streets": [
            {"name": "rue Pasteur", "one_way": "west", "a": [-55, 0], "b": [55, 0], "half": 5.3},
            {"name": "rue Voltaire", "one_way": "east", "a": [-55, -44.0], "b": [55, -36.0], "half": 4.0},
        ],
        "off_page": [
            {"text": "métro 7, Le Kremlin-Bicêtre", "at": [-52, -2], "dir": [-1, 0]},
            {"text": "Porte d'Italie", "at": [52, -2], "dir": [1, 0]},
        ],
        "labels": [
            {"text": "cour Pasteur", "at": [12.0, 30.0]},
        ],
    }
    out = os.path.join(ROOT, "assets", "levels", "campus_plan.json")
    with open(out, "w") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    print("wrote", out, "buildings", len(plan["buildings"]), "rooms", len(plan["rooms"]))


if __name__ == "__main__":
    main()
