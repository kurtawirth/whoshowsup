"""House hex map: one hexagon per congressional district, arranged by state.

Base layout: Pitch Interactive's Tilegrams "US Congressional Districts 2018"
(ISC license) -- state shapes built from equal pointy-top hexagons, one per
district under the 2010 apportionment.

Steps
  1. Decode the TopoJSON and recover every hex center inside each state shape.
  2. Re-apportion to the 2020 census (used for 2022-2030): add hexes on a state's
     open edge, remove hexes from its edge, never splitting a state into more pieces.
  3. Assign districts to hexes so each sits near its real location within the
     state: match hex positions to Census district center points (2024
     gazetteer, 119th Congress) with an optimal assignment (Hungarian algorithm)
     after scaling both to the state's box. States that redrew for 2026 keep the
     119th-Congress centroids -- an approximation, as in any hex map.

Output: data/processed/house_hexmap.json
  hexes:  [{state, district, q, r, x, y}]        (x, y in hex units; y grows down)
  borders: [[x1, y1, x2, y2], ...]               hex edges between different states
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "house_hexmap.json"

APPORTION_2020 = {"TX": +2, "CO": +1, "FL": +1, "MT": +1, "NC": +1, "OR": +1,
                  "CA": -1, "IL": -1, "MI": -1, "NY": -1, "OH": -1, "PA": -1, "WV": -1}
NAME_TO_PO = {  # tilegram uses upper-case state names
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO",
    "CONNECTICUT": "CT", "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX",
    "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY"}


def decode_topojson(t: dict) -> dict:
    """state -> list of rings (arrays of absolute coordinates)."""
    sx, sy = t["transform"]["scale"]
    tx, ty = t["transform"]["translate"]
    arcs = []
    for arc in t["arcs"]:
        a = np.cumsum(np.array(arc, dtype=float), axis=0)
        arcs.append(np.column_stack([a[:, 0] * sx + tx, a[:, 1] * sy + ty]))
    def ring(idx):
        pts = []
        for i in idx:
            seg = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.extend(seg if not pts else seg[1:])
        return np.array(pts)
    out = {}
    for g in t["objects"]["tiles"]["geometries"]:
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        out[NAME_TO_PO[g["properties"]["name"]]] = [ring(r) for poly in polys for r in poly]
    return out


def hex_centers(states: dict, w: float, h: float) -> dict:
    """Recover hex centers: every center is a vertex minus one of the 6 vertex offsets;
    keep candidates that fall strictly inside a state's shape."""
    r = h / 2
    offsets = np.array([[0, -r], [w / 2, -r / 2], [w / 2, r / 2], [0, r], [-w / 2, r / 2], [-w / 2, -r / 2]])
    verts = np.vstack([ring for rings in states.values() for ring in rings])
    cand = (verts[:, None, :] - offsets[None, :, :]).reshape(-1, 2)
    cand = np.unique(np.round(cand, 1), axis=0)
    # A true center is a full radius from every vertex; drop candidates that land on a vertex.
    from scipy.spatial import cKDTree
    d, _ = cKDTree(verts).query(cand)
    cand = cand[d > r / 2]
    out = {}
    for st, rings in states.items():
        inside = np.zeros(len(cand), bool)
        for ring in rings:
            inside ^= MplPath(ring).contains_points(cand, radius=-1e-6)
        pts = cand[inside]
        # de-duplicate near-identical candidates (rounding noise)
        keep = []
        for p in pts:
            if all(np.hypot(*(p - k)) > w / 3 for k in keep):
                keep.append(p)
        out[st] = np.array(keep)
    return out


def to_axial(pts: np.ndarray, origin: np.ndarray, w: float, h: float) -> list[tuple[int, int]]:
    """Pointy-top hex centers -> integer (col, row) offset coordinates.
    Alternate rows sit half a hex to the right; which ones is measured from the data
    (each row's x-offset modulo the hex width), then rows are numbered so that the
    shifted rows are the odd ones -- the convention neighbors() relies on."""
    rows = np.round((pts[:, 1] - origin[1]) / (h * 0.75)).astype(int)
    frac = ((pts[:, 0] - origin[0]) / w) % 1.0
    shifted = np.abs(frac - 0.5) < 0.25
    if np.any(shifted & (rows % 2 == 0)):   # shifted rows landed on even numbers: renumber
        rows = rows + 1
    assert not np.any(shifted != (rows % 2 == 1)), "inconsistent row offsets"
    cols = np.round((pts[:, 0] - origin[0]) / w - np.where(shifted, 0.5, 0.0)).astype(int)
    return list(zip(cols.tolist(), rows.tolist()))


