"""House hex map, "state islands" layout: one hexagon per district, each state its own
cluster of identical hexes, separated from its neighbours by open space.

    .venv/Scripts/python.exe core/build_hexmap_islands.py

How it works
  1. Shape: each state's real outline (us-atlas, Albers) is scaled so its area equals its
     number of hexes; the hexes whose centres fall deepest inside that outline form the
     state's cluster (trying several grid offsets, keeping the best fit). So Tennessee
     comes out as a strip and California as a tall diagonal, whatever their seat counts.
  2. Place: each cluster starts at its state's real position, then clusters are nudged
     apart until every pair is separated by at least GAP hex-widths, while a spring keeps
     each one near home. States with many seats in small areas (the Northeast) spread out.
  3. Districts: within each state, districts go to hexes by optimal assignment against
     their real centroids (Census gazetteer), so e.g. New York City sits at New York's
     south end.

Output: data/processed/house_hexmap.json -- {"hexes": [{state, district, x, y}], "labels":
[{state, x, y, anchor}], "borders": []}; x, y in hex-width units (neighbouring centres are 1 apart).
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd
from matplotlib.path import Path as MPath
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ATLAS = ROOT / "site" / "src" / "data" / "states-albers-10m.json"
OUT = ROOT / "data" / "processed" / "house_hexmap.json"

GAP = 0.55            # minimum empty space between two states' hexes, in hex widths
SCALE = 0.046         # hex widths per Albers pixel for home positions in the final map
START_SCALE = 0.11    # the blown-up map the layout shrinks from
SPRING = 0.05         # pull of each cluster toward its real position, per iteration
LABEL_DY = 0.95       # label sits this far above the top row of hexes
ROW = np.sqrt(3) / 2  # vertical distance between hex rows (pointy-top, unit width)

FIPS = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE",
        "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS",
        "21": "KY", "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
        "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY",
        "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC",
        "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
        "55": "WI", "56": "WY"}


def state_polygons() -> dict[str, list[np.ndarray]]:
    """state -> outer rings (Albers pixels, y down), largest first."""
    t = json.loads(ATLAS.read_text())
    sx, sy = t["transform"]["scale"]
    tx, ty = t["transform"]["translate"]
    arcs = []
    for arc in t["arcs"]:
        a = np.cumsum(np.array(arc, float), axis=0)
        arcs.append(np.column_stack([a[:, 0] * sx + tx, a[:, 1] * sy + ty]))

    def ring(idx):
        pts = []
        for i in idx:
            seg = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.extend(seg if not pts else seg[1:])
        return np.array(pts)

    out = {}
    for g in t["objects"]["states"]["geometries"]:
        po = FIPS.get(g["id"])
        if po is None:
            continue
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        rings = [ring(p[0]) for p in polys]
        out[po] = sorted(rings, key=lambda r: -abs(area(r)))
    return out


def area(r: np.ndarray) -> float:
    x, y = r[:, 0], r[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def centroid(r: np.ndarray) -> np.ndarray:
    x, y = r[:, 0], r[:, 1]
    c = x * np.roll(y, 1) - np.roll(x, 1) * y
    a = c.sum() / 2
    return np.array([((x + np.roll(x, 1)) * c).sum(), ((y + np.roll(y, 1)) * c).sum()]) / (6 * a)


def boundary_distance(pts: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Distance from each point to the ring's edges."""
    a, b = r[:-1], r[1:]
    ab = b - a
    t = np.clip(((pts[:, None, :] - a[None]) * ab[None]).sum(-1) / np.maximum((ab ** 2).sum(-1), 1e-12), 0, 1)
    proj = a[None] + t[..., None] * ab[None]
    return np.sqrt(((pts[:, None, :] - proj) ** 2).sum(-1)).min(1)


def grid(n: int, dx: float, dy: float) -> np.ndarray:
    """Hex centres (pointy-top, unit width) covering roughly [-n, n]^2, shifted by (dx, dy) of a cell."""
    rows = np.arange(-n, n + 1)
    pts = [(c + (0.5 if r % 2 else 0) + dx, r * ROW + dy * ROW) for r in rows for c in range(-n, n + 1)]
    return np.array(pts)


def connected(cells: np.ndarray) -> bool:
    if len(cells) <= 1:
        return True
    d = np.sqrt(((cells[:, None] - cells[None]) ** 2).sum(-1))
    adj = d < 1.05
    seen, stack = {0}, [0]
    while stack:
        i = stack.pop()
        for j in np.flatnonzero(adj[i]):
            if j not in seen:
                seen.add(j)
                stack.append(j)
    return len(seen) == len(cells)


def cluster_shape(ring: np.ndarray, n: int) -> np.ndarray:
    """n hex centres (relative to the state's centroid) that best fill the state's outline."""
    c = centroid(ring)
    k = np.sqrt(n * ROW / abs(area(ring)))            # scale so outline area = n hex areas
    poly = (ring - c) * k
    path = MPath(poly)
    span = int(np.ceil(np.abs(poly).max())) + 2
    best, best_score = None, -np.inf
    for dx in np.linspace(0, 1, 4, endpoint=False):
        for dy in np.linspace(0, 2, 4, endpoint=False):
            pts = grid(span, dx, dy)
            inside = path.contains_points(pts)
            depth = boundary_distance(pts, poly) * np.where(inside, 1, -1)   # signed: + inside
            pick = pts[np.argsort(-depth)[:n]]
            if not connected(pick):
                continue
            score = np.sort(depth)[::-1][:n].sum() - 0.3 * np.abs(pick.mean(0)).sum()  # deep + centred
            if score > best_score:
                best, best_score = pick, score
    if best is None:  # a shape too thin to stay connected: fall back to a compact blob
        pts = grid(span, 0, 0)
        best = pts[np.argsort((pts ** 2).sum(1))[:n]]
    return best - best.mean(0)


