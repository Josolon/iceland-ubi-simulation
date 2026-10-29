# The known limits: what is known, and how 2.0 closes them

[VALIDATION.md](VALIDATION.md) §5 lists what the model leaves out. Six of those limits matter most to what it says
about a basic income. This document gathers, for each, what the evidence says, what Iceland's own data give, and
how the model will represent it, with the check that would show the mechanism wrong. The data come from
`scripts/fetch_limits_data.py` and sit in `data/reference/`.

Each mechanism follows the rules the rest of the model keeps:

* **The status quo is its own reference.** A new mechanism must leave the 2025 base year as the record has it,
  and a check says so.
* **Evidence first, estimates marked.** A parameter from a study names it; one without is marked EST and gets a
  sensitivity lever when the results turn on it.
* **A failing check is a finding.** No tolerance is widened to let a mechanism pass.

## 1. Regions

**What is left out.** One national market for housing, work and services.

**Iceland's figures** (`regions_2025.json`):

| | Capital area | Rest of the country |
|---|---|---|
| People, 1 January 2026 (MAN03250) | 251,912 (63.9%) | 142,412 |
| Pay per employee, 2025 (TEK02003) | 872 þús. kr. a month | 755–854, about 790 on average |
| Unemployment, 2025 (VIN01104) | 4.9% | 3.2% |
| Hours a week, 2025 | 34.5 | 38.4 |
| Moves to the other area, 2025 (MAN01002) | 3,974 | 3,661 |
| Arrivals from abroad, 2025 | 11,632 | 7,042 |

Pay is about 10% higher in the capital area, and housing is dearer there by more than that. Moves between the two
are small and nearly balanced: about 1.5% of the capital area's people a year. The gap in house prices narrowed
over the decade: from December 2015 to December 2025 prices outside the capital area rose 3.1-fold, against
2.4-fold for flats and 2.7-fold for houses inside it (VIS01106).

**Why it matters.** A payment that is the same everywhere buys more housing where housing is cheap, and a
reform that changes who works changes how much the capital area's higher pay is worth to someone deciding where
to live. The direction of the net effect is not settled by theory alone. In the spatial equilibrium of Rosen (1979)
and Roback (1982) people move until real income net of amenities is equal. If housing takes a fixed share of
spending, a payment that is the same everywhere leaves the ratio of real incomes between areas unchanged for
someone who does not work; it favours the cheaper area only by making pay, which is higher in the capital area,
a smaller part of income. If housing is a necessity, a richer household spends a smaller share on it and the pull
of cheap housing weakens. How many move depends on how much people respond to gaps in real income across regions,
and in Nordic data that response is weak: Kornstad et al. (2023) find small responses to relative
wages across Norway's regions, and Eliasson et al. (2023) find that dear housing in Stockholm deters
more than its pay draws. Most moves follow study, partners and jobs. In Finland, earnings-related unemployment
benefit weakens the pull of pay on the displaced (Maczulskij et al. 2023); the cross-country gravity
models of Cavalleri, Luu and Causa (OECD 2021) find house prices a barrier wherever they have diverged.

**How it is modelled (2.0, `regions.py`).** Each person lives in one of two areas; a couple, their children and an
adult living with them share it. At the start the better paid are more likely to live in the capital area: the
tilt is set so that pay per employee there is 1.11 times the rest's, as TEK02003 has it, and 63.9% of people live
there. Smaller households are also more likely to live there. A second tilt gives the record's persons per
household against the rest's: 0.957 in 2015 and 0.984 in 2025. These are families and single people in MAN07108:
1.80 against 1.88 persons in 2015, so students, the young and the old in flats in the capital area, and families
outside it. Each area has its own housing market. Its stock is counted at the start as the households living there,
and its price and rent move against the market-wide index with how full it is against its stock, as each size's
do on the housing ladder. New building goes to each area in proportion to its stock, tilted towards the one whose
price has risen. In the base year the capital area takes 69.3% of it, the share of the dwellings completed in
2015–21 (IDN03001, IDN03002), more than its share of the stock: homes there sell further above what they cost to
build. The levels are the base population's: homes are 1.56 times dearer in the capital area and rents 1.37 times.