def neighbors(c: int, r: int) -> list[tuple[int, int]]:
    odd = r % 2 == 1  # odd rows are shifted right
    d = [(-1, 0), (1, 0), (0, -1), (0, 1), (1, -1), (1, 1)] if odd else [(-1, 0), (1, 0), (-1, -1), (-1, 1), (0, -1), (0, 1)]
    return [(c + dc, r + dr) for dc, dr in d]


def reapportion(cells: dict) -> dict:
    occupied = {cell: st for st, cs in cells.items() for cell in cs}
    for st, delta in sorted(APPORTION_2020.items(), key=lambda x: x[1]):  # removals first free up space
        cs = cells[st]
        for _ in range(abs(delta)):
            cen = np.mean(cs, axis=0)
            if delta < 0:
                # remove the edge cell farthest from the center whose removal keeps the state connected
                # (Michigan's Upper Peninsula is its own piece, so "don't add pieces", not "one piece")
                before = components(cs)
                # Remove from the coast/outer edge (a cell next to empty space) so no hole opens
                # in the middle of the map; among those, the one farthest from the state's center.
                def edge_first(c):
                    open_side = any(n not in occupied for n in neighbors(*c))
                    return (not open_side, -np.hypot(c[0] - cen[0], c[1] - cen[1]))
                for cell in sorted(cs, key=edge_first):
                    rest = [c for c in cs if c != cell]
                    if components(rest) <= before:
                        cs.remove(cell); occupied.pop(cell); break
                else:
                    raise RuntimeError(f"could not remove a hex from {st}")
            else:
                free = {n for c in cs for n in neighbors(*c) if n not in occupied}
                if free:
                    # prefer free cells touching the most of this state's cells (compact), then nearest the center
                    best = max(free, key=lambda n: (sum(m in cs for m in neighbors(*n)),
                                                     -np.hypot(n[0] - cen[0], n[1] - cen[1])))
                    cs.append(best); occupied[best] = st
                else:
                    push_to_open(st, cells, occupied)
    return cells


def fill_holes(cells: dict) -> dict:
    """Fill interior holes (an empty cell surrounded on all six sides): the neighboring
    state touching it most takes the hole and gives up its outermost edge cell."""
    for _ in range(20):
        occupied = {c: st for st, cs in cells.items() for c in cs}
        qs = [q for q, _ in occupied]; rs = [r for _, r in occupied]
        holes = [(q, r) for q in range(min(qs), max(qs) + 1) for r in range(min(rs), max(rs) + 1)
                 if (q, r) not in occupied and all(n in occupied for n in neighbors(q, r))]
        if not holes:
            return cells
        filled = False
        for hole in holes:
            owners = [occupied[n] for n in neighbors(*hole)]
            for st in sorted(set(owners), key=owners.count, reverse=True):
                cs = cells[st]
                cen = np.mean(cs, axis=0)
                before = components(cs)
                trial = cs + [hole]
                occ2 = {**occupied, hole: st}
                exterior = [c for c in cs if any(n not in occ2 for n in neighbors(*c))]
                for cell in sorted(exterior, key=lambda c: -np.hypot(c[0] - cen[0], c[1] - cen[1])):
                    rest = [c for c in trial if c != cell]
                    if components(rest) <= before:
                        cells[st] = rest
                        filled = True
                        break
                if filled:
                    break
            if filled:
                break
        if not filled:
            return cells  # remaining holes cannot be rebalanced
    return cells


def push_to_open(st: str, cells: dict, occupied: dict) -> None:
    """A landlocked state needs one more hex: find the shortest path from its edge to an
    empty cell, then shift each state along the path one cell toward the open space.
    Every state keeps its count; the target gains the first cell on the path."""
    from collections import deque
    start = set(cells[st])
    prev, queue, goal = {c: None for c in start}, deque(start), None
    while queue:
        c = queue.popleft()
        if c not in occupied:
            goal = c
            break
        for n in neighbors(*c):
            if n not in prev:
                prev[n] = c
                queue.append(n)
    path = []
    while goal is not None:
        path.append(goal)
        goal = prev[goal]
    path = path[::-1]  # path[0] is the target's own cell, path[-1] the empty cell
    # walk backwards: each cell passes to the owner of the cell before it
    for k in range(len(path) - 1, 0, -1):
        new_owner = occupied[path[k - 1]]
        old_owner = occupied.get(path[k])
        if old_owner is not None:
            cells[old_owner].remove(path[k])
        cells[new_owner].append(path[k])
        occupied[path[k]] = new_owner
    # the target now holds path[1]; the chain shifted everyone else by one


def components(cs: list) -> int:
    """Number of separate pieces a set of hex cells forms."""
    left, n = set(cs), 0
    while left:
        stack = [left.pop()]
        n += 1
        while stack:
            for nb in neighbors(*stack.pop()):
                if nb in left:
                    left.remove(nb); stack.append(nb)
    return n


