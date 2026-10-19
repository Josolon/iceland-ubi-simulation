# How the model works — the reference

This is the full account of the Iceland borgaralaun model: what it simulates, in what order, by which equations,
from which data, on which research, and with which numbers that are estimates rather than measurements. Every parameter, with its value and status, is listed in [PARAMETERS.md](PARAMETERS.md), generated from
the source so it cannot fall out of step.

Nothing here is advocacy. Where the evidence runs both ways the model carries both sides, and where a number is a
guess it is marked as one.

Tags such as (v3) or (v9) mark the version in which a mechanism was added. Later versions changed some figures:
where this text and [PARAMETERS.md](PARAMETERS.md) disagree, PARAMETERS.md is the current value, since it is
generated from the source. [CHANGELOG.md](../CHANGELOG.md) lists what changed when.

---

## 1. What the model is

An **agent-based model** of Iceland at one-to-one scale: 394,108 simulated people in 2025, one for every resident,
built from Hagstofa's published tables. Each year every person ages, some reconsider whether and how much to work,
some start firms, some move abroad and others arrive, children are born and people die. Around them sit markets —
wages by profession, prices, the króna, interest rates, rents and house prices — and the public accounts.

The same society is run twice under the same world:

* the **status quo**: Iceland's 2026 tax and benefit rules, carried forward;
* a **reform**: the borgaralaun and whatever else is switched on.

Every result is the difference between the two, year by year, in the same world (the same world prices, the same
pace of AI). Money is in **2025 krónur** throughout — deflated by each run's own price level — so "income" always
means what it buys.

**Two ways to use it.** The model itself takes minutes per run. The explorer page cannot run it, so it carries a
*surrogate*: a statistical fit to about 2,000 runs across the levers (§17). Anything found on the page — like the
balanced scenarios — is then checked by running the model itself.

---

## 2. The people (population.py)

| What | How | Source |
|---|---|---|
| Age, sex, immigrant background | one agent per resident, by single year of age | Hagstofa MAN00101 (population 1 Jan 2026) |
| Citizenship | immigrants are EEA with probability 0.72, otherwise non-EEA | EST |
| Years in Iceland | geometric, mean 7 years, for immigrants | EST |
| Education and occupation | drawn jointly by sex from employed persons by occupation × education | Hagstofa VIN tables (employment by occupation and education, 2025) |
| Profession (27) | within the occupation group, by the wage survey's weights, education a strong preference (×0.12 if under-qualified) | VIN02001 |
| Potential full-time pay | the group's earnings percentiles (10th–90th), shifted so each profession's median matches; × age factor (0.72 under 25 … 1.05 at 35–54) and sex factor (0.94 women, 1.04 men) | VIN02001–02005 |
| Wage bill | all pay scaled so the synthetic wage bill equals taxable wages | TEK02001: 2,174.5 ma.kr. (2025) |
| Public sector | by profession's public share, then thinned so public pay equals government compensation of employees net of ~18% employer costs | THJ05143: 709.6 ma.kr. |
| Working status | employment and part-time rates by age band and sex, scaled to the published 16–74 total | VIN01104 / VIN01006 / VIN00961: employment 77.8% |
| Self-employed | by age band | Hagstofa LFS |
| Disabled / long-term ill | LFS inactive disabled + ill, 80% among those not working, 20% part-time, weighted to older ages | Hagstofa LFS |
| Students | 19,528 tertiary students spread across course years | SKO00000 |
| Couples | ~158,000 partnered adults, matched within 5-year age bins | MAN07108 |
| Children | attached to mothers by family type and number of children | Hagstofa families tables (2026) |
| Housing | renter probability by age (×2.2 for immigrants); capital area 64% | EST, HMS |
| Wealth | net worth excluding pensions 206% of GDP, split liquid/housing, distributed by age and pay (lognormal) | THJ09006/09007, Seðlabanki |
| Occupational pensions | replacement rate on pay, scaled by years contributed, mean near 280 þús. at 67+ | EST, Landssamtök lífeyrissjóða |

Each person also carries **traits**: the *meaning* they find in their profession, how much they value *leisure*,
their *enterprise* (likelihood of an idea for a firm), *mobility* (readiness to emigrate), and a *creative* pull
towards self-directed work (art, writing, study, care). Traits are drawn from lognormal distributions and nudged by
ten *characters* (Student, Retiree, Carer, Founder, Guest worker, Mobile professional, Vocation, Breadwinner …),
which exist so the model can report who changes behaviour.

**Base year.** The model starts in 2025 by default. For the backcast (§16) it is built from 2015's data instead,
with every national aggregate (GDP, the wage bill, public payroll, debt, property values) taken from that year.

---

## 3. One year, step by step (model.py `step`)

