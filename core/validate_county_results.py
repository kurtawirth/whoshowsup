"""Compare county_results.parquet (summed to state) against MEDSL state-level
official totals. Prints every race whose total, DEM, or REP votes differ by
more than the tolerance, so data problems are visible rather than silent."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOL = 2.0  # percent


def state_reference() -> pd.DataFrame:
    rows = []
    for f, office in [("senate_1976_2024.csv", "SEN"), ("president_1976_2024.csv", "PRES")]:
        s = pd.read_csv(ROOT / "data" / "raw" / "medsl" / f, encoding="latin-1")
        s = s[s["year"] >= 2000]
        if "stage" in s:
            s = s[s["stage"].str.lower() == "gen"]
        s["special"] = s.get("special", False)
        s["special"] = s["special"].astype(str).str.upper().eq("TRUE")
        g = s.groupby(["year", "state_po", "special"])
        ref = pd.DataFrame({
            "ref_total": g["totalvotes"].first(),
            "ref_dem": s[s.party_simplified == "DEMOCRAT"].groupby(["year", "state_po", "special"])["candidatevotes"].sum(),
            "ref_rep": s[s.party_simplified == "REPUBLICAN"].groupby(["year", "state_po", "special"])["candidatevotes"].sum(),
        }).reset_index()
        rows.append(ref.assign(office=office))
    return pd.concat(rows)


def main() -> None:
    c = pd.read_parquet(ROOT / "data" / "processed" / "county_results.parquet")
    got = c.groupby(["year", "state_po", "office", "special"])[["dem", "rep", "total"]].sum().reset_index()
    m = got.merge(state_reference(), on=["year", "state_po", "office", "special"], how="outer")
    have = set(zip(c["year"], c["office"]))
    m = m[[(y, o) in have for y, o in zip(m["year"], m["office"])]]
    m = m[m["state_po"] != "AK"]  # Alaska reports by legislative district, not county
    for a, b in [("total", "ref_total"), ("dem", "ref_dem"), ("rep", "ref_rep")]:
        m[f"d_{a}"] = (m[a] / m[b] - 1) * 100
    bad = m[(m[["d_total", "d_dem", "d_rep"]].abs() > TOL).any(axis=1) | m["total"].isna()]
    pd.set_option("display.width", 200)
    print(bad[["year", "state_po", "office", "special", "d_total", "d_dem", "d_rep"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