def separate(shapes: dict, home: dict, iters: int = 3000) -> dict:
    """Place clusters without overlaps, near home, in their real relative order.

    Start with the map blown up (START_SCALE: nothing touches, every state exactly at home)
    and shrink it step by step to SCALE while clearing overlaps each step -- states bump into
    each other rather than jumping past each other, so north stays north and west stays west.
    `shapes` include each state's label slot, so neighbours keep clear of the label too.
    `home` is each state's real centroid in Albers pixels."""
    states = list(shapes)
    pos = {s: home[s] * START_SCALE for s in states}
    radius = {s: np.sqrt((shapes[s] ** 2).sum(1)).max() + 0.5 for s in states}
    need = 1 + GAP

    def sweep() -> float:
        moved = 0.0
        for i, a in enumerate(states):
            for b in states[i + 1:]:
                d = pos[b] - pos[a]
                if np.hypot(*d) > radius[a] + radius[b] + need:
                    continue
                pa, pb = shapes[a] + pos[a], shapes[b] + pos[b]
                dd = pb[None] - pa[:, None]
                dist = np.sqrt((dd ** 2).sum(-1))
                j = np.unravel_index(dist.argmin(), dist.shape)
                over = need - dist[j]
                if over <= 0:
                    continue
                v = dd[j] / max(dist[j], 1e-6)
                u = d / max(np.hypot(*d), 1e-6)
                v = 0.6 * v + 0.4 * u          # blend in centre-to-centre so clusters don't slide forever
                v /= np.hypot(*v)
                wa, wb = len(shapes[b]), len(shapes[a])     # bigger states move less
                pos[a] -= v * (over + 0.01) * wa / (wa + wb)
                pos[b] += v * (over + 0.01) * wb / (wa + wb)
                moved += over
        return moved

    for it in range(iters):
        scale = START_SCALE + (SCALE - START_SCALE) * min(1, it / (0.8 * iters))
        for s in states:
            pos[s] += SPRING * (home[s] * scale - pos[s])
        sweep()
    for it2 in range(2000):   # final pass: no spring, just clear every overlap
        if sweep() < 1e-4:
            break
    print(f"spring phase {iters} its; clean-up {it2 + 1} its; worst remaining overlap {sweep():.4f}")
    return pos


def assign(shapes: dict, pos: dict) -> list[dict]:
    gaz = pd.read_csv(RAW / "census" / "2024_Gaz_119CDs_national.txt", sep="\t")
    gaz.columns = [c.strip() for c in gaz.columns]
    gaz["GEOID"] = gaz["GEOID"].astype(str).str.zfill(4)
    gaz = gaz[gaz["GEOID"].str[2:].str.isdigit() & gaz["USPS"].isin(shapes)]
    gaz["district"] = gaz["GEOID"].str[2:].astype(int)
    out = []
    for st, cells in shapes.items():
        g = gaz[gaz["USPS"] == st].sort_values("district")
        n = len(g)
        assert n == len(cells), f"{st}: {len(cells)} hexes vs {n} districts"
        lat = g["INTPTLAT"].to_numpy(float)
        lon = g["INTPTLONG"].to_numpy(float) * np.cos(np.radians(lat.mean()))
        geo = np.column_stack([lon, -lat])

        def norm(a):
            a = a - a.mean(0)
            s = np.abs(a).max()
            return a / s if s > 0 else a
        cost = ((norm(cells)[:, None] - norm(geo)[None]) ** 2).sum(-1)
        rows, cols = linear_sum_assignment(cost)
        for i, j in zip(rows, cols):
            x, y = cells[i] + pos[st]
            out.append({"state": st, "district": 0 if n == 1 else int(g["district"].iloc[j]),
                        "x": round(float(x), 4), "y": round(float(y), 4)})
    return out


def main() -> None:
    polys = state_polygons()
    gaz = pd.read_csv(RAW / "census" / "2024_Gaz_119CDs_national.txt", sep="\t")
    counts = gaz[gaz["GEOID"].astype(str).str.zfill(4).str[2:].str.isdigit()].groupby("USPS").size()
    counts = counts[counts.index.isin(polys)]
    assert counts.sum() == 435, counts.sum()

    shapes = {s: cluster_shape(polys[s][0], int(n)) for s, n in counts.items()}
    label_at = {}
    for s, c in shapes.items():                       # label slot: centred just above the top row
        top = c[:, 1].min()
        row = c[np.abs(c[:, 1] - top) < 0.1]
        label_at[s] = np.array([row[:, 0].mean(), top - LABEL_DY])
    padded = {s: np.vstack([c, label_at[s]]) for s, c in shapes.items()}
    pos = separate(padded, {s: centroid(polys[s][0]) for s in shapes})
    hexes = assign(shapes, pos)
    labels = [{"state": s, "x": round(float(label_at[s][0] + pos[s][0]), 3),
               "y": round(float(label_at[s][1] + pos[s][1]), 3), "n": len(shapes[s])} for s in shapes]
    minx = min(h["x"] for h in hexes)
    miny = min(min(h["y"] for h in hexes), min(l["y"] for l in labels) - 0.6)
    for h in hexes + labels:
        h["x"] = round(h["x"] - minx, 4)
        h["y"] = round(h["y"] - miny, 4)
    OUT.write_text(json.dumps({"hexes": hexes, "labels": labels, "borders": [],
                               "source": "state-islands layout from us-atlas outlines + Census gazetteer"}))
    print(f"wrote {OUT} ({len(hexes)} hexes)")


if __name__ == "__main__":
    main()
