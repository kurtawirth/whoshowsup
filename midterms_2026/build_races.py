"""Build the 2026 race lists: House, Senate, Governor.

Sources (cached in data/raw/):
  - Wikipedia 2026 overview pages: incumbents, status, general-election candidates.
    Only the candidate/incumbent tables are read; the ratings tables (Cook, Sabato,
    etc.) are deliberately ignored -- the model does not use other forecasters.
  - The Downballot: 2024 (and, where lines are unchanged, 2020) presidential
    results by congressional district on the 2026 lines.
  - MEDSL: statewide presidential results, for Senate/Governor partisan lean.

Outputs (data/processed/):
  races_2026_house.csv, races_2026_senate.csv, races_2026_governor.csv
  races_2026_review.csv  every non-standard race (see classify()) for a human look
"""
from pathlib import Path
import io
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
WIKI = RAW / "wikipedia"

STATE_PO = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
    "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
PARTY = {"Democratic": "D", "Republican": "R"}
# State affiliates of the national parties that Wikipedia labels by local name.
DEM_LABELS = {"Democratic", "DFL", "Democratic-NPL", "Democratic–NPL"}


def _tables(page: str) -> list[pd.DataFrame]:
    html = (WIKI / f"{page}.html").read_text(encoding="utf-8")
    out = []
    for tb in pd.read_html(io.StringIO(html)):
        if isinstance(tb.columns, pd.MultiIndex):
            tb.columns = [re.sub(r"\[.*?\]", "", c[-1]).strip() for c in tb.columns]
        else:
            tb.columns = [re.sub(r"\[.*?\]", "", str(c)).strip() for c in tb.columns]
        out.append(tb)
    return out


def clean(s) -> str:
    s = re.sub(r"\s+", " ", str(s).replace(" ", " "))
    return re.sub(r"\[.*?\]", "", s).strip()


def party_code(p) -> str:
    p = clean(p)
    return "D" if p in DEM_LABELS else "R" if p == "Republican" else p


# Hand-reviewed special cases. Each race gets a race_type the model understands:
#   standard     one Democrat vs one Republican
#   same_party   only one party can win (CA top-two D-vs-D / R-vs-R, or no opponent)
#   jungle       several candidates per party on one ballot (LA House); party blocs compete
#   rcv_bloc     Alaska top-four + ranked choice; Democratic bloc vs Republican bloc
#   independent  the main opposition to one party is an independent
INDEPENDENT_OPPONENTS = {
    ("SEN", "NE", None): "Dan Osborn",       # runs against Ricketts; no Democrat on the ballot
    ("HOUSE", "CA", 6): "Kevin Kiley",       # ex-Republican, now running as independent vs a Democrat
    # Alaska's top-four ballot: Begich's real opponent is independent Bill Hill (DCCC "Red to Blue";
    # 33% in the primary to Begich's 44%), not Democrat Eric Hafner (~10% in polls). Hill won't say
    # which party he'd caucus with, so, like Osborn, a Hill win counts for neither party.
    ("HOUSE", "AK", 0): "Bill Hill",
}


def classify(df: pd.DataFrame, office: str) -> pd.DataFrame:
    def one(r):
        key = (office, r["state_po"], r.get("district") if office == "HOUSE" else None)
        if key in INDEPENDENT_OPPONENTS:
            return "independent", INDEPENDENT_OPPONENTS[key]
        if r["state_po"] == "AK":
            return "rcv_bloc", ""
        if office == "HOUSE" and r["state_po"] == "LA" and (r["n_dem"] > 1 or r["n_rep"] > 1):
            return "jungle", ""
        if r["n_dem"] == 0 or r["n_rep"] == 0:
            return "same_party", "D" if r["n_dem"] else "R"
        return "standard", ""
    out = df.apply(one, axis=1, result_type="expand")
    return df.assign(race_type=out[0], race_note=out[1])


def parse_candidates(cell: str) -> list[tuple[str, str]]:
    """'▌Jon Ossoff (Democratic)[76] ▌Mike Collins (Republican)' -> [(name, party), ...]"""
    return [(m.group(1).strip(), m.group(2).strip())
            for m in re.finditer(r"▌+\s*([^▌(]+?)\s*\(([^)]+)\)", clean(cell))]


def major_candidates(cands: list[tuple[str, str]]) -> dict:
    d = [n for n, p in cands if p in DEM_LABELS]
    r = [n for n, p in cands if p == "Republican"]
    other = [f"{n} ({p})" for n, p in cands if p not in DEM_LABELS | {"Republican"}]
    return {"dem_candidate": "; ".join(d), "rep_candidate": "; ".join(r),
            "other_candidates": "; ".join(other), "n_dem": len(d), "n_rep": len(r)}