Each household moves to the other area at a yearly rate. In the status quo's first year the rates come out as
the record's: 1.6% of the capital area's people and 2.6% of the rest's. The rates are higher for the young (EST,
after the usual age schedule of migration), and they move with how much better off the household would be in the
other area. That gain is its real income there against here: housing weighs 30% of what it spends (the CPI's
weight), and its pay is 5% higher in the capital area (EST, about half the observed gap; the rest is sorting).
The rate rises by 1 per unit of that gain in logs (EST: 10% better off, 10% more moves). An owner who moves sells
and buys the same size in the other area; the difference passes through savings and the mortgage. A mover's pay
changes by the premium. Arrivals from abroad settle in the capital area in the record's share: 62% in 2025, 63–70%
over 2015–25. Emigrants leave from either area as they come, which matches the record's 63–70%. A reform's rates
are scaled from the status quo's first year.

What it finds (three seeds, each reform against the status quo of its seed): a borgaralaun moves people out of the
capital area, but not many. At 450 þús. it raises the gain from leaving the capital area from 9.3% to 10.4% of real
income, through the smaller weight of pay in income. Over ten years about 1,360 more people leave it, net, than in
the status quo, and its share is 0.38 points lower (62.5% against 62.9%; the seeds differ by up to 0.1 points). At
350 þús. the share is 0.34 points lower. Most of the difference is the moves. The larger population a reform brings
settles 62% in the capital area, as arrivals did in 2025, and accounts for less than a tenth of a point. House
prices in the capital area end 1.5% lower against the rest's than in the status quo.

In the status quo the capital area's share drifts down by 0.9 points in ten years, against a steady 64.0–63.9% in
2015–25. The likely reason is that the model's capital area is no younger than the rest, so it has no natural
increase of its own. Its pay advantage narrows from 1.10 to 1.05, since nothing makes the better paid more likely
to move there.

Not represented: the areas' own labour markets (pay and unemployment are national apart from who lives where; the
record's 4.9% against 3.2% unemployment and 34.5 against 38.4 hours a week are not reproduced), demand for local
services, commuting, who moves by education, and the eight regions within the rest of the country.

**Check.** The QC checks three things:
- the base year's areas: 63.9% in the capital area, and moves each way within 25% of the record's;
- the status quo's share holds within a point and a half;
- a borgaralaun makes leaving the capital area more worth while.

The 2016–2025 backcast must reproduce three things, without fitting:
- the capital area's share of the population within half a point;
- the moves between the areas within 25%;
- the narrowing of the price gap, in direction.

The backcast takes the base year's figures and each year's arrival share from the record (`history_params.py`).

| 2016–25 backcast | Model | Record |
|---|---|---|
| Capital area's share, 2019 / 2024 / 2025 | 64.2 / 63.9 / 63.8% | 63.9 / 64.0 / 63.9% |
| Moves between the areas, mean a year | 7,806 | 7,657 |
| Moves, mean error | 421 a year (5.5%) | |
| Price gap, December 2025 against 2015 | 0.960 | 0.812 |

