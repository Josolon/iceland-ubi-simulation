# iceland-ubi-simulation

An agent-based model of Iceland, built to explore what a universal basic income (*borgaralaun*) could do there,
what it would take to pay for one, and how much of that can be known.

It simulates the whole resident population, 394,108 people in 2025: their work, pay, households, homes, children,
studies, health and migration. Each year it runs twice, once under today's rules and once under a reform, and
reports the reform as the difference between the two runs in the same year.

**Who and why.** This is an independent research project by Jónatan Sólon, done out of academic interest. It has
no funder, no client and no party affiliation, and it argues for no outcome. The reform it starts from is one
specification of many (see [docs/REFORM.md](docs/REFORM.md)). Every component is a lever that can be set to
today's rules, and the explorer pages exist so that anyone can build a different package and see what follows.

**Explore it:** [ubi.josolon.com](https://ubi.josolon.com) (a guided walk through the main choices) and
[ubi.josolon.com/explorer](https://ubi.josolon.com/explorer) (every lever).

## The question, as a hypothesis

> Can a monthly payment to every resident of Iceland, replacing today's social benefits, be financed within
> Iceland's public accounts by changes to taxes and spending, and what does it do to work, incomes, poverty, prices,
> housing and population compared with today's system?

The model does not assume an answer. Every channel through which a basic income might pay for itself (more
start-ups, work that suits people better, less administration) is matched by a channel through which it costs
(less work, higher prices, emigration of high earners, arrivals drawn by the payment). The behavioural strengths are
levers with stated ranges. [docs/DESIGN.md](docs/DESIGN.md) sets out the hypotheses and the results that would
refute them.

## What it finds at present (version 2.1)

These are for the reference reform at 300 þús. kr. a month, run in the model itself, in 2035 against the status
quo in the same year:

| | Reform | Status quo |
|---|---|---|
| Public balance, ma.kr. a year | −348 | −207 |
| Net public debt, % of GDP | 105 | 73 |
| Household income after tax and transfers, þús. a month | 898 | 783 |
| Work per adult, full-time equivalents | 0.59 | 0.69 |
| Unemployment | 3.7% | 4.4% |
| Price level, 2025 = 1 | 2.20 | 1.39 |
| Child poverty | 14.0% | 19.2% |
| Poverty against a fixed 2025 line | 3.0% | 6.0% |
| Essential public services short, full-time posts | 1,403 | 1,256 |

Each figure is the mean of five runs with different random draws; the budget's spread between them is ±10 ma.kr.

How to read this:

* **The reference reform falls short of the status quo's budget.** Its largest financing line, restricting VAT
  refunds to value-chain inputs, is now a cost to someone: what it raises falls on prices, pay, profits or
  investment, and 20–40% is taken off for avoidance, leaving 275–370 of its 459.5 ma.kr. a year. The 459.5 is itself an
  estimate, with a range of 385–574, of a rule no country has applied. Packages that
  do keep up with the status quo exist: at 250 and 300 þús. the named scenarios come to +73 to +234 in 2035, and the
  Guide's start, at 275 þús., to −132.
* **Work falls and prices rise.** Work per adult is about 14% lower and the price level about 59% higher: the single
  VAT rate adds to it once, and pay set by what it takes to fill each profession (the haggling round) raises the
  pay of the work people least want to do, which households then pay for. Essential public services are somewhat
  shorter of staff than in the status quo (about 1,400 posts against 1,260). In 2.0, with today's agreements
  kept, prices rose about 23% and public services were shorter of staff. In 1.0 work
  fell about 7%; the young adults' choices and unemployment without a floor in 1.1 added about 4.5 points, the
  norm to work among peers about 2 and hours within a job about 1.
* **Groups differ.** Pensioners' median income is about 11% higher, now that earned pensions are paid alongside
  the payment; in-work income about 25% higher. The poorest tenth gains most. Of the adults of 2025, 21% have lost
  more than 5% of their household's real income by 2035, against 25% in the status quo (on the page's fitted
  surface).
* **Treat directions and orders of magnitude as the finding,** never the decimals. Around thirty behavioural
  settings are estimates; [docs/VALIDATION.md](docs/VALIDATION.md) lists what is calibrated, what was checked
  out of sample, where the model is known to fail, and the predictions by which it can be shown wrong.

## Reading the results

Always as a **difference from the status-quo run in the same year.** Both runs share the same people, the same
random draws and the same world, so a common drift cancels. Levels drift more than differences do. A run with
nothing changed reproduces the status quo to the last digit (the null test, a gate in every build).

## Documentation

| | |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | research design, hypotheses and the results that would refute them |
| [docs/REFORM.md](docs/REFORM.md) | the reference reform, component by component, against today's rules |
| [docs/VALIDATION.md](docs/VALIDATION.md) | calibration, out-of-sample tests, known failures, falsifiable predictions |
| [docs/REFERENCE.md](docs/REFERENCE.md) | how the model works: what it simulates, in what order, by which equations, on which evidence |
| [docs/ABM.md](docs/ABM.md) | the model's structure section by section, with the repairs it has had |
| [docs/PARAMETERS.md](docs/PARAMETERS.md) | every parameter: value, status (DATA, CALIBRATED, TUNED, EST, POLICY), source |
| [docs/DATA.md](docs/DATA.md) | data sources |
| [docs/FISHERIES_PAST.md](docs/FISHERIES_PAST.md) | the fisheries resource rent since 1984, for the counterfactual past |
| [docs/THOROUGH.md](docs/THOROUGH.md) | the checklist each model change goes through |
| [CHANGELOG.md](CHANGELOG.md) | what changed in each version, including errors found and corrected |

## Reproducing it

Tested with Python 3.14.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/quality_check.py                 # calibration, accounting and lever checks
.venv/bin/python scripts/null_test.py                     # nothing changed must reproduce the status quo
.venv/bin/python scripts/income_effect_check.py           # work given up per króna, against lottery evidence
.venv/bin/python scripts/backcast.py                      # 2016-2025 from 2015, against the record
```

The calibration targets (`data/processed/baseline_2025.json`, `baseline_2015.json`) are included. To rebuild them
from Hagstofa's API, run `PYTHONPATH=src .venv/bin/python -m ubisim.abm.data_prep` (add `--year 2015` for the
backcast's starting point). The first run calibrates the base society, about 25 minutes, and caches it. `quality_check.py` writes its results
to `data/processed/quality_check.md`. The explorer's fitted surface is rebuilt with `scripts/build_emulator.py`,
from about 6,400 model runs, which takes two days or more on ten cores.

Some source files are not redistributed here. Where a figure comes from a source that cannot be shared, the
parameter's comment names the publisher, and [docs/DATA.md](docs/DATA.md) says how to obtain it.

## Naming in the code

The code calls the reform regime `platform` (for example `policy.platform_income_tax_scale`). This is an internal
name from early development and means the reform scenario, nothing more.

## Licence

Code under the MIT licence ([LICENSE](LICENSE)). Documentation, text and figures under CC BY 4.0
([LICENSE-docs](LICENSE-docs)). To cite the model, see [CITATION.cff](CITATION.cff).
