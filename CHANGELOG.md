# Changelog

What changed in each version, and the errors found and corrected along the way, with what each did to the results.
Corrections are listed because a reader judging the model should know where it has been wrong.

Version 1.0 is the first public release. Before it, the model went through development versions that were not
published: the model's own v0–v6.1 (2026-09-15 to 2026-09-18; sections 9–30 of [docs/ABM.md](docs/ABM.md)
describe each step), then explorer versions v1 to v10 (from 2026-09-18). Comments in the code and in ABM.md refer to
those development versions as v1, v2 and so on. From 1.0 on, each release is a git tag.

## 1.0.1 (2026-10-20)

Fixes to the pages, found by testing them in a browser. The model and its results are unchanged.

* **Sliders:** dragging a slider no longer rebuilds the whole lever panel on every movement. The figures are redrawn
  at most once a frame while dragging and the panel when the slider is let go. A long drag could make Safari reload
  the page.
* **Phones:** the pages now declare a document type and a viewport, so phones lay them out at their own width
  instead of a shrunken desktop page.
* **Settings outside the runs:** a setting farther from every model run than the runs lie from each other is now
  marked as an extrapolation ([VALIDATION.md](docs/VALIDATION.md) §4).
* **Floors:** shares, counts and spreads that the fitted surface put slightly below zero are shown as zero.
* **Formatting:** differences between two rates are given in percentage points rather than as relative changes;
  no more "−0.0%" or a "+" before a negative number; net debt below zero is stated as net assets.
* **Saved comparisons:** names typed by the viewer are shown as text, not interpreted as markup.

## 1.0.0 (2026-10-19)

The first public release. The model and its results are those of development version 10; the text of the pages and
documents was revised for publication, and DESIGN.md, VALIDATION.md, REFORM.md and the registered forecasts
(`scripts/predictions.py`) were added.

# Development versions (not published)

## v10 (2026-10-16)

* **The housing ladder.** Homes come in six sizes, from studio to large house, each with its own stock, price and
  rent. Households need a size given their adults and children, move up when crowded and able to pay, and move
  down when they have room to spare: more often with age, after a partner's death and below the poverty line.
  Downsizing frees equity, 60% of it taken as a lifetime income. Construction and conversions follow prices.
* **Couples form.** Before v10 couples only ended, so the share of adults in couples fell from 48% to 23% by 2060
  in the status quo. Singles now pair so that each age band keeps its 2026 share.
* **The pension top-up as a loan against the home** (lever `floor_loan`), and deferred property tax recovered from
  estates.
* **Surface:** 4,300 runs, with a third adaptive round in the page's own world. The 2035 budget at the nine named
  scenarios is within −50 to +140 ma.kr. of the model, about 40 on average.
* **Checks:** null test exact; quality check 168 of 170, no failures; income effect 0.044 / 0.084 / 0.119.

## v9 (2026-10-13)

Prompted by an external review of v8.

* **Households share income** for poverty, costs and hardship: partners, young adults living with parents, older
  relatives living with family. Work decisions still use each person's own income.
* **Capital income** assigned by wealth rank (355 ma.kr. in total), taxed at 22% above the allowance.
* **Disability as registered:** 29,465 people, about a third working, none full-time.
* **Occupational pensions** spread to match the record; the child pension and the interest rebate added.
* **Financing figures re-sourced:** the input-VAT restriction (459.5 ma.kr. in full), the public pay offset,
  property tax by home value, subsidies, religious bodies, per diems, pension assets, customs, the fishing fee.
* **New levers:** earned pensions kept while contributions are redirected (`pension_keep`); pensioners deferring
  the extra property tax (`prop_defer`).
* **Income effect test corrected:** wages are now held at the status quo's in the payment run, since a lottery
  winner's pay rate does not move when they work less. Before, the market bid wages up and offset most of the
  measured response.
* **Surface:** a near round of 300 runs, and the kernel correction kept when it removes a tenth of the
  cross-validated error. The 2035 budget at the scenarios moved from 150–300 ma.kr. below the model to within −9 to
  +113.

## v8 (2026-10-09)