1. **Borgaralaun indexed.** Set to the price level expected for the year (last year's × trend inflation), and
   phased in if a phase-in is set.
2. **AI.** Machine capability rises; take-up of automation and augmentation is updated (§13).
3. **Housing market** clears rents against the dwelling stock (§9).
4. **Incomes refreshed** for everyone under this year's rules.
5. **Who reconsiders.** 35% of working-age people each year (50% in a reform's first year), plus everyone who lost
   a job, was cut to part time, turned 16 or 67, or just arrived. Students mid-course do not.
6. **The labour market clears** (§5): the wage for new contracts in each of 27 professions is found where the
   work people choose to offer meets what employers want.
7. **Choices drawn.** Each person who reconsiders picks one of five options by the probabilities in §4.
8. **Shortfalls.** Where employers want less than is offered at the agreed wage, part is taken as lost
   purchasing power (prices), the rest as dismissals and hours cut; plus frictional separations.
9. **Health, childhood, schooling, tenure, moving between professions.**
10. **Firms** are founded, grow, fail or exit.
11. **Emigration, immigration, births and deaths.**
12. **Start-of-life funds** are paid in and paid out.
13. **Childcare** places constrain parents' hours.
14. **Sectors**: fisheries, energy and smelters, frontier programmes, infrastructure.
15. **Public accounts** computed from every person (§10).
16. **Markets close the year**: prices, the króna, interest, construction, debt (§8, §9).

---

## 4. The choice: whether and how much to work

Each person who reconsiders weighs five options: **not working**, **part-time** (0.55 of full time), **full-time**,
**running a firm**, and **self-directed work** (no employer: art, writing, study, care — earnings uncertain).

For each option *j* the model computes the household's disposable income *H_j*: own net income under the tax and
benefit rules of the regime (§6), plus the partner's, plus usable child payments, plus a drawdown of savings (4% a
year), less property and wealth taxes. Utility is

$$U_j = \alpha \ln\!\left(\frac{\max(H_j/P - s\,c_{\min},\ \varepsilon\,c_{\min})}{e\cdot 10^5}\right)
 + h_j(\gamma_m m - \gamma_d d) - \ell\,h_j^{1.5}\tau_j + \text{ASC}_{g,j} + \text{ASC}_{o} + \dots$$

* $P$ price level; $c_{\min}$ the household's essential costs (basic 170 þús. per adult-equivalent + housing);
  $s = 0.70$ the share truly essential; $e$ the equivalence scale (1 + 0.5 partner + 0.3 per child).
* Logarithmic: a krónur lost near subsistence weighs far more than one gained above it.
* $h_j$ hours; $m$ meaning of the profession, $d$ its disamenity (×2.5 for the disabled); $\gamma_m=0.6$,
  $\gamma_d=0.8$.
* $\ell$ the person's taste for leisure (lognormal, mean 0.5); $\tau_j$ = 1 except for self-directed work, whose
  hours are chosen for their own sake and cost less leisure.
* **Self-directed work** is valued as the expected utility of a year the work sells and a year it does not — so a
  floor under the bad year (a borgaralaun) makes it more attractive, which is the mechanism the reform relies on.
* **Running a firm** needs an idea (probability rising with enterprise and a degree, falling with commercial
  rent) and access to capital (35% of would-be founders today; 60% under the reform, where the borgaralaun is the
  runway; more with start-of-life money in hand).
* A secure contract is worth something (0.35 per year of length, up to 5); a course in progress makes full-time
  work and a firm harder.

Probabilities are the logit $\Pr(j) = e^{U_j} / \sum_k e^{U_k}$, averaged over whether an idea arrives.

**Calibration (status quo, 2025).** The alternative-specific constants (ASC, by 10 demographic groups and by
profession) are solved so that the model reproduces the published activity shares — not working, part-time,
full-time or firm — for each group, the full-time equivalents in each profession, 2,700 new founders a year and
the share in self-directed work. $\alpha$ is solved so that a 10% pay rise raises participation by the target
**extensive-margin elasticity of 0.25** (literature range 0.1–0.5; Chetty et al. 2011 survey the macro and micro
estimates; the range is the literature's, the target the model's choice). A burn-in of 14 simulated rounds keeps those shares steady over time with ageing and inertia;
separations are then fitted to 2025 unemployment and the employment level to 77.8%.

---

## 5. Wages and the labour market

**Demand** for each profession $o$ (full-time equivalents):

$$D_o = S\cdot\Big[D^{pub}_o(1-\text{cut}) + D^{priv}_o\, w_o^{-\eta}\, c^{\kappa_o}\, x^{\,\chi_o\epsilon_x}\Big]
 \cdot a_o \cdot (1-\text{low-value}_o) + \text{sector, tourism, venture, programme jobs}$$

* $w_o$ the **real, productivity-adjusted** wage relative to the reference path: firms respond to unit labour
  cost, so pay that rises with productivity costs no jobs. $\eta = 0.47$ (TUNED; literature 0.3–1.5).
* $c$ household spending relative to the reference, loaded by how much each profession serves consumers
  ($\kappa_o$); $x$ competitiveness (króna over unit labour cost), loaded by export exposure ($\chi_o$).
* $S$ scales with the working-age population and with the work people offer (absorption 1: an economy absorbs
  the labour offered to it, as Iceland absorbed its immigration without unemployment rising).
* Care, teaching, childcare and refuse collection follow the population they serve, with a weak response to pay.
* $a_o$ = AI: $(1-\text{automated}_o)(1+\text{new tasks}_o)$ (§13).

**Clearing.** The wage for new contracts $\omega_o$ is found by iteration: $\omega \leftarrow \omega\,
(D/S)^{0.15}$, bounded to −20%/+25% per step and within ±15% of what the profession already pays (a new offer cannot sit
far from the going rate). Up to 80 iterations. Supply is the full-time equivalents offered at those wages by the
choice model; demand is evaluated at the pay firms actually bear, mostly contracted.

**Contracts.** Most people are paid by contract, not the market rate. A contract lasts 1–5 years (longer where
workers are scarce), with scheduled raises of expected inflation each year. At renewal:

$$\omega^{renew} = \max\!\Big(\omega_{signed}^{1-b}\,\omega_{market}^{b},\ \ \omega_{signed}\cdot
\underbrace{\left(\tfrac{P}{P_{signed}\,\pi^{sched}}\right)^{\lambda}}_{\text{prices}}
\underbrace{(1+g)^{t}}_{\text{productivity}}
\underbrace{\left(\tfrac{ToT}{ToT_{signed}}\right)^{0.039}}_{\text{terms of trade}}
\underbrace{(1+0.0055)^{t}}_{\text{premium}}
\underbrace{\tfrac{AI}{AI_{signed}}}_{\text{AI}}\Big)$$

The second term applies under **collective agreements** (kjarasamningar, the status quo): settlements compensate
prices since the last round in full ($\lambda = 1$), pass on productivity ($g$ = 1.07%/yr, THJ11011), a small share
of terms-of-trade gains and a small real premium (both TUNED) — Icelandic real wages (LAU04800) rose 2.1%/yr over
2005–2025 against 1.07% productivity and never fell over any ten-year window. In v3 the productivity AI adds is
passed on too. Without collective agreements (the reform as specified), each contract renews at the market rate
($b = 0.98$, TUNED).

**When agreed pay does not clear.** Iceland takes shortfalls as lost purchasing power more than lost jobs —
unemployment stayed near 4% through 2008 while real wages swung. A share of any shortfall raises the price level
(at most 6% a year); the rest is dismissals (80% of surplus staff a year, a quarter as hours cut to part time).
**Frictional separations** (a rate calibrated so 2025 unemployment comes out right) end jobs for reasons unrelated
to demand. Dismissals carry 3 months' notice pay.

**Minimum wage and hours** are levers; so is **public pay held at its old take-home** (the state pays public
employees, after tax and with the borgaralaun, what they took home before — cutting gross pay by the borgaralaun
grossed up at their marginal rate).

---

## 6. Taxes and transfers (policy.py)

**Status quo (2026 rules), per month:**

* Income tax: 31.49% to 498,122; 37.99% to 1,398,450; 46.29% above (Skatturinn 2026), less the personal credit
  72,492. Brackets, credit and benefits rise with prices every year, as Iceland adjusts them.
* Employee pension contribution 4% (deductible); employer 11.5%; payroll tax (tryggingagjald) 6.35%.
* Old-age pension (TR) with clawback on occupational pensions and earnings above the exemptions; disability
  pension with its own work exemption; support for adults without work where a partner's income is low.
* Child benefit (barnabætur) per child.
* Effective VAT on household spending 18% (the 24%/11%/exempt mix).

**Reform:**

* **Borgaralaun** to every eligible adult (18+). EEA arrivals are eligible while working or involuntarily
  unemployed until permanent residence (5 years); non-EEA after 5 years.
* **Child payment** the same amount per child; a share (50% flat by default) goes into the child's
  **start-of-life fund**, paid out at 25 (§12).
* Income tax: today's brackets × a scale lever; personal credit a lever (the reform abolishes it).
* Pension funds folded in (a lever): contributions become 7.75% + 7.75% social security to the state, the funds'
  real return (3%) goes to the borgaralaun, occupational pensions stop, with a top-up for anyone whose pension beat
  the borgaralaun. At 0, pensions stay and the borgaralaun is paid on top.
* One VAT rate (25% as written).
* Optional taper (withdraw above an earnings threshold), optional forced saving.

Household **levies** are taken off disposable income as Hagstofa (EU-SILC) does: the change in property tax on the
home, any tax on net wealth, and in v3 the extra heating bill of a cold-area home when rural heating support is cut.

---

## 7. Public accounts (model.py `accounts`, `balance`)

$$\text{Balance}_t = \text{Deficit}_{2025} + \underbrace{\Delta\text{Revenue} - \Delta\text{Expenditure}}_{\text{from every person, vs the base year}} + \text{Unmodelled growth}_t - \Delta\text{Interest}_t + \sum \text{static lines}$$

Every run — the status quo and a reform alike — is measured from the **base year's accounts**. Until September 2026
a reform was measured from the status quo's own path, which left the status quo's drift (ageing, pay, interest)
out of the reform's balance and credited the reform with all of it on the page.

* **From the agents:** income tax, social security, payroll tax, VAT on consumption, corporate tax on firms,
  the state's equity income, property tax, fund returns, fisheries fee, energy dividends, tax on machine income,
  wealth and inheritance tax; benefits, child payments, the borgaralaun, pension top-ups, public payroll,
  programmes, health, crime and schooling costs as they change with the population and its condition.
* **Static lines** (reform): subsidy cuts (farm 19.7; innovation 21.7; rural heating 4.5; transition grants 7.2;
  buses and routes 6.0; other 15.9 — THJ05161), governing costs, church funding, customs (7.7), input VAT
  restriction (EST 200, range 100–350 — the least certain large number in the budget), per diems (EST 13), pension
  fund returns, VAT on tourists, health care as in Denmark, internet as infrastructure, agricultural start-ups,
  prison, tax enforcement, exit tax, custodianship administration, other social benefits replaced.
* **Unmodelled lines.** Revenue the agents do not produce (excises, customs, fees, property income: record revenue
  less modelled, 749 ma.kr. in 2025) grows with real output; the state's purchases, investment and subsidies
  (record spending less modelled and interest, 1,026) grow with output smoothed over the cycle. Held flat, as
  before, they read over thirty years as an unannounced cut to both. In 2015-25 both grew about three-fifths.
* **Interest** is booked as the national accounts book it: nominal coupons on the non-indexed 65% of the debt, a
  real coupon on the indexed 35% and the indexation of its principal. The base year's interest is split between
  them at that year's inflation (4.1% in 2025) with a real coupon of 2.5% (EST). Coupons reprice over ~6 years
  toward the base year's plus the change in the nominal policy rate (non-indexed) or half the change in the real
  rate (indexed). The debt, held in base-year krónur, is worn down by inflation as a whole; the reported balance
  carries the full interest, and `balance_operational_bn` is the balance net of that erosion. A surplus can go to
  a sovereign fund instead of repaying debt.

Base year (THJ01102, THJ05181, THJ05132): GDP 4,941 ma.kr.; household consumption 2,440; exports 1,997; imports
2,103; general government liabilities 4,361; interest 211.7; property value 17,300; recurrent property tax 102.8.

---

## 8. Prices, the króna and interest (macro.py)

**Consumer prices**

$$CPI = \big[(0.38\,P_T + 0.32\,P_N)\,\tfrac{1+VAT}{1+VAT_0} + 0.30\,\text{Rent}\big]\times F_{subsidy}\times F_{absorbed}\times(1.025)^t$$

* Tradables $P_T = e\cdot$ import price $\cdot$ (1 + customs).
* Non-tradables move part-way (0.64 a year, TUNED) to $\big(\tfrac{\text{wage cost}}{\text{productivity}}\big)^{0.73}(1+\text{gap})^{0.22}$ (both TUNED); input VAT a firm can no longer reclaim is a cost that reaches prices.
* $F_{subsidy}$: dearer domestic food when farm support is cut (+0.3% at full cut), dearer heating, cars and fares
  when energy and transport support is cut (+0.1%, +0.1%, +0.4% in v3).
* The trend of 2.5% a year is Seðlabanki's target; everything reported is net of it.

**The króna** (real exchange rate):
$\Delta\ln e = 0.54\,(\tfrac{CA_0}{GDP_0} - \tfrac{CA}{GDP}) + 0.60\,(\pi - \pi^*) + \text{risk premium}$ (TUNED).
Pension funds can sell foreign assets to hold it up. **Exports** follow competitiveness (elasticity 1.16, TUNED),
export capacity and world prices of fish, aluminium and tourism; **imports** follow spending (1.26, TUNED), output
and relative prices (0.84, TUNED), plus in v3 the extra fuel imported when the transition grants are cut.

**Interest** (real policy rate), a Taylor rule:
$r = 3.5\% + 1.0\,(\pi - 2.5\%) + 0.25\,\text{gap} + \text{premium} + \text{shock}$; the premium is 5 points per unit
of debt/GDP above 2025's, damped by capital controls; the shock is the bank's departure from the rule, identified
year by year in the backcast (zero ahead). (Taylor 1993; the response of 1.0 is TUNED, above the textbook 0.5.)
House buyers face a **mortgage rate**, not the policy rate: a real rate that follows half the policy rate's
departure from 3.5%, catching up over three years (EST). On the policy rate itself, the user cost of a home hit its
floor when real rates reached -3.7% in 2022 and house prices trebled in the backcast.

---

## 9. Housing

Rents clear against the stock: $\text{Rent}^* = (\text{demand}/\text{stock})^{1/0.71}$, demand rising with
population and income (0.63, TUNED) and with start-of-life fund payouts; rents move 60% of the way each year.
House prices follow rent over the user cost of owning ($r$ + property tax + 3% depreciation and risk − expected
growth). Construction answers price over building cost (elasticity 1.3, TUNED); the state can build dwellings
regardless. A property-tax rise lowers prices through the user cost (it capitalises) and is paid by owners from
their income. Ownership caps, custodianship and finite ownership terms act on markups, variety of owners, upkeep
and value (DESIGN.md §20–21).

---

## 10. Migration and demography

**Emigration.** Each adult has a base hazard by age and citizenship, fitted to Hagstofa 2025 emigration
(recent arrivals ×2.5 in their first three years; households with children less mobile, the factor solved so
children leave at the recorded rate). It moves with how pay abroad compares with income at home:

$$h = h_0 \cdot \text{clip}\!\left(\left(\frac{R}{R_0}\right)^{\beta\,\mu},\ 0.25,\ 4\right),\qquad
R = \frac{\text{pay abroad for the profession}}{\text{net income at home}}$$

$\beta$ = 0.82 (TUNED), $\mu$ the person's mobility. A partner goes along 80% of the time; a mother takes her
children. An exit tax can be levied on the unrealised gains of the wealthy who leave.

**Immigration.** Four streams — EEA workers, EEA non-workers, non-EEA workers, returning Icelanders — each at its
2025 level scaled by the expected income of an arrival against 2025 (elasticity 1.33, TUNED), by real pay in the
professions immigrants fill (2.94, TUNED), by how many jobs are unfilled (1.97, TUNED), and — for EEA workers — by
the jobs the economy added this year (98% filled from abroad, TUNED: the tourism boom's workers came for jobs, not
pay). Residence rules can hold back arrivals who would not work; a cap can close the experiment. Arrivals bring
partners and children at the recorded rates.

**Births** respond to usable child income against household income (elasticity 0.5, EST, range 0.1–1).
**Deaths** follow a Gompertz curve scaled to ~2,600 a year, with death rates falling 1.2% a year at every age (EST; about a year of life expectancy a decade, as Hagstofa's projections assume).

---

## 11. Firms and the state's stake

Founders start firms with an idea and access to capital (§4). Firms have a quality draw, grow jobs if they survive,
fail, or exit (1% a year at 8× profit). Founders draw a salary from year two.

**The state as investor in its citizens' lives (v3).** The state takes a stake in new firms (in v10's reference reform,
half of a firm built on the borgaralaun alone, less with outside funding, never below 5%; a lever) because it pays for the upbringing, schooling, health and borgaralaun of the people
who found them. The stake is **diluted** as outside investors come in: by a third on average across firms, by 60%
by the time of an exit. It earns dividends (30% payout) and a share of exits; it also leaves founders less, so
fewer start. **No seed money** is paid per firm (v2 paid 3 m kr.); the borgaralaun is the runway. **RANNÍS
continues** — the innovation support is kept — and part of the cut farm support funds agricultural start-ups
(1.5 ma.kr. a year, ~15 m kr. each, half surviving with 1.5 jobs each).

---

## 12. Children and the start-of-life fund

Under the reform each child's payment is split: a share to the household (usable), a share into the child's fund
(50% flat, or a graduated schedule by birth order). The fund is held in real terms and paid out at **25**: half to a
home (enough for a deposit turns a renter into an owner), half as savings, of which a quarter of the payout is
kept as capital to start something (EST).
Payouts raise housing demand.

**Moving out early (v3).** A 16- or 17-year-old who moves out is paid their whole borgaralaun, and nothing more goes
into their fund; they still get it at 25. Who does is a fixed share of each cohort (3%, a setting; Hagstofa does not
publish it), picked by a hash of the person so it takes no random draw from anything else. *Limit:* the teenager's
own household budget is not modelled — they are counted and their income reported, but they are not an income unit
in the poverty measures.

Child poverty, childhood years spent poor, schooling outcomes and the demand for kindergarten places follow from
the households children live in.

---

## 13. AI (automation.py)

AI capability grows at a rate set by the scenario: $C_t = (1+a)^t$. Three channels (v3):

1. **Displacement.** Each profession has an exposure (share of tasks a machine could do: clerks 0.85, care
   0.10 …, EST from the task literature — Autor, Levy & Murnane 2003; Frey & Osborne 2017; Eloundou et al. 2023).
   Take-up rises with capability and with what the work costs:
   $\text{score}_o = \text{exposure}_o\cdot w_o^{1.2}\cdot C_t$; take-up is logistic in the score (midpoint 1.6,
   curvature 3), installed 25% of the way each year, never reversed. The wage bill no longer paid becomes machine
   income (less 40% running costs), taxed at the corporate rate — in both worlds.
2. **Augmentation.** AI makes people in complementary work more productive rather than replacing them.
   Complementarity by profession is EST after Pizzinelli et al. (IMF WP 2023/216): managers, doctors, lawyers
   0.65–0.75; clerks 0.20; cleaners 0.05. Take-up follows capability alone. It raises output per hour, and
   negotiated rounds pass it into pay.
3. **Reinstatement.** New tasks appear as old ones go (Acemoglu & Restrepo 2019): half of the displaced work returns
   as new demand, with a lag, where complementarity is high.

**Calibration target.** Forecasters converge on about +0.5 points a year of productivity growth from AI with little
change in unemployment (OECD — Filippucci et al. 2024 — from a fraction of a point to about one point a year; Acemoglu 2024: about
0.7% in total over ten years; Goldman Sachs 2023: about 1.5 points a year; Penn Wharton 2025: +1.5% in the level
by 2035). The standard picture uses 5% a year; fast AI (15%) displaces faster
than new tasks come back.

**In both worlds (v3).** The status quo has the same pace of AI as the reform it is compared with. In v2 it had
none, so the tax on machine income counted as a gain of the borgaralaun; the v2 page now borrows the reform's AI
response for its status quo as a stop-gap.

---

## 14. Sectors

* **Fisheries.** Revenue follows the world price of fish, the catch and the króna; costs, imported inputs and
  labour. Resource rent = EBITDA less a 6% normal return (SJA08109: 72.8 ma.kr. in 2023). Veiðigjald captures 24%
  today; the reform leases quotas for 50 years priced to capture a share (80% as written).
* **Energy and smelters.** Smelters use 12.9 TWh. Ending their contracts costs compensation, exports and jobs in
  the East and Hvalfjörður, and sells the power to other buyers at a higher price. Smelters are 1.8 of Iceland's
  4.6 Mt CO2e.
* **Tourism.** Employment follows what tourism earns (elasticity 0.57, TUNED); VAT on stays changes what tourists
  buy (elasticity 0.8, EST); a job-retention scheme can hold jobs through a collapse (2020–21).
* **Agriculture.** 3,500 FTE of farm work; a full cut of support ends a quarter of it; abolishing customs exposes
  another 10% to imports; start-ups funded from the cut add work back (v3).
* **Energy and transport subsidies (v3), in three parts:**
  * *Rural heating* (4.5 ma.kr.): homes without geothermal heat — about 9% of people, a quarter of households
    outside the capital area in the model — are paid part of the cost of heating with electricity or oil.
    Cutting it puts the whole saving on those homes' bills, about 25 þús. a month each.
  * *Transition grants* (7.2): EV purchase grants and Orkusjóður. Cutting them slows electrification where it
    is slowest already: road transport emits ~0.95 Mt; +0.12 Mt by the tenth year at a full cut (EST), ~4 ma.kr.
    more fuel imported (35 ma.kr. per Mt).
  * *Buses and regional routes* (6.0): fares up or routes closed, prices +0.4%, +0.02 Mt.
* **Frontier programmes and infrastructure** (optional): state investments with capex, jobs, returns and
  productivity gains; DESIGN.md.

---

## 14b. Shortages in the public services, and what leave costs (v3)

**A shortage shows up three ways at once, not one.** Where the state cannot fill its posts, the model splits
what is missing:

* **Pay rises.** A public employer buys a service it must provide, so it cannot meet a shortage by providing less
  of it on purpose. The premium it pays above the going rate grows with the share of its own posts left unfilled
  and falls back as they fill (`labour.public_shortage_pay_speed`, `_decay`, `_cap`). Iceland's nurses' and
  teachers' settlements were made this way, outside the general round. The premium applies in both worlds,
  because the state behaves like this today as well; what a reform changes is how large the shortages get. The
  cost is charged to the public payroll and appears in the budget.
* **Some of the work is not done.** What pay does not fill becomes service that does not happen — waiting lists,
  closed wards, larger classes. It is reported as `essential_service_unmet`, `health_service_unmet` and
  `teaching_service_unmet` rather than left inside a gap figure.
* **The rest falls on the people who stay.** Their workload rises, which makes the job worse to hold, so more of
  them go part time or stop — which widens the shortage again. This is the one loop in the model that makes a
  shortage compound rather than settle (`labour.workload_disamenity`, anchored on nurse burnout and
  intention-to-leave evidence, Aiken et al. 2002).

`labour.shortage_absorbed` sets the split between the second and third (EST: half and half).

*Limit, and it matters:* an agent's profession does not change. So the model answers a pay premium with the hours
and participation of the people already in a profession — which is the own-wage supply elasticity the nursing
literature measures, around 0.2–0.4 — and never with a school leaver choosing nursing because it now pays better.
That is why the premium closes only part of a gap here. Recruitment into a profession is the next structural
piece, and until it exists the model's shortages are the pessimistic end of the range.

**Public staffing follows need, not a flat cut.** Child protection, home visits, benefit and debt counselling,
the police, the courts and the prisons exist in proportion to distress. `labour.social_need_share` says how much
of each profession's public work is of that kind, and the index it follows is built from hardship, child poverty
and crime against the base year, with a year's lag, as a budget would be. A reform that lifts people out of
poverty therefore needs fewer of these staff; one that does not needs more. Care and teaching are driven by the
population they serve and are *not* in this table, so nothing here can cut a nurse or a teacher. The evidence the
link rests on: Forget (2011), Costello (2003) and Akee et al. (2010) on the Cherokee payments, and the income and
child-maltreatment literature (Berger et al. 2017; Raissian & Bullinger 2017). AI reaches public administration
and legal work through the same automation channel as private work — no separate assumption.

**Sick pay and parental leave.** Once the borgaralaun is the floor, no one falls to nothing, so the state's two
schemes end: sick pay for its own staff and the parental leave fund. What is paid *above* the borgaralaun becomes
the employer's — the period law and agreements already give, rising with seniority, then compulsory private
insurance beyond it, as occupational pensions are compulsory now. Nobody may be dismissed for taking leave. A
parent also has half the newborn's own payment while on leave.

* The state's saving is computed from the model's own births and wages (the fund pays about 80% of pay under a
  cap of 800,000 kr. a month for a year per birth), not from a fixed figure, so it moves with the scenario.
* The employers' cost is charged on wages like a payroll contribution, so it shows up in hiring rather than being
  quietly dropped.
* **The level of the top-up is left to bargaining in the reform**, so the model states an assumption and gives
  it a lever: 80% of pay where collective agreements survive, 55% where pay is set job by job. Both are
  assumptions about where bargaining lands, not findings.

**Benefits follow wages, not only prices.** Lög um almannatryggingar (69. gr.) sets benefit levels each year
with regard to how wages have moved, and never by less than prices. The model indexed them to prices alone,
which made relative poverty climb through the status quo for no reason but the arithmetic — hardship nearly
doubled and child poverty rose five points over ten years with no policy change at all, and every reform looked
better for it. Benefits now carry 80% of real wage growth (`benefits.wage_indexation`, EST) with the price level
as a floor, as the law has it.

**A second status quo (`markets.history_like`).** The forecasts have inflation near the 2.5% target, a stable
króna and rents roughly flat in real terms. The decade 2016–25 did not: prices rose 4.3% a year (VIS01005), the
króna drifted weaker and housing outran incomes. At 1 the model runs the decade's pattern instead of the
forecasts, **for the reform and the status quo alike**, so the comparison stays like for like. A calmer world could
favour either side of the comparison, and this is how to check whether a result depends on it.

## 14c. What changed in the September 2026 review

* **Births come earlier under a secure income** (`demography.birth_*`, lever `birth_timing`). Births move a year
  earlier at a 300 þús. payment (EST), over five years, with the tempo effect that brings (Bongaarts and Feeney
  1998). A birth early in a career costs a mother 4% of her wage rate for good (EST; Miller 2011), one while
  studying or before 25 half that (Herr 2011; Bach et al. 2025) — measured against today's timing, so the status
  quo is unchanged. A baby slows a course to 70% of its pace.
* **Profession moves** go where people of the same education work, follow take-home pay (the reform's public pay
  offset and the shortage premium included), carry the new job's pay and public/private split, and only the moves
  a secure income adds (`labour.occupation_mobility_security`, EST +50% at 300 þús.; Nekoei and Weber 2017 for
  the direction) earn the match gain. Today's churn is already in the trend.
* **Pay follows age** (`population.age_wage_factor`) as people get older, not only when the population is drawn,
  and a child born in the run takes its own profession, schooling and pay at 16 with a quarter of its mother's
  standing (`childhood.earnings_persistence`, Nordic estimates 0.2-0.3).
* **Agreements may index net of the tax switch** (`policy.indexation_net_of_tax`, lever `net_indexation`), as
  Denmark's use the nettoprisindeks; the Scottish micro-macro study found this "social contract" decisive
  (Connolly et al. 2021). **The central bank looks through the VAT step** (`markets.policy_looks_through_tax`).
* **A floor for disability and old-age pensioners** (`policy.benefit_floor_topup`, lever `benefit_floor`): the
  gap to what today's system pays the same person, untaxed. Off in the reform as specified.
* **Shared behaviour.** The sensitivity levers and the profession-move rate are applied to the status quo as well
  (`WORLD` in build_emulator.py), and the page's defaults are the backcast-tuned values.
* **Two double counts removed**: the parental leave fund (in the national-accounts benefit total the reform
  books as replaced, and saved again by the leave lever), and public sick pay (saved by two levers).

---

## 15. Health, crime, schooling, wellbeing

* **Health** (0–1) drifts towards a ceiling set by age, hardship and involuntary idleness. Evidence: Manitoba's
  Mincome cut hospital use 8.5% (Forget 2011); Finland's trial improved mental wellbeing with no employment
  effect (Kangas et al. 2019). Ill health moves people into disability. Public health spending scales with
  population and morbidity.
* **Free health care, GP first (Danish model) (v3):** service co-payments (~15 of the 65 ma.kr. households pay out of pocket, EST)
  become free — +10% use; specialists by GP referral trims specialist use 15% (Sripa et al. 2019 review), half of
  that saving going on GP time, phased over four years. Medicines and adult dental care stay paid. *Limit:* better
  access does not yet feed back into health.
* **Crime** responds to hardship (0.55), youth idleness (0.70) and the payment cycle — the evidence runs both ways
  and both are carried: cash reduces acquisitive crime (Akee et al. 2010; Cherokee), and Alaska's dividend saw
  substance incidents rise after payment while property crime fell slightly (Watson, Guettabi & Reimer 2020).
  Certainty of being caught deters, severity hardly (Nagin 2013). Costs follow the responsive 57 ma.kr.
* **Schooling and tertiary study** respond to income and the option of study; the fund and a degree raise the
  chance of starting a firm.
* **Life satisfaction** (0–10, anchored on Iceland's ~7.5) from income relative to needs, work status (involuntary
  idleness hurts most), health and security.
* **Gambling and loans.** About 20 ma.kr. a year goes to foreign betting sites; a payment block stops much of it.
  The borgaralaun cannot be pledged, so it cannot back a risky loan.

---

## 16. The backcast and tuning

To test whether the model can reproduce history, it is built from **2015** data and walked through 2016–2025 as
they happened: each year's tax brackets and credits (verified with Skatturinn, deflated by actual CPI), benefit
levels, payroll tax, employer pension (8% → 11.5%), the inheritance floor; world prices of aluminium and oil
(World Bank Pink Sheet), fish and tourism (Hagstofa export values); partners' inflation (euro-area HICP); COVID
crisis support (3% of GDP in 2020, 2% in 2021) and job retention (60% of tourism jobs kept in 2020, 30% in 2021).
Its outputs are set against Hagstofa's record: employment and unemployment, CPI, real wages (LAU04800, same-job
index — v3 compares like with like, a fixed-weight index of the model's pay by profession), real GDP, population,
emigration and immigration, the public balance and debt, real exports.

**Tuning.** 25 behavioural parameters were searched (a Latin hypercube over plausible ranges, 400 runs each round,
two rounds) to minimise the error on **2016–2021**; **2022–2025 were held out**. Round 2's chosen values cut the
held-out error from 28.6 (defaults) to 19.3 (round 1: 23.4). One value was *not* adopted: the tuner set
labour-market absorption below 1, which fits the decade by pushing wages down every year — harmless over ten years,
wrong over thirty.

**What still misses** (structural, not tunable): population grows too slowly (the 2022–24 immigration surge is only
partly reproduced) and real wages grow too slowly (the model's pay follows productivity; Iceland's outran it on
terms of trade and settlements). These are next.

**Identified shocks (September 2026).** Tuning parameters until the model reproduces the decade would bend the
behaviour everything else rests on, and some of the decade's forces are not in the model at all: the investment
and construction boom of 2016-18, the refugees of 2022-24, the budget's one-offs. So, as a historical shock
decomposition does, the unexplained part of each year is measured as a shock (`backcast.py --identify`, written
to `data/processed/history_shocks.json`): a level of labour demand that reproduces unemployment, a productivity
level that reproduces real output, a scale on arrivals that reproduces immigration, a scale on leaving that
reproduces emigration, the bank's departure from its rule that reproduces the real policy rate (the key rate less
inflation; `policy.key_rate_pct` in the history file), and a residual that reproduces the budget. Prices, pay and
debt are not targeted and remain a test of the model.

