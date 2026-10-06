"""Tipping points and voter power, from the simulation's margin draws.

In each simulated election, line up the seats the winning side took, from its safest to its closest, and count
seats until it reaches a majority: the seat that gets it there is that simulation's tipping point. A race's
tipping-point chance is the share of simulations in which it was that seat. The chances add up to 100% across
the races (plus any simulations where an independent's win leaves neither party a majority; those go to the
independent's race, since its result decided control).

Voter power divides a race's tipping-point chance by the votes expected in it, then scales so the average voter
in the chamber's races scores 1: a score of 3 means a vote there is three times as likely as the average one to
decide control. It says nothing about whether any single vote will matter (that chance is tiny everywhere);
it compares places.

Written for any chamber or tally: Senate (weights 1, Democrats need 51, Republicans 50 with the vice president's
tiebreak), House (218/218), and later the Electoral College (weights = electoral votes, 270).
"""
import numpy as np


def tipping_point(margin: np.ndarray, weights: np.ndarray, base_d: float, base_r: float,
                  need_d: float, need_r: float, independent: np.ndarray | None = None) -> dict:
    """margin: (seats, sims) D-minus-R margins for the seats being decided (positive = Democrat, or the
    independent in an independent's race, wins). weights: seats or electoral votes per race. base_d/base_r:
    what each side holds before these races (holdovers and one-party races). need_d/need_r: what each side
    needs for control. independent: True for races where a win by the non-Republican is neither party's.

    Returns per-race `tipping` (share of simulations), the tipping seat's margin in each simulation
    (`tp_margin`, NaN when no one has a majority) and the share of simulations with no majority."""
    n, sims = margin.shape
    w = np.asarray(weights, dtype=float)
    ind = np.zeros(n, bool) if independent is None else np.asarray(independent, bool)
    d_won = (margin > 0) & ~ind[:, None]
    r_won = margin < 0
    d_tot = base_d + (w[:, None] * d_won).sum(axis=0)
    r_tot = base_r + (w[:, None] * r_won).sum(axis=0)

    tip = np.full(sims, -1)
    for won, tot, base, need, sign in ((d_won, d_tot, base_d, need_d, 1), (r_won, r_tot, base_r, need_r, -1)):
        ctrl = tot >= need
        if not ctrl.any():
            continue
        # the winner's seats, safest first; seats it lost sort last
        score = np.where(won[:, ctrl], sign * margin[:, ctrl], -np.inf)
        order = np.argsort(-score, axis=0)
        cum = base + np.cumsum(w[order], axis=0)
        k = (cum >= need).argmax(axis=0)              # first seat that reaches the majority
        tip[ctrl] = order[k, np.arange(ctrl.sum())]

    # no majority: an independent's win left both parties short, so the independent's race decided it
    none = tip < 0
    if none.any() and ind.any():
        ind_won = (margin > 0) & ind[:, None]
        first = np.where(ind_won[:, none].any(axis=0), ind_won[:, none].argmax(axis=0), -1)
        tip[none] = first
    counts = np.bincount(tip[tip >= 0], minlength=n)
    tp_margin = np.where(tip >= 0, margin[np.maximum(tip, 0), np.arange(sims)], np.nan)
    return {"tipping": counts / sims, "tp_margin": tp_margin, "p_no_majority": float(none.mean())}


def voter_power(tipping: np.ndarray, votes: np.ndarray) -> np.ndarray:
    """Tipping-point chance per expected vote, scaled so the average voter in these races scores 1.
    Include one-party races (tipping 0) in `votes` so their voters count in the average."""
    tipping, votes = np.asarray(tipping, float), np.asarray(votes, float)
    return (tipping / votes) / (tipping.sum() / votes.sum())
