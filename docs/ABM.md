# Agent-based model ("model society")

Every resident of Iceland is an agent: ≈394k people, at 1:1 scale. Each has
demographics, a household, an occupation and wage, and **traits** that drive
behaviour. Traits are grouped into **characters** that can be tuned. Each year,
every agent may re-think:

- work full-time, part-time, or not at all;
- start a venture;
- emigrate.

Wages then adjust until the labour market clears. Immigrants arrive, people
age, children are born, and the public accounts are tallied.

Code: `src/ubisim/abm/`. Parameters: `scenarios/*.yaml`.
Run: `scripts/run_sweep.py`.

## 1. Where agents come from (Hagstofa, 2025–26)

| Attribute | Source |
|---|---|
| Age, sex, immigrant background | MAN43000 (1 Jan 2026) |
| Education, occupation (ISCO major group) | VIN01100, employed persons by occupation × education × sex, 2025 |
| Monthly earnings | VIN02004, earnings percentiles by occupation, 2025 |
| Public vs private sector | VIN02004, weighted observations by sector |
| Employment, part-time, hours by age and sex | VIN01104 |
| Inactive: students, retired, disabled, ill, home | VIN00961 |
| Self-employment | VIN01006 |
| Households: couples, single parents, children | MAN07108 |
| Emigration and immigration by age and citizenship | MAN01401 |
| Firm births and survival | FYR09002 |
| Tax and TR parameters 2026 | Skatturinn, Tryggingastofnun |

Attributes without a published joint distribution are marked **EST** in
`params.py`: household tenure, housing costs, trait distributions, years of
residence. These are the first candidates for better data.

## 2. Traits and characters

Every adult has four continuous traits:

| Trait | Meaning | Drives |
|---|---|---|
| `meaning` | How much the person values the work itself (occupation mean + individual spread) | Staying in work when money matters less |
| `leisure` | Taste for free time | Cutting hours or exiting |
| `enterprise` | Appetite for risk and founding | Ventures |
| `mobility` | Willingness to move country | Emigration response |

Occupations also carry a **disamenity**: how unpleasant or dull the work is.

**Characters** are labels derived from traits and circumstances, used for
reporting and tuning. Each character can multiply its members' traits in the
scenario file, e.g. make Founders bolder or Guest workers more mobile:

| Character | Who |
|---|---|
| Student | 16–24, in education |
| Retiree | 67+ or retired |
| Constrained | Disabled or long-term ill |
| Carer | Parent of a child under 6 with a strong leisure/care preference |
| Founder | Top decile of `enterprise`, or already self-employed |
| Guest worker | Immigrant, < 5 years in Iceland, lower-wage occupation |
| Mobile professional | Tertiary education, top quartile `mobility` |
| Vocation | High `meaning` (nurses, teachers, craftspeople, …) |
| Breadwinner | Low `meaning`: works mainly for the money |
| Balanced | Everyone else |

## 3. Decision: work, hours, venture

Each year a share of agents (`reoptimise_rate`) re-chooses among these options:
not working, part-time (55% of full time), full-time, or founding a venture
(ages 20–64). The rest keep their status, so change is gradual, as in reality.

Utility of option *j*:

```
U_j = α · ln( max(C_j − s·c_min , ε) )             consumption above subsistence
    + h_j · (γ_m · meaning − γ_d · disamenity)       what the work itself is worth
    − leisure · h_j^1.5                              cost of hours
    + ASC_j(age band, sex) + work_ethic·[h_j>0]      calibrated constants
    + ε_j (logit)
```

- `C_j` is **real household disposable income per adult-equivalent** under
  option *j*. It includes the partner's income, benefits or the UBI, the usable
  share of the children's UBI, and all taxes. It is deflated by the price level
  (VAT and wage pass-through).
- `c_min` is the household's essential cost: basic consumption plus housing, by
  tenure and region.
- **The subsistence term produces the exit threshold.** While UBI + household
  income < `s·c_min`, not working is very costly. Once the UBI covers it,
  refusing unpleasant work becomes affordable, and each person's threshold
  depends on rent, household and children.

**Calibration**, before any policy change:
1. `ASC` constants reproduce the 2025 employment rate and part-time shares by
   age band and sex.
2. `α` is set so that the baseline **extensive-margin labour supply elasticity**
   matches a target: default 0.25, range 0.1–0.5 in the Nordic literature. The
   size of people's reaction to income is thus pinned to evidence, not guessed.
3. The venture constant reproduces baseline founders per year (FYR09002 births).

Policy then changes budgets (UBI, taxes, benefits, prices), never preferences.
Behavioural knobs (`work_ethic`, `entrepreneurial_spirit`, character
multipliers) are explicit scenario levers.

## 4. Labour market and wages

- **Demand:** one market per occupation. Firm demand for full-time equivalents:
  `D_o = D0_o · ω_o^(−η) · (consumption index)^κ_o · (labour-cost competitiveness)^(−x_o) + venture jobs`.
  - The consumption loading κ_o is high for service and elementary work.
  - The export loading x_o is high for fishery, craft and plant work.
  - Public-sector demand is set by government (payroll-cut lever), but the
    state pays market wages.
- **Supply:** the sum of agents' expected FTE choices at wage multiplier ω_o.
- **Clearing:**
  - `free_market` (collective agreements gone): ω_o moves up or down until
    S = D.
  - `status_quo`: wages cannot fall below the agreed level; excess supply
    becomes involuntary unemployment.
- **Emergent result:** the right-to-exit effect appears as rising ω for
  high-disamenity occupations and falling ω where people are happy to work for
  less.

## 5. Ventures

- **Entry:** the venture option in the choice model. Its utility depends on the
  income floor (the UBI), seed money (state seed with a 30% stake in the
  reform), `enterprise`, and the global `entrepreneurial_spirit`.
- **Firm life:**
  - survival hazard from FYR09002 (≈79% to t+1, ≈54% to t+3);
  - profits drawn from a heavy-tailed (Pareto) distribution;
  - jobs created feed labour demand;
  - corporate tax and the state's 30% dividend/exit share feed the accounts.
- **Selection:** when many more people found, the average venture quality
  falls (`entry_selection_elasticity`).

## 6. Migration

- **Emigration:** base hazard by age and citizenship (MAN01401) × (foreign real
  net income / home real net income)^(β·mobility), relative to baseline.
  Emigrants forfeit the UBI.
- **Immigration:** three pools (EEA workers, non-EEA workers, returning
  Icelanders). Each scales from 2025 inflows by expected real income in Iceland
  vs baseline, labour demand, and residence rules:
  - EEA arrivals get the UBI only with worker status until 5 years' residence;
  - non-EEA arrivals get no UBI until eligible;
  - a resources test limits non-working arrivals.

## 7. Public accounts

Computed from agents:
- UBI (adult and child, usable and invested);
- benefits (status quo);
- income tax, social security contributions, employer contributions;
- VAT on household consumption;
- public payroll at market wages;
- venture corporate tax and state equity income.

Non-agent items (property tax, fisheries rent, pension-fund returns, subsidies,
VAT input restriction, per diems) come from `models/static_balance.py`.

**Validation:** baseline income tax, VAT and wage bill are compared with
Hagstofa totals and reported as diagnostics.

## 8. Calibration safeguards

These were added after test runs exposed artefacts.

- **Dynamic recalibration.** After the one-off fit, eight 10-year status-quo
  burn-ins adjust the constants so activity shares stay at 2025 levels, given
  inertia and ageing.
  - Residual drift: status-quo employment +2–4 pp over 10 years, and the
    agent-modelled balance moves by under 25 bn.
  - All results are therefore reported **against the status-quo run in the
    same year**.
- **Labour demand grows with the working-age population.** Immigrants also
  consume, and capital adjusts.
- **Ventures:** only venture jobs beyond the status-quo path add net demand.
  The simulation starts from a steady-state stock of founder-run firms.
- **New arrivals** get their own mobility trait and higher return migration in
  their first three years. Their occupation mix tilts towards occupations whose
  real wages rose.
- **Occupational mobility:** up to 3% of workers a year move towards
  better-paid occupations, within education limits.
- **Housing-lite:** rents rise when population outgrows a housing stock growing
  1.5% a year. Rents feed essential costs, prices and migration.
- **Single-firm profits are capped** at 20 bn ISK/yr, since the heavy-tailed
  draws otherwise swamp the accounts.
- **Status-quo agreed wages** can fall at most 2% a year. Unemployment arises
  only where wages cannot adjust.

## 9. First results (v0, 2026-09-15)

Year 10 vs status quo. Chart: `data/results/comparison.png`. Tables:
`data/results/{default,closed,entrepreneurial}/report.md`.