def assign_districts(cells: dict) -> list[dict]:
    gaz = pd.read_csv(RAW / "census" / "2024_Gaz_119CDs_national.txt", sep="\t")
    gaz.columns = [c.strip() for c in gaz.columns]
    gaz["GEOID"] = gaz["GEOID"].astype(str).str.zfill(4)
    gaz = gaz[gaz["GEOID"].str[2:].str.isdigit() & gaz["USPS"].isin(cells)]  # drop "ZZ" water parts, DC, territories
    gaz["district"] = gaz["GEOID"].str[2:].astype(int)
    out = []
    for st, cs in cells.items():
        g = gaz[gaz["USPS"] == st].sort_values("district")
        n = len(g)
        assert n == len(cs), f"{st}: {len(cs)} hexes vs {n} districts"
        hx = np.array([[c + (0.5 if r % 2 else 0), r * 0.866] for c, r in cs], float)
        lat = g["INTPTLAT"].to_numpy(float)
        lon = g["INTPTLONG"].to_numpy(float) * np.cos(np.radians(lat.mean()))
        geo = np.column_stack([lon, -lat])  # y grows down, like the hex grid
        def norm(a):
            span = np.ptp(a, axis=0)
            return (a - a.min(axis=0)) / np.where(span > 0, span.max(), 1)
        cost = ((norm(hx)[:, None, :] - norm(geo)[None, :, :]) ** 2).sum(-1)
        rows, cols = linear_sum_assignment(cost)
        for i, j in zip(rows, cols):
            c, r = cs[i]
            dist = int(g["district"].iloc[j])
            out.append({"state": st, "district": 0 if n == 1 else dist, "q": c, "r": r,
                        "x": c + (0.5 if r % 2 else 0), "y": r * 0.866})
    return out


def borders(hexes: list[dict]) -> list[list[float]]:
    """Hex edges shared by hexes of different states (for drawing state outlines)."""
    by_cell = {(h["q"], h["r"]): h["state"] for h in hexes}
    # pointy-top unit hex (width 1): vertex offsets and which neighbor each edge faces
    rad = 1 / np.sqrt(3)
    angles = np.radians([-90, -30, 30, 90, 150, 210])
    vx, vy = rad * np.cos(angles), rad * np.sin(angles)
    segs = []
    for h in hexes:
        c, r = h["q"], h["r"]
        odd = r % 2 == 1
        # edge k runs vertex k -> k+1; neighbor across it:
        nb = [(c + (1 if odd else 0), r - 1), (c + 1, r), (c + (1 if odd else 0), r + 1),
              (c - (0 if odd else 1), r + 1), (c - 1, r), (c - (0 if odd else 1), r - 1)]
        for k in range(6):
            if by_cell.get(nb[k]) != h["state"]:
                segs.append([round(h["x"] + vx[k], 4), round(h["y"] + vy[k], 4),
                             round(h["x"] + vx[(k + 1) % 6], 4), round(h["y"] + vy[(k + 1) % 6], 4)])
    return segs


def main() -> None:
    t = json.load(open(RAW / "tilegrams" / "us-congressional-districts-2018.json"))
    size = t["properties"]["tilegramTileSize"]
    w, h = size["width"], size["height"]
    states = decode_topojson(t)
    centers = hex_centers(states, w, h)
    counts = {g["properties"]["name"]: g["properties"]["tilegramValue"] for g in t["objects"]["tiles"]["geometries"]}
    bad = {st: (len(p), counts[k]) for k, st in NAME_TO_PO.items() for p in [centers[st]] if len(p) != counts[k]}
    assert not bad, f"hex recovery mismatch: {bad}"
    # TopoJSON y grows up; flip to screen coordinates (north at top) BEFORE snapping to the
    # grid, so the half-hex shift of alternating rows is applied to the right rows.
    centers = {st: p * np.array([1, -1]) for st, p in centers.items()}
    origin = np.vstack(list(centers.values())).min(axis=0)
    names = [st for st, p in centers.items() for _ in range(len(p))]
    allcells = to_axial(np.vstack(list(centers.values())), origin, w, h)  # one grid for the whole map
    cells = {st: [] for st in centers}
    for st, cell in zip(names, allcells):
        cells[st].append(cell)
    taken = [c for cs in cells.values() for c in cs]
    assert len(taken) == len(set(taken)), "two hexes snapped to the same grid cell"
    cells = fill_holes(reapportion(cells))
    hexes = assign_districts(cells)
    assert len(hexes) == 435
    OUT.write_text(json.dumps({"hexes": hexes, "borders": borders(hexes),
                               "source": "Layout adapted from Pitch Interactive Tilegrams (ISC license)."}))
    print(f"{len(hexes)} hexes, {len({h['state'] for h in hexes})} states")


if __name__ == "__main__":
    main()
