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

## What it finds at present (version 1.0)

These are for the reference reform at 300 þús. kr. a month, run in the model itself, in 2035 against the status
quo in the same year:

| | Reform | Status quo |
|---|---|---|
| Public balance, ma.kr. a year | +467 | −261 |
| Net public debt, % of GDP | 11 | 75 |
| Household income after tax and transfers, þús. a month | 836 | 769 |
| Work per adult, full-time equivalents | 0.63 | 0.68 |
| Unemployment | 3.4% | 4.4% |
| Price level, 2025 = 1 | 2.06 | 1.70 |
| Child poverty | 10.4% | 20.6% |
| Poverty against a fixed 2025 line | 6.5% | 7.7% |
| Essential public services short, full-time posts | 4,549 | 2,358 |

How to read this:

* **The surplus rests on a few large financing choices.** Measured one at a time, the largest are restricting VAT
  refunds to value-chain inputs, folding the pension funds into the scheme, abolishing the personal tax credit and
  a higher property tax. The VAT figure is an estimate with a range of 385–574 ma.kr. a year, and no country has
  applied that rule. If these choices yield less than estimated, the balance moves towards the status quo's.
* **Work falls and prices rise.** Work per adult is about 7% lower, the price level about 20% higher (the single
  VAT rate adds to it once, and inflation then runs higher), and public services are shorter of staff.
* **Groups differ.** Pensioners' median income is about 12% lower unless the top-up lever is used. The poorest
  tenth gains most.
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
from about 4,300 model runs, which takes a day or more on six cores.

Some source files are not redistributed here. Where a figure comes from a source that cannot be shared, the
parameter's comment names the publisher, and [docs/DATA.md](docs/DATA.md) says how to obtain it.

## Naming in the code

The code calls the reform regime `platform` (for example `policy.platform_income_tax_scale`). This is an internal
name from early development and means the reform scenario, nothing more.

## Licence

Code under the MIT licence ([LICENSE](LICENSE)). Documentation, text and figures under CC BY 4.0
([LICENSE-docs](LICENSE-docs)). To cite the model, see [CITATION.cff](CITATION.cff).
