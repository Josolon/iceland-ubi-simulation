# Changelog

What changed in each version, and the errors found and corrected along the way, with what each did to the results.
Corrections are listed because a reader judging the model should know where it has been wrong.

Version 1.0 is the first public release. Before it, the model went through development versions that were not
published: the model's own v0–v6.1 (2026-09-15 to 2026-09-18; sections 9–30 of [docs/ABM.md](docs/ABM.md)
describe each step), then explorer versions v1 to v10 (from 2026-09-18). Comments in the code and in ABM.md refer to
those development versions as v1, v2 and so on. From 1.0 on, each release is a git tag.

## 2.0.0 (2026-10-29)

The limits 1.0 named, each given a part of the model, with its evidence, findings and checks in
[docs/LIMITS.md](docs/LIMITS.md). Each new part leaves the status quo's base year as the record has it; the base
year is recalibrated and the surface rebuilt. 2.0.0 also carries the changes prepared as 1.1.0 (below), which were
tested in full but not released on their own: the published pages go from 1.0.1 to 2.0.0. The pages keep the josolon.com
design and Vercel Web Analytics added to the site after 1.0.1.

**New in the model**
* **The pension funds' solvency** (`pensions.py`). Two pools from the Central Bank's figures for 2025, guaranteed
  and not, with the law's test of the total position and cuts or rises in every right when it fails. Replaying the
  record's returns from 2007 brings one cut after 2008, as the funds made. Under the reform the rights folded in end
  and the state's special payments to the guaranteed divisions end with them (69.8 ma.kr. a year in full).
* **The norm to work among peers.** The value of not working rises with the share of one's peers (same age band
  and sex) out of work, sized to the Norwegian evidence; a lever scales it from 0 to twice that. It makes a
  borgaralaun's labour response about a fifth larger. It also reverses one earlier result: at 450 þús. fewer people
  work for themselves than in the status quo (3,092 against 3,505 after six years), where without the norm more do.
* **Returns that rise with wealth**, after Fagereng et al. (2020) and Bach et al. (2020), as a sensitivity. Iceland's
  own record sets it to zero: one return for all already gives the richest tenth's other wealth a little more
  growth than the tax returns show.
* **The informal economy** (`informal.py`). Each worker keeps a share of earnings off the books that follows their
  marginal rate. The status quo hides about 0.9% of GDP of earnings; a borgaralaun barely moves it.
* **The business capital stock** (`capital.py`): q-investment with time to build, against the firms' cost of
  capital and the real rate. Fewer hours leave more capital per hour for a few years. A higher corporate tax leaves
  less capital per hour.
* **VAT on capital goods.** Restricting VAT refunds to value-chain inputs makes capital goods dearer. Under a
  borgaralaun of 350 þús. it leaves output per hour 3.7% lower by the twelfth year, still falling; the yield still
  outweighs that in the budget within the run.
* **Hours within a job** (`hours.py`): the week moves with the marginal rate against today's and with income that
  does not depend on work (compensated elasticity 0.15, income effect 0.04 after Vivalt et al.). About 1% shorter
  under a borgaralaun of 350 þús.
* **Banks and the pension funds' balance sheets** (`financial.py`), with loan losses, the banks' capital and what
  the funds' bonds and lending add to rates. The banks' capital does not bind in these runs. Folding the funds in
  adds about 13 basis points to the state's borrowing cost by the eighth year.
* **Two areas** (`regions.py`): the capital area and the rest of the country, each with its own housing market, and
  moves between them at the record's rates, responding to real income after housing. People start in the record's
  shares, the capital area's households better paid and smaller than the rest's, and new building goes there in the
  record's share of completions. The 2016–25 backcast reproduces the share, the moves and the narrowing of the price
  gap in direction (4% against the record's 19%). A borgaralaun moves few people: at 450 þús. the capital area's
  share is 0.38 points lower after ten years, as about 1,360 more people leave it than in the status quo.

## 1.1.0 (not released on its own; part of 2.0.0)

New mechanisms, a corrected wealth distribution, and the fixes of 1.0.1. The status quo's base year is unchanged
except where a correction says otherwise; the surface is rebuilt.

**New in the model**
* **Top incomes answer the tax rates.** Pay above the second threshold responds to the net-of-tax share against
  today's (elasticities 0.10 between the thresholds and 0.25 above the top one, after Saez, Slemrod and Giertz 2012
  and Kleven and Schultz 2014); half the response is less work and half is reported differently. Owners of their
  own firm take more pay as dividends when dividends keep more than pay (Alstadsæter and Jacob 2016). A sensitivity
  lever scales both responses.
* **The career ladder.** Each person carries the experience gained or lost against what the base year's rates
  would give them, and pay follows it (2% a year, bounded). Where machines take the entry-level work of a
  profession, fewer juniors are hired into it, and those turned away look again the next year. A reform lever pays
  a share of juniors' wages in those professions. In the status quo the ladder leaves the base year untouched (a
  new check).
* **Robotics as its own track.** Office AI and robotics are separate technologies with their own exposures by
  profession, pace, adoption cost and take-up speed; until 1.0 one exposure covered every machine. Reform levers
  subsidise the take-up of each.
* **What machines produce is now counted in output:** the value added of automated work (80% of it domestic) is
  in GDP, and half of machines' earnings after tax reaches households here as their owners. The stand-in used
  before (`output_gain` .25) is set to 0.