All three pass. The share is within 0.3 points in every year it can be compared, and the moves are within 25% in
every year (the widest miss is 2019, 11% above the record's 6,925). The gap narrows in every year, as in the record,
but by a fifth as much: 4% against 19%.

The first run failed this check: the model's gap widened by 3% to 2021. Two things in the model were the wrong way
round:
- New building went to each area in proportion to its stock, about 64% to the capital area, against the record's 69%.
- Households were larger in the model's capital area than outside it, because the tilt by pay put couples there.
  From that start, the capital area's households multiplied faster than the rest's: 28% against 26% over the
  decade. In the record it is the other way: units outside grew 31% and in the capital area 26% (MAN07108), as
  people per household fell faster outside.

Fixing the building share alone left the gap at 1.03 in 2021. Starting from the record's household sizes as well
turned it. The rest of the narrowing likely lies in what the model does not have:
- Building costs by area. In parts of the country homes sell below what they cost to build; HMS's rural loans
  (landsbyggðarlán) exist to bridge that, so prices there can rise for a long time before anything is built.
- Pay and work by area. Pay is national in the model apart from who lives where.

## 2. The financial sector

**What is left out.** No banks, no balance sheets, no role for the pension funds as buyers of government bonds and
lenders of mortgages.

**Iceland's figures** (`financial_accounts.json`, THJ10001, end of 2025, ma.kr.):

| | Assets | of which loans | of which bonds | Deposits owed | Bonds issued | Equity |
|---|---|---|---|---|---|---|
| Deposit-taking banks (S122) | 6,332 | 4,929 | 710 | 3,173 | 1,799 | 866 |
| Pension funds (S129) | 8,824 | 805 | 2,809 | – | – | (rights owed: 8,863) |
| Households (S14) | 13,674 | – | – | (deposits held: 1,666) | – | (loans owed: 3,477) |
| General government (S13) | 2,533 | – | – | – | 2,035 | (net: −1,890) |

Equity is 13.7% of the banks' assets; their risk-weighted capital ratios run 20–24%. The pension funds hold
more bonds than the banks do, and lend to their members directly.

**Why it matters.** The reform redirects pension contributions. Money that would have flowed into the funds, and
from them into government bonds and mortgages, is paid out instead. Less demand for bonds raises the state's
borrowing costs; less lending by the funds pushes borrowers to the banks. A recession under any scenario raises
loan losses, which bind the banks' capital and tighten credit.

**How it is modelled (2.0, `financial.py`).** The central bank sets the policy rate as before (macro.py); two
balance sheets add what they do to the rates households, firms and the state pay on top of it. The banks' household
loans follow the model's own mortgages, less what the funds lend, and their loans to firms the business capital
stock (`capital.py`). Their equity earns the base year's return (11%, EST) and loses what borrowers fail to repay:
0.2% of loans a year in normal times, 0.2 points more per point of unemployment above the base year's and 0.04 per
unit of a fall in house prices (EST, on the scale of the central bank's stress tests). They pay out what lifts equity
above the base year's 17.6% of loans and keep everything while below it, and below it they charge more: 0.13 on the
shortfall in the ratio (the steady-state effect in the Basel Committee's assessment of 2010, 13 basis points per
point of capital). The pension funds' mortgage book and bonds follow the assets in the funds' ledger (`pensions.py`).
Where a reform folds the funds into the state, the state holds what it takes, bonds and members' loans among them,
so nothing moves at once; what changes is the flow, as contributions no longer buy bonds or lend to members and the
banks lend what the funds would have. A missing buyer weighs as an added seller: the yield on the state's bonds
rises by 0.05 per unit of GDP of bonds the funds hold less than in the status quo (EST, the size of the macro part's
debt premium; Laubach 2009 finds 3–4 basis points per point of debt to GDP). The banks' spread, weighted by their
share of household loans, and the bond premium go into the mortgage rate, which firms' cost of capital also uses;
the bond premium goes into the state's coupons.

What it finds: the balance sheets add little in these scenarios. The banks' capital never binds in the paths the
model produces — a year's losses stay well within a year's profit — so their spread stays at nothing but for a few
basis points in a bad year. Folding the pension funds in adds about 1.6 basis points a year to the state's
borrowing cost, 13 by the eighth year of a borgaralaun of 350 þús., and the funds' share of household loans falls
from 23% to 17% as the banks take up the lending.

Not represented: the central bank's balance sheet, the banks' foreign funding, deposit flight, a bank failing, and
the funds' choice of how much of their assets to lend to members, which the model takes at the base year's share.

**Check.** The base year's balance sheets as THJ10001 has them (QC); the status quo is its own reference for the
bond market; folding the funds in raises the state's borrowing cost and not folding them does not. The backcast
checks are not yet run. An annual series of mortgage rates is not published in a form the model can read; and the
funds' share of household loans went from 9% in 2015 to 23% in 2025 while their loans grew from 5% to 9% of their
assets — their own choice to lend to members, which a constant share cannot reproduce, so the check would fail by
design until that choice is modelled.

## 3. Pension-fund solvency

**What is left out.** The funds' assets are tracked; what they owe is not.

**Iceland's figures.** Pension rights owed by the funds were 8,863 ma.kr. at the end of 2025 (THJ10001, FL6),
against assets of 8,824. Households' pension claims, 10,348 ma.kr., include the rights the state guarantees
without funds behind them (S13 FL6, 1,243). At the end of 2024, 19 of 25 departments had a negative actuarial
position; without the employer-guaranteed funds the average was just over 1% short, and those funds were 74% short
(Íslandsbanki's reading of the Central Bank's figures). The law (129/1997, art. 39) requires a fund to change its
rights when the gap exceeds 10%, or 5% for five years running, valued at a 3.5% real discount rate.

**Why it matters.** Redirecting contributions while keeping earned rights (the lever `pension_keep`) leaves the
funds paying out more than comes in, and the gap is borne either by cuts to rights or by the state. A lower return
does the same. The model can say how fast assets fall, but not whether the funds stay solvent.

**How it is modelled (2.0, `pensions.py`).** Two pools, from the Central Bank's figures for the end of 2025: the
funds no employer guarantees (assets 7,528 ma.kr., accrued rights 7,606 at 3.5% real) and the divisions the state
and municipalities guarantee (345 against 1,485). Each year a pool's assets earn the funds' real return (3.81%,
1997–2025) and take in contributions and pay out pensions, each the 2025 record times the model's own flow against
its base year; its rights grow at 3.5%, by what the year's contributions buy and less what is paid. The law's test
is the total position, which adds the present value of today's members' future contributions and the rights they
will buy; LIVE's review for 2025 puts the first at 46% of its accrued rights, and the two are taken as balanced, so
the future part dampens a gap in the accrued one. When the total position is out by more than 10%, or by more than
5% five years running, every right in the pool — pensions now paid, pensions to come and the accrual table — is cut
or raised alike to close it, unless the lever `pensions.state_cover` has the state pay the shortfall in, a budget
cost. Guaranteed rights are never cut; the state's special payments to those divisions (57 ma.kr. in 2025) are
what keeps them paid.

Under the reform, the rights folded in end as the fold phases in, and the state takes the returns on the assets
that backed them. The special payments end with what they pay for: 57 ma.kr. a year to the guaranteed divisions,
13 to LSR A and for disability equalisation (lever `pensions.guarantee_saving`). Kept earned pensions
(`pension_keep_earned`) stay in the funds, which then run off with no contributions; their position is tested on
the accrued rights alone, since no future contributions are left.

Not represented: each fund on its own (one pool stands for twenty-odd), the funds' costs, a future position out of
balance (LIVE's was 4.7% short of its future contributions, from an accrual table it means to replace), and
mortality beyond what the funds' tables project.

**Checks.** The status quo's accrued position starts within a point of the record's −1.0%, and at the mean return
stays within the law's 5% band with no right cut. Replaying the record's returns from 2007 brings one cut in rights
of 5–30% after 2008 (the funds cut by 10–20% in 2008–10), and the position ends within the band. The reform's fold
ends the rights it folds in and saves the special payments (69.8 ma.kr. a year in full); without the fold the
funds' rights go on as in the status quo.

## 4. The capital stock

**What is left out.** No capital stock or investment in the usual sense; capital follows labour in a reduced form.

**Iceland's figures** (`capital_stock.json`, THJ03204). The net capital stock was 14,644 ma.kr. at current prices
at the end of 2025, about three times GDP, and its consumption 854 ma.kr., 5.8% of it. Dwellings are about 40% of
the stock.

**Why it matters.** A reform changes the return on capital (the corporate tax, the staked share, the automation
levy) and the supply of savings (the pension funds). Whether that changes investment, and so output and wages over
decades, is where the long-run results rest.

**How it is modelled (2.0, `capital.py`).** The business sector's stock, 6,540 ma.kr. at the end of 2025 (1.32 times
GDP; dwellings are in the housing market and the state's capital in its accounts), depreciates at the record's 8.8%
a year. Firms invest to replace what wears out, to grow as they expect the economy to (from the record's 3.1% a
year, moving a fifth of the way each year to the status quo's trend), and more or less as capital pays more or less
than it costs: Tobin's q, the return after corporate tax on a króna of capital against the real interest rate plus
depreciation plus a risk premium (4%, EST), each set against the base year's. A q of 0.9 lowers investment by 1.2% of
the stock a year (EST; Chirinko 1993 finds investment answers q weakly and slowly), two years after the decision:
what is put in place in a year was decided earlier (time to build, Kydland and Prescott 1982; Koeva 2000 finds about
two years from decision to completion). Output per hour rises with capital
per unit of labour with elasticity 0.33, capital's share of income (EST). A run is set against its reference, as
the other parts are: the status quo is its own and nothing in it changes, since its output per hour already carries
capital's growth in the productivity trend; a reform's capital per hour worked is set against the status quo's in the
same year. The corporate tax and the staked share enter through the return; the real rate, and the VAT on capital
goods that the restriction of refunds to value-chain inputs no longer refunds (§7), through the cost; wages
outrunning prices through the profit margin.

What it finds: fewer hours worked need less capital, and capital takes years to follow them down, so for a few
years each hour worked has more capital behind it. Under a borgaralaun of 350 þús. output per hour is up to 5% higher
in the second and third years than labour alone would give, and back to the status quo's by the tenth, as investment
falls to about 10.5% of GDP against the status quo's 12.8%. A corporate tax of 30% on top of that leaves output per
hour 2.4% lower than without it by the tenth year, and still falling. The real rate matters as much as the tax: where the reform's
deficit sends it to its 12% ceiling, q falls by a fifth.

Not represented: investment as demand (part of it spent at home), capital from abroad beyond what the real rate
carries, and machines' capital for office AI and robotics, which the automation part keeps apart.

**Checks.** The status quo's output per hour is untouched (factor 1 every year); the status quo invests a share of
GDP within the record's range for 2016–25 (11.4–17.7%); a higher corporate tax leaves less capital per hour worked.
The backcast compares business investment's share of GDP with the record, 2016–2025, without fitting it: a mean
error of 1.8 points (bias +0.8), inside the two points set before it was run. Without the time to build the error was
2.0 points; the lag was taken from Koeva and run once, not tuned. The model misses the slump of 2019–20 (the fall of
WOW air, then COVID), which nothing in q foresees, and follows the boom of 2023–25 from the low real rates of
2021–22.

## 5. Social norms in the choice to work

**What is left out.** Whether others work does not affect whether one works.

**What the evidence says.** Norms to work are real and measurable. In Switzerland, the unemployed in communities
whose vote showed a work norm 10 points stronger found jobs 7–8% faster (Stutzer and Lalive 2004, JEEA), about as
much as a replacement rate ten points lower. Claiming spreads among peers: in Norway, a point more long-term
claimants among close neighbours raises one's own chance of claiming by about 0.2 points, a long-run social
multiplier of about 1.28 (Markussen and Røed 2015, JHR), with similar figures for disability pensions (Rege, Telle
and Votruba 2012) and between parents and children (Dahl, Kostøl and Mogstad 2014, QJE). In theory, a norm that
weakens as more people live off transfers can tip a welfare state into lasting dependency (Lindbeck, Nyberg and
Weibull 1999, QJE; 2003, JEEA).

**Why it matters.** It is the commonest objection to a basic income, and the evidence on individuals (lottery
winners, the trials) cannot test it: a winner's neighbours did not win. If the norm is as strong as Norwegian
claiming suggests, the labour response measured on individuals understates the response of a whole country by
about a quarter.

**How it is modelled (2.0).** The value a person puts on not working rises with the share of their peers out of
work in the year before, against that share in the base year: peers are those who choose whether to work in the
same age band and sex (ten groups). The size is set so that a point more peers out of work raises one's own chance
of not working by 0.2 points in the status quo, as in Norway, with a sensitivity lever (`behaviour.norm_scale`)
from 0 to twice that. The individual income effect (M3) is measured with peers held fixed, so it still tests the
individual response alone. Not represented: area (peers are counted nationally, though the model now has two
areas) and the family's own example, which the Norwegian and Dahl, Kostøl and Mogstad estimates find stronger still.

What it finds: the norm multiplies a borgaralaun's labour response by about 1.2 after six years, within the range
the Norwegian multiplier gives. It also reverses one result of 1.0 and 1.1. Without the norm, a borgaralaun of
450 þús. raises the number who work for themselves (3,823 against the status quo's 3,515 after six years), since
it takes away the risk of self-directed work. With it, the count falls to 3,092 against 3,505. In a logit, a
higher value of not working takes the same share out of each kind of work for a given person, so it falls hardest
on those already closest to not working, and many of those who would work for themselves are among them. The
evidence does not say whether the stigma of not working weighs against self-directed work as it does against a
job; the model assumes it does.

**Check.** The status quo's base year unchanged; the income-effect check unchanged; under a reform the aggregate
response larger than the individual one by a factor near the multiplier; and the payment's effect on
self-directed work checked both ways: up with the norm held at zero, and lower with the norm than without it.

## 6. The informal economy

**What is left out.** Undeclared work.

**Iceland's figures.** Estimates differ by method. The MIMIC method of Medina and Schneider puts Iceland's shadow
economy at about 16% of GDP in 2015–2017, a method known to run high against direct measures. The working group
Alþingi appointed in 2002 put lost tax at 7–11.5% of revenue (report of December 2004). The model's enforcement
section already takes 200 ma.kr. a year of evasion as a starting point.

**Why it matters.** Means-tested benefits give people a reason to hide income; a payment without a means test
removes it. Higher flat tax rates give a reason to hide more. Which is larger decides whether the reform shrinks or
grows the informal economy.

**How it is modelled (2.0, `informal.py`).** Each worker keeps a share of their earnings off the books: 20% of
self-reported earnings (the self-employed and founders) and 2% of employees' (cash work no employer reports), both
EST and set against Denmark's audits, where 37% of self-reported income and 0.3% of third-party-reported income was
hidden (Kleven, Knudsen, Kreiner, Pedersen and Saez 2011). The share rises with what declaring a little more would
cost — income tax, contributions and withdrawn benefits, read off the rules person by person — with elasticity 0.5
(EST; Clotfelter 1983 finds 0.5–0.8, Kleven et al. less). The norm that keeps most people honest is in the levels,
which the pure Allingham–Sandmo model would put far higher. Each person is set against themselves under today's
rules on the same earnings, so the status quo is its own reference and its record of declared incomes stands; under
a reform, earnings that come onto the books pay tax and leave less in hand, and those that go off do the reverse.
The work and its output are unchanged.

What it finds: the status quo hides about 104 ma.kr. of earnings, some 45 ma.kr. of tax, about 0.9% of GDP — the
labour part of an evasion the finance ministry's working group put at 3–5% of GDP (June 2017). A borgaralaun of
350–450 þús. barely moves it (under 1 ma.kr. a year): few people both work and lose benefits as they earn today, and
the reform's flat rates are close to today's for most workers. A tenth higher income tax drives more off the books.

Not represented: people out of work who work off the books while claiming, which a payment without a means test
would remove the reason for; VAT and companies' evasion (left in the enforcement section's 200 ma.kr.); and
detection, which the enforcement lever applies to the static figure only.

**Checks.** The status quo's tax lost on hidden earnings between 15 ma.kr. and 5% of GDP; no tax moved on or off
the books in the status quo; a tenth higher income tax lowers the tax from earnings brought onto the books.

## 7. The other mechanisms for 2.0

* **Hours within a job (2.0, `hours.py`).** The choice of status — out of work, part time at 55%, full time, a
  firm, independent work — stays the large margin. Within a job each worker's week now moves too, set against the
  same person under today's rules at the same pay: up with what is left of a little more pay after tax and
  withdrawn benefits (compensated elasticity 0.15, EST; Chetty 2012 puts the intensive elasticity at most 0.33 once
  frictions are allowed for), and down with income that does not depend on hours (0.04 for each unit of income
  after tax as a share of income today, EST). In the trial of Vivalt, Rhodes, Bartik, Broockman, Krause and Miller
  (NBER w32719) $1,000 a month, some 40% of income, cut hours by 1.3 a week, mostly through people leaving work, a
  margin the choice model carries; within the job that leaves at most about 2%. Hours move half the way in a year,
  between 75% and 110% of the standard week, and the collective four-day-week lever multiplies them. The status quo
  is its own reference. What it finds: a borgaralaun of 350 þús. shortens the week within the job by 1.1% by the third
  year, 450 þús. by 1.6%; for 350 þús. that is about 0.7% less output and some 35 ma.kr. a year on the balance by
  the sixth year, beside the far larger move between statuses.
  **Checks.** No week moves in the status quo; a borgaralaun of 450 þús. shortens the week within the job by no
  more than the trial's 3% on both margins.
* **Input VAT.** The yield of restricting VAT refunds to value-chain inputs is the result most exposed to error
  (DESIGN.md R1). The plan was to rebuild it from Skatturinn's records by industry. Those records exist — the tax
  authority holds turnover, output tax and input tax by taxpayer and can compile them by industry (answer to
  Alþingi, 149th session, þskj. 714) — but they are not published, beyond a few industries in answers to
  parliament. The split of the 997 ma.kr. of input VAT into goods for resale, materials, energy, subcontracted
  work, other services and capital goods stays an estimate from the supply-use tables, scaled to the total the VAT
  returns and the state accounts imply; the range (385–574 ma.kr.) stays as the lever. Skatturinn could settle it
  with one table.

  What 2.0 adds is what the restriction does to investment. In every variant of the estimate, capital goods are not
  among the value-chain inputs, so a firm can no longer reclaim the VAT on a machine or a building: capital goods
  cost it a quarter more at the reform's 25%, as far as the lever applies the restriction. That enters the cost of
  capital in `capital.py`, and the part of the yield that falls on capital goods (119 of 489 ma.kr. at 2025 rates,
  central variant) is paid on what firms still invest. Under a borgaralaun of 350 þús. the restriction leaves output
  per hour 3.7% lower by the twelfth year than the same reform without it, and still falling; in the long run, with
  capital's share at a third, a quarter on the price of capital goods takes about a tenth off output per hour
  (production efficiency: Diamond and Mirrlees 1971 argue against taxing inputs for this reason). Within twelve
  years the yield still outweighs it in the budget by far. The price effects at constant volumes
  (`vat_input_price_per_100bn`, exporters' costs) do not yet allow for firms buying less capital, so the two
  overlap a little.
* **Returns that rise with wealth.** Returns on wealth rise with wealth and persist in Norway's and Sweden's
  records (Fagereng, Guiso, Malacrino and Pistaferri 2020, Econometrica; Bach, Calvet and Sodini 2020, AER). 2.0 has
  the mechanism (`model.wealth_returns`): an extra return by rank in savings and other assets, from 1.6 points
  between the 10th and 90th percentiles to about 4.5 points at the top 0.1%, with the whole shifted so that the
  return on all savings together stays 2%. It is set to zero by Iceland's own record: in the backcast, one return
  for all already gives the richest tenth's wealth outside housing 4.7% a year over 2016–25, against about 4% in the
  tax returns (THJ09005), and Norway's gradient takes it to 5.6%. It stays as a sensitivity
  (`wealth.return_gradient_scale`, 1 for Norway's gradient); what the forward run's falling top lacks is in housing,
  where homes turn into savings as estates settle and buyers take on new mortgages, not in the return.
* **Real wages and exports in the backcast.** Both run low (VALIDATION.md §2). The capital stock and the regions
  give the backcast two channels it lacks; the errors are to be read again once they are in.
