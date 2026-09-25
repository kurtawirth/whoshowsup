"""How do House results deviate from presidential lean? (incumbency + district noise)

For each contested House race in 2018, 2020, and 2024 we compare the House
two-party margin with the district's presidential two-party margin (same
lines), after removing that year's national House-vs-president gap:

    resid[i,t] = house_margin[i,t] - pres_margin[i] - year_effect[t]
    resid      = inc_effect * incumbent_side[i,t] + noise   (noise sd by seat type)

incumbent_side = +1 if a Democratic incumbent is on the ballot, -1 for a
Republican incumbent, 0 for an open seat. An incumbent is the previous
winner in the same district, found by name, when district lines did not change.

Presidential margins by district come from The Downballot's recalculations:
2016 pres on 2012-2020 lines (House 2018), 2020 pres on the same lines
(House 2020), 2024 pres on 2024 lines for districts unchanged into 2026
(House 2024).

Output: data/processed/house_calibration.csv and a printed summary with the
incumbency advantage and the district-level noise the simulation will use.
"""
from pathlib import Path
import re

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = RAW / "downballot"


def house_results() -> pd.DataFrame:
    h = pd.read_csv(RAW / "medsl" / "house_1976_2024.tab", sep=None, engine="python", encoding="latin-1")
    h = h[(h["stage"].str.upper() == "GEN") & ~h["special"].astype(str).str.upper().eq("TRUE") & (h["year"] >= 2014)]
    h["party"] = h["party"].astype(str).str.upper()
    h["side"] = np.where(h["party"].str.contains("DEMOCRAT"), "D", np.where(h["party"].eq("REPUBLICAN"), "R", "O"))
    h["district"] = pd.to_numeric(h["district"], errors="coerce").fillna(0).astype(int)
    # Fusion voting (New York): a nominee's Conservative / Working Families / etc. lines count
    # for them. Give every line the side of the candidate's major-party line.
    major = h[h["side"] != "O"].groupby(["year", "state_po", "district", "candidate"])["side"].first()
    k = pd.MultiIndex.from_frame(h[["year", "state_po", "district", "candidate"]])
    h["side"] = np.where(h["side"] == "O", major.reindex(k).fillna("O").to_numpy(), h["side"])
    g = h.groupby(["year", "state_po", "district", "side"])["candidatevotes"].sum().unstack(fill_value=0)
    out = pd.DataFrame({"dem": g.get("D", 0), "rep": g.get("R", 0)}).reset_index()
    tot = h.groupby(["year", "state_po", "district", "candidate", "side"], as_index=False)["candidatevotes"].sum()
    winners = tot.sort_values("candidatevotes").groupby(["year", "state_po", "district"]).tail(1)
    cands = h.groupby(["year", "state_po", "district"])["candidate"].apply(lambda s: [_key(x) for x in s])
    out = out.merge(winners[["year", "state_po", "district", "candidate", "side"]].rename(
        columns={"candidate": "winner", "side": "winner_side"}), on=["year", "state_po", "district"])
    out = out.merge(cands.rename("cand_keys").reset_index(), on=["year", "state_po", "district"])
    out["house_margin"] = 100 * (out["dem"] - out["rep"]) / (out["dem"] + out["rep"])
    out["contested"] = (out["dem"] > 0) & (out["rep"] > 0)
    return out


def _key(name: str) -> str:
    """'JOHN Q. PUBLIC JR.' -> 'PUBLIC J' (last name + first initial) for fuzzy matching."""
    parts = [p for p in re.sub(r"[^A-Z ]", " ", str(name).upper()).split() if p not in {"JR", "SR", "II", "III", "IV"}]
    return f"{parts[-1]} {parts[0][0]}" if len(parts) >= 2 else " ".join(parts)


def _pres(file: str, col_d: int, col_r: int, skip: int) -> pd.DataFrame:
    raw = pd.read_csv(DB / file, header=None, skiprows=skip, dtype=str)
    num = lambda s: pd.to_numeric(s.str.replace(r"[,%]", "", regex=True), errors="coerce")
    df = pd.DataFrame({"cd": raw[0], "d": num(raw[col_d]), "r": num(raw[col_r])})
    df = df[df["cd"].str.match(r"^[A-Z]{2}-(\d{2}|AL)$", na=False)]
    df["state_po"] = df["cd"].str[:2]
    df["district"] = df["cd"].str[3:].replace("AL", "00").astype(int)
    df["pres_margin"] = 100 * (df["d"] - df["r"]) / (df["d"] + df["r"])
    return df[["state_po", "district", "pres_margin"]]


def main() -> None:
    hr = house_results()
    pres = {
        2018: _pres("1VfkHtzB_0.csv", 3, 4, 2),    # 2016 pres, 2012-2020 lines
        2020: _pres("1XbUXnI9_0.csv", 3, 4, 2),    # 2020 pres, 2012-2020 lines
        2024: None,
    }
    lines26 = pd.read_csv(ROOT / "data" / "processed" / "races_2026_house.csv")
    pres[2024] = lines26.loc[~lines26["lines_changed"], ["state_po", "district", "pres24_margin"]].rename(
        columns={"pres24_margin": "pres_margin"})

    rows = []
    for y, p in pres.items():
        cur = hr[hr["year"] == y].merge(p, on=["state_po", "district"])
        prev = hr[hr["year"] == y - 2][["state_po", "district", "winner", "winner_side"]]
        cur = cur.merge(prev, on=["state_po", "district"], how="left", suffixes=("", "_prev"))
        on_ballot = [isinstance(w, str) and _key(w) in keys for w, keys in zip(cur["winner_prev"], cur["cand_keys"])]
        cur["incumbent_side"] = np.where(on_ballot, np.where(cur["winner_side_prev"] == "D", 1, -1), 0)
        if y == 2020:
            cur = cur[cur["state_po"] != "NC"]  # NC redrew its map for 2020
        rows.append(cur)
    df = pd.concat(rows)
    df = df[df["contested"]].copy()
    df["resid_raw"] = df["house_margin"] - df["pres_margin"]
    df.to_csv(ROOT / "data" / "processed" / "house_calibration.csv", index=False)

    m = smf.ols("resid_raw ~ C(year) + incumbent_side", data=df).fit()
    df["resid"] = m.resid
    print(m.summary().tables[1])
    print(f"\nIncumbency advantage: {m.params['incumbent_side']:.2f} pts of margin (se {m.bse['incumbent_side']:.2f})")
    for y in sorted(df["year"].unique()):
        print(f"  {y}: n={int((df.year == y).sum())}, incumbency-only fit ->",
              f"{smf.ols('resid_raw ~ incumbent_side', data=df[df.year == y]).fit().params['incumbent_side']:.2f}")
    open_ = df["incumbent_side"] == 0
    print(f"District noise (sd of residual): incumbent races {df.loc[~open_, 'resid'].std():.2f}, "
          f"open seats {df.loc[open_, 'resid'].std():.2f}  (n open = {open_.sum()})")
    close = df["pres_margin"].abs() < 15
    print(f"  in competitive districts (|pres| < 15): incumbent {df.loc[~open_ & close, 'resid'].std():.2f}, "
          f"open {df.loc[open_ & close, 'resid'].std():.2f}")


if __name__ == "__main__":
    main()