* **Error corrected: the comparison was not neutral.** Reforms ran under rules the status quo did not: labour
  demand and arrivals were measured against the status quo's previous year, and the backcast's identified shocks
  reached only the status quo. A status quo re-run under those rules, with nothing changed, drifted by 2025 to
  output −15%, prices −20% and a budget +209 ma.kr., and every reform carried that drift as its own effect. Reforms
  now run under the same rules, and `scripts/null_test.py`, a gate in every build, requires the re-run to reproduce
  the status quo exactly. The counterfactual past at 300 þús. moved from output −16.7% to about −4%, employment
  from −4.2 to −2.4 points, and the budget from +459 to +191 ma.kr. Forward results from v7 carried part of the
  same drift.
* **The reform's pace** (`transition`, 1–6 years): the public-job cut and the pension fold phase in, and today's
  recipients are protected for the share not yet phased in.
* **A fisheries fund from 1984** for the counterfactual past ([docs/FISHERIES_PAST.md](docs/FISHERIES_PAST.md)).
* **The past tab** became 170 exact runs.

## v7 (2026-10-07)

* **The state's deemed stake:** one start-of-life fund's worth deemed paid into every company each time it raises
  capital, with corporate tax on staked firms a lever.
* **Support for people out of work varies by person,** which removed an artificial poverty cliff in the status quo
  in 2051.
* **The surface runs to 2060.**
* **Speed:** two solver fixes took a model-year from 8–30 seconds to about 3.5.

## v6 (2026-10-02)

A 35-year horizon exposed drift in the status quo (unemployment from 2.7% to 9% by 2060 with no shock). Faults
corrected:

* tax thresholds and the personal credit followed prices only; they now follow prices plus 1%, as the law sets
  them;
* debt was floored at zero;
* new tasks created by AI were scaled down by the automation of the profession they landed in;
* a nominal cap on the wage index bound once prices had roughly quadrupled.

Added: new entrants following empty posts, study answering the return to a degree, a wage curve in agreed floors,
and an identified exchange-rate shock in the backcast. Real-wage error in the backcast fell from 11.9% to 6.9%;
export error rose from 5% to 12%.

## v4–v5 (2026-09-26 to 2026-10-01)

* **Error corrected: reforms left out the status quo's drift.** A reform's balance was measured from the status
  quo's own path, so the status quo's ageing, pay and interest never reached it, crediting the reform with about
  +200 ma.kr. a year by 2035. Every run is now measured from the base year's accounts.
* **Backcast faults corrected:** benefits indexed twice; interest following the real rate alone, so the interest
  bill vanished at 2021–22's negative real rates; house prices priced off the policy rate. Population error in the
  backcast fell from about 9,000 to 900 a year.
* Mortality falls 1.2% a year; unmodelled revenue and purchases grow with the economy.

## v3 (2026-09-21)

* **Error corrected: benefits followed prices only,** where the law has them follow wages. Hardship nearly doubled
  and child poverty rose five points in the status quo with no policy change, which biased every comparison in the
  reform's favour.
* **Public-service shortages** show up as pay, work not done and load on those who stay; public staffing follows
  need.
* **A second status quo** in which the world runs as the last decade did.
* **The income effect** first checked against the lottery evidence.
* **Scenarios on the page are run in the model itself,** and the page carries the model's figures.
* **The backcast** from 2015 ([docs/ABM.md](docs/ABM.md) §30).

## v1–v2 (2026-09-18 to 2026-09-19)

The first explorer pages: a surrogate fitted to 660 model runs over 33 levers (v1), then every component of the
reform on its own lever (v2).

## Model development, v0–v6.1 (2026-09-15 to 2026-09-18)

* v0: the first agent-based model, calibrated to Hagstofa 2025.
* v1–v5.7: dynamic markets; sectors and household wealth; professions; contracts and automation; risk, study and
  life satisfaction; the start-of-life fund; inflation, health and childhood; crime; trade and schooling; ownership.
* v6.0: **26 calculation faults** found in a systematic sweep and corrected, among them eight in which a nominal
  amount was set against a real one. Each is listed with its effect in [docs/ABM.md](docs/ABM.md) §24–25.
* v6.1: world prices applied to both runs.
