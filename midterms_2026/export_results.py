"""After the election: grade the final forecast against the results.

Reads the final forecast the site still shows (site/src/data/races.json, topline.json, seats.json), the latest
counts and calls (site/src/data/live.json, from civicAPI), other forecasters' final ratings (outlets.json) and
PredictIt's final prices (markets.json). Writes site/src/data/scorecard.json for the "How we did" page, the race
pages and the overview. Changes nothing in the forecast itself. Rerun after every results update:

    .venv/Scripts/python.exe midterms_2026/export_results.py
"""
import json
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "site", "src", "data")


def load(name):
    return json.load(open(os.path.join(D, name), encoding="utf-8"))


races = load("races.json")
top = load("topline.json")
seats = load("seats.json")
live = load("live.json")
outlets = load("outlets.json")
markets = load("markets.json")
senate_base = load("live_model.json")["senate_base"]  # Democratic-caucus seats not on the ballot
L = live["races"]

PICK = {"Safe D": "D", "Likely D": "D", "Lean D": "D", "Tilt D": "D", "Toss-up": None,
        "Tilt R": "R", "Lean R": "R", "Likely R": "R", "Safe R": "R"}
FINAL_PCT = 95          # margins are compared only once a race is this far counted
BANDS = [(.5, .6), (.6, .7), (.7, .8), (.8, .9), (.9, .97), (.97, 1.001)]


def votes(x):
    return (x.get("d") or 0) + (x.get("r") or 0)


def r1(v, n=1):
    return None if v is None else round(v, n)


rows = []
for z in races:
    if z["race_type"] == "same_party":
        continue
    rid, x = z["race_id"], L.get(z["race_id"]) or {}
    p = z["p_dem"]
    fav = "D" if p > .5 else "R" if p < .5 else None
    called = x.get("called") if x.get("called") in ("D", "R") else None
    n, e = votes(x), z.get("expected_votes") or 0
    m = x.get("margin")
    # a margin we trust enough to grade: mostly counted, both sides on the count, and a vote total near what we
    # expected (a far smaller two-party total means a third candidate took a big share, so D-vs-R isn't comparable)
    graded = (m is not None and z["race_type"] == "standard" and (x.get("pct") or 0) >= FINAL_PCT
              and x.get("d") and x.get("r") and e and .7 * e <= n <= 1.5 * e)
    row = {
        "id": rid, "office": z["office"], "called": called, "fav": fav, "p": round(p, 4),
        "med": r1(z["margin_median"]), "lo": r1(z["margin_p10"]), "hi": r1(z["margin_p90"]),
        "margin": r1(m, 2), "pct": x.get("pct"), "d": x.get("d"), "r": x.get("r"),
        "graded": bool(graded),
    }
    if called:
        row["right"] = fav is not None and fav == called
    if graded:
        row["miss"] = r1(m - z["margin_median"], 2)
        row["inside"] = z["margin_p10"] <= m <= z["margin_p90"]
    o = outlets["races"].get(rid)
    if o:
        row["outlets"] = o
    mk = markets["races"].get(rid)
    if mk:
        row["pi"] = mk["p"]
    rows.append(row)

called = [w for w in rows if w["called"]]


def tally(ws):
    right = sum(w["right"] for w in ws)
    exp = sum(max(w["p"], 1 - w["p"]) for w in ws)
    brier = sum((w["p"] - (w["called"] == "D")) ** 2 for w in ws) / len(ws) if ws else None
    return {"n": len(ws), "right": right, "expected_right": r1(exp), "brier": r1(brier, 4)}


summary = {"all": tally(called)}
for off in ("HOUSE", "SEN", "GOV"):
    summary[off] = tally([w for w in called if w["office"] == off])
for side in ("D", "R"):
    ws = [w for w in called if w["fav"] == side]
    summary[f"fav_{side}"] = {"n": len(ws), "won": sum(w["right"] for w in ws)}
summary["coin_flips"] = sum(w["fav"] is None for w in called)

calib = []
for lo, hi in BANDS:
    ws = [w for w in called if w["fav"] and lo <= max(w["p"], 1 - w["p"]) < hi]
    if ws:
        calib.append({"lo": lo, "hi": min(hi, 1), "n": len(ws), "won": sum(w["right"] for w in ws),
                      "said": round(st.mean(max(w["p"], 1 - w["p"]) for w in ws), 4)})

