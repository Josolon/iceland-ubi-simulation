# Research design

What the model is for, how a result is produced, what it would take to show a result wrong, and what the model
cannot answer.

## 1. Purpose and scope

The model asks what a universal basic income would do in Iceland if it replaced today's social benefits and were
paid for within the public accounts. It is exploratory: it maps how outcomes depend on the design of the payment, on
how it is financed and on how people and markets respond, so that the dependence can be seen and argued about. It
does not recommend a policy, and its starting reform (the *reference reform*, [REFORM.md](REFORM.md)) is a
specification to be varied, not a proposal.

In scope: the resident population one person at a time (394,108 in 2025), its work, pay, households, homes,
births, studies, health, wellbeing and migration; firms only in reduced form; the public accounts line by line;
prices, rents, the króna and the policy rate; the external sector as four export earners against imports.
Horizon: yearly to 2035, then every fifth year to 2060. Out of scope: anything listed under "Not in the model" on
the explorer page and in [VALIDATION.md](VALIDATION.md) §5.

## 2. How a result is produced: the paired comparison

1. **One calibrated society.** A synthetic population is built from Hagstofa's 2025 tables and calibrated to
   published aggregates ([VALIDATION.md](VALIDATION.md) §1).
2. **Two runs from it.** The status quo runs with today's rules. The reform runs with its rules from the same
   starting society, the same random draws and the same world (world prices, AI, the pace of change abroad).
3. **The difference is the result.** Every figure is reported against the status quo in the same year. A common
   drift in levels cancels; what remains is the effect of the rules.
4. **The comparison must be neutral.** A run with nothing changed, measured exactly as a reform is, must reproduce
   the status quo to the last digit (`scripts/null_test.py`, forward from 2025 and through the past from 2015). It
   is a gate in every build. Before v8 it failed, and part of every reform's effect was the comparison itself
   ([CHANGELOG.md](../CHANGELOG.md), v8).
5. **Behaviour is the same on both sides.** A behavioural setting (how strongly emigration answers income, how
   strongly births answer child income, and so on) applies to the status quo and to the reform alike. Only policy
   settings differ between the runs.

The explorer pages read a statistical surface fitted to about 4,300 such pairs, so that any combination of levers
gives an answer at once. The surface is an approximation of the model, and its error is reported: per output, as
cross-validated R², and at the page's named scenarios, as the difference from the model's own runs
([VALIDATION.md](VALIDATION.md) §4). Where the two differ, the model's runs are the result.

## 3. What each number rests on

Every parameter carries one of five statuses, listed with its value and source in [PARAMETERS.md](PARAMETERS.md),
which is generated from the source code:

| Status | Meaning | Count (1.0) |
|---|---|---|
| DATA | a published figure, used as is | 35 |
| CALIBRATED | solved for so the base year matches a published aggregate | 2 |
| TUNED | set so the model reproduces a published pattern | 25 |
| EST | an estimate: from the literature, from another country, or a judgement | 670 |
| POLICY | a setting of the rules, which the levers move | 105 |

Most EST parameters are small (a share, a lag, a threshold). The thirty or so that the results lean on most have
ranges in `src/ubisim/abm/uncertainty.py`, are swept by `scripts/run_montecarlo.py`, and the ones that matter most
for the headline results are levers on the explorer page, so a reader can see what changes if they are wrong.

## 4. Hypotheses and what would refute them

The model is tested at two levels. The first is whether it describes Iceland as it is: these tests use data and
can fail. The second is what it says about a reform that has not happened: these are conditional statements,
and what can be tested is whether their premises hold.

### 4.1 The model describes Iceland as it is