def build_house() -> pd.DataFrame:
    rows = []
    for tb in _tables("2026_United_States_House_of_Representatives_elections"):
        cols = list(tb.columns)
        if "Location" not in cols or not any(c.startswith("Candidates") for c in cols):
            continue
        cand_col = [c for c in cols if c.startswith("Candidates")][0]
        for _, r in tb.iterrows():
            loc = clean(r["Location"])
            m = re.match(r"(.+?) (\d+|at-large)$", loc, re.I)
            if not m or m.group(1) not in STATE_PO:
                continue
            rows.append({
                "state_po": STATE_PO[m.group(1)],
                "district": 0 if m.group(2).lower() == "at-large" else int(m.group(2)),
                "incumbent": clean(r["Member"]),
                "incumbent_party": party_code(r["Party"]),
                "status_text": clean(r["Status"]),
                **major_candidates(parse_candidates(r[cand_col])),
            })
    df = pd.DataFrame(rows)
    # A district can list several incumbents when redistricting paired them. Keep
    # one row per district and describe it: the seat is incumbent-held only if
    # some incumbent is actually on the November ballot there.
    def collapse(g):
        first = g.iloc[0].copy()
        on_ballot = [(inc, p) for inc, p in zip(g["incumbent"], g["incumbent_party"])
                     if re.sub(r"Redistricted from.*", "", inc).strip() in
                     (first["dem_candidate"] + ";" + first["rep_candidate"])]
        first["incumbent"] = on_ballot[0][0] if on_ballot else " / ".join(g["incumbent"])
        first["incumbent_party"] = on_ballot[0][1] if on_ballot else ""
        first["incumbent_running"] = bool(on_ballot)
        first["paired_incumbents"] = len(g)
        return first
    df = df.groupby(["state_po", "district"], as_index=False).apply(collapse, include_groups=False)
    df["incumbent"] = df["incumbent"].str.replace(r"\s*Redistricted from.*", "", regex=True)

    pres = load_pres_by_cd()
    df = df.merge(pres, on=["state_po", "district"], how="left", validate="one_to_one")
    return df.sort_values(["state_po", "district"]).reset_index(drop=True)


def load_pres_by_cd() -> pd.DataFrame:
    raw = pd.read_csv(RAW / "downballot" / "pres_by_cd_2026_lines.csv", header=None, skiprows=4, dtype=str)
    num = lambda s: pd.to_numeric(s.str.replace(r"[,%]", "", regex=True), errors="coerce")
    df = pd.DataFrame({
        "cd": raw[0], "harris24": num(raw[4]), "trump24": num(raw[5]), "total24": num(raw[6]),
        "biden20": num(raw[11]), "trump20": num(raw[12]), "total20": num(raw[13]),
    }).dropna(subset=["cd"])
    df = df[df["cd"].str.match(r"^[A-Z]{2}-(\d{2}|AL)$")]
    df["state_po"] = df["cd"].str[:2]
    df["district"] = df["cd"].str[3:].replace("AL", "00").astype(int)
    # Two-party Democratic margin, in points (positive = Harris/Biden ahead).
    df["pres24_margin"] = 100 * (df["harris24"] - df["trump24"]) / (df["harris24"] + df["trump24"])
    df["pres20_margin"] = 100 * (df["biden20"] - df["trump20"]) / (df["biden20"] + df["trump20"])
    df["lines_changed"] = df["biden20"].isna()  # Downballot leaves 2020 blank for redrawn districts
    return df.drop(columns="cd")


def statewide_pres() -> pd.DataFrame:
    p = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    p = p[p["year"].isin([2020, 2024]) & p["party_simplified"].isin(["DEMOCRAT", "REPUBLICAN"])]
    w = p.pivot_table(index=["state_po", "year"], columns="party_simplified", values="candidatevotes", aggfunc="sum")
    w["m"] = 100 * (w["DEMOCRAT"] - w["REPUBLICAN"]) / (w["DEMOCRAT"] + w["REPUBLICAN"])
    return w["m"].unstack("year").rename(columns={2020: "pres20_margin", 2024: "pres24_margin"}).reset_index()


def _statewide(page: str, office_col: str, want_cols: set) -> pd.DataFrame:
    rows = []
    for tb in _tables(page):
        if not want_cols <= set(tb.columns):
            continue
        cand_col = [c for c in tb.columns if c.startswith("Candidates")][0]
        status_col = "Results" if "Results" in tb.columns else "Status"
        for _, r in tb.iterrows():
            st = clean(r["State"])
            special = "Class 3" in st
            st = re.sub(r"\s*\(.*\)", "", st)
            if st not in STATE_PO:
                continue
            rows.append({
                "state_po": STATE_PO[st], "special": special,
                "incumbent": clean(r[office_col]),
                "incumbent_party": party_code(r["Party"]),
                "status_text": clean(r[status_col]),
                **major_candidates(parse_candidates(r[cand_col])),
            })
    df = pd.DataFrame(rows).drop_duplicates(["state_po", "special"])
    df["incumbent_running"] = [inc in (d + ";" + rp) or clean(inc).split()[-1] in (d + rp)
                               for inc, d, rp in zip(df["incumbent"], df["dem_candidate"], df["rep_candidate"])]
    return df.merge(statewide_pres(), on="state_po", how="left")


def main() -> None:
    house = build_house()
    senate = _statewide("2026_United_States_Senate_elections", "Senator", {"State", "Senator", "Party"})
    gov = _statewide("2026_United_States_gubernatorial_elections", "Governor", {"State", "Governor", "Party", "Candidates"})
    house, senate, gov = classify(house, "HOUSE"), classify(senate, "SEN"), classify(gov, "GOV")
    for name, df in [("house", house), ("senate", senate), ("governor", gov)]:
        df.to_csv(PROC / f"races_2026_{name}.csv", index=False)
    review = pd.concat([
        df[df["race_type"] != "standard"].assign(office=o)
        for o, df in [("HOUSE", house), ("SEN", senate), ("GOV", gov)]
    ])
    review.to_csv(PROC / "races_2026_review.csv", index=False)
    print(f"House: {len(house)} districts ({house['lines_changed'].sum()} on new lines, "
          f"{(~house['incumbent_running']).sum()} open, {house['pres24_margin'].isna().sum()} missing lean)")
    print(f"Senate: {len(senate)} races ({senate['special'].sum()} special); Governor: {len(gov)} races")
    print("Non-standard races:", review.groupby(["office", "race_type"]).size().to_dict())


if __name__ == "__main__":
    main()
