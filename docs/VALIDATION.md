# Validation

What the model has been checked against, how well it does, where it is known to fail, and the forecasts by which it
can be shown wrong. Every check here is a script in `scripts/` and can be rerun ([README](../README.md#reproducing-it)).
The figures are for version 2.1.

## 1. Calibration: the base year

`scripts/quality_check.py` builds the 2025 society and sets it against published figures. Its full output, with the
source of every target, is `data/processed/quality_check.md`: 212 checks, of which 211 pass, 1 warns and none fail.
A selection:

| Target | Source | Record | Model |
|---|---|---|---|
| Population | Hagstofa MAN43000 | 394,108 | 394,108 |
| Part-time share | VIN01104 | 24.3% | 24.9% |
| Wage bill | TEK02001 | 2,174 ma.kr. | 2,097 |
| Income tax of individuals | GFS 1111 | 694.1 ma.kr. | 699 |
| Corporate tax | THJ05132 | 148 ma.kr. | 148 |
| Property tax | THJ05132 | 102.8 ma.kr. | 102 |
| Public payroll | THJ05143 | 709.6 ma.kr. | 684 |
| Public health spending | THJ05511 | 405.8 ma.kr. | 406 |
| Students in tertiary education | SKO00000 | 19,528 | 19,528 |
| Disability and rehabilitation recipients | Tryggingastofnun 2025 | 29,465 | 29,452 |
| Over 67 living with a partner | Hagstofa, 1 January 2026 | 60% | 59.9% |
| Over 67 living alone | 2021 census | about 22% | 22.1% |
| Poverty, persons, year 1 | EU-SILC | 9.0% | 8.2% |
| Child poverty, year 1 | EU-SILC 2023 | 12.8% (±3.3) | 14.6% |
| Employment rate 16–74, year 1 | VIN01104 | 77.8% | 76.3% |
| Emigrants, year 1 | Hagstofa | 15,508 | 15,843 |
| Immigrants, year 1 | Hagstofa | 18,674 | 19,115 |
| Unemployment benefit, year 1 | GFS | 35.7 ma.kr. | 41.8 |
| Disability pensions and supplements, year 1 | the 2026 law | about 111 ma.kr. | 110.4 |
| People in the capital area, base year | MAN03250 | 63.9% | 63.7% |
| Moves out of and into the capital area, year 1 | MAN01002 | 3,974 and 3,661 | 4,045 and 3,629 |

The one warning: eighteen parameters are defined but read nowhere. The interest rebate (vaxtabætur), a warning in
1.0 at 0.5 ma.kr., is now 1.06 against the record's 1.1–1.6.

The labour-supply response is calibrated to an extensive-margin elasticity of 0.25, the central estimate of the
quasi-experimental literature, and unemployment to the published 4.3% with migration running.

The same script also checks that the accounts add up, that every lever moves results in the direction theory
requires, and that **inflation leaves real outcomes alone**: the status quo and a 450 þús. payment are each run with
2.5% trend inflation and with none, and fifteen real outcomes must match. That test found eight faults in which a
nominal amount had been set against a real one ([ABM.md](ABM.md) §25).

## 2. Out of sample: the decade 2016–2025

`scripts/backcast.py` starts the model from 2015's data and runs it through 2016–2025 with each year's tax and
benefit rules and world prices, then compares it with what Hagstofa recorded.

**What is fitted and what is not.** No model generates every force that moved a decade: the construction boom of
2016–18, COVID, the refugees of 2022–24, the budget's one-off items. As in a historical shock decomposition, the
part of each year the model does not explain is measured as a shock that makes it reproduce six series:
unemployment, output, immigration, emigration, the real policy rate and consumer prices, plus a fiscal residual for
the budget. Those series are matched by construction and are **not** a test. The shocks are identified again whenever the
model changes, and every run from the past (the backcast, "The past" and the long view from 2015) uses the same
ones. What is a test is everything else,
because nothing was fitted to it:

| Not targeted | Mean absolute error, 2016–2025 | Bias | 2025, model / record |
|---|---|---|---|
| Real wages (index) | 8.3% | −8.3% | 1.100 / 1.252 |
| Employment rate 16–74 | 1.7 points | −1.5 | 75.9% / 77.8% |
| Exports (real) | 11.3% | −9.2% | 0.978 / 1.092 |
| Net public debt, % of GDP | 3.9 points | +1.8 | 86.1 / 88.3 |
| Population | 1,438 people | +1,438 | 395,873 / 394,324 |
| Business investment, % of GDP | 1.7 points | +0.9 | 17.5 / 17.7 |
| People in the capital area | 0.2 points | +0.2 | 64.0% / 63.9% |
| Moves between the two areas | 444 a year (5.8%) | +146 | 8,499 / 7,635 |
| Capital area's house prices against the rest's (2015 = 1) | 0.093 | +0.093 | 0.958 / 0.812 |

Real wages and exports are the model's clearest failures on the past: both are too low throughout, and the error
does not shrink with time. The gap in house prices between the two areas narrows in the right direction but by a
fifth as much as the record's ([LIMITS.md](LIMITS.md) §1). The real-wage error is larger than in 1.0 (6.5%) for
a reason that is itself a correction: unemployment had a floor near 4%, so the backcast raised the demand for labour by up to 40% to reach
the record's 3.1–3.4%, and that demand lifted pay. With the floor gone, the record's unemployment needs at most 12%
more demand, and the population error fell from 2,306 people in 1.0 to 669 in 2.0 ([CHANGELOG.md](../CHANGELOG.md), 1.1).
In 2.1 it is 1,438, and the model is above the record in every year: 500 more people in 2016, 2,300 in 2018, then
1,000-1,700. The flows in and out are matched by the shocks, so the gap lies in births, deaths or the timing of
arrivals; it is not yet traced.
Most of the remaining gap opens from 2020: the record's real pay rose through COVID and 2022–24, faster than
output per hour, and the model ties agreed pay to output per hour, the terms of trade and a small premium. Differences between two runs are less affected than levels, since the same error is in
both, but a reform that works mainly through wages or exports should be read with this in mind.

`scripts/counterfactual_past.py` then runs the same decade with the reform in place from 2016, given the same
shocks. Its results are on the explorer's "The past" tab; every combination there is an exact run, not a fit.

## 3. Behaviour

| Check | Script | Standard | 2.1 |
|---|---|---|---|
| Work given up per króna of unearned income | `income_effect_check.py` | 0.04–0.20 per person (Cesarini et al. 2017; Golosov et al. 2024; Vivalt et al. 2024; Gromadzki 2024) | 0.044 at 100 þús. (sd 0.025 between seeds), 0.104 at 200, 0.161 at 300 (four seeds; prices and wages held at the status quo's, and the input-VAT restriction off, since it now cuts pay) |
| A run with nothing changed reproduces the status quo | `null_test.py` | exactly | exact, from 2025 and from 2015 |
| Extensive labour-supply elasticity | `quality_check.py` | 0.25 | 0.250 |

The income-effect test is made on the same people in both runs, and only on working-age adults who drew no benefits
in the status quo, for whom the payment is a pure windfall, as a lottery prize is.

**What the fall in work rests on** (`scripts/work_sensitivity.py`, `data/processed/work_sensitivity.json`): the
reference reform in 2035, ten years on, each run against a status quo with the same behaviour. Work is full-time
equivalents per adult.

| Setting | Work, reform / status quo | Budget against the status quo, 2035, ma.kr. | Child poverty, reform / status quo |
|---|---|---|---|
| Firms' own-wage elasticity of labour demand 0.40 | 0.586 / 0.685 | −126 | 14.1% / 19.6% |
| 0.47, the fitted value | 0.588 / 0.686 | −150 | 14.2% / 19.2% |
| 0.67 | 0.586 / 0.685 | −145 | 14.1% / 19.6% |
| 0.93 | 0.583 / 0.686 | −166 | 13.8% / 19.4% |
| 1.20 | 0.583 / 0.688 | −183 | 13.6% / 18.9% |
| The norm to work among peers off | 0.608 / 0.688 | −64 | 12.4% / 18.9% |
| The norm doubled | 0.568 / 0.671 | −231 | 18.0% / 20.0% |

Labour demand barely moves the fall in work (from 14.4% to 15.3% below the status quo across its range); the norm
moves it most (11.6% off, 15.4% doubled). Built up a part at a time, in the order the reform works: the payment on
today's taxes takes work from 0.686 to 0.609, the rest of the package without the haggling round to 0.579, and the
round gives back a little, to 0.588. These are single runs; at the fitted values the budget against the status quo
(−150) is near the headline's mean of five (−348 against −207, a difference of −141).

## 4. The fitted surface

The explorer pages do not run the model. They read a surface fitted to 5,800 model runs (Latin hypercube draws,
anchors at the page's defaults, adaptive rounds around its scenarios, and random sets of Guide answers), with 713
more kept out of the fit to score it: 600 sets of Guide answers and 113 runs moving one lever at a time from the
Guide's start. In 2.1 each run's difference from the status quo in its own world is fitted, not its level. Its
error is reported in three ways.

**Cross-validated fit,** five-fold, per output, averaged over the years shown:

| R² | Outputs |
|---|---|
| 0.95 or more | 93 |
| 0.85 to 0.95 | 63 |
| 0.5 to 0.85 | 55 (marked * on the page) |
| below 0.5 | 2: the spread of net income and the ratio of the 90th to the 10th percentile (0.48) |

In 2035 the budget fits at 0.98, debt at 0.96, household income at 0.97 and child poverty at 0.95; unemployment at
0.65 and the childcare shortfall, now that one exists, at 0.26. On the 600 sets of Guide answers kept out, the 2035
budget against the status quo is off by 265 ma.kr. (root mean square), against 308 cross-validated.

**Single moves.** On the 113 runs that move one lever alone from the Guide's start to an end of its range, the 2035
budget is off by 184 ma.kr. These are what a reader tries first, and a fit over thousands of combined moves can miss
the shape of one lever on its own; the pages' error band comes from the combined sets and is narrower than this.

**Coverage.** The surface is reliable only near the runs it was fitted to. The pages measure how far the current
setting lies from the nearest run (in lever units, each lever's range being 0 to 1) and compare it with the largest
distance between a run and its nearest neighbour. Beyond that, the pages say that the figures are an extrapolation
and can be far off. This happens when many levers are pushed to the ends of their ranges at once; for example,
every lever at its minimum gives net assets of nearly three times GDP by 2060, a figure no run supports.

**Floors.** Shares of people, counts and spreads cannot fall below zero. Where the fitted surface puts one a little
below zero, the pages show zero.

**Against the model's own runs** at the page's nine named scenarios, each the mean of five runs: the surface puts
the 2035 budget between 58 below and 280 above the model, 96 on average in either direction (2.0: −62 to +104, 36 on
average). At the seven scenarios without a windfall the gap is 8 to 81; at the two with one, 240 and 279. It reads
high at most of them for a reason that does not show on runs drawn at random: the scenarios are found by searching
the surface for packages that keep up with the status quo, and a search finds the places where the surface errs on
the generous side. A round of runs centred on the scenarios found brings the gap down (from about 200 on average in
this build, before it) but the next search finds new such places. The named scenarios themselves show the model's
own figures, in their notes and on the cards; the gap matters for settings a reader moves away from them, which are
likely to look somewhat better on the page than in the model. Fitting to differences, which the review proposed,
narrowed the error on held-out runs a little (265 against 296 when levels were fitted in the previous build, on an
earlier model, so not a clean comparison). `data/processed/scenarios_verified.json` has both figures, and `scenarios_guide_start_verified.json` the Guide's
start (model −132, surface −170, status quo −207).

## 5. Known limits

Ranked by how much they could matter to the results.

**Structure** (2.0 adds a part for each of the limits 1.0 named; [LIMITS.md](LIMITS.md) has the evidence, the
findings and the checks)
1. **The financial sector is two balance sheets.** The banks and the pension funds are represented (`financial.py`),
   with loan losses, capital and what the funds' bonds and lending add to rates; not the central bank's balance
   sheet, the banks' foreign funding or a bank failing. The funds lend to members a constant share of their assets,
   where the record shows that share rising from 5% to 9% in 2015–25, so the backcast check of the funds' lending is
   not yet run.
2. **Two areas, one labour market.** The capital area and the rest of the country have their own housing markets
   and people move between them (`regions.py`), but pay and unemployment are national apart from who lives where,
   and the eight regions outside the capital area are one. The status quo's capital area loses 0.9 points of the
   population in ten years, where the record holds it steady, and the backcast's capital-area house prices fall
   against the rest's by a fifth as much as the record's (4% against 19% in 2016–25).
3. **The capital stock follows investment** (`capital.py`) with time to build; the backcast's error on business
   investment as a share of GDP is 1.7 points against a limit of 2, with a bias of +0.9.
4. **Hours within a job move only a little** (`hours.py`, between 75% and 110% of the standard week); part-time
   work as a status is still a single point at 55% of full time.

**Behaviour**
5. **Social norms enter through peers of the same age and sex,** nationally; the family's own example, which the
   Norwegian evidence finds stronger, is not represented.
6. **Decisions are one year at a time,** without expectations.
7. **How top earners report income when rates change** is modelled from elasticities estimated abroad (0.10 and
   0.25, with half the response real), and owners shifting pay into dividends from Swedish and Norwegian evidence.
   Iceland has no estimate of its own, so the lever `s_top_income` scales both; timing of income is not modelled.
8. **Benefits not claimed.** Housing benefit and social assistance are claimed by calibrated shares of those
   entitled; every other benefit is assumed claimed in full, which overstates today's safety net somewhat.
9. **Couples separating, money sent abroad, short-term rentals and student finance** are not represented;
   undeclared work is (`informal.py`), as a share of earnings kept off the books that follows the marginal rate. Unpaid family care is, but only for what it replaces of care assistants' work: not whether a care
   tie changes the choice to work, carers' own health, or long-term care for older people as a sector.

**Calibration**
10. **Real wages and exports run low** in the backcast (§2).
11. **Wealth at the very top.** The spread is fitted by family to the 2025 tax returns, which value shares at
    nominal value and so understate the richest families' wealth. The richest 1% of families hold 10.4% of net worth
    in the model; estimates at market value put it higher. Valuing their savings and other assets at twice the
    returns' figure gives 12.1% and a net wealth tax above 100 m.kr. 9% more base
    (`scripts/wealth_valuation_sensitivity.py`). The negative net worth of the poorest tenth is not modelled.
    Over the run, savings earn the same real return of 2% whatever their size, and real house prices hold roughly
    level, so the richest tenth's share falls from 51% to about 46% in six years and the 99th percentile loses about
    a tenth in real terms, while the median family's net worth grows about 6% a year. The tax returns of 2015–2025
    show the same direction (the richest tenth's share fell from 61% to 50%), carried by house prices; but the
    richest tenth's other wealth also grew about 4% a year in real terms, which a single return does not give.
    Returns that rise with wealth, as Norwegian and Swedish records show, are in 2.0 as a sensitivity
    (`wealth.return_gradient_scale`) and set to zero by Iceland's own record ([LIMITS.md](LIMITS.md) §8).
12. **The status quo's effective VAT rate** on household consumption is about 18%, not yet reconciled with
    estimates from the national accounts that put it lower. This affects the yield of the single rate.
13. **Relative poverty rises in the status quo,** from 8.0% in 2026 to 10.5% in 2030 and child poverty from 13.8% to
    17.7%, as the base year's population settles into the model's own ([LIMITS.md](LIMITS.md) §7). This is a
    forecast (§6), and the one most at risk of failing.
14. **Older people in the first year.** A static microsimulation of the same reform by an external reviewer found
    fewer people over 67 falling below today's poverty line in the first year (13%) than the model does (17%),
    mostly among those living alone.
15. **Self-employment no longer drains** (fixed in 2.1). The flag is now drawn at the labour survey's rates by age
    for people who come of age or arrive, as for the 2025 population. In the status quo the number working for
    themselves rises from 28,000 in 2026 to 33,500 in 2060, 12.3% of those working, then 11.6%.

**The surface**
16. Two outputs cannot be fitted (§4), and the surface is least accurate at the edge of the sampled settings and
    for one lever moved alone (184 ma.kr. on the 2035 budget).

## 6. Falsifiable forecasts

`scripts/predictions.py` records the status quo's forecasts for 2026–2030, with a margin for each fixed before the
record exists. Each release writes its own file (`data/processed/predictions_<version>.json`), and the earlier
releases' files stay as they were made. They are conditional on today's rules and the forecast
world (world prices at their 2025 level). Inflation comes out at 3-4% a year, above the 2.5% target, from rents,
non-tradable prices and a slow real fall in the króna. A forecast outside its margin in **two or more of
the five years** has failed, and will be reported as failed with the version that made it.

| Series | 2026 | 2027 | 2028 | 2029 | 2030 | Margin |
|---|---|---|---|---|---|---|
| Unemployment, 16–74 | 3.8% | 4.3% | 4.5% | 4.4% | 4.3% | ±1.0 point |
| Employment rate, 16–74 | 76.1% | 75.1% | 74.5% | 74.3% | 74.4% | ±2.5 points |
| Consumer price inflation | 3.1% | 2.8% | 2.6% | 3.6% | 3.4% | ±2.0 points |
| Population | 399,376 | 403,275 | 405,588 | 408,852 | 412,140 | ±1.5% |
| Live births | 4,348 | 4,294 | 4,304 | 4,299 | 4,315 | ±10% |
| At-risk-of-poverty rate, persons | 8.0% | 9.0% | 9.7% | 10.2% | 10.5% | ±2.0 points |
| At-risk-of-poverty rate, children | 13.8% | 15.1% | 16.5% | 17.1% | 17.7% | ±3.0 points |

The table is version 2.1's; 1.0's and 2.0's forecasts stay in `predictions_1.0.json` and `predictions_2.0.json`.

A miss can come from the world rather than the model: a tourism collapse or an eruption would move unemployment
without any fault in the model's behaviour. The stronger test, once the years have happened, is the backcast's:
rerun them with the world as it was and compare again. Both will be reported.

The reform's own results cannot be tested this way, since the reform has not happened. What can be tested are the
premises they rest on ([DESIGN.md](DESIGN.md) §4.2): above all the yield of restricting input VAT, which depends on
Skatturinn's records of what firms reclaim and what for.

## 7. Reporting a problem

Errors found by anyone are welcome as GitHub issues, with the version, the settings and what was expected. Each
confirmed error is recorded in the [changelog](../CHANGELOG.md) with what it changed in the results.
