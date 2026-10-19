"""Compare summary.csv of several sweep runs in one chart: data/results/comparison.png"""
import pathlib, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
names = sys.argv[1:] or ["default", "closed", "entrepreneurial"]
labels = {"default": "EEA rules as designed (open)", "closed": "Closed experiment (immigration capped)",
          "entrepreneurial": "Closed + 2x venture ideas"}
fig, ax = plt.subplots(2, 3, figsize=(15, 8.5))
panels = [
    ("fte_per_adult_rel", "Stöðuígildi (FTE) per adult 16-74, % vs status quo"),
    ("part_time_share_pp", "Part-time share of workers, pp vs status quo"),
    ("harsh_jobs_real_wage_pct", "Real wage, unpleasant jobs, % vs status quo"),
    ("real_wage_pct_Professionals", "Real wage, professionals, % vs status quo"),
    ("new_ventures_per_year", "New ventures per year (status quo ≈ 2,800)"),
    ("balance_bn_final", "General government balance, year 10 (bn ISK)"),
]
for n in names:
    s = pd.read_csv(ROOT / "data/results" / n / "summary.csv")
    s["fte_per_adult_rel"] = 100 * (s.fte_per_adult / s.fte_per_adult_sq - 1)
    x = s.ubi_isk_month / 1000
    for a, (col, title) in zip(ax.flat, panels):
        a.plot(x, s[col], marker="o", ms=4, label=labels.get(n, n))
        a.set_title(title, fontsize=10)
for a in ax.flat:
    a.axhline(0, color="grey", lw=.6)
    a.set_xlabel("UBI, thousand ISK per month")
    a.grid(alpha=.3)
ax[0, 2].axhline(5, color="grey", lw=.6, ls="--")
ax[0, 0].legend(fontsize=8)
fig.suptitle("Iceland UBI agent-based model v0 — year 10 of each run vs status quo (EST behavioural parameters)", fontsize=11)
fig.tight_layout()
out = ROOT / "data/results/comparison.png"
fig.savefig(out, dpi=130)
print(out)