* **The family home free of inheritance tax** when an heir lives in it for ten years, as in Germany
  (§ 13 Abs. 1 Nr. 4c ErbStG). Some heirs move in because of it, and older owners downsize less.
* **Social assistance as claimed:** a calibrated 37% of those the model finds entitled claim it, to the record's
  ~2,700 recipients. Before, everyone entitled claimed.
* **Unpaid family care.** Each person has a care tie with the weekly share Iceland's health interview survey of
  2019 gives for their age (22–33% of 16–64 year-olds), and a carer gives the hours EU-SILC 2016 gives for carers in
  and out of work (6.9 and 7.9 a week). Care given beyond the status quo's takes the place of half as many hours of
  care assistants' work. Under a basic income this replaces about a hundred posts: most care in Iceland is light,
  and carers out of work give only about an hour a week more.

**Corrections**
* **Wealth at the top.** The spread of wealth is now fitted by family to the 2025 tax returns (Hagstofa THJ09005,
  THJ09007). The richest tenth of families hold 50.9% of net worth (returns: 50.0%), the median family 12.8 m.kr.
  (11.9), and the 99th percentile is 2.69 times the 90th (2.66). In 1.0 the richest tenth held 34% and the median
  family 33 m.kr. Real estate held now rises with other wealth. The returns value shares at nominal value, so the
  top is still understated; `scripts/wealth_valuation_sensitivity.py` shows what valuing them higher does.
* **Adults living in someone else's home** were given homes of their own as owners when the population was drawn,
  homes no household in the housing ladder held. They now own none; they rent when they leave.
* **Housing benefit** is no longer paid to an adult living in someone else's home: it needs a registered lease of
  three months or more (law 75/2016, 9. gr.). Together with the correction above, this brings the benefit from
  12.8 ma.kr. to the record's 11.2.
* **Unemployment had a floor.** Jobs ended at a fixed rate whatever the demand for labour, so unemployment could
  hardly fall below the base year's: with 60% more demand it went from 3.6% to 3.5%. In the backcast it stayed near
  4% through 2016–18 and 2023–24, where the record has 3.1–3.4%. The backcast then kept raising demand to reach
  the record, up to 40% above the model's own by 2023, and the arrivals that demand draws put the population 4,000
  (in 1.0) to 8,500 (with this version's other changes) above the record by 2025. Now, where a profession has open posts, some of those whose job ends move straight
  to another within the year (at most half, rising with the vacancy rate), and the wage curve reads the same lower
  unemployment where posts outnumber people. The backcast now matches unemployment in every year, with demand at
  most 12% above the model's own. Its population error fell from 2,306 to about 1,050 people a year. The real-wage
  error rose from 6.5% to about 8%: the larger demand shock had been lifting pay, so 1.0's figure flattered the
  model ([VALIDATION.md](docs/VALIDATION.md) §2). The calibration's tolerance for unemployment is also halved, to
  0.15 points.
* **Young adults out of work.** In the status quo the share of 20–29 year-olds neither working nor studying
  drifted up within a few years to well above the record's 5–9% (Eurostat edat_lfse_20). Five faults were behind
  it, each corrected:
  * people who started or finished a course, turned 16, 20 or 67, or had just arrived kept their old status until
    a random re-choice came round, and they now choose again at the event;
  * students never chose again at all, and their share without a job is now fitted to EUROSTUDENT 8 (24% of
    students in Iceland without paid work in term time);
  * no one left compulsory education after 16, so cohorts that finished upper secondary school stayed in the
    lowest education group for life. At 20, the share of each cohort with upper secondary education now matches
    the base year's, and those who move up take the pay of people who already have it;
  * the floor on consumption in the choice to work erased the difference in income between working and not for
    anyone whose costs exceeded their income, so many were indifferent to work. The floor now shrinks the gap
    smoothly instead of removing it;
  * arrivals from abroad spent their first year out of work before they first chose. They now choose on arrival,
    and their rate out of work matches the record (Eurostat edat_lfse_28: 8.5% of those born abroad, against
    5.2% of those born in Iceland).

  The check is on the measure the model can compare: 20–29 year-olds not employed, studying or not
  (Eurostat edat_lfse_18), which the status quo now keeps within 2016–2025's range every year. The model follows
  only courses at university level, so its count of those "not studying" includes people the survey counts as in
  education.
* **The inflation-neutrality checks** read one seed. On it, corporate tax differed by 9% between runs with and
  without inflation, from the heavy tail of venture profits, where five seeds showed no difference on average.
  The checks now read the mean of three seeds, with the tolerances unchanged.
* **The wiring check** read only the modules it was written with, so the career ladder's parameters showed as
  unused. It now reads every module.

**New checks:** top-income percentiles against the 2025 tax returns (TEK01006); wealth by family against the
returns; social-assistance recipients; family carers against the survey; the career ladder and family care leaving
the status quo untouched; 20–29 year-olds not employed against Eurostat; family care replacing some care posts under a reform, and few.

**Pages:** new levers for robotics, junior wage subsidies, adoption subsidies, the home exemption, and sensitivities
for top incomes and family care; new indicators for the career ladder and family care. The text and page fixes of
1.0.1 are included.

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