margins = {}
for off in ("ALL", "HOUSE", "SEN", "GOV"):
    ws = [w for w in rows if w["graded"] and (off == "ALL" or w["office"] == off)]
    if ws:
        margins[off] = {"n": len(ws), "mean_miss": r1(st.mean(w["miss"] for w in ws), 2),
                        "mean_abs": r1(st.mean(abs(w["miss"]) for w in ws), 2),
                        "inside": sum(w["inside"] for w in ws),
                        "toward_d": sum(w["miss"] > 0 for w in ws)}


# seat totals: called seats, plus the leaders in uncalled races, against the forecast distribution
def chance_at_least(dist, k):
    return round(sum(q["p"] for q in dist if q["seats"] >= k), 4)


def chance_at_most(dist, k):
    return round(sum(q["p"] for q in dist if q["seats"] <= k), 4)


chambers = {}
fixed = {s: sum(1 for z in races if z["office"] == "HOUSE" and z["race_type"] == "same_party" and z.get("race_note") == s) for s in "DR"}
by_id = {z["race_id"]: z for z in races}
for off, key in (("HOUSE", "house"), ("SEN", "senate"), ("GOV", "gov")):
    ws = [w for w in rows if w["office"] == off]
    def party(w, side):  # an independent takes one party's slot (sides() in wsu.js): D slot if a Republican is running
        z = by_id[w["id"]]
        if z["race_type"] == "independent" and side == ("D" if z.get("rep_candidate") else "R"):
            return "I"
        return side
    c = {"D": 0, "R": 0, "I": 0}
    lead = {"D": 0, "R": 0, "I": 0}
    for w in ws:
        if w["called"]:
            c[party(w, w["called"])] += 1
        elif w["margin"] is not None and votes(w):
            lead[party(w, "D" if w["margin"] > 0 else "R")] += 1
    base_d = fixed["D"] if off == "HOUSE" else senate_base if off == "SEN" else 0
    base_r = fixed["R"] if off == "HOUSE" else 100 - senate_base - len(ws) if off == "SEN" else 0  # seats not up this year
    dist = seats["house" if off == "HOUSE" else "senate" if off == "SEN" else "governor"]
    d_called = base_d + c["D"]
    chambers[off] = {
        "d_called": d_called, "r_called": base_r + c["R"], "i_called": c["I"],
        "uncalled": sum(1 for w in ws if not w["called"]), "d_leading": lead["D"], "r_leading": lead["R"], "i_leading": lead["I"],
        "median": top[f"{key}_median"], "p10": top[f"{key}_p10"], "p90": top[f"{key}_p90"],
        "p_control_d": top.get(f"p_{key}_d"),
        "p_at_least_called": chance_at_least(dist, d_called),
        "p_at_least_with_leaders": chance_at_least(dist, d_called + lead["D"]),
        "seats_total": 435 if off == "HOUSE" else 100 if off == "SEN" else len(ws),
    }

# other forecasters, on the races each one rated that have been called. The main comparison uses our own
# published ratings (Safe/Likely/Lean/Toss-up; Toss-up = 40-60%), the same kind of call the raters make. A second
# yardstick scores every call as a probability (Brier score), turning categories into chances with a common
# convention (CAT_P), so a confident miss costs more than a Toss-up. Our probability picks are kept alongside.
CAT_P = {"Safe": .975, "Likely": .875, "Lean": .70, "Tilt": .55}


def cat_p(rating):
    if rating == "Toss-up":
        return .5
    k, side = rating.split()
    return CAT_P[k] if side == "D" else 1 - CAT_P[k]


def brier(ws, prob):
    return round(sum((prob(w) - (w["called"] == "D")) ** 2 for w in ws) / len(ws), 4)


for w in rows:
    w["rating"] = by_id[w["id"]]["rating"]
our_pick = lambda w: PICK[w["rating"]]


def grade(ws, pick):
    right = sum(pick(w) == w["called"] for w in ws)
    toss = sum(pick(w) is None for w in ws)
    return {"right": right, "wrong": len(ws) - right - toss, "toss": toss}


