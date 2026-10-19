# Running the model thoroughly

The published pages are built for speed. The long view runs each scenario once, and the explorer reads a
fitted surface that is checked against single runs. One run carries one draw of chance and one set of estimates.
Before a result is used for a real decision, three questions need answers:

1. How much of the result is the model's own randomness?
2. How much comes from the estimates it leans on?
3. Does the sign survive both?

This file sets out how to answer them with more computing, from one machine to a cluster.

## What the model costs

* **One society, one agent per resident.** The model has about 400,000 agents, so there is no sampling of people
  to refine.
* **A model-year takes about 8 seconds on one core.** A 10-year run takes about 1.5 minutes and a 35-year run
  about 5.
* **Calibration takes 20-25 minutes per base.** There is one base for 2025 and one for 2015.
* **Memory is about 1.5 GB per worker process.** With 16 GB, run six to eight workers.

## Tier 1 — on this machine, overnight to a week

| Step | Command | Cost |
|---|---|---|
| Quality check, including the 30-year checks | `quality_check.py` | about 40 min |
| Seeds and parameter draws over the page scenarios | `ensemble.py plan/run/summarise` | see below |
| Monte Carlo over the estimates, 10 years | `run_montecarlo.py … --draws 40` | about 6 h |
| Denser fitted surface | `build_emulator.py --draws 3000` | about 16 h |

A useful first ensemble:

```
ensemble.py plan --name base --seeds 5 --draws 20 --years 35 --shocks none ai_shock
```

That comes to 420 jobs, or about 250 core-hours: roughly 40 hours on six workers. Its `report.md` gives, for each
scenario, three things:

* the median difference from the status quo in 2035 and 2060;
* the 5-95% range of that difference;
* the share of runs in which the scenario beats the status quo.

## Tier 2 — a cluster

`ensemble.py slurm --name X --shards N` writes a job-array script. Each array task runs every Nth job of the
manifest. Finished jobs are skipped, so a failed or pre-empted task is simply resubmitted.

**Before submitting:** build the calibrated bases once on one node, because every task reads them.

**What a cluster makes possible:**

* **Population seeds (`--population-seeds k`).** Each seed builds a whole population from the same data with
  different draws: who is where, earns what, and lives with whom. This is the variance a single calibration hides.
  Each seed needs its own calibration, which is done once and cached.
* **The labour-supply elasticity on its three calibrated levels (`--elasticity-levels`).**
* **The full parameter range at scale.** For example, 200 draws × 10 seeds × 8 events × 7 scenarios. That is about
  90,000 model runs and 450,000 core-hours: a few days on 5,000 cores.

## Tier 3 — what more compute would buy, in order of value

1. **Scenario search in the model, not on the surface.** The search now runs on the fitted surface, and only the
   final picks are verified in the model. A cluster could run the search itself in the model, for example with
   CMA-ES at 30-50 runs per generation. Each generation is then a single array wave.
2. **Calibration under uncertainty.**
   * The backcast (2016-2025) is now matched by identified shocks with the estimates held fixed.
   * Simulated method of moments or approximate Bayesian computation over the estimated parameters, fitted to the
     decade's record, would replace the hand ranges in `ensemble.RANGES` with posteriors.
   * Cost: thousands of 10-year backcasts, which is a cluster job.
3. **Global sensitivity (Sobol indices).** These rank which estimates the headline results depend on, and so
   which ones most deserve new data. Cost: about 10,000 runs.
4. **Out-of-sample tests.**
   * Calibrate to 2015 and run to 2025 without the identified shocks, scoring what the model gets right on its own.
   * Repeat from 2005, through the 2008 crash, if the data can be assembled.

## What compute cannot fix

Some limits are structural. They need research and data, not cycles (docs/VALIDATION.md, "Known limits"):

* no regional split;
* no financial sector or bank balance sheets;
* pension-fund solvency only partly represented;
* no explicit capital stock;
* no social norms in the choice to work;
* no informal economy.

Each of these can move results more than any number of seeds. The ensemble shows how wide the model's
uncertainty is *given its structure*. It does not show whether the structure is right.
