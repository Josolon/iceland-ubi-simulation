# Validation

What the model has been checked against, how well it does, where it is known to fail, and the forecasts by which it
can be shown wrong. Every check here is a script in `scripts/` and can be rerun ([README](../README.md#reproducing-it)).
The figures are for version 1.0.

## 1. Calibration: the base year

`scripts/quality_check.py` builds the 2025 society and sets it against published figures. Its full output, with the
source of every target, is `data/processed/quality_check.md`: 170 checks, of which 168 pass, 2 warn and none fail.
A selection:

| Target | Source | Record | Model |
|---|---|---|---|
| Population | Hagstofa MAN43000 | 394,108 | 394,108 |
| Part-time share | VIN01104 | 24.3% | 24.5% |
| Wage bill | TEK02001 | 2,174 ma.kr. | 2,125 |
| Income tax of individuals | GFS 1111 | 694.1 ma.kr. | 698 |
| Corporate tax | THJ05132 | 148 ma.kr. | 148 |
| Property tax | THJ05132 | 102.8 ma.kr. | 102 |
| Public payroll | THJ05143 | 709.6 ma.kr. | 692 |
| Public health spending | THJ05511 | 405.8 ma.kr. | 406 |
| Students in tertiary education | SKO00000 | 19,528 | 19,528 |
| Disability and rehabilitation recipients | Tryggingastofnun 2025 | 29,465 | 29,452 |
| Over 67 living with a partner | Hagstofa, 1 January 2026 | 60% | 59.9% |
| Over 67 living alone | 2021 census | about 22% | 22.1% |
| Poverty, persons, year 1 | EU-SILC | 9.0% | 8.8% |
| Child poverty, year 1 | EU-SILC 2023 | 12.8% (±3.3) | 14.5% |
| Employment rate 16–74, year 1 | VIN01104 | 77.8% | 76.1% |
| Emigrants, year 1 | Hagstofa | 15,508 | 15,899 |
| Immigrants, year 1 | Hagstofa | 18,674 | 19,279 |
| Unemployment benefit, year 1 | GFS | 35.7 ma.kr. | 34.9 |
| Disability pensions and supplements, year 1 | the 2026 law | about 111 ma.kr. | 111.5 |

The two warnings: the interest rebate (vaxtabætur) is 0.5 ma.kr. in the model against 1.1–1.6 in the record, and
eighteen parameters are defined but read nowhere.

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
the budget. Those series are matched by construction and are **not** a test. What is a test is everything else,
because nothing was fitted to it:

| Not targeted | Mean absolute error, 2016–2025 | Bias | 2025, model / record |
|---|---|---|---|
| Real wages (index) | 6.5% | −6.5% | 1.142 / 1.252 |
| Employment rate 16–74 | 1.4 points | −1.1 | 76.8% / 77.8% |
| Exports (real) | 12.1% | −9.6% | 0.976 / 1.092 |
| Net public debt, % of GDP | 3.9 points | +2.0 | 86.4 / 88.3 |
| Population | 2,306 people | +2,306 | 398,387 / 394,324 |

Real wages and exports are the model's clearest failures on the past: both are too low throughout, and the error
does not shrink with time. Differences between two runs are less affected than levels, since the same error is in
both, but a reform that works mainly through wages or exports should be read with this in mind.

`scripts/counterfactual_past.py` then runs the same decade with the reform in place from 2016, given the same
shocks. Its results are on the explorer's "The past" tab; every combination there is an exact run, not a fit.

## 3. Behaviour

| Check | Script | Standard | 1.0 |
|---|---|---|---|
| Work given up per króna of unearned income | `income_effect_check.py` | 0.04–0.20 per person (Cesarini et al. 2017; Golosov et al. 2024; Vivalt et al. 2024; Gromadzki 2024) | 0.044 at 100 þús., 0.084 at 200, 0.119 at 300 (four seeds; prices and wages held at the status quo's) |
| A run with nothing changed reproduces the status quo | `null_test.py` | exactly | exact, from 2025 and from 2015 |
| Extensive labour-supply elasticity | `quality_check.py` | 0.25 | 0.250 |

The income-effect test is made on the same people in both runs, and only on working-age adults who drew no benefits
in the status quo, for whom the payment is a pure windfall, as a lottery prize is.

## 4. The fitted surface

The explorer pages do not run the model. They read a surface fitted to 4,300 model runs (Latin hypercube draws,
anchors at the page's defaults, and adaptive rounds around its scenarios). Its error is reported in two ways.

**Cross-validated fit,** five-fold, per output, averaged over the years shown:

| R² | Outputs |
|---|---|
| 0.95 or more | 76 |
| 0.85 to 0.95 | 62 |
| 0.5 to 0.85 | 31 (marked * on the page) |
| below 0.5 | 2: the childcare shortfall (0.26) and the P90/P10 ratio (0.31) |

The budget, debt and household income fit at 0.98, unemployment at 0.69.

**Coverage.** The surface is reliable only near the runs it was fitted to. The pages measure how far the current
setting lies from the nearest run (in lever units, each lever's range being 0 to 1) and compare it with the largest
distance between a run and its nearest neighbour. Beyond that, the pages say that the figures are an extrapolation
and can be far off. This happens when many levers are pushed to the ends of their ranges at once; for example,
every lever at its minimum gives net assets of nearly three times GDP by 2060, a figure no run supports.

**Floors.** Shares of people, counts and spreads cannot fall below zero. Where the fitted surface puts one a little
below zero, the pages show zero.

**Against the model's own runs** at the page's nine named scenarios: the surface puts the 2035 budget within −50
to +140 ma.kr. of the model, about 40 on average. Each scenario's note on the page gives the model's own figures,
and `data/processed/scenarios_verified.json` has both.

## 5. Known limits

Ranked by how much they could matter to the results.

**Structure**
1. **No financial sector.** The reform redirects pension-fund contributions and returns; the model has no banks,
   no balance sheets and no role for the funds as buyers of government bonds and as mortgage lenders.
2. **No regional split.** Housing, wages and commuting differ between the capital area and the rest of the country;
   the model has one national market, which also blunts what it can say about rural infrastructure.
3. **No capital stock or investment** in the usual sense; a reduced form stands in for capital following labour.
4. **Hours are chosen among few options.** Part-time is a single point at 55% of full time, so a move from full time
   to four days a week cannot be represented, and that intensive margin is where much of a basic income's labour
   response is expected.

**Behaviour**
5. **No social norms in the decision to work.** Whether others work does not affect whether one works. The
   commonest objection to a basic income turns on this mechanism, and the model can neither produce it nor rule it
   out.
6. **Decisions are one year at a time,** without expectations.
7. **How top earners report income when rates change** (shifting to dividends, timing) is not modelled.
8. **Benefits not claimed.** Apart from housing benefit, where a calibrated share of renters claims, everyone
   entitled is assumed to claim in the status quo, which overstates today's safety net somewhat.
9. **Undeclared work, unpaid family care, couples separating, money sent abroad, short-term rentals and student
   finance** are not represented.

**Calibration**
10. **Real wages and exports run low** in the backcast (§2).
11. **Wealth at the very top is too thin:** the richest 1% hold 8.6% of net wealth in the model, where tax data
    suggest nearer 20%. Taxes on wealth are therefore estimated on too small a base at the top.
12. **The status quo's effective VAT rate** on household consumption is about 18%, not yet reconciled with
    estimates from the national accounts that put it lower. This affects the yield of the single rate.
13. **Relative poverty rises in the status quo,** from 8.9% in 2026 to 11.4% in 2030 and child poverty from 14.6% to
    18.2%. This is a forecast (§6), and the one most at risk of failing.
14. **Older people in the first year.** A static microsimulation of the same reform by an external reviewer found
    fewer people over 67 falling below today's poverty line in the first year (13%) than the model does (17%),
    mostly among those living alone.

**The surface**
15. Two outputs cannot be fitted (§4), and the surface is least accurate at the edge of the sampled settings.

## 6. Falsifiable forecasts

`scripts/predictions.py` records the status quo's forecasts for 2026–2030 in `data/processed/predictions.json`,
with a margin for each fixed now, before the record exists. They are conditional on today's rules and the forecast
world (world prices at their 2025 level, inflation near target). A forecast outside its margin in **two or more of
the five years** has failed, and will be reported as failed with the version that made it.

| Series | 2026 | 2027 | 2028 | 2029 | 2030 | Margin |
|---|---|---|---|---|---|---|
| Unemployment, 16–74 | 3.2% | 4.2% | 4.5% | 4.6% | 4.4% | ±1.0 point |
| Employment rate, 16–74 | 76.1% | 75.1% | 74.5% | 74.5% | 74.6% | ±2.5 points |
| Consumer price inflation | 2.7% | 2.7% | 2.6% | 3.4% | 3.3% | ±2.0 points |
| Population | 398,919 | 402,821 | 406,201 | 409,458 | 413,479 | ±1.5% |
| Live births | 4,316 | 4,388 | 4,357 | 4,322 | 4,259 | ±10% |
| At-risk-of-poverty rate, persons | 8.9% | 9.7% | 10.4% | 11.0% | 11.4% | ±2.0 points |
| At-risk-of-poverty rate, children | 14.6% | 15.5% | 16.4% | 17.5% | 18.2% | ±3.0 points |

A miss can come from the world rather than the model: a tourism collapse or an eruption would move unemployment
without any fault in the model's behaviour. The stronger test, once the years have happened, is the backcast's:
rerun them with the world as it was and compare again. Both will be reported.

The reform's own results cannot be tested this way, since the reform has not happened. What can be tested are the
premises they rest on ([DESIGN.md](DESIGN.md) §4.2): above all the yield of restricting input VAT, which depends on
Skatturinn's records of what firms reclaim and what for.

## 7. Reporting a problem

Errors found by anyone are welcome as GitHub issues, with the version, the settings and what was expected. Each
confirmed error is recorded in the [changelog](../CHANGELOG.md) with what it changed in the results.
