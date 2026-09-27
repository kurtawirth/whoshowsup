"""Who are undecided voters, do they show up, and what moves them? Cooperative Election Study, 2006-2024.

    .venv/Scripts/python.exe core/ces_undecided.py

Source: Cumulative CES Common Content 2006-2025 (Kuriwaki, Harvard Dataverse doi:10.7910/DVN/II2DB6,
CC0), data/raw/ces/cumulative_2006-2025.feather. Each even-year respondent is interviewed before the
election and again after; the study checks state voter files to record whether each person actually
voted ("validated turnout", vv_turnout_gvm).

  undecided (UN)   answered "Not sure" when asked before the election how they'd vote for the House
  decided          named the Democrat or the Republican
  voted            the voter file shows a vote in the general election
  broke            among UNs with a validated vote who reported a Democratic or Republican House vote
  economy_worse    the national economy "over the past year" got somewhat/much worse (economy_retro 4-5)
  hardship         unemployed or temporarily laid off, or without health insurance (a personal kitchen-table
                   measure; the cumulative file has no "household better or worse off" question)

Findings (2026-09-27): UNs vote at about half the rate of decided voters; when they vote they break
toward the party out of the White House in every midterm (6-11 points, including 2018); thinking the
economy got worse doesn't change their turnout, while personal hardship (jobless, uninsured) lowers it
by ~15 points; but economic views strongly predict which way they break (50-75 points apart) -- an
effect already carried by the national mood, since the year's share saying "worse" doesn't predict the
year's break. Young (D+17) and Hispanic (D+25) UNs lean far more Democratic than others but vote less.

All shares are weighted (vvweight_post when present, else weight_post, else weight). Writes
data/processed/ces_undecided_years.csv and prints the findings.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
PRES = {2006: "R", 2008: "R", 2010: "D", 2012: "D", 2014: "D", 2016: "D", 2018: "R", 2020: "R", 2022: "D", 2024: "D"}
COLS = ["year", "weight", "weight_post", "vvweight_post", "tookpost", "citizen", "intent_rep", "voted_rep_party", "vv_turnout_gvm",
        "economy_retro", "employ", "no_healthins", "faminc", "age", "race", "hispanic", "educ", "pid7", "newsint",
        "approval_pres"]


def load() -> pd.DataFrame:
    d = pd.read_feather(ROOT / "data" / "raw" / "ces" / "cumulative_2006-2025.feather", columns=COLS)
    d = d[d.year.isin(PRES) & (d.tookpost == 1) & d.vv_turnout_gvm.notna()].copy()
    d = d[d.citizen != 2]  # 1 = citizen, 2 = non-citizen (a few are missing)
    d["w"] = d.vvweight_post.fillna(d.weight_post).fillna(d.weight).fillna(0)
    ir = d.intent_rep.astype(str)
    d["group"] = np.select([ir.str.contains("Democrat"), ir.str.contains("Republican"), ir.eq("Not Sure")],
                           ["D", "R", "UN"], "other")
    d["voted"] = (d.vv_turnout_gvm.astype(str) == "Voted").astype(float)
    vr = d.voted_rep_party.astype(str)
    d["vote"] = np.select([vr.eq("Democratic"), vr.eq("Republican")], [1.0, -1.0], np.nan)  # D=+1, R=-1
    d["economy_worse"] = np.where(d.economy_retro.between(1, 5), (d.economy_retro >= 4).astype(float), np.nan)
    d["hardship"] = (d.employ.astype(str).isin(["Unemployed", "Temporarily Laid Off"])
                     | (d.no_healthins.astype(str) == "Yes")).astype(float)  # "Yes" = has NO health insurance
    d["young"] = (d.age < 30).astype(float)
    d["hisp"] = ((d.hispanic == 1) | (d.race.astype(str) == "3")).astype(float)  # hispanic 1 = yes; race 3 = Hispanic
    d["pres_party"] = d.year.map(PRES)
    d["midterm"] = (d.year % 4 == 2).astype(float)
    return d


def wmean(x, w):
    m = x.notna() & (w > 0)
    return float(np.average(x[m], weights=w[m])) if m.any() else np.nan


def main() -> None:
    d = load()
    pd.set_option("display.width", 220)
    print(f"{len(d):,} respondents with a validated vote record, {d.year.nunique()} election years\n")

    rows = []
    for y, g in d.groupby("year"):
        un, dec = g[g.group == "UN"], g[g.group.isin(["D", "R"])]
        brk = un[(un.voted == 1) & un.vote.notna()]
        decv = dec[(dec.voted == 1) & dec.vote.notna()]
        against = -1 if PRES[y] == "D" else 1  # sign: + = toward the party out of the White House
        rows.append({
            "year": y, "pres": PRES[y], "UN_share": wmean((g.group == "UN").astype(float), g.w),
            "UN_turnout": wmean(un.voted, un.w), "decided_turnout": wmean(dec.voted, dec.w),
            "UN_break_D_minus_R": 100 * wmean(brk.vote, brk.w), "decided_margin": 100 * wmean(decv.vote, decv.w),
            "UN_break_toward_out_party": 100 * wmean(brk.vote, brk.w) * against,
            "UN_econ_worse": wmean(un.economy_worse, un.w), "all_econ_worse": wmean(g.economy_worse, g.w),
            "UN_n": len(un), "UN_voters_reporting": len(brk)})
    yr = pd.DataFrame(rows)
    yr.to_csv(PROC / "ces_undecided_years.csv", index=False)
    print("1-2. Undecided House voters by year (UN = 'Not sure' before the election):")
    print(yr.round(3).to_string(index=False))

    print("\nWho are the UNs? (weighted shares, all years)")
    un = d[d.group == "UN"]
    dec = d[d.group.isin(["D", "R"])]
    for name, col in [("under 30", "young"), ("Hispanic", "hisp"), ("think the economy got worse", "economy_worse"),
                      ("personal hardship", "hardship")]:
        print(f"  {name:<30} UNs {wmean(un[col], un.w):.0%}   decided {wmean(dec[col], dec.w):.0%}")
    ind = d.pid7.isin([4, 8])  # 4 = independent, 8 = not sure
    print(f"  {'independent / not sure (party)':<30} UNs {wmean(ind[un.index].astype(float), un.w):.0%}   "
          f"decided {wmean(ind[dec.index].astype(float), dec.w):.0%}")

    # 3. Do economic opinions and hardship move turnout -- more for UNs than decided voters?
    print("\n3. Validated turnout by economic view (weighted), UNs vs decided:")
    for name, g in [("UN", un), ("decided", dec)]:
        worse = wmean(g[g.economy_worse == 1].voted, g[g.economy_worse == 1].w)
        notw = wmean(g[g.economy_worse == 0].voted, g[g.economy_worse == 0].w)
        hard = wmean(g[g.hardship == 1].voted, g[g.hardship == 1].w)
        nohard = wmean(g[g.hardship == 0].voted, g[g.hardship == 0].w)
        print(f"  {name:<8} economy worse {worse:.0%} vs not {notw:.0%} (gap {100*(worse-notw):+.1f} pts);   "
              f"hardship {hard:.0%} vs none {nohard:.0%} (gap {100*(hard-nohard):+.1f} pts)")
    # within-year version (so it isn't just 'bad-economy years have different turnout')
    gaps = []
    for y, g in un.groupby("year"):
        a, b = g[g.economy_worse == 1], g[g.economy_worse == 0]
        gaps.append({"year": y, "UN_turnout_gap_econ_worse": 100 * (wmean(a.voted, a.w) - wmean(b.voted, b.w))})
    print("  Within each year, UNs who think the economy got worse vs not (turnout gap, pts):",
          {int(r["year"]): round(r["UN_turnout_gap_econ_worse"], 1) for r in gaps})

    # 4. Direction: among UNs who voted, does 'economy worse' push them against the president's party?
    print("\n4. How UNs who voted broke, by economic view (+ = toward the party OUT of the White House):")
    v = un[(un.voted == 1) & un.vote.notna()].copy()
    v["toward_out"] = v.vote * np.where(v.pres_party == "D", -1, 1)
    for y, g in v.groupby("year"):
        a, b = g[g.economy_worse == 1], g[g.economy_worse == 0]
        print(f"  {y} ({PRES[y]} president): economy worse {100*wmean(a.toward_out, a.w):+6.1f}  (n={len(a):>4})   "
              f"not worse {100*wmean(b.toward_out, b.w):+6.1f}  (n={len(b):>4})")

    # 5. Young and Hispanic UNs
    print("\n5. Young and Hispanic UNs:")
    for name, col in [("under 30", "young"), ("Hispanic", "hisp")]:
        s = un[un[col] == 1]
        sv = s[(s.voted == 1) & s.vote.notna()]
        o = un[un[col] == 0]
        ov = o[(o.voted == 1) & o.vote.notna()]
        print(f"  {name:<9} turnout {wmean(s.voted, s.w):.0%} (other UNs {wmean(o.voted, o.w):.0%});   "
              f"broke D{100*wmean(sv.vote, sv.w):+.0f} (other UNs D{100*wmean(ov.vote, ov.w):+.0f})   n={len(s):,}")

    print("\nYear-level link: UN break toward the out-party vs share of all respondents saying the economy got worse")
    print("  correlation:", round(yr.UN_break_toward_out_party.corr(yr.all_econ_worse), 2),
          "| midterms only:", round(yr[yr.year % 4 == 2].UN_break_toward_out_party.corr(yr[yr.year % 4 == 2].all_econ_worse), 2))
    print("  UN turnout vs economy-worse share, correlation:", round(yr.UN_turnout.corr(yr.all_econ_worse), 2))


if __name__ == "__main__":
    main()
