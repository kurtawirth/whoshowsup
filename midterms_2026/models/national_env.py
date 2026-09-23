"""National environment: the president's party's national House margin.

Three independent reads on the same unknown number, each calibrated on history:

  1. FUNDAMENTALS   y = a + b_mid * midterm + b_app * net_approval + noise_F
                    (1978-2024; the classic "referendum on the president")
  2. GENERIC BALLOT y = generic + bias_G + noise_G            (1996-2024)
  3. SPECIALS       y = specials_implied + bias_S + noise_S    (2018-2022 only)

Frames matter. Fundamentals are about the PRESIDENT'S party (a referendum),
so that equation is fit in president's-party terms. The poll-type reads carry
biases toward a PARTY regardless of who is president -- generic-ballot polls
and low-turnout special electorates have historically leaned Democratic -- so
their bias is fit in D-minus-R terms. (Fitting the specials bias in president's-
party terms made it flip sign between 2020 and 2022 and look like noise.)
Everything is combined in D-R terms, as of the forecast date (Sept 22).

Each equation is fit as a small Bayesian regression (NumPyro), so we get not
just a best guess for its bias and noise but a full range of plausible values.
The 2026 estimate combines the three reads by inverse-variance weighting: a
read that historically missed by less gets proportionally more say. Because
the specials equation rests on only three elections, its noise has a wide
prior -- the model is forced to be humble about it.

Backtest: leave-one-election-out for every year that has the needed inputs,
comparing the predicted interval to what actually happened.
"""
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np
import numpyro
import numpyro.distributions as dist
import pandas as pd
from numpyro.infer import MCMC, NUTS

numpyro.set_host_device_count(1)
ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
OUT = ROOT / "midterms_2026" / "outputs"
DRAWS = 2000


def load() -> pd.DataFrame:
    df = pd.read_csv(PROC / "national_history.csv")
    sign = np.where(df["pres_party"] == "D", 1, -1)
    # Net approval is already the president's own; flip the D-R margins to the president's party.
    df["sign"] = sign
    df["y_pp"] = sign * df["house_margin"]   # president's-party frame (fundamentals)
    df["y"] = df["house_margin"]             # D-R frame (poll reads, combination)
    df["midterm"] = df["midterm"].astype(float)
    return df


# ---------- the three measurement models ----------

def fundamentals_model(midterm, net_app, y=None):
    a = numpyro.sample("a", dist.Normal(0, 5))
    b_mid = numpyro.sample("b_mid", dist.Normal(-3, 5))    # prior: midterms usually hurt the president's party
    b_app = numpyro.sample("b_app", dist.Normal(0.1, 0.2))  # points of margin per point of net approval
    sigma = numpyro.sample("sigma", dist.HalfNormal(6))
    numpyro.sample("obs", dist.Normal(a + b_mid * midterm + b_app * net_app, sigma), obs=y)


# How noisy do we believe the specials read is BEFORE seeing its (only three) data
# points? None = weak prior (let the 3 elections speak); a number = a prior centered
# on that many points of noise. This is a judgment call the user decides.
SPECIALS_NOISE_PRIOR = None


def offset_model(signal, y=None, bias_sd=3.0, sigma_sd=4.0, sigma_center=None):
    """y = signal + bias + noise -- used for the generic ballot and specials."""
    bias = numpyro.sample("bias", dist.Normal(0, bias_sd))
    sigma = numpyro.sample("sigma", dist.HalfNormal(sigma_sd) if sigma_center is None
                           else dist.LogNormal(np.log(sigma_center), 0.35))
    numpyro.sample("obs", dist.Normal(signal + bias, sigma), obs=y)


def _fit(model, seed=0, **data):
    mcmc = MCMC(NUTS(model), num_warmup=1000, num_samples=DRAWS, progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed), **{k: jnp.asarray(v, dtype=jnp.float32) for k, v in data.items()})
    return {k: np.asarray(v) for k, v in mcmc.get_samples().items()}


