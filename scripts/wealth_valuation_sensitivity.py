"""How much the top of the wealth distribution, and a tax on it, depend on how shares are valued (1.1).

The tax returns the wealth spread is fitted to value listed and unlisted shares at nominal value, not market value,
and most of the shares are held at the top, so the returns understate the richest families' net worth. The
population is drawn once, before any year runs, so this cannot be a lever on the surface; instead the same
population is drawn with the richest 1%'s savings and other assets multiplied by `top_share_valuation`, the national
total pinned again each time, and the base of a net wealth tax above the 100 m.kr. threshold compared.

  python scripts/wealth_valuation_sensitivity.py            # factors 1, 1.5, 2 and 3
"""
import copy
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ubisim.abm import params, population  # noqa: E402


def family_net_worth(A):
    """Net worth by family as the returns count it: a couple together, every other adult alone."""
    worth = A["wealth"] + np.maximum(A["home_value"] - A["mortgage_debt"], 0)
    adult = A["alive"] & (A["age"] >= 16)
    partner = A["partner"]
    lead = adult & ((partner < 0) | (np.arange(len(partner)) < partner))
    fam = worth[lead] + np.where(partner[lead] >= 0, worth[np.maximum(partner[lead], 0)], 0)
    return fam


def summary(k, seed=1):
    p = copy.deepcopy(params.DEFAULTS)
    p["wealth"]["top_share_valuation"] = k
    A = population.build(p, np.random.default_rng(seed))
    fam = np.sort(family_net_worth(A))
    total = fam.sum()
    n = len(fam)
    top10, top1 = fam[int(.9 * n):].sum() / total, fam[int(.99 * n):].sum() / total
    worth = A["wealth"] + np.maximum(A["home_value"] - A["mortgage_debt"], 0)
    adults = A["alive"] & (A["age"] >= 18)
    thr = p["policy"]["net_wealth_tax_threshold"]
    base = np.maximum(worth[adults] - thr, 0).sum() / 1e9
    return {"k": k, "top10": top10, "top1": top1, "median": float(np.median(fam)) / 1e6,
            "payers": int((worth[adults] > thr).sum()), "base": base}


def main():
    rows = [summary(k) for k in (1.0, 1.5, 2.0, 3.0)]
    print("Shares at the top valued at k times the returns' figure (savings and other assets of the richest 1%)")
    print(f"{'k':>4} {'richest tenth':>14} {'richest 1%':>11} {'median family':>14} "
          f"{'above 100 m.kr.':>16} {'taxable base':>13}")
    for r in rows:
        print(f"{r['k']:>4.1f} {r['top10']:>13.1%} {r['top1']:>11.1%} {r['median']:>10.1f} m.kr. "
              f"{r['payers']:>16,} {r['base']:>9,.0f} ma.kr.")
    b0 = rows[0]["base"]
    print("\nA 1% net wealth tax above 100 m.kr. raises, before avoidance: "
          + ", ".join(f"{r['base'] / 100:.1f} ma.kr. at k={r['k']:g}" for r in rows)
          + f" ({rows[2]['base'] / b0:.2f} times as much at k=2 as at 1)")


if __name__ == "__main__":
    main()