**The status quo's budget (September 2026).** A line-by-line comparison with the national accounts
(`scripts/fiscal_decomp.py`) found the residual of +60 to +136 ma.kr. a year came from four faults, all fixed:
benefits indexed twice in the backcast (the record's real levels and the model's own wage indexation on top);
the public shortage premium lifting public pay 18% above the market by 2025 (speed .35 → .12); interest that
followed the real policy rate alone and so vanished at 2021-22's negative real rates, with indexation not booked
as interest; and house prices priced off the policy rate. A fifth — support paid to every voluntary non-worker
whatever their savings — is real, but a means test pushed the response to a payment out of the evidence (the
choice model gives a person without income no drawing on savings), so it is written and switched off
(`benefits.nonwork_asset_limit_months` = 0) until savings enter the choice. Population, emigration and the real
rate are reproduced; the untargeted errors are prices (the model's CPI runs several % high by 2025), real wages
(~12% low) and debt (~6 points low).

**The counterfactual past** (`scripts/counterfactual_past.py`). The reference reform from 2016, through the same
world and the same identified shocks, measured against the status quo's own path as the forward runs are, and
reported as the record moved by the model's difference. It reads off each shock — the tourism boom, COVID, the
2022-23 inflation — as the change across it with and without the payment, and the start-of-life fund's first
decade. The labour-demand shock is given only to runs without a reference path: a run measured against the status
quo's path already carries it through that path. `scripts/counterfactual_trace.py` prints every account line
and flow for chosen years, to see what drives a difference.

---

## 16b. The long view (v4, `scripts/build_timeline.py`, the page's "The long view" tab)

Whole model runs rather than the fitted surface, for every scenario the page offers:

* **From the past**: the 2015 society through 2016-2025 as they happened (each year's world, crisis support and
  identified shocks), then ten years on in the world the page assumes, the decade's levels held and its one-year
  shocks ended. The status quo has each year's own rules; from 2025 its benefits follow wages again from the level
  the record left them at. The record is drawn beside the status quo.
* **From today**: the 2025 society to 2060 — long enough for the start-of-life fund to pay whole cohorts.

A **shock ahead** hits both runs from the same year (2028 from the past, 2030 from today): an oil price shock or
collapse, an AI jobs shock (automation at the model's fastest pace), a collapse of the Atlantic overturning
circulation (AMOC), a pandemic, a banking and currency crisis at half 2008's depth, a fish stock collapse. Each is a
change to the world — prices, productivity, migration, automation, the bank's rate — with its size anchored on a
historical episode or the scientific literature (sources in the script and on the page); the AMOC sizes are EST,
since no economic study of a collapse for Iceland exists. The page marks the record's shocks, the shock ahead, the
fund's first payouts and the first cohort with a whole childhood in the fund.

## 16c. The long-run review (v6, 2026-10-01)

Running scenarios over 35 years exposed faults that a ten-year horizon hides. Each is fixed in every run, the
status quo included.

**Faults fixed**

* **Tax thresholds.** The personal credit and the bracket thresholds now rise each year with the CPI plus 1%, the
  law's estimate of productivity growth (`policy.threshold_real_growth`; `policy.threshold_price`). Indexed to
  prices alone, real growth pushed everyone up the brackets, and the 35-year budget drifted into a surplus the law
  does not produce. The backcast imposes the record's own thresholds each year and switches the rise off.
* **Net debt.** The debt can now pass zero: surpluses beyond it are held as net financial assets, which earn the
  same coupons. Before, it was floored at zero, so a run that repaid its debt lost every later surplus from its
  accounts. The page labels the series "net public debt".
* **New tasks under AI.** The work AI creates now *adds* to what it takes, (1 − automated + reinstated), instead of
  being multiplied by it. The product's cross term took 4-5% of all jobs by the 2050s at 5% a year.
* **Wage-index bounds.** The solver's bounds on a profession's wage index are now real: they scale with the price
  level, and the top one also with productivity. As fixed nominal numbers, the upper bound bound once prices had
  roughly quadrupled. Real pay then fell year after year while vacancies climbed.

**Labour-supply responses added**

* **Choosing a profession.** Young people at 16, and new arrivals, are drawn towards professions with empty posts
  and rising pay, through the same pull as job movers (`occupation_pull`). When nothing has changed, the pull is 1
  everywhere and the base mix is kept. Copied from 2025's teenagers unweighted, every cohort to 2060 entered the
  professions in 2025's proportions.
* **Studying responds to the returns** (`education.return_elasticity` .8, EST). The return is the expected pay of
  work that asks for a degree — pay times the chance of a post — against work that does not.
* **Graduates change profession.** 60% of graduates take work that asks for their new level
  (`education.graduate_switch_share`, EST).
* **The wage curve in agreements** (`labour.wage_curve_elasticity` .10, `frictional_unemployment` .035). An
  agreement's floor for a profession now moves with the profession's excess supply. The factor is
  (u / u_frictional)^−0.1, with u the frictional rate plus the excess, against its value when the contract was
  signed. The elasticity is Blanchflower and Oswald's, confirmed in meta-analysis (Nijkamp and Poot 2005), and holds
  under Nordic bargaining too. Without it, under kept agreements, the professions automation emptied went on
  receiving the economy's productivity raises for decades, at 15-20% unemployment. The trigger: a payment raises
  low-wage pay, and dearer labour is automated sooner (`automation.wage_sensitivity`, EST).
* **Why these were needed.** Without them, AI's new tasks (placed where complementarity is high) found no one
  qualified to do them. By 2045, low-skill work queued at 12-18% unemployment beside 10-27% shortages of doctors,
  nurses, teachers and managers.

**New levers**

* **A resource windfall** (`windfall.*`, the world lever "A resource windfall"). Oil, gas or minerals bring a
  yearly rent; the state takes 78%, Norway's marginal rate. The exports lift the króna, which costs the other
  export industries. A what-if: it happens to both runs, and is also one of the long view's events ahead.
* **State ownership of automation capital** (`automation.state_capital_share`, lever `robot_stake`). It is now
  separate from the levy. The stake is bought at a fair price with borrowed money (`stake_required_return` .07,
  `stake_financing_rate` .03, EST), so the state gains the return above its borrowing cost, not the machines'
  whole income. Before, the dividends came with no purchase.
* **The payment can follow pay** (`policy.ubi_wage_indexation`, lever `ubi_wage`). This is the rule today's
  benefits follow. At 0, the reference setting, the payment keeps its value in goods but falls about a third
  behind pay over 35 years. The long view shows that as a growing surplus.

**Scenario search fixes** (`scripts/surrogate.py`): the search's status quo now matches the page's.

* It no longer borrows AI on top of a world fit that already contains it (counted twice: ~300 ma.kr. over 2027-35).
* It is measured from where the exact status-quo run was made, not from the page's defaults (which put it in the
  last decade's world).

**Higher payments** (`scenarios.py high`). For three openly optimistic routes — a robot dividend, a resource
windfall, and both with the state's programmes — the search finds the largest payment, in steps of 50 þús., whose
budget does as well as today's status quo *without* the windfall or robots, since those are what pays. The
payment slider now runs to 800 þús.

---

## 17. The surrogate (the explorer page)

The page cannot run a model that takes minutes. It carries a fit:

* A **design** of ~2,000 runs: a Latin hypercube over all levers (the least-correlated of 300 drawn), with the
  world (prices and, in v3, AI) taken from 60 points, each with its own status-quo run.
* For each output and year, a **quadratic** in the levers centred on the middle of their ranges; every lever
  crossed with the borgaralaun; per output, the pairs among its six most important levers. Pure budget lines enter
  linearly. Ridge regression, penalty by cross-validation.
* Where it helps, a **Gaussian-kernel correction** over the runs on the eight levers that matter most to the output.
* Five-fold cross-validated R² is shipped for every output and year; the page shows it and refuses fits that do not
  hold. In v2: R² ≥ 0.95 for 77 outputs, 0.85–0.95 for 23, below 0.5 for two (income spread measures).
* The **status quo** moves with the world by its own quadratic fitted to the 60 status-quo runs.

---

## 18. Scenarios that balance the budget (scripts/scenarios.py)

For a given borgaralaun, some levers are fixed (the choices that define the scenario: public take-home unchanged,
housing, childcare, retraining, no cuts to governing, church or culture, forecast world prices, AI at 5%, a
tax-free inheritance of 75 m kr. so heirs keep the family home) and the financing levers are searched within caps.
The search minimises *disruption* — the weighted distance of each lever from today, broad taxes weighing most —
plus penalties for any deficit after the first year, prices more than 5% above the status quo, unemployment more
than half a point above it, the poorest tenth losing, and essential services falling short. Random search then
local refinement, on the surrogate; the chosen settings are then run in the model.

---

## 19. Data sources

**Statistics Iceland (PxWeb).** Population MAN00101, projections MAN09010/09012, fertility MAN05201/05303,
families and households, migration by citizenship and age; employment THJ11002, VIN10022, VIN01104, VIN01006,
VIN00961; earnings VIN02001–02005; labour cost VIN02091/02092/02100; taxable wages TEK02001/02003; productivity
THJ11011; income TEK01001/01006/01007; disposable income and wealth by percentile THJ09006/09007; poverty LIF01151;
pensions FEL02001/02003/02005; public finance THJ05111, 05132, 05142, 05143, 05161, 05165, 05181; GDP THJ01102;
consumption THJ02103; forecast THJ07000; trade UTA06002/06101/06201; fisheries SJA08101/08103/08107/08109, SJA09001;
agriculture LAN1101/1105, LAN05001–05008; firms FYR08000/08001/08010; wage index LAU04800; CPI; education SKO00000.
The whole catalogue (1,906 tables) is indexed in `data/catalog/hagstofa_tables.tsv`.

**Other.** Skatturinn (tax brackets and credits 2015–2026); Seðlabanki Íslands (policy rate, pension-fund assets,
Monetary Bulletin 2026/3 forecasts); HMS (property values, fasteignamat); Tryggingastofnun (benefit rules);
Fiskistofa (quotas, veiðigjald); Orkustofnun and Landsvirkjun (energy, smelter contracts); Hafró (catch advice);
Isavia (tourist numbers); World Bank Commodity Price Data (aluminium, Brent); Eurostat (euro-area HICP, foreign
earnings); OECD (health spending, AI productivity); UST (emissions inventory).

---

## 20. Research the behaviour rests on

* Labour supply: Chetty, Guren, Manoli & Weber (2011), *Are micro and macro labor supply elasticities consistent?*;
  basic-income trials — Kangas, Jauhiainen, Simanainen & Ylikännö (2019, Finland); Forget (2011, Mincome);
  Jones & Marinescu (2022, Alaska); Banerjee et al. (2023, Kenya); Vivalt et al. (2024, OpenResearch).
* Health: Forget (2011); Kangas et al. (2019).
* Crime: Akee, Copeland, Keeler, Angold & Costello (2010); Watson, Guettabi & Reimer (2020); Nagin (2013).
* Wealth and avoidance: Jakobsen, Jakobsen, Kleven & Zucman (2020, Denmark); Seim (2017, Sweden).
* AI: Acemoglu & Restrepo (2019); Acemoglu (2024); Pizzinelli, Panton, Mendes Tavares, Cazzaniga & Li (2023, IMF);
  Eloundou, Manning, Mishkin & Rock (2023); Filippucci et al. (2024, OECD); Hatzius et al. (2023, Goldman Sachs);
  Autor, Levy & Murnane (2003); Frey & Osborne (2017);
  Penn Wharton Budget Model (2025).
* Health systems: Sripa et al. (2019, BJGP) on gatekeeping.
* Migration: family migration and return-migration hazards follow Hagstofa's own age profiles.
* Monetary policy: Taylor (1993).

---

## 21. What the model does not do — its limits

* **Structural misses in the backcast:** immigration during the 2022–24 surge and real-wage growth above
  productivity are only partly reproduced.
* **One country, one currency, no financial sector:** banks, credit cycles and asset bubbles are not modelled;
  the pension funds only as an asset pool.
* **Firms are simple:** no firm-level wage bargaining, no market power beyond the ownership markups.
* **Behaviour is calibrated, not observed under a borgaralaun:** the response to a payment this large is an
  extrapolation from trials that were smaller, shorter or partial.
* **Estimates** (502 of 634 parameters, [PARAMETERS.md](PARAMETERS.md)) are judgements informed by the literature;
  the explorer has sensitivity levers for the five the results lean on most.
* **The surrogate** is an approximation of the model, with cross-validated error shown; scenarios found on it are
  checked in the model before being reported as results.
* **Horizon:** ten years. The start-of-life fund first pays out in full at 25, so its effects need a 30-year run —
  planned once the model reproduces history well enough to be trusted that far.
* **Not modelled yet:** health gains from free visits; the teenager's own household budget; regional labour
  markets beyond the capital/elsewhere split; climate policy beyond the emissions count.