def fit_reads(train: pd.DataFrame) -> dict:
    f = train.dropna(subset=["net_approval", "y"])
    g = train.dropna(subset=["generic_margin", "y"])
    s = train.dropna(subset=["specials_implied", "y"])
    reads = {"fundamentals": ("F", _fit(fundamentals_model, 1, midterm=f["midterm"], net_app=f["net_approval"], y=f["y_pp"])),
             "generic": ("G", _fit(offset_model, 2, signal=g["generic_margin"], y=g["y"]))}
    if len(s) >= 2:
        reads["specials"] = ("S", _fit(lambda signal, y=None: offset_model(signal, y, bias_sd=4.0, sigma_sd=4.0,
                                                                                sigma_center=SPECIALS_NOISE_PRIOR),
                                       3, signal=s["specials_implied"], y=s["y"]))
    return reads


def predict(reads: dict, row: pd.Series, rng: np.random.Generator) -> dict:
    """Combine the reads available for `row` into draws of the national margin."""
    means, variances, parts = [], [], {}
    for name, (_, p) in reads.items():
        if name == "fundamentals":
            if pd.isna(row["net_approval"]):
                continue
            mu = row["sign"] * (p["a"] + p["b_mid"] * row["midterm"] + p["b_app"] * row["net_approval"])
        elif name == "generic":
            if pd.isna(row["generic_margin"]):
                continue
            mu = row["generic_margin"] + p["bias"]
        else:
            if pd.isna(row["specials_implied"]):
                continue
            mu = row["specials_implied"] + p["bias"]
        means.append(mu)
        variances.append(p["sigma"] ** 2)
        parts[name] = (float(np.mean(mu)), float(np.mean(p["sigma"])))
    means, prec = np.array(means), 1 / np.array(variances)
    w = prec / prec.sum(axis=0)
    mu = (w * means).sum(axis=0)
    sd = np.sqrt(1 / prec.sum(axis=0))
    draws = rng.normal(mu, sd)
    weights = {k: float(np.mean(wi)) for k, wi in zip(parts, w)}
    return {"draws": draws, "parts": parts, "weights": weights}


def backtest(df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for yr in df.loc[df["y"].notna() & df["net_approval"].notna() & (df["year"] >= 1996), "year"]:
        train = df[(df["year"] != yr) & df["y"].notna()]
        res = predict(fit_reads(train), df[df["year"] == yr].iloc[0], rng)
        d, actual = res["draws"], df.loc[df["year"] == yr, "y"].iloc[0]
        lo, hi = np.percentile(d, [10, 90])
        rows.append({"year": yr, "actual": actual, "predicted": d.mean(), "error": d.mean() - actual,
                     "p10": lo, "p90": hi, "inside_80": lo <= actual <= hi,
                     "reads_used": "+".join(res["weights"])})
    return pd.DataFrame(rows)


def main() -> None:
    df = load()
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 200)

    print("=== Backtest (leave one election out, as of Sept 22) ===")
    bt = backtest(df)
    print(bt.round(1).to_string(index=False))
    print(f"Mean abs error {bt['error'].abs().mean():.1f} pts | 80% interval hit rate "
          f"{bt['inside_80'].mean():.0%} (should be ~80%)")
    bt.to_csv(OUT / "national_env_backtest.csv", index=False)

    print("\n=== 2026 ===")
    reads = fit_reads(df[df["y"].notna()])
    for name, (_, p) in reads.items():
        summ = {k: f"{v.mean():.2f} [{np.percentile(v, 5):.2f}, {np.percentile(v, 95):.2f}]" for k, v in p.items()}
        print(f"{name:>12}: {summ}")
    row = df[df["year"] == 2026].iloc[0]
    res = predict(reads, row, np.random.default_rng(2026))
    d = res["draws"]
    for name, (m, s) in res["parts"].items():
        print(f"  {name:>12} read: D{m:+.1f} (historical noise +/-{s:.1f}), weight {res['weights'][name]:.0%}")
    print(f"  Combined national House margin: D{d.mean():+.1f}  "
          f"(80% interval D{np.percentile(d, 10):+.1f} to D{np.percentile(d, 90):+.1f})")
    pd.DataFrame({"dem_margin": d}).to_csv(OUT / "national_env_2026_draws.csv", index=False)


if __name__ == "__main__":
    main()