ours_all = grade(called, our_pick) | {"brier_cat": brier(called, lambda w: cat_p(w["rating"]))}
comp = []
for o in outlets["outlets"]:
    name = o["name"]
    ws = [w for w in called if name in (w.get("outlets") or {})]
    if not ws:
        continue
    pick = lambda w: PICK[w["outlets"][name]]
    toss = [w for w in ws if pick(w) is None and our_pick(w)]
    dis = [w for w in ws if pick(w) and our_pick(w) and pick(w) != our_pick(w)]
    comp.append({
        "name": name, "short": o["short"], "kind": o["kind"], "rated_on": o["rated_on"], "n": len(ws),
        **grade(ws, pick), "brier_cat": brier(ws, lambda w: cat_p(w["outlets"][name])),
        "ours": grade(ws, our_pick) | {"brier_cat": brier(ws, lambda w: cat_p(w["rating"])), "brier": brier(ws, lambda w: w["p"])},
        "ours_odds": {"right": sum(w["right"] for w in ws), "wrong": sum(not w["right"] and w["fav"] is not None for w in ws)},
        "toss_we_picked": len(toss), "toss_ours_right": sum(our_pick(w) == w["called"] for w in toss),
        "disagree": [{"id": w["id"], "theirs": w["outlets"][name], "ours": w["rating"], "ours_right": our_pick(w) == w["called"]} for w in dis],
    })
ws = [w for w in called if "pi" in w]
if ws:
    # a market gives probabilities, so it's compared with our probabilities
    pi_fav = lambda w: "D" if w["pi"] > .5 else "R" if w["pi"] < .5 else None
    comp.append({
        "name": "PredictIt", "short": "PredictIt", "kind": "market", "rated_on": markets["asof"], "n": len(ws),
        **grade(ws, pi_fav), "brier": brier(ws, lambda w: w["pi"]),
        "ours": grade(ws, lambda w: w["fav"]) | {"brier": brier(ws, lambda w: w["p"])},
        "ours_odds": {"right": sum(w["right"] for w in ws), "wrong": sum(not w["right"] and w["fav"] is not None for w in ws)},
        "toss_we_picked": 0, "toss_ours_right": 0,
        "disagree": [{"id": w["id"], "theirs": round(w["pi"], 3), "ours": None, "ours_right": w["right"]}
                     for w in ws if pi_fav(w) and w["fav"] and pi_fav(w) != w["fav"]],
    })
markets_ctl = {k: markets["races"][f"control-{k}"]["p"] for k in ("house", "senate") if f"control-{k}" in markets["races"]}

out = {
    "asof": live["asof"], "source": live.get("source", "civicAPI"), "forecast_date": top["forecast_date"],
    "called": len(called), "contested": len(rows),
    "summary": summary, "calibration": calib, "margins": margins, "chambers": chambers,
    "ours_ratings": ours_all, "cat_p": CAT_P, "forecasters": comp, "markets_control": markets_ctl, "races": rows,
}
json.dump(out, open(os.path.join(D, "scorecard.json"), "w", encoding="utf-8"), separators=(",", ":"))

# a readable summary for whoever ran it
s = summary["all"]
print(f"counts as of {live['asof']}: {len(called)} of {len(rows)} contested races called")
print(f"favorite won {s['right']} of {s['n']} (expected {s['expected_right']}), Brier {s['brier']}; "
      f"D favorites {summary['fav_D']['won']}/{summary['fav_D']['n']}, R favorites {summary['fav_R']['won']}/{summary['fav_R']['n']}, coin flips {summary['coin_flips']}")
for c in calib:
    print(f"  favorites {c['lo']:.0%}-{c['hi']:.0%}: {c['won']}/{c['n']} (said {c['said']:.0%})")
for k, v in margins.items():
    print(f"  margins {k}: n {v['n']}, mean miss {v['mean_miss']:+} (D+ = toward Democrats), mean abs {v['mean_abs']}, inside 80% {v['inside']}")
for k, v in chambers.items():
    print(f"  {k}: {v}")
print("our ratings, all called:", ours_all)
for c in comp:
    print(f"  {c['short']:16} n {c['n']:3} theirs {c['right']}/{c['wrong']}/{c['toss']} score {c.get('brier_cat', c.get('brier'))} | ours {c['ours']} | disagreements {len(c['disagree'])}, ours right {sum(d['ours_right'] for d in c['disagree'])} | their toss-ups we picked {c['toss_ours_right']}/{c['toss_we_picked']}")
print("misses:", [w["id"] for w in called if not w["right"]])