| | Hypothesis | Test | Refuted if |
|---|---|---|---|
| M1 | The base year matches the record | `quality_check.py`: 170 checks against Hagstofa, Skatturinn, Tryggingastofnun and others | a calibration check fails its stated tolerance |
| M2 | The decade 2016–2025, run from 2015, reproduces the series that were not targeted | `backcast.py`: real wages, the employment rate, exports and debt are not fitted | the untargeted errors grow beyond those in [VALIDATION.md](VALIDATION.md) §2 when the model changes |
| M3 | People give up work for unearned income as the evidence says they do | `income_effect_check.py`: krónur of pay given up per króna received, on the same people, prices and wages held | the figure falls outside 0.04–0.20 (Cesarini et al. 2017; Golosov et al. 2024; Vivalt et al. 2024) |
| M4 | The status quo's forecasts for 2026–2030 hold | `predictions.py`: seven series with margins fixed in advance | a series misses its margin in two or more years ([VALIDATION.md](VALIDATION.md) §6) |
| M5 | The comparison is neutral | `null_test.py` | any difference at all |

### 4.2 What the model says about the reform, and what would overturn it

Each result below is conditional. What can be checked is the premise it rests on, and each premise is either
published data, a figure from the literature, or a lever whose setting the reader chooses.

| | Result in the model (reference reform, 2035) | Rests mainly on | Overturned if |
|---|---|---|---|
| R1 | The budget balances, with a surplus of several hundred ma.kr. a year | the yield of restricting VAT refunds to value-chain inputs (459.5 ma.kr., range 385–574), folding in the pension funds, abolishing the personal credit, the higher property tax | the VAT restriction yields less than about 40% of its estimate, other settings unchanged: on the fitted surface the 2035 balance is +301 ma.kr. at 75% of it, +90 at 50%, +7 at 40% and −321 without it, against −181 in the status quo (the lever *VAT refunds only on value-chain inputs*) |
| R2 | Child poverty roughly halves | the child payment, half of it paid to the family | largely mechanical: the payment lifts most families above the line; behaviour changes the size, and a low share paid to the family shrinks it (a lever) |
| R3 | Work per adult falls by about 7% | the income effect (M3) and how pay and hiring respond | the income effect is far from the evidence's range (M3 would then fail), or hiring responds to wages much more or less than estimated (a lever) |
| R4 | Prices rise faster than in the status quo | the single VAT rate of 25%, and whether pay agreements compensate it | agreements index to prices net of the tax switch, as Denmark's do (a lever) |
| R5 | Pensioners' median income falls unless topped up | the payment being below today's pensions | the top-up lever is used |
| R6 | More people arrive than leave | the payment's pull against the residence rules | residence testing is strict (a lever) |

R1 is the result most exposed to error. Restricting input VAT in this way has not been applied anywhere, so its
yield is an estimate from Skatturinn's records of reclaimed input VAT (997 ma.kr. in 2025) and Hagstofa's
supply-use tables, not an observation.

## 5. Uncertainty

Three sources are kept apart:

* **Chance.** Runs are repeated with independent seeds where it matters (the births grid uses three; the income
  effect check four). A difference smaller than the spread between seeds is not a finding.
* **Estimates.** The Monte Carlo samples the EST ranges by Latin hypercube, each draw with its own status quo.
* **The surface.** Cross-validated fit per output, and the gap to the model's own runs at the named scenarios.

[THOROUGH.md](THOROUGH.md) sets out how to run all three at scale before using a result for a real decision. The
rule throughout: **directions and thresholds are the finding, never the decimals.**

## 6. What the model cannot answer

* Whether the reform is desirable. That depends on values the model does not hold.
* Effects through channels it does not represent ([VALIDATION.md](VALIDATION.md) §5): social norms around work,
  a financial sector, regional differences within Iceland, undeclared work, and others.
* Magnitudes far outside Iceland's experience: a payment far above today's pensions, or a resource windfall on
  Norway's scale, are extrapolations.

## 7. Reproducibility

Everything in the repository runs from the commands in the [README](../README.md). The model is deterministic
given its seeds: the same code and inputs give the same numbers. Each published version is a git tag, and the
explorer page states the version it was built from. Corrections are recorded in [CHANGELOG.md](../CHANGELOG.md)
with what they changed in the results.