| | Closed experiment | Open (EEA rules) | Closed + 2× ideas |
|---|---|---|---|
| Right-to-exit threshold (unpleasant jobs' real wage ≥ +5%) | ≈350k | ≈450k | ≈300k |
| Stöðuígildi per adult at 350k / 450k | −8% / −16% | −8% / −14% | −7% / −14% |
| Part-time share at 450k | +20 pp | +19 pp | +21 pp |
| Year-10 break-even UBI | ≈370k | ≈355k | ≈410k |
| Immigrants/yr at 450k (sq ≈18k) | ≈21k | ≈27k | ≈21k |

Readings:
- **The exit effect exists in the model**, but it arrives together with a
  large shift to part-time. Headcount employment understates the loss of
  stöðuígildi.
- **Open EEA rules with a UBI** draw substantially more immigrants. That
  dilutes the wage effect for unpleasant jobs and raises the fiscal cost.
- **Low UBIs balance only because they cut** pensions and disability pay below
  today's levels (all benefits are replaced).
- **Doubling venture ideas roughly doubles founding** and moves the break-even
  up ≈40k, but not to 450k within 10 years.

## 10. Limits of v0 (to improve)

- **Behavioural parameters** marked EST (foreign wage ratios, housing costs,
  trait spreads, idea rate, fertility response) are single values. Monte Carlo
  over their ranges is the next step before drawing conclusions.
- **A productivity gain from removing low-value jobs is not yet modelled.** Neither are
  sector detail for energy, fisheries and agriculture: they enter only through
  the static fiscal items.
- **Households:** the partner's income is taken from the previous year. There
  are no explicit housing market, savings or wealth.
- **State equity returns** from ventures need longer than 10 years to show.
  Run with `--years 25`.

## 11. Dynamic markets (v1, 2026-09-16)

`src/ubisim/abm/macro.py` surrounds the agents with markets that adjust
year by year with lags instead of clearing instantly.

**Wages.** Each year wages close part of the gap to the market-clearing
level: 70% of it under free wage setting, 30% under collective agreements.
Excess supply at the resulting wage becomes unemployment; excess demand
becomes vacancies.

**Goods prices.**
- *Non-tradables* move towards unit labour cost and demand pressure, closing
  60% of the gap each year.
- *Tradables* follow the króna, with tariffs removed under the reform.
- *CPI* = 40% tradables + 40% non-tradables (both carry VAT) + 20% rents.

**Króna.** It weakens when the current account worsens relative to 2025,
passes through inflation, and adds a debt risk premium that capital
controls damp.

**External balance.**
- Exports respond to competitiveness (króna over domestic costs, including
  the cost of the VAT input-credit restriction) and to employment in
  export-oriented occupations.
- Imports respond to household consumption and relative prices.

**Interest.** The real policy rate starts at 3.5%, from 7.75% nominal less
~4% inflation, and follows a Taylor rule on inflation and labour-market
pressure, plus the debt premium.

**Housing.**
- *Rents* clear housing demand (population, real income, start-of-life fund
  payouts) against the dwelling stock.
- *House prices* follow rents divided by the user cost of owning: real rate,
  property tax, depreciation and risk, less expected growth. A property-tax
  increase therefore capitalises into lower prices.
- *Construction* responds to prices over building costs.
- *Households feel it directly:* renters pay market rents, mortgage holders
  feel rates and rents, and owners pay the extra property tax each month.

**Public debt.**
- Interest reprices over about 6 years.
- Only the non-indexed part of the debt (65%) is eroded by inflation.
- Deficits accumulate into the debt, which feeds the risk premium and
  interest costs.

**Reference path.** In the status quo, labour demand absorbs the workforce's
own composition at today's relative wages. External flows and demand
pressure are measured against the status quo's own previous year. Reforms
move markets only through their deviation from that path, so a mild common
drift (employment rising as immigrants' share grows) cancels out of every
comparison.

**Interactive explorer.** `scripts/build_explorer_data.py` runs a
192-scenario grid over 15 years:

| Lever | Values |
|---|---|
| UBI (ISK/month) | 200k–600k |
| Immigration | open or closed |
| Entrepreneurial spirit | normal or 2× |
| Property tax | +0, +1 or +2 pp |
| Output gain from removing low-value jobs | 0% or 5% |

It writes `artifacts/explorer/data.js`, which `artifacts/explorer/index.html`
reads.

## 12. Sectors, household wealth, payroll, uncertainty (v2, 2026-09-16)

### Fisheries (`sectors.py`)
- **Revenue** is earned in foreign currency, so it scales with the króna
  (SJA08109, 2023: revenue 303.6 bn, compensation 113.5 bn, EBITDA 110.8 bn).
- **Costs:** imported inputs follow the króna; wages follow the
  fishery/processing occupations.
- **Resource rent** = EBITDA less a 6% normal return (72.8 bn in 2023).
  Under the reform, quota leases capture `rent_capture` (80%) of it.
- **Employment:** processing jobs respond weakly to wage costs in foreign
  currency.

### Energy and aluminium (`sectors.py`)
- **Base:** 12.9 TWh of 19.6 TWh goes to smelters at an estimated
  35 USD/MWh; net aluminium exports ≈17 bn per TWh; ~2,000 direct jobs.
- **Smelter exit lever:** from `exit_start_year`, contracts wind down over
  `exit_years`, with `contract_compensation_bn` paid over the same period.
- **Reallocation:** freed power goes to data centres, e-fuels/hydrogen,
  land-based aquaculture, greenhouses and electrified transport. Each use
  has its own price, jobs per TWh, net exports and ramp-up.
- **Links to the rest of the model:**
  - state dividends (Landsvirkjun) follow the rent change;
  - job changes feed labour demand by occupation;
  - export changes feed the current account.

### Household savings and wealth (`model.py`, `population.py`)
- **Starting wealth:** net worth outside pensions is 206% of GDP. 30% is
  liquid savings, distributed by age, earnings and a lognormal spread; the
  rest is housing equity for owners, split within couples.
- **Consumption** = an income-rank propensity to consume (0.98 at the
  bottom, 0.80 at the top), plus 4% of liquid savings and 1.5% of housing
  equity a year. It falls about 2% per point of higher real interest rate,
  which is how monetary policy works in the model.
- **Savings** accumulate. Mortgages amortise, housing equity follows house
  prices, and wealth passes to a surviving partner.
- **Wealth affects choices:** a 4% drawdown of the household's liquid
  savings enters every option, so savings make not working easier.

### Output gain → payroll
The `low_value_jobs_productivity_gain` lever now removes FTE demand.
- **Size:** a gain *g* produces the same output with 1/(1+g) of the hours.
- **Where:** the cut is weighted towards low-value-job occupations
  (clerical ×2.0, managers ×1.6, associate professionals ×1.2), phased in
  over 3 years, in both the public and private sector.
- **Result at 450k:** +10% removes ~17,600 FTE. Public payroll falls
  ~96 bn a year at first, ~31 bn by year 15 as wages re-balance. Income tax
  falls by about as much, so the net budget gain is ~+100–150 bn a year,
  with unemployment almost unchanged.

### New policy levers
- `adult_ubi_invested`: forced saving of part of adult UBI.
- `ubi_phase_in_years`, `ubi_indexation` (0–1).
- `platform_personal_credit`, `platform_income_tax_brackets`.
- `markets.freeze_prices`: a diagnostic that switches off all price
  reactions.

### Experiments and Monte Carlo
- **Experiments:** `scripts/run_experiments.py experiments/<name>.yaml`
  runs any set of named reforms against the status quo, changing any policy,
  market, labour, sector or wealth setting.
- **Monte Carlo:** `scripts/run_montecarlo.py experiments/montecarlo.yaml
  --draws 48` samples the ~30 estimated parameters in `uncertainty.py`
  (Latin hypercube). The labour-supply elasticity takes one of three
  pre-calibrated levels.
  - Each draw runs its own status quo, and all scenarios share its random
    numbers.
  - Output: percentile bands, the chance of an exit effect or a balanced
    budget, and rank correlations showing which parameters decide each
    outcome.
- **Explorer:** `scripts/build_explorer_data.py --bundle-only` bundles both
  into the explorer page.

## 13. Professions, frontier programmes, distribution (v3, 2026-09-16)

### The labour market is now 27 professions
Each named profession is its own market, with pay, size, unpleasantness and
meaning of its own (wage survey VIN02001, 2025; traits are EST):

| | Median pay 2025 | | Median pay 2025 |
|---|---:|---|---:|
| Pilots, officers, controllers | 2,144k | Nurses and midwives | 1,179k |
| Doctors | 1,993k | Primary/pre-school teachers | 911k |
| Managers | 1,439k | Artists and writers | 919k |
| Academics | 1,252k | Refuse collectors | 941k |
| Lawyers | 1,213k | Cooks | 821k |
| Engineers and IT | 1,222k | Waiters and bar staff | 691k |
| Business professionals | 1,109k | Child-care workers | 625k |

- **"Unpleasant work"** now means rated hard or dirty *and* paid below the
  middle of the ladder, so nurses no longer count as unpleasant-and-underpaid.
- **"Best-paid"** is the top quarter of professions by median pay.
- Group-level settings (consumption and export loadings, low-value-job weights,
  sector job mixes, immigrant mix) are expanded to professions by size.
- Education is a strong preference, not a hard gate, for entering a profession.

### Reported per profession
Numbers employed, real wage index, median earnings and part-time share — so the
model answers what happens to teachers, doctors, artists, waiters or refuse
collectors one by one.

### New levers
- **Public pay offset:** public wages cut by a share of the UBI, since public
  staff receive it too.
- **Culture on ticket sales:** state support for the arts withdrawn; what
  remains follows household spending.
- **Corporate tax rate**, with an economy-wide profit base (148 bn at 20% in
  2025) that shrinks when wage costs outrun prices.
- **Pension funds hold the króna:** foreign assets sold each year to finance
  imports. The fund shrinks, and its contribution to the UBI shrinks with it.
- **Tax brackets:** `platform_income_tax_brackets` and a personal credit.

### Frontier programmes (`frontier.py`)
Switchable state investments, each with capital cost, build time, power use,
jobs, exports or import substitution, and a return to the state. All are EST
magnitudes, meant to be argued with:

| Programme | Power | Jobs | What it changes |
|---|---:|---:|---|
| Indoor farming at scale | 1.2 TWh | 1,400 | Food prices −12% |
| Cultivated protein works | 1.8 TWh | 900 | Exports, food prices −6% |
| Autonomous fishing and processing | 0.4 TWh | 400 | Fisheries labour −35%, revenue +8% |
| Factory-built housing | 0.3 TWh | 1,200 | Building costs −20% |
| Carbon storage services | 1.5 TWh | 700 | Export services |

### Families and childcare
Kindergarten places wanted (all ages 1–5, full-day, and under-2s separately),
parents' working hours and the share of parents not working.

### Caveats addressed
- **CPI weights** now come from the 2025 basket (housing 30.3%, food 15.4%).
- **Household spending** is calibrated to the observed saving rate (consumption
  2,439.6 bn against disposable income 2,520.6 bn).
- **Corporate tax** reproduces the actual 148 bn.
- **Status-quo drift:** arrivals now bring partners and children, the founder
  stock starts at its steady state, and the base year is drawn from the model's
  own equilibrium. Remaining drift over 15 years is +5.9 pp of employment, of
  which only +1.7 pp remains when migration is switched off — the rest is the
  rising immigrant share, who work and rent more, as in Iceland since 2015.
  Prices, the króna and the budget are now stable in the status quo.
- **Still open:** at 450k some random paths tip into a current-account and
  price spiral; the Monte Carlo medians do not, so treat 450k as near an
  instability boundary rather than a central case.

## 14. Contracts, automation and the quality check (v4, 2026-09-16)

### Employment contracts replace the wage cap
Earlier versions stopped wages moving more than ±25% a year — a crude brake that
hid the very instability it was meant to contain. Wages are now held by
**contracts** instead (`labour.contract_lengths_private/public`). Pay is agreed
when a contract is signed and holds until it ends, so what the economy pays in
any year is a mixture of contract vintages. Ending a contract early takes a
notice period (`notice_months`) and costs severance.

Three things follow, and all three are now measured:
- **Firms respond to the wage they actually pay**, averaged over vintages
  (`implied_paid_index`), not to the rate a new hire would cost.
- **Contract length is endogenous.** A profession that cannot fill its posts
  offers longer contracts (`offer_length_sensitivity`); a slack one offers
  shorter ones.
- **Security is worth something.** Workers value a secure contract
  (`labour.stability_value`), which is why they do not simply chase the highest
  bidder each year, and why lengths settle rather than collapsing to one year.

Reported per profession: `prof_contract_*` (mean years left), plus
`contract_years_mean`, `short_contract_share`, `contracts_expiring_share`,
`mean_tenure_years` and `severance_bn`.

### Demand responds to relative wages
Labour demand now uses the wage **relative to the reference path**
(`reference_wage`) rather than its absolute level. An economy-wide level shift is
matched by prices and buys no extra jobs; before this, nothing pinned the wage
level, and the status quo drifted down about 10% over ten years while employment
looked fine. The reference is the status-quo run for a reform, and the run's own
previous year for the status quo itself.

### Automation that answers to wages (`automation.py`)
Machine capability improves at `ai_progress_rate`; each profession has an
exposure; take-up depends on what the work costs, so rising real wages pull
automation forward. The wage bill no longer paid becomes machine income, which
the state can claw back through corporate tax, a levy (`levy_rate`) or an
ownership stake (`state_capital_share`).

### New levers
| Lever | What it does |
|---|---|
| `minimum_wage` | statutory monthly floor, applied to the new-contract rate |
| `full_time_hours_factor` | a shorter standard week (.80 = four days) |
| `ubi_taper_start` / `ubi_taper_rate` | withdraw the UBI above an income point |
| `childcare_places_added` | state-funded full-day places |
| `public_dwellings_per_year` | dwellings built whatever the price signal says |
| `retraining_bn_per_year` | speeds movement between professions |
| `net_wealth_tax_pct` / `_threshold` | yearly tax on household net wealth |
| `sovereign_fund_share` | share of a surplus put aside rather than repaying debt |
| `pension_fx_support_bn` | pension funds' foreign assets sold to hold the króna up |
| `corporate_tax_rate` | reform corporate rate, machine income included |

### New measures
- **Is working worth it:** `participation_tax_rate` (share of gross full-time pay
  the household never sees), `marginal_tax_rate_to_full_time`,
  `share_facing_over_70pct_ptr`, `gain_from_full_time_isk`,
  `ubi_replacement_rate`.
- **Housing:** `house_price_to_income`, `housing_cost_burden`,
  `share_housing_over_40pct`, `renter_share`.
- **Who leaves:** `emigrants_young_graduates` alongside total emigration.
- **Public services:** `shortfall_nurse/doctor/teacher/care`,
  `essential_services_gap`.
- **Tax mix:** `tax_share_labour/consumption/capital/resource`.

### `scripts/quality_check.py`
One command runs four groups of checks and writes
`data/processed/quality_check.md`:
1. **Calibration** — employment, part-time share, wage bill, income tax,
   corporate tax, property tax, public payroll, consumption, VAT, household net
   worth and the profession mix, each against its published 2025 figure.
2. **Accounting** — profession headcounts against employment, FTE against heads,
   child UBI splitting into spent and saved, debt moving against the balance,
   and nothing pinned to a solver bound or left NaN.
3. **Behaviour** — every lever must move the result in the direction theory
   says, using common random numbers so a difference is the lever and not the
   draw. A UBI must cut hours and poverty; a property tax must cut house prices;
   dearer labour must automate faster; building houses must cut rents.
4. **Wiring** — parameters read but never defined, defined but never read, read
   from the wrong section, or the wrong length for what indexes them.

Bugs it caught on its first run, all of the same family — an index or a name
that no longer meant what the code assumed:
- `wage_ratio_harsh_to_top` indexed **professions** with **occupation-group**
  numbers, so it was comparing artists and engineers as the "unpleasant" jobs.
- House-building costs were driven by `omega[6]`, which after the move to 27
  professions is **lawyers**, not the building trades.
- The Monte Carlo was sampling `labour.wage_adjustment_free`, which nothing had
  read since contracts replaced it — one of its uncertainty dimensions was inert.
- `sovereign_fund_share` was a documented lever that nothing implemented.
- The demand fix above was itself written against the snapshot when the
  reference path stores accounts, so it silently did nothing until the check
  showed the numbers had not moved at all.

### The baseline: what was wrong and what fixed it
The status quo used to slide — real wages fell about 14% over ten years and prices
with them — which mattered because every reform is read against that baseline.
Tested against Iceland's own record (`data/processed/historical_benchmarks.json`):
real wages (Hagstofa LAU04800) grew **2.1%/yr over 2005-2025**, 3.2%/yr over the
last decade, and the worst ten-year window since the index began in 1989 —
2003-2013, across the banking collapse — was still **+0.5%/yr**. Real wages have
never fallen over a decade in Iceland, so the slide was a bug, not a feature.

Six defects were behind it, all found by the quality check or by instrumenting
the model rather than reasoning about it:

1. **No productivity growth at all.** `Macro.productivity()` returned a constant,
   so the economy had no source of real wage growth and any workforce growth could
   only be absorbed by falling pay. Now grows at Iceland's own rate (THJ11011:
   **+1.07%/yr**, 2008-2025).
2. **Nothing represented collective bargaining.** Renewals tracked the market
   down. An Icelandic kjarasamningur compensates the price rises since the last
   round (`labour.inflation_compensation`, at 0.9 — settlements lag, which is how
   real wages erode between rounds) and passes through productivity growth.
3. **The solver and the renewal disagreed.** The market cleared assuming renewals
   adopt the new rate in full, while `renew_contracts` moved only part of the way
   — so the solver pushed the offer further down every year to close a gap that
   never closed. Both now call one function, `renewal_wage`.
4. **Demand was anchored to last year's own employment**, so a dip in employment
   cut demand, which deepened the dip. It now follows the workforce, the labour
   actually offered (`labour.supply_absorption`), and **unit labour costs** — pay
   that rises with productivity costs no jobs, which is what lets real wages grow
   without employment falling.
5. **The labour-supply elasticity was mis-measured.** The calibration raises the
   market wage 10% and watches the response — but once contracts were introduced,
   most agents' pay is fixed by contract and never saw the rise. `alpha` ran to
   whatever bound it was given (8, then 40) and the elasticity stalled at 0.10-0.13
   against a 0.25 target. The boost now applies to what a person would actually be
   paid, and the calibration lands on **0.250 exactly**.
6. **The employment rate calibrated 3.5pp high** — a symptom of the slide, not an
   independent bug. `dynamic_recalibration` tunes the start so the *average* over a
   twelve-year burn-in hits 77.8%, so a path that drifts down has to start high.
   With the slide fixed the base year lands at **77.6%** against VIN01104's 77.8%.

The baseline now holds: employment 73.0% → 73.9% over ten years, the CPI flat
(−0.2%/yr), real wages flat rather than collapsing.

### The baseline now holds
Over ten status-quo years: employment 75.3% → 78.7% against VIN01104's 77.8%, real
wages **+1.55%/yr** (history: +2.1%/yr, productivity +1.07%/yr), inflation
+1.6%/yr, unemployment averaging about 3.5% against a published 4.3%. The quality
check passes 67 of its 68 tests.

Two further fixes got it there, both of the same family — a quantity calibrated
in one world and used in another:

7. **The demand level was calibrated with migration switched off.**
   `dynamic_recalibration` deliberately disables migration to isolate ageing and
   inertia, which is right for the preference constants. But how many jobs the
   economy has room for is exactly what a growing workforce tests, so a demand
   level fixed in a no-migration world left everything migration added to show up
   as involuntary unemployment — 3.3% inside the burn-in, 7-8% in the real run.
   `_calibrate_demand_level` now measures it **with migration running** and
   settles at 1.234.
8. **Poverty was measured against a moving line.** A relative line — 60% of the
   median — rises with the median a UBI lifts, so it reported no change (12.8% vs
   12.6%) while people were plainly better off. `poverty_rate_anchored` holds the
   2025 median fixed in real terms, and the same run reads **1.3% against 12.3%**.
   Report the anchored measure; keep the relative one for inequality.

### Still open
- **Independents fall slightly under a UBI** (3,780 against 3,931). Self-directed
  work now earns real money from selling the work, scaled by how good the person
  is at it, but the option still loses a little ground to not working at all.
  Loading the full meaning term onto it was tried and reverted: it made the option
  so attractive that its calibration constant pinned at -12 and took the
  labour-supply elasticity down with it.
- **Real wages grow 1.5%/yr against a historical 2.1%.** The gap is roughly the
  terms-of-trade and tourism contribution the model does not project, so this is a
  conservative baseline rather than a wrong one.
- `labour.real_wage_absorption` lets a labour shortfall land on prices instead of
  jobs — Iceland's own adjustment margin — but is off by default, because with the
  negotiated floor also on, the two chase each other into a wage-price spiral.

## 15. Risk, study and life satisfaction (v5, 2026-09-16)

### Creative income is a lottery, not a salary
Independents used to *fall* under a basic income, which was wrong, and the reason
was that the model treated what an artist earns as a certainty. Decomposing the
choice for strongly creative agents showed self-directed work beating idleness by
+3.41 points in the status quo but only +3.03 under a UBI: the same krónur of
earnings simply matter less once income is higher, while the creative reward is a
fixed constant.

What was missing is the thing a basic income actually changes. Creative earnings
are uncertain — the work sells in some years and not in others — and because
utility is logarithmic a bad year hurts far more than a good year helps. That
asymmetry is why people with a vocation take a salary instead, and a floor under
the bad year removes it. Self-directed work is now judged on the **expected
utility across a year that sells and one that does not**
(`behaviour.independent_sale_probability`, `independent_floor_share`), with
expected earnings unchanged. Independents now rise under a UBI rather than fall.

### People study when they can afford to
Education was fixed at build: nobody ever went and learned anything. That left the
model able to show a basic income costing output but never building any, which is
too narrow a test of the reform. `step_education` lets 18–34 year
olds without a degree enrol, at a rate that responds to **what they would have to
live on while not working** — the channel the US negative income tax experiments
found, where school attendance and completion rose. Three years later they
graduate, earn a premium, and can enter professions that require a degree.

The stock is anchored on Hagstofa SKO00000: **19,528 in tertiary education in
2025**. Reported as `students`, `new_students`, `graduates` and
`tertiary_share_16_74`, and it costs the state ~2.2 m ISK per place per year.

### Life satisfaction, 0–10
The old wellbeing index was three crude terms. It is now built per adult from the
determinants the life-satisfaction literature identifies, with weights whose signs
and rough sizes follow it (`params["wellbeing"]`): income against the median in
logs, involuntary unemployment (which costs far more than the income it takes
away), ill health, partnership, job quality as meaning less disamenity, job
security, housing cost burden above 40% of income, hardship below subsistence, and
time pressure for full-time workers with a child under school age.

The model cannot predict how happy Icelanders are, so the scale is **anchored on
the published figure (~7.5 on the Cantril ladder) in the base year** and every
scenario is read as a difference from it. Reported as a mean, a 10th percentile,
the shares struggling (<5) and thriving (≥7), a breakdown by component — which
says *why* a scenario moves wellbeing — and separately for workers, independents,
the involuntarily idle, pensioners and parents.

The model's known limits, and the evidence each mechanism rests on, are in
**docs/VALIDATION.md**.

## 16. The fund, the degree and the firm (v5.1, 2026-09-16)

Three links in the reform's own argument were either mis-specified or absent.

### The start-of-life fund now reaches the person, at 25
It paid out at **18** and the money never arrived: the sum only nudged aggregate
housing demand, and no household's balance sheet changed. It now pays out at
`policy.fund_payout_age` (**25** — the age both the housing and the starting-a-
business decisions are actually made), and splits three ways: into housing equity,
which turns a renter into an owner once it covers a deposit
(`fund_deposit_share`); into liquid wealth; and into `seed_capital`
(`fund_venture_share`), money of one's own to start something with.

### Capital of your own makes starting something easier
`seed_capital` raises the effective capital access in the venture decision
(`ventures.seed_capital_effect`) and decays as it is spent. Before this, the
reform's state stake had no counterpart on the founder's side — the money
existed in the accounts but never in anyone's hands.

### A course goes at the speed the rest of life allows
Study progress now depends on whether the student is working: a full year of the
course for someone who does not have to work, `progress_part_time` (.55) for
someone working part-time, `progress_full_time` (.25) for someone holding down a
full-time job. This is where a basic income buys **completion**, not just
enrolment, and it is why `students_full_time` is reported alongside `students`.

### And a degree is where ideas come from
Venture formation ignored education entirely. A degree now raises both the chance
of having an idea worth acting on (`ventures.education_idea_bonus`) and the
quality of the firm that comes of it (`education_quality_bonus`), which is the
link that makes a longer education pay off for the country rather than only for
the person holding it.

Together these close the reform's own causal chain — basic income → afford to
study → finish rather than drop out → better ideas, with capital at 25 to act on
them and the state holding a stake in what results — so it can be **tested**
rather than asserted. Every one of those steps is a parameter with an EST value,
and the Monte Carlo sweeps them.

## 17. Inflation, health, childhood and public works (v5.2, 2026-09-16)

### The model had no inflation
What it called the CPI was a **relative-price** index — unit labour costs, the
exchange rate and rents, normalised to 2025 = 1 — with no money growth and no
target. It ran at +1.3%/yr where Iceland has averaged **4.55%/yr since 2005**
(VIS01005), 3.43% over the last decade, against a 2.5% Seðlabanki target.

That was not cosmetic. Contract wages are **nominal** and fixed until renewal, so
with no trend inflation they never lost value between settlements and the erosion
mechanism barely bit. `markets.trend_inflation` (2.5%, the target) now carries the
nominal path; the króna and the policy rate respond to the **differential** against
trading partners rather than the level. The status quo now runs at 3.5%/yr.

### Health is a state variable
The evidence that a secure income improves health is unusually direct: Manitoba's
Mincome cut hospital use **8.5%**, concentrated in accidents and mental health
(Forget 2011); Finland's trial found clearly better mental wellbeing with no
employment effect; the Cherokee casino payments reduced children's psychiatric
symptoms. What does the damage is hardship and involuntary idleness rather than low
income as such, so those are what `step_health` responds to, with recovery once the
cause is removed.

Health now drives public health spending (anchored on THJ05511: **405.8 ma.kr.**
in 2025, of which 261.0 is hospital services — 8.5% of which is the ~22 ma.kr. the
hardship weight is set to reproduce), the rate at which people leave work through
ill health, and the health term in life satisfaction, which is now a continuum
rather than a disability flag.

### A childhood spent poor follows you
`poverty_years` counts the years a child spends in a poor household. It then costs
them: earnings when they reach working age, and the chance of going on to study.
The Cherokee payments raised educational attainment and cut criminality (Akee et
al.); Baby's First Years found unconditional cash to low-income mothers changed
infant brain activity (Noble et al. 2022). Because a payment to every child removes
this, the benefit arrives with a **fifteen-year lag** — which is precisely why it
needs to be in a model rather than argued about.

### Public works
`infrastructure.py` adds the projects Iceland keeps deferring: Reykjavík light
rail, a Keflavík rail link, tunnels for the countryside, a railway around the
country. They differ from the frontier programmes — no export revenue, no state
return. They pay back in **travel time, which shows up as productivity** once a
thing opens, and employ people while being built. Ordinary road building is not
modelled because it continues at about the same level either way and nets out of
any comparison.

Costs are EST, anchored where public estimates exist (light rail ~100-130 ma.kr.,
a Keflavík link ~105-150, tunnels ~15-30 each); the ring railway has no serious
costing and its figure is a placeholder of the right order.

### Reading FTE under a shorter week
`fte_per_adult_16_74` is measured in **2025 full-time weeks**, so a four-day week
lowers it by design — someone working the full standard week counts as 0.8. That is
the policy working, not a denominator error. `standard_weeks_per_adult` counts a
standard week as 1.0 whatever the week currently is, and `weekly_hours_per_adult`
gives the hours. Use those two when the question is "is everyone working?".

## 18. Crime, and the costs of governing (v5.3, 2026-09-17)

### Crime
Offending is driven by what the evidence says drives acquisitive crime: hardship,
involuntary idleness among the under-30s where offending concentrates, and years
of childhood spent poor. The Cherokee casino payments cut minor offending among
the young, working through less poverty and better parenting (Akee et al.), and
studies of welfare payment timing find property crime tracks how much money
households have.

**The model also carries the finding that cuts the other way.** Alaska's Permanent
Fund Dividend reduced property crime slightly while *raising* substance-related
incidents in the days after payment (Watson, Guettabi & Reimer 2020). That is a
live term (`crime.substance_weight`, biting above a threshold payment), so a large
basic income does not automatically read as less crime. A model carrying only the
favourable half of a literature is advocacy, not evidence.

Anchored on Hagstofa THJ05142: public order and safety cost **75.9 ma.kr.** in
2025 — police 41.5, courts 10.8 — of which about **57.3 ma.kr.** is the part that
responds to offending, fire protection excluded. Reported as `crime_index` against
the base year and `crime_cost_bn`, because the *level* of crime in Iceland is not
something this model can predict; how it moves is.

### The costs of governing, measured rather than guessed
THJ05142 (COFOG 0111) puts the whole executive and legislative apparatus —
parliament, ministers, the ministries' running costs, the presidency — at
**16.1 ma.kr.** The split between the lines within it is still EST; the total is
not. Added to it, separately identified: party funding, rural travel support, the
foreign service, and **church and religious funding** (7.8 ma.kr., sóknargjöld
being collected through the income tax system so that ending them simply leaves
the money with the state).

The whole package is worth about **14 ma.kr. a year** against a residual gap near
358. It closes under 4%. Ministers barred from sitting in parliament is a **cost**,
not a saving, because the alternates take the vacated seats. Each can be argued
for on its own terms, but none of them is a material source of financing.

## 19. Trade, schooling, emissions and sick pay (v5.4, 2026-09-17)

Added after a deliberate audit against Hagstofa's COFOG breakdown (THJ05142) — the
state's own budget being the nearest thing to a list of what a society does, and
therefore the right way to find what a model has quietly left out.

| Function | ma.kr. 2025 | before | now |
|---|---:|---|---|
| Social protection | 544.9 | yes | yes |
| Health | 424.1 | **no** | yes (§17) |
| General public service | 388.9 | partly | executive/legislative measured at 16.1 |
| Education | 347.5 | tertiary only | **+ schooling, 258** |
| Economic affairs | 249.6 | partly | + tourism |
| Recreation, culture, religion | 149.4 | partly | + church funding |
| Public order and safety | 75.9 | **no** | **yes, 57.3 responsive** |
| Environment | 36.1 | **no** | emissions tracked |
| Housing | 26.2 | partly | partly |
| Defence | 13.1 | no | no — 0.6% of spending |

### Terms of trade, and tourism
Exports were one flow moving with the exchange rate. They are now **tourism .36,
marine .21, aluminium .17, other .26**, each with a world price, against an import
price. Terms of trade feed export earnings, and tourism — the largest earner —
**employs people** for the first time, in the service, sales and food professions
where those jobs are.

This closes a real hole: the model could not previously represent a fish-price
crash, an aluminium swing or a tourism collapse, which are Iceland's three main
external risks. It is also the likeliest explanation for the residual puzzle in
§16 — real wages grew 2.1%/yr historically against 1.07%/yr of productivity, and
terms of trade are where the rest came from.

### Schooling
Compulsory and upper-secondary schooling (EST 258 ma.kr. of the 347.5 education
total) now costs money in proportion to how many children there are, so fertility
and migration move it. Tertiary is modelled agent by agent (§13).

### Emissions
Territorial emissions with the smelters explicit (EST 1.8 Mt of 4.6). Reallocating
12.9 TWh away from aluminium is a large emissions decision as well as a fiscal one,
and arguably the reform's most defensible argument for doing it — which the model
previously could not state at all.

### Sick pay
`policy.public_sick_pay_cut`: the state stops carrying sick leave for its own
employees and private insurance takes the risk. At an EST 5.5% absence rate this is
worth about **39 ma.kr. a year — more than every cut to the cost of governing put
together.**

It is not free, and the model says so: whoever falls ill without cover loses income,
which runs through hardship into health, wellbeing and, via §18, offending. The
share who insure privately is a parameter, and what the uninsured remainder suffers
is carried explicitly rather than assumed away.

### Already covered, for the avoidance of doubt
Unemployment benefit needs no separate lever. Under the reform the **entire**
358.6 ma.kr. social benefits envelope is replaced by the borgaralaun — jobseeker's
allowance, disability pension and old-age pension alike.

## 20. Who owns the buildings (v5.5, 2026-09-17)

Commercial real estate did not exist in the model, and neither did ownership
concentration in either market. Both now do.

**The mechanism.** Concentrated ownership of rental property supports rents above
what a competitive market would set. A cap — expressed as the share of total square
metres any one company or affiliated group may hold — forces a sale wherever it
binds. That adds sellers and competitors, and the premium comes out of rents over
`divestment_years`.

At the reform's setting of **5% residential and 10% commercial**, against EST current
top-owner shares of 14% and 22%, the model gives residential rents **−3.6%** and
commercial rents **−4.5%** once divestment completes.

**Why commercial matters differently.** Residential rent is a household cost, and
lower rents run through the CPI, the housing cost burden and wellbeing. Commercial
rent is a *fixed cost that decides whether a small business is viable at all* — so
it enters the venture decision through capital access, which is the mechanism
behind the argument for capping it.

**Honesty about the magnitudes.** That concentration raises rents is supported by
work on institutional landlords, but the size is contested and these four numbers
(`residential_markup`, `commercial_markup`, and the two current top-owner shares)
are EST. The Monte Carlo sweeps them. Treat the direction as the finding.

## 21. Ownership for a term, not for ever (v5.6, 2026-09-17)

The proposal: property reverts to the public after a term — 30, 50, 75 or 100
years depending on the project — with extensions when the owner adds or upgrades,
and a builder's exemption from the ownership cap that lasts ten years per project,
after which they must sell if they are at capacity. In effect, freehold converted
to long leasehold with reversion, which is how the Netherlands, Hong Kong and
Singapore already hold land.

**What is not in dispute** is the pricing. A claim that ends in T years, discounted
at a real rate r, is worth `1 − (1+r)^−T` of a perpetual one. At 3.5%:

| Term | Worth, against owning for ever | Property values |
|---|---:|---:|
| 100 years | 96.8% | −3% |
| 75 years | 92.4% | −8% |
| 50 years | 82.1% | −18% |
| 30 years | 64.4% | **−36%** |

The market prices this the day the rule passes, so the fall is immediate, not
gradual. For housing affordability, a
30-year term is the single most powerful lever in the model — and also the one
whose second-order effects are least certain.

**What is in dispute** is everything after that, and the model carries both sides:

- **Under-maintenance.** Leasehold systems show real neglect as terms run down —
  nobody reroofs a building they lose in eight years. Modelled as faster
  depreciation of the housing stock (`maintenance_decay`), partly won back by the
  extensions for upgrades (`upgrade_extension_offset`). At a 30-year term the stock
  depreciates about 10% faster even after the offset.
- **Reversion revenue** arrives decades out, **beyond any horizon this model runs**.
  The state's eventual acquisition of the stock is real and large and this model
  will not show it. That is a limitation to state plainly rather than a result.
- **Continuous building.** A builder's exemption that expires per project means
  staying at capacity requires selling and building again, which the model treats
  as a further construction incentive on top of the exemption itself.

**A caution worth putting in writing.** This is the most far-reaching option in the
reform and the one where the model is least able to be trusted on magnitude. The
price effect is arithmetic and solid. The behavioural response — whether people
still build, maintain, and lend against property whose ownership ends — is EST,
and the international leasehold evidence comes from systems that have always been
leasehold rather than ones that converted. Converting is the untested part, and it
is the part that matters.

## 22. The child payment, flat (v5.7, 2026-09-17)

The graduated schedule invested more of each additional child's payment —
50% for the first two, rising to 90% for a seventh — which was a guard against a
household living off its children. That guard is now **off by default**:
`policy.child_invested_flat` at .5 treats every child alike, and the schedule
remains available by setting it to None.

The consequence is not subtle and should not be presented as though it were. At
450,000 a month per child with half invested, a household keeps **225,000 per
child, with nothing taken back at any number of children**. Five children bring in
**1,125,000 a month** — more than most salaries in the country.

Whether people then have children for a living is exactly the sort of question a
model exists to answer rather than assert, so it is now a continuous lever from 20%
to 90% invested, and the outputs to watch alongside it are **births**, the **cost
of child payments**, and the **budget**. The fertility response runs through
`demography.fertility_income_elasticity`, which is EST and swept in the Monte
Carlo — so read the direction and the threshold, not the decimal.

Two things the model will *not* tell you here. It has no view on whether children
raised by a parent at home do better or worse, because nothing in it represents
parenting quality. And the childhood-poverty channel (§15) cuts the other way: a
payment per child that keeps households out of poverty improves those children's
adult earnings and their chance of studying, which arrives fifteen years later.


## 23. The surrogate, and what it cannot do (v1.0.0)

*Superseded by §24. Kept because two of the explanations below were wrong, and the record of that is worth
more than a tidy page.*

The explorer's 33 continuous levers are possible only because the page evaluates a fitted surface rather than
looking up a run. 660 Latin-hypercube draws over the levers, 10 years each, 99 outputs; the basis is a constant,
a linear and a square term per lever, and an interaction of each lever with the payment itself — 99 terms, ridge
least squares, five-fold cross-validated per output *per year*. The whole build takes about 4.2 hours.

The fit is honest about itself. 84 outputs reach R² ≥ 0.85 and a further 9 sit between 0.5 and 0.85. Six do not
fit at all:

| output | median R² | why |
|---|---|---|
| `involuntary_part` | 0.00 | ~~a small count; nearly all of its variation is the run's own seed~~ **wrong: it was zero in every run, because the model could not produce it (§24)** |
| `schooling_cost` | 0.00 | ~~driven by a child count that moves in integer steps~~ **wrong: it was frozen at 258 in every run by a missing baseline (§24)** |
| `p90_p10` | −0.14 | a ratio of two tail estimates, so both tails' noise compounds |
| `births` | −0.15 | Poisson draws on a small base; year-to-year noise swamps the lever effect |
| `income_volatility` | 0.18 | a second moment of a difference — noisy by construction |
| `net_income_sd` | 0.45 | the same problem, one moment down |

A negative R² is not a weak fit, it is no fit: the surface does worse than that output's own mean. The response
was **not** to smooth them or widen the basis until the number looked better — that would fit the noise. The page
prints *not fitted* in the scenario column and shows the exact status-quo figure beside it, and the income tab
says in words why the spread columns are blank. The fix, if these matter for a question, is a direct run.

`births` is the one that costs something: the flat child payment is meant to be read against it, and the
surrogate cannot carry that reading. Run the scenario directly to answer it. *(§24: births were not noise alone —
they did not respond to the payment at all.)*

Since this build, `build_emulator.py` writes the raw design and runs to `data/processed/emulator_runs.json`
before fitting, so trying a different basis costs seconds instead of another four hours. That file did not exist
when the shipped surrogate was built, which is why these six were left as they are.


## 24. Seven faults behind the fits, and the surrogate rebuilt (v6.0, 2026-09-17)

Chasing the six outputs the v1.0.0 surrogate could not fit turned up faults in the model, not only in the fit.
A value of exactly 0.00 was the fitting routine's marker for "nothing to fit", not a measurement, and that was
the thread.

### The faults

| | what was wrong | what it did | fix |
|---|---|---|---|
| 1 | `children0` was never on the calibrated society: it was added to `calibrate()` after the cached calibration was written, and `schooling_cost()` read it through `getattr(..., None) or kids` | the schooling bill was 258 ma.kr. in every year of every run, whatever happened to the number of children | set during calibration; the fallback removed |
| 2 | the calibration cache was stamped with a hash of the parameters only | any baseline added to the code later was silently missing from the cached society | the stamp now covers `src/ubisim` too, taken when the process loads the model; every script with a cache uses it; `scenario()` refuses a society missing any of `model.BASELINES` |
| 3 | the birth response measured the child payment against `per_child0`, set lazily in a scenario's own first year — with the payment already in place | **births never responded to the child payment** | the reference is taken at calibration, under the status quo; also in `BASELINES` |
| 4 | the `involuntary` flag is cleared whenever someone re-chooses and set only together with being laid off | involuntary part-time was zero by construction; parents cut to part time for want of a childcare place were never recorded as such | a separate `underemployed` flag: a shortfall cuts a quarter of the full-timers it reaches to part time instead of dismissing them (`labour.hours_cut_share`, EST), and childcare cuts are recorded |
| 6 | unemployment was calibrated by holding labour demand at 93% of supply for good | the surplus laid people off at the right rate, but it also pinned every new contract at the bottom of its allowed range (15% below the going pay), year after year; **status-quo real wages fell 0.9%/yr** | demand equals supply at base wages; unemployment comes from frictional separations (jobs ending for reasons unrelated to demand), their rate calibrated to VIN01104 (≈1.5%/yr); only dismissals carry paid notice |
| 7 | wages are nominal (contracts are indexed to a CPI that carries the 2.5% trend), but non-tradable prices, export competitiveness and profit margins set them against relative prices, and the CPI then multiplied the trend in again | the trend was counted twice in prices; each renewal chased it, so **real wages could not grow whatever productivity did**. Present since trend inflation was added (v5.2) | `Macro.relative_wage_cost()` takes the trend out before a wage meets a relative price, in all four places |
| 5 | emigration was scaled assuming half a child per adult; arriving partners and children were added on top of totals that already counted them; only couples could bring a child | 23,000 emigrants a year, 29% of them children (Hagstofa 2025: 15,508 and 7%); 27,000 arrivals (18,674). **The child population fell 21% in ten years of the status quo** | both flows solved against Hagstofa 2025, children included — see below |

On emigration, two numbers are solved from the actual rule (a partner follows 80% of the time, a mother takes her
children): an overall scale, and how much less readily a household with children moves. The data put the second
at **0.14** — households with children leave at a seventh of the rate of others. That is on the strong side of
the family-migration literature, and it is what Hagstofa's own count of children among emigrants implies under
this rule. Arrivals are drawn as adults, a share bring a partner, and children follow at Hagstofa's rate per
adult (0.15 for returning Icelanders, 0.08 for others) with its age profile, to single mothers as well as
couples. The calibration is solved once more after burn-in, on the population scenarios actually start from;
solved only before it, year one overshot emigration by a quarter.

After the fixes, year one of the status quo against Hagstofa 2025: emigrants 16,327 (15,508), of them children
1,133 (1,129); immigrants 17,656 (18,674), of them children 1,469 (1,597). The child population moves −1.8% over
ten years instead of −21%. The quality check now tests all five figures.

The burn-in fits the choice model under the separation rate it is given, so that rate starts at 1.5%, where
calibration ends: fitted under 4% the model chose work too readily (part-time 28%), and fitted under none,
employment fell to 73% once churn began.

After all seven, the quality check passes 90 of 92. Status-quo real wages grow (about +0.5%/yr across a contract
cycle, below Iceland's recorded +2.1%, much of which came from the terms of trade rather than productivity) and
prices rise about 2.2%/yr. Employment is 77.3% in the base year and 74.8% → 76.2% over the run, against 77.8%.
**Still failing: status-quo real median household income, −0.46%/yr** (−0.29% at v1.0.0). Part is composition —
with migration at Hagstofa's flows the adult population ages faster — and part is the wage growth above falling
short of the record. Status-quo income *levels* should still not be quoted; differences are the reading.

What the fixes change in results, status quo against the reform at 450,000 *(measured on the calibration
before faults 6 and 7 were fixed; to be refreshed from the rebuilt runs)*:

* **Births rise about 15% under the reform** (≈4,950 against ≈4,330 a year). Before, zero.
* **The schooling bill follows the children**: 257 → 252 ma.kr. in the status quo, 261 → 282 under the reform,
  which keeps more of them. That is about 30 ma.kr. a year the reform was not being charged by year ten.
* **Involuntary part-time exists**, at up to about 1% of adults in the status quo. It starts at zero because
  the 2025 population is not seeded with it — a remaining gap.
* **The reform's population grows 12% faster** than the status quo's over ten years (456,800 against 407,800),
  from births, from arrivals and from fewer leaving.

Not changed, and not caused by these faults: the reform's nominal balance widens every year, from about −420
to −1,760 ma.kr. by year ten, as it did before (−579 to −1,876). Debt as a share of GDP is the steadier reading.

### The surrogate, rebuilt

* **Design.** 1,200 points, the Latin hypercube with the least correlated columns of 300 drawn.
* **Levers.** 32: the presidency folded into governing costs, where its description already was. The ownership
  term is sampled evenly in what a finite claim is worth, from 30 years to for ever. In years, "for ever" had
  been coded as 0, beside 1 year — a cliff at the edge of the range that no smooth surface can follow, and one that
  fed house prices and rents.
* **Basis.** Levers centred on the middle of their range (a lever and its square are no longer near-copies),
  columns standardised, the ridge penalty chosen per output and year by five-fold cross-validation. Every lever
  crossed with the payment, and per output the pairs among its six most important levers. Governing costs and
  church funding enter linearly only.
* **Correction.** Where it adds at least 0.01 to cross-validated R² on average, a Gaussian kernel over the runs,
  on the eight levers that matter most to that output, is laid over what the polynomial misses.
* **Averages.** Births, the standard deviation of income, the top-to-bottom ratio and income volatility are fitted
  and shown as trailing three-year means, the status quo averaged the same way, and labelled on the page.
* **Formulas.** The value of a finite ownership term, the upkeep it costs, and infrastructure spend and jobs are
  computed on the page rather than fitted. Each formula is checked against every run and used only if it matches
  every one; on the smoke run they matched to machine precision.
* **Honesty.** R² is that of the whole procedure — penalty, basis, correction — under five-fold cross-validation.
  Choosing the penalty on the same folds flatters it slightly.
* **Durability.** Raw runs are saved every 50 runs; `--resume` continues a broken build and `--refit` refits in
  minutes.

### Births, run rather than fitted

`scripts/build_births_grid.py` runs 64 settings — the payment at 0 to 600 þús., the share held in the child's fund
at 20% to 90% — with every other lever at the reform default, each with three independent seeds. The explorer's
Children tab shows the grid, the spread between seeds, and says when the viewer has moved levers it does not
reflect. The fertility response is `demography.fertility_income_elasticity` (EST, .5, range .1–1), and the base
number of births does not follow the number of women of child-bearing age: treat the direction as the finding.

### The page

The published explorer never loaded `emulator.js`, so it ran the older path — fixed stops, lever effects added
together — while this document described continuous levers. Had the file loaded, the page would have failed:
the lever state read `PLATFORM_DEFAULTS` before it was declared. Both are fixed, and the page now takes its
status quo from the surrogate's own runs, so an averaged output is compared with an averaged baseline.


## 25. The calculation sweep (v6.0, 2026-09-17): 26 faults

Prompted by the property tax: raising it made "income after tax and transfers" *rise*, because the tax was never
taken off anyone's income. A sweep of every formula for the same class of fault — a variable left out, an index
divided by krónur, a real amount set against a nominal one, a thing counted twice or not at all — found the
following. Many of them are enough to have moved headline results on their own.

**Units: the model has three kinds of number.** Wages, taxes and transfers are in *today's* krónur (contracts are
indexed to a CPI that carries the 2.5% trend). Wealth, house values, the fund, public debt, the budget balance and
the base-year service budgets are in *2025* krónur. Prices, the króna, rents and house prices are *indices relative
to the trend*. Most of the faults were one of these meeting another.

| # | where | what was wrong | effect |
|---|---|---|---|
| 1 | income | **property tax and the wealth tax were never deducted from household income** (`household_levies`, now in `refresh_net_now` and every option income, once per household) | **headline income rose with the property tax** |
| 2 | housing | burden divided a rent *index* by income in krónur | median burden 0.000002; nobody ever over 40%; the housing term in life satisfaction never moved |
| 3 | accounts | 21 flows built in 2025 krónur (property tax, corporate tax, health, schooling, crime, education, infrastructure, fisheries…) were deflated again by `balance()` | **the budget balance was biased by about 2.5% of those items a year** |
| 4 | macro | real debt divided by nominal GDP (also the risk premium, net foreign assets, the fund ratio) | **debt ratios fell with inflation: status-quo debt appeared to halve in ten years, and the reform's debt path was hidden** |
| 5 | macro | a nominal wage set against relative prices in non-tradables (fixed earlier today), construction costs, fisheries and needs-driven demand | prices double-counted the trend; building, fisheries rent and care/teaching jobs shrank with inflation |
| 6 | policy | occupational pensions never indexed | **every pensioner lost 2.5% of real income a year** |
| 7 | policy | status-quo child benefit, parental support, the minimum wage and pay floors never indexed | each eroded with inflation |
| 8 | step | the UBI indexed to *last* year's prices | **the payment lost a year's inflation in real value, permanently** |
| 9 | migration | an arrival's tax brackets unindexed, and the wrong schedule under the reform; pay abroad held flat while pay here grew | immigration drifted down; staying looked better every year |
| 10 | hardship | one person's income set against the *household's* budget, in crime, health and childhood poverty | a low-earning partner in a comfortable couple counted as in hardship |
| 11 | childhood | a mother's own income only — **child payments and the partner's pay left out** | **the child UBI never lifted a child out of the poverty count** that feeds adult pay, study and crime |
| 12 | wealth | stored in 2025 krónur, read as today's in option incomes, consumption, the wealth tax and the savings buffers | |
| 13 | independents | income paid without the creative trait the choice was priced on | people chose one income and were paid another |
| 14 | demand | culture compared total with per-head consumption; essential-service gaps used unscaled demand | |
| 15 | macro | the króna answered total inflation against partners', not inflation beyond the trend | a real exchange rate drifting with the nominal trend |
| 16 | macro | government interest carried the 2025 inflation premium whatever the trend | |
| 17 | crime | the substance effect added a fixed amount to everyone's pressure; the 2025 population had no childhood-poverty history | status-quo offending rose 166% in six years; the substance term outweighed everything else |
| 18 | ratios | house price to income: a real price over nominal income | fell with inflation |

**Found by the inflation test itself**, which kept failing until each of these was fixed:

| # | where | what was wrong | effect |
|---|---|---|---|
| 19 | contracts | pay frozen in krónur for the whole agreement; Icelandic agreements schedule yearly raises that build in expected inflation | real pay several percent lower at 2.5% inflation than at none, prices below trend, lower rates, higher house prices and profits. **This was also why status-quo household income fell** — the check that failed from v1.0.0 now passes |
| 20 | contracts | a new hire's contract start and price level never reset | the first renewal made good inflation and productivity since someone else's agreement began |
| 21 | choice model | taxes in the option incomes indexed to last year's prices while the solver valued everything at this year's | a year of fiscal drag in every work decision |
| 22 | macro | measured inflation started at zero, not at the trend | a phantom disinflation in year one: rate cut and stronger króna in every run with a trend |
| 23 | debt | nominal interest on non-indexed debt charged at face value while the debt was deflated | the budget paid inflation's premium without its full erosion back |
| 24 | wage solver | started from last year's krónur, and stopped short with bounded steps | corporate tax depended on the inflation rate |
| 25 | wage solver | **the ±15% window on new pay sat around last year's krónur** | a trend's width lower in real terms; the reform's large shock pressed on the ceiling, so **real wages cleared 5–6% lower with inflation than without, and platform debt 5–7 points higher** |
| 26 | diagnostics | the price-freeze switch dropped the trend from the CPI | frozen runs were not comparable with others |

After all 26: across four random seeds the reform's debt ratio differs by 0.5–1.7 points with and without the
trend (it was 5–7), its real wage bill by 0.5–1.5% — the lag of pay fixed between renewals, which is real — and
the status quo by less. The balance is also reported net of inflation's erosion of the debt
(`balance_operational_bn`), because the conventional balance counts inflation's premium in interest and cannot be
neutral; the page shows both.

**The test that now guards this.** `quality_check.py` runs the status quo and the reform twice — with the 2.5%
trend and with none — and requires fifteen real outcomes to match: income, employment, the balance, the debt
ratio, housing burden and prices, schooling, property, fisheries and corporate tax, the housing stock, savings
buffers, immigration, fixed-line poverty and offending. Every fault above except 1, 2, 10, 11, 13 and 14 fails it.
The only legitimate gap is pay fixed in krónur between contract renewals, which is what the tolerances allow for.

The property-tax test after the fixes, reform, year 5: median equivalised income 731 → 716 → 695 þús. at +0,
+1 and +3 pp; the tax households pay (70 ma.kr. at +1 pp) matches the residential part of the extra revenue.

Not changed, noted: status-quo unemployment support is one flat 250,000 for all prime-age non-workers, not
Iceland's earnings-related insurance; the "customs abolished" static item applies whenever the reform does.
The share paying over 40% of income for housing now reads about 28%, well above Eurostat's figure for Iceland —
the housing costs in `params.costs` are EST and want checking against HMS data.

## 26. Indexation (v6.0, 2026-09-17)

A lever for taking CPI indexation (verðtrygging) out of household lending, in stages. The government intends to
reduce its weight from around the turn of 2026-27, starting with minimum principal payments on indexed mortgages
and protecting first-time buyers by other means, with the stated aim of making interest rates reach demand faster
([RÚV](https://www.ruv.is/frettir/innlent/2026-03-29-vilja-draga-ur-vaegi-verdtryggingar-fyrir-arslok-471319),
[Vísir](https://www.visir.is/g/20262837622d/fyrsta-skrefid-stigid-um-ara-mot-ad-af-nami-verd-tryggingar)).
Earlier bills let borrowers convert indexed loans without a new credit assessment
([Alþingi 155/128](https://www.althingi.is/altext/155/s/0128.html)). Nearly two in three household mortgages are
indexed, and indexed lending grew while non-indexed shrank through 2024-25. The IMF asks that the change be timed
with care, since indexation has helped borrowers weather high rates
([2025 Article IV](https://www.imf.org/en/news/articles/2025/05/05/mcs-iceland-staff-concluding-statement-of-the-2025-article-iv-mission)).

`policy.indexation_phaseout` (0–1) moves that share of indexed household debt to nominal terms over
`indexation_phase_years` (5). Government bonds and pension-fund assets keep their indexation. It acts through:

* **payments** — a non-indexed loan pays inflation in cash, so `Macro.mortgage_payment_factor()` raises what
  owners with mortgages pay while inflation runs, which reaches the subsistence budget, housing burden and hardship;
* **transmission** — household spending answers the real policy rate more strongly, by
  `markets.indexation_transmission_gain` (EST: twice as strongly with no indexation left).

The real-terms paydown of non-indexed debt is deliberately left out: the higher payments that achieve it are not
taken out of consumption in this model, so eroding the debt alone created wealth from nothing (it failed the
inflation test). Treat the lever's direction as the finding; its size rests on an estimate.

## 27. World prices, in both worlds (v6.1, 2026-09-18)

Two faults in how the four world-price levers (tourism, fish, aluminium, imports) worked:

1. **What imports cost did nothing.** `trade.import_price` entered only the reported terms of trade. It now sets
   the krónur price of tradable goods with the exchange rate (`P_T = e · import_price · tariff`), and so the CPI
   and what wages buy; the import bill scales with `import_price^(1 − 0.6)` — fewer imports, each dearer — as a
   level. (Routed through the króna term, which answers change against the reference path, the volume response
   lasted one year in the status quo while the dearer bill lasted for ever; a 10% dearer world raised the CPI
   12% by pushing the króna down year after year.) Fishing inputs bought abroad carry it too; other business
   input costs do not carry it separately.
2. **The status quo did not share the world.** Every reform was compared with one status-quo run at 2025 prices,
   and used it as its reference path. A fall in fish prices then showed up as a cost of the reform.
   `build_emulator.py` now draws the four world-price columns from 60 world points of their own (a Latin
   hypercube), runs the status quo at each, and gives each design run the status quo of its world as reference.
   A quadratic in the four prices, fitted to those 60 status-quo runs, is shipped as `status_quo_world`; the page
   adds its change from 2025 prices to the exact status-quo run, so at 2025 prices it is that run exactly.

The explorer starts from the forecasts, as ten-year averages against 2025 net of general inflation:

| Lever | Start | Basis (September 2026) |
|---|---|---|
| What tourism earns | 97 | visitors flat at 2.2-2.3 m since 2023, −2% in 2026, modest growth after; spending per visitor slipping (Seðlabanki PM 2026/3, Isavia, Íslandsbanki) |
| Fish prices (earnings) | 100 | prices up — most of the 2026 terms-of-trade gain — against marine export volumes −6.0% (2025) and −4.3% (2026); cod advice −1% for 2026/27, flat two to three years (Hafró) |
| Aluminium prices | 108 | $2,632/t in 2025, World Bank $3,200 (2026) and $3,000 (2027), easing later; smelter output −4.9% then +8.5% |
| What imports cost | 101 | Brent $69 (2025), $86 (2026), $70 (2027); food flat in real terms; partners' inflation 2.1-2.7% |

The births grid is still run at 2025 world prices; the Children tab says so when these levers move.

The fishing industry's own accounts now follow the world as well: the catch earns at the marine price, so the
resource rent a lease can capture moves with it, and fuel and gear bought abroad cost the import price. Part of
the smelters' power price follows aluminium (`energy.aluminium_price_link`, EST 0.4).

## 28. Version 2: every piece of the reform on its own lever (2026-09-18)

The reform switch used to bring in a bundle no slider could undo. Each piece now has its own lever with a
position for today, so the explorer can show the borgaralaun and nothing else, and add the rest one piece at a
time. The page offers three starting points: the borgaralaun alone, the reform as specified, and the standard
picture.

| Lever | Today | Reform | What it does in the model |
|---|---|---|---|
| Pension funds folded into the UBI | 0 | 100% | contributions go to the state as social security, occupational pensions stop with a top-up above the UBI, the funds' returns go to the UBI; at 0 the funds keep paying and the UBI comes on top |
| Seed money and a state stake | 0 | 100% | 3 m kr. per new firm, a 30% state stake, easier access to capital |
| Per diems abolished | 0 | 100% | static saving, ~13 ma.kr. |
| Pay set without collective agreements | off | on | wages renewed at market rates instead of agreed compensation for prices and productivity |
| Personal tax credit | 72.5 þús. | 0 | persónuafsláttur |
| Customs duties | 100% | 0 | 7.7 ma.kr., and the price of imported goods |
| Farm support cut | 0 | 100% | 19.7 ma.kr.; farm jobs (EST 25% of 3,500 FTE) and food prices (EST +0.3% CPI) |
| Other subsidies cut | 0 | 100% | 55.3 ma.kr., the saving only |
| Fisheries rent captured | 24% | 80% | veiðigjald today ≈ 17 ma.kr.; the status quo now collects it (it collected nothing, crediting the reform with the whole fee) |
| VAT refunds only on value-chain inputs | 0 | 200 ma.kr. | EST 100-350; exporters' costs scale with it |
| Pension-fund returns | — | 3% | a market assumption, not a policy |
| Inheritance tax, rate and tax-free amount | 10%, 6.5 m | 10%, 6.5 m | see below |
| Custodianship | 0 | 100% | see below |
| Public pay held at its old take-home | 0 | 0 | see below |
| End smelter power contracts | 0 | 100% | as before, now a lever |

**Public pay.** A full-time public job pays, after tax and with the borgaralaun, what it paid before: gross pay is
cut by the borgaralaun grossed up at the employee's marginal rate. It saves payroll and lowers the wage costs that
set prices, and it removes what a public job adds over not working, so the model shows who leaves.

**Inheritance.** Estates with no spouse to take them used to vanish from the model — every lone death took its
savings and home equity out of the economy. They now pass to the dead person's adult children where the model
knows them, otherwise to two adults of the next generation, net of tax. A spouse pays nothing, as today. The tax
is levied on a share of estate value (EST 0.45: assessed values, debts, undivided estates) above the tax-free
amount, and taxable estates shrink with the net-of-tax rate (elasticity EST 0.2, Kopczuk and Slemrod). Revenue is
the expectation over everyone's chance of dying that year, plus advance inheritance in the 2024 proportion
(9.1 of 14.7 ma.kr.), so the budget line is not a lottery.

**Custodianship.** Holding property — a home, a building, a firm, land, a quota — for as long as it is looked after
and earns, and losing it to the market when neglected. EST throughout: the stock wears out 15% more slowly, 2% of
dwellings (empty or derelict) return to use over five years, output rises 1.5% over eight years as neglected assets
change hands, prices carry a 3% risk discount, and assessments cost 2 ma.kr. a year. It would face Article 72.

**Variety.** A commercial ownership cap spreads ownership of the high street. Cheaper premises and room for small
owners now raise how many venture ideas are viable (they only entered the choice between working and starting a
firm, where nearly everyone with an idea starts one, so they changed nothing), and the spread itself is worth
something in people's lives: EST 0.03 life-satisfaction points and 0.4% of consumption at full effect.

## 29. Could this affect that? The links review, and the levers it added (2026-09-18)

Every lever was read against every part of the model with one question: could this affect that? What was missing,
and is now carried (all magnitudes EST, in `params.links`):

| Lever | The link that was missing |
|---|---|
| VAT | Tourists pay VAT on stays, mostly 11% today. A flat 25% makes a stay about 5% dearer for them; what they buy falls (elasticity 0.8) and the treasury gains the higher VAT on what remains (`VAT on tourists`). |
| VAT refunds only on value-chain inputs | The 200 ma.kr. is a cost to every business, not only exporters: 2% on home-market prices per 100 ma.kr. |
| Pension funds folded in | Part of what a job pays today is a pension. The choice between working and not now counts it (at 40% of its cost), so folding the funds in makes work pay less. |
| Customs | Most duties protect food: without them, 10% of farm work goes. |
| Custodianship | Upkeep as a condition of holding property: 1,500 FTE of trades work at full strength. |
| Energy and transport subsidies | Heating and fares: +0.8% on the CPI at a full cut. |
| Innovation and film subsidies | Less research and fewer new firms: −0.3% output, 5% fewer venture ideas at a full cut. |
| Net wealth tax | Wealth moves, hides and is revalued: elasticity 0.3 on the net-of-tax return, narrowed by an exit tax and by enforcement. |
| Capital controls | Damp the debt premium, and cost 0.5% of output at full strength. |
| World prices | Fishing's own rent follows the fish price and its imported inputs the import price; part of the smelters' power price follows aluminium. |

New levers: the other subsidies split in three (innovation and film 21.7, energy and transport 17.7, culture, media,
waste and other 15.9 — THJ05161, 2024); gift and advance-inheritance tax; a tax on moving assets abroad (on the
unrealised gains of emigrants above 50 m kr., as in Norway and Denmark); staff moved to tax enforcement (evasion
~4% of GDP, diminishing returns, and narrower ways round the inheritance and wealth taxes); the borgaralaun withheld
in prison (today benefits stop after four months; severity deters little, so the effect on crime is small); the
payment protected from lenders; payments to foreign gambling sites blocked; free health care (65 ma.kr. out of
pocket, taken over) and free internet (13 ma.kr.); residence rules and capital controls.

Inheritance avoidance is split by route: gifts (closed when gifts are taxed alike), moving wealth abroad (closed by
an exit tax at the inheritance rate), and the rest, which enforcement narrows.

**Gambling and credit.** On average cash transfers do not raise spending on gambling, alcohol or tobacco (Evans and
Popova, 19 studies). At-risk gamblers (2% of adults) lose part of the payment on top of what they lose today; two and a
half times as much where a lender will lend against it. Blocking payments to foreign sites stops part of today's ~20
ma.kr. a year, half of which moves to licensed Icelandic games. Protecting the payment from creditors — as benefits
are protected today — removes it as collateral without taking it from the borrower. Forfeiting it on taking out a
risky loan would do the same to lenders but punish the borrower's family, so it is not the design modelled.

### How the levers are arranged

The explorer presents its 65 levers as an economic model presents its inputs, without dropping any part of the
reform:

1. **Policy instruments**, classified as public finance classifies them: the borgaralaun itself; taxes on labour
   income, on spending, on profits and capital, on property and wealth; collecting what is owed; public services
   and transfers; public employment and pay; subsidies; public investment; then the rules of markets — the labour
   market, property rights and competition, money, credit and the border, energy. Each has a position for today
   and one for the reform, and budget lines show their size as a share of GDP.
2. **Conditions outside policy**: world prices, the pace of AI, the return on the pension funds' assets.
3. **How people and markets respond**: five elasticities from `uncertainty.RANGES`, for sensitivity — emigration
   against income, births against child income, labour demand against wages, tourists against prices, and a
   multiplier on every tax-avoidance response. The status quo is run at their central values: in it there is
   little for them to respond to — no borgaralaun, no change of tax — so the comparison holds. The labour-supply
   elasticity is not among them: the model is calibrated to it, and each value needs its own calibration.

## 30. The backcast: 2015 to 2025 (v3, 2026-09-18)

The model starts in 2015 from that year's Hagstofa data (`data_prep --year 2015`: population, jobs, pay by
profession; the waiters' suppressed 2015 cell is carried from 2018 as a ratio to their group) and walks through
2016-2025 as they happened (`scripts/backcast.py`). The base year is a parameter block (`base`): the national
figures the macro block starts from, the wage bill and public payroll the population is scaled to, and the 2015
tax rules. Settings written in 2025 krónur are carried back by the CPI (prices, benefits, living costs), the wage
index (costs that follow pay) or nominal GDP (public spending lines) — `scripts/history_params.py` says which for each.

Each year the backcast imposes (`history/policy_calendar.json`, `history/world_prices.json`, all sourced there):
the year's income tax brackets and allowance (Skatturinn), payroll tax, the employer pension contribution rising
from 8% to 11.5% (2016-2018), the inheritance-tax floor, benefit generosity (real social benefits per person 67+,
2020-21 interpolated), what tourism, fish and aluminium earned (UTA05003, deflated), oil and partners' inflation
(World Bank, Eurostat), the COVID support (3% of GDP in 2020, IMF; 2% in 2021, EST) and the partial-unemployment
scheme keeping part of the lost tourism jobs (EST 60% and 30%). The 2016 budget surplus from the old banks' estates
is left out of the comparison.

**What it found, before any tuning.** The status quo settled about three points below the published employment
rate from its first year — at the 2025 base too (78.0% calibrated, 75.2% in year one against 77.8%). Calibration
fitted activity shares with migration off and separations with it on, and nothing checked the settled rate after
both; `_calibrate_employment_level` now does. The largest remaining misses: population and immigration (the model
held arrivals near 2015's 12,000 a year against 15,000-22,000), real wages (Iceland's rose 2.2% a year, above
productivity, with the terms of trade and the strong króna of 2016-17; the model's track productivity), and the
budget in the COVID years. Immigration now can follow unfilled jobs (`immigration_tightness_elasticity`, 0 by
default), and `scripts/tune_backcast.py` tunes 22 uncertain responses on 2016-2021 and tests on 2022-2025.
