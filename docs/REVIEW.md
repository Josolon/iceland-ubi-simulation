# Review of version 2.0, and the path to the next versions

Version 2.0 was put to six referees on 29–30 October 2026: an economist, a sociologist, a political scientist, a
philosopher, a lawyer (Icelandic constitutional law, EEA law, tax and labour law) and a modelling methodologist.
Each read the documents and the code, searched the literature and the law, and wrote a report. None of them ran or
changed the model. Their strongest claims were then checked in the model itself (§2). This file digests the six
reports, says what was confirmed, and sets out what to change, in order.

The referees' citations are given as they gave them. Several said that some were from memory; each must be checked
against the source before it is quoted anywhere else.

## 1. What all six agree on

The model's engineering was praised by every referee: the paired comparison against a status quo in the same world,
the null test that must match to the last digit, the status tag on every parameter, the pre-registered forecasts,
the backcast that reports its misses, and a changelog that records errors. All of that stays.

What they found, grouped by theme rather than by referee:

**A. The headline budget rests on three assumptions, not on the payment.** (Economist, lawyer, political scientist.)
The +369 ma.kr. surplus of the reference reform in 2035 comes largely from:

* folding the pension funds in *without* paying the pensions already earned, so that the state takes both the
  contributions and the funds' returns, which amounts to cancelling about 9,000 ma.kr. of accrued rights;
* ending collective wage agreements under the reform only, so that the one-off price rise from the single VAT rate is
  absorbed into real wages under the reform but compensated in the status quo;
* restricting the reclaim of input VAT, whose 460 ma.kr. yield is a fixed line whose cost is only partly passed on to
  prices, wages or profits anywhere in the model, and from which nothing is lost to avoidance.

**B. Three settings of the reference reform are not lawful as modelled.** (Lawyer, political scientist.)

* Cancelling earned pension rights: Constitution art. 72; ECHR Protocol 1 art. 1, where Iceland has lost a case on a
  cut pension (*Kjartan Ásmundsson v. Iceland*, no. 60669/00, 2004).
* Ending collective agreements: Constitution arts. 74 and 75(2), ECHR art. 11, ILO conventions 87 and 98.
* Standing capital controls: EEA art. 40. Art. 43 allows only temporary measures in a crisis, which is how the
  2008–17 controls were upheld (EFTA Court E-3/11).

Several smaller items carry costs the accounts leave out:

* child payments that must be paid to EEA workers' children abroad (Reg. 883/2004 art. 67; *Commission v Austria*,
  C-328/20);
* the state's guaranteed payments to LSR B and Brú;
* compensation where an option expropriates: ownership terms, custodianship, the deemed state stake;
* delays until the current wage agreements expire.

**C. The pages show no uncertainty, and the surface is judged by the wrong measure.** (Methodologist, economist,
philosopher.)

* A cross-validated R² of 0.98 for the budget still allows errors of 140–210 ma.kr., because the payment alone spreads
  the budget by more than 1,000.
* The cross-validation also leaks: the 120 drawn worlds and the near rounds put near-copies of the same runs into
  both training and test folds.
* The coverage warning on the pages compares an unweighted distance in 96 dimensions with the largest gap between
  runs, so it almost never fires. The 170–270 ma.kr. errors found near readers' own Guide answers went unflagged.
* Every run uses one seed (±15 ma.kr.), and the pages show point values only.

**D. The labour response is calibrated outside its evidence.** (Economist, sociologist, methodologist.)

* The extensive elasticity is pinned at 0.25. Iceland's own natural experiment, the tax-free year of 1987, suggests
  about 0.09 at the extensive margin and 0.4 at the intensive (Sigurdsson, *AEJ: Economic Policy*, 2025).
* The accepted band for the income effect (0.04–0.20) leaves out the estimate of the very study it cites (Golosov et
  al., *QJE* 2024, about 0.5).
* Labour demand follows labour supply one for one (`supply_absorption = 1`). That fits migration, but not people
  leaving work on a transfer they go on spending, and it may overstate the fall in work.
* The norm to work is sized to peer effects in *claiming* benefits, which run partly through stigma, and there is no
  stigma in a universal payment. Students no longer count among the peers.

**E. The pages carry values they do not state.** (Philosopher, political scientist.)

* The work card scores less paid work as a loss, while the agents' own utility values leisure. Care and study count
  for nothing.
* The colour thresholds (work red below −12%, inflation "holding" below 5%) are not shown, and the budget card judges
  the balance in absolute terms while the scenario search judges it against the status quo.
* "No group worse off" is tested on the medians of groups that people move between because of the reform.
* The Guide opens on a preset reform. Until now, its summary called unanswered questions "as today" when they kept
  the preset's settings (fixed, §3).
* It shows earlier respondents' answers beside each option, and its "why" texts mostly give one side.
* The reference reform bundles some forty items that are not a basic income: church funding, the presidency, state
  stakes, ownership caps and capital controls among them.

**F. The social structure is thin.** (Sociologist.)

* Immigrants, 23% of the employed in 2023, are drawn into professions like natives. The residence test turns the
  payment into an in-work benefit for recent EEA arrivals, which ties them to low-paid care work while natives can
  leave it.
* There is no parental leave, no term for a child's age in the choice to work, and no joint decision in couples.
  Results are not reported by sex or origin.
* Young adults and older people living with others are attached to random households.
* The anchored poverty line covers adults only. There is no after-housing-cost measure.
* The status quo's child poverty drifts from 12.8% to 20.2%, which inflates the reform's gain.

**G. The essential-service shortage is mostly the public-pay offset.** (Sociologist, confirmed in §2.) When public
pay is cut so that pay plus the payment equals the old take-home pay, staying in a nurse's or teacher's job pays
almost nothing over leaving it. The offset also cuts the pay of public employees who are not eligible for the payment.

## 2. Checked in the model

All model runs, 2035, against the status quo of the same world.

**The reference reform, 300 þús.** (status quo −241):

| Variant | Balance, ma.kr. | Work per adult | Price level | Child poverty | Posts short |
|---|---|---|---|---|---|
| As published | +369 | 0.584 | 2.11 | 13.5% | 4,101 |
| Earned pensions still paid | +87 | 0.575 | 2.13 | 14.3% | 4,666 |
| Wage agreements kept | +267 | 0.578 | 2.01 | 13.3% | 5,168 |
| **Both: the lawful version** | **+1** | 0.568 | 2.06 | 14.7% | 5,339 |

So:

* Paying earned pensions is worth about 280 ma.kr. a year in 2035.
* Keeping the agreements is worth about 100.
* Done lawfully, the reference reform only just balances, though it still stands about 240 ma.kr. better than the
  status quo.

**350 þús. with the property tax at 2% of value and income-tax rates as today** (one reader's Guide answers
otherwise; status quo −136):

| Variant | Balance | Posts short | Work per adult |
|---|---|---|---|
| Public pay cut fully (the reader's answer) | +192 | 4,976 | 0.551 |
| Public pay cut halfway | +106 | 4,381 | 0.561 |
| Public pay not cut | +31 | 2,896 | 0.571 |
| Public pay not cut, earned pensions still paid | −295 | 3,410 | 0.559 |

* Not cutting public pay removes about 40% of the shortage, and work rises with it.
* Retraining, childcare places and fewer job cuts each move the shortage by a few hundred posts.
* With earned pensions honoured, 350 þús. does not balance.

**The surface near readers' answers.** At the reader's 375 þús. Guide answers the model gives −380 against the
surface's −206; at four nearby settings the surface was 100–270 too optimistic.

## 3. Already done

* The Guide's summary now says "not answered: the starting picture's setting" instead of "as today", and the code
  comment that said the Guide starts from today is corrected.
* 1,200 new model runs are being added to the surface. 600 are random sets of Guide answers, which is where readers
  land; the other 600 are a fresh hypercube over every lever, half of it in the page's own world. The 2.0 surface is
  kept aside, so the new runs serve first as a test set it has never seen (§4, item 1), and only then are fitted.

## 4. The path

### 2.0.1: the pages, before more people use them (days)

1. Score the 2.0 surface on the 1,200 new runs and publish the error in ma.kr.: RMSE, 95th percentile and largest,
   for the 2035 balance against the status quo. Refit with them, and replace the page's "within about 140" with the
   new figures.
2. Run the README's reference reform in the page's own world. Today it runs in the last decade's world, with
   behaviour settings the rest of the pages no longer use, which is why the status quo reads −241 in one place and
   −136 in another. Show poverty for all persons and for pensioners beside child poverty.
3. In the Guide:
   * let the reader choose the start, today's rules plus a payment or the preset package, with today's rules as the
     default;
   * show earlier answers only after the reader has answered, labelled as a self-selected sample;
   * give each "why" one sentence for and one against;
   * name the pension option for what it does ("earned pensions end");
   * give each option a badge for what it would need: ordinary law, a constitutional change, an agreement, EEA risk,
     no precedent.
4. Rename the work card "Paid work per adult", give it a neutral colour, and state the thresholds behind every colour.
5. Add "Law, politics and reversal" to *Not in the model* and to VALIDATION §5.
6. Withdraw from the README and DESIGN, until 2.1 checks them:
   * the 2035 surplus as a point figure;
   * "child poverty falls by a third" without the anchored and after-housing-cost measures;
   * the shortage described as people working less.

### 2.1: a lawful, honest baseline (weeks)

**The reference reform**

* Earned pensions paid (`pension_keep` = 1), with the guaranteed payments kept.
* Wage agreements replaced by three regimes:
  * agreements stay;
  * the extension law (Act 55/1980) is repealed and coverage decays;
  * a negotiated pact with net-of-tax indexation.
* Capital controls at 0.
* The disability and pension floor on.
* Residence strictness capped at what Dir. 2004/38 allows.
* The deemed state stake recast as a tax or removed.
* The public-pay offset phased in as agreements expire, never applied to people without the payment, and with a lever
  to exempt essential professions.

**New lines in the accounts**

* Payments exported under Reg. 883/2004, and pro-rata payments to pensioners who emigrate.
* Compensation owed for any option that expropriates.
* A ledger of pension rights that are not honoured.
* The essential-service shortage costed, through agency premiums or waiting lists, instead of booked as a saving.

**Input VAT**

* Close the incidence of the restriction, so its whole yield falls on prices, wages, profits or investment.
* Trace the cascade through a price model on Hagstofa's supply-use tables.
* Take 20–40% off the yield for avoidance and disputes.
* Show the yield as a range on the pages.
* Ask Skatturinn for input VAT by industry and purpose.

**Labour**

* Labour demand follows supply only for population changes; sweep the share 0, 0.5, 1.
* Re-anchor the extensive elasticity to the Icelandic evidence, and widen the income-effect band to include Golosov
  et al.
* Leave students out of the peer measure, and give the norm's multiplier as a range (1.0–1.4).
* Break the fall in work down by channel.

**Uncertainty on the pages**

* 5–10 seeds at every published scenario.
* A band on every card: surface error plus seed noise.
* For the budget, the probability that the balance beats the status quo.
* A badge reading "run exactly" when the band crosses a colour threshold.
* The probability of a positive balance in place of the coverage warning.

**The surface**

* Fit the difference against the status quo, net of the accounting that `models/static_balance.py` already computes,
  instead of levels.
* Cross-validation grouped by world and by design round.
* A held-out test set drawn the way readers answer, with a gate: the 2035 balance difference within 50 ma.kr. RMSE.

**Measures**

* An anchored child poverty rate, poverty after housing costs, and a deprivation proxy checked against EU-SILC.
* Poverty by group, defined by 2025 status.
* The share of people losing more than 5% or 10%.
* Every result by sex and by origin.

**Tests**

* The null test for the reform regime with every lever at today's values, in both the model and the surface.
* Directional checks with a minimum effect instead of a 0.5% slack.
* A pytest suite.

### 3.0: what the reviews say the model is missing (months)

**Politics and time**

* A fiscal reaction: a surplus is partly spent or returned, and a deficit freezes the payment.
* Erosion of a payment indexed to prices.
* A start year for each component.
* A staged path:
  * first a refundable personal credit;
  * then about 150 þús. with child and unemployment benefits folded in;
  * then rises only if pre-stated thresholds are met.

Referendums, coalitions and courts stay as documented scenarios, not modelled behaviour.

**The open economy**

* Uncovered interest parity with a premium on net foreign assets and on institutional change.
* A stress case: 15–20% depreciation and +200 basis points.

**People**

* Immigrants' professions and pay by origin and years in Iceland.
* Parental leave as a status.
* A term for the youngest child's age in the choice to work.
* Joint decisions in couples.
* Linked families, separation, and child support.
* Non-market time divided between care, study, volunteering and leisure.
* The crime and child-development channels re-anchored to the later evidence.

**Calibration**

* Publish a backcast without its identified shocks, and the persistence of each shock series.
* Replace hand tuning with history matching or the simulated method of moments.
* Morris screening over about 45 uncertain inputs, then Sobol indices on the surface.

**The surrogate**

* A Gaussian-process or ensemble correction with heteroscedastic noise.
* New runs chosen where predictive variance, weighted by readers' answers, is largest.
* Exact runs on demand for a finished Guide answer set, cached and added to the design.

**Values**

* Value profiles a reader can choose:
  * welfarist, with an inequality aversion;
  * real freedom, the largest sustainable payment;
  * reciprocity;
  * productivist, which is today's implicit profile;
  * sufficientarian;
  * relational.
* An equivalent-income measure that values leisure.
* A participation-income lever for comparison.
* A core basic income kept apart from the add-ons, with two or three reference packages from different traditions.
* "Argues for no outcome" replaced by "makes its value choices explicit and adjustable".

**Documentation**

* An ODD+D description of the agents, schedule and rules, separate from the development log.

## 5. A balanced reform, defined so it can be searched for

From the philosopher's proposal, adapted. Every condition is judged on the model's own runs across seeds, plus the
surface's measured error, and must hold with probability at least 0.8.

1. **Budget.** The cumulative balance for 2027–35 is at least the status quo's, and net debt in 2060 is no higher than
   the status quo's.
2. **Sufficiency.** Hardship, anchored poverty and child poverty are no higher than in the status quo in any year.
3. **No severe losers.** In every group defined by 2025 status, the 20th percentile of individual change in income is
   no worse than −5%, and no more than 5% of people lose more than 10%.
4. **Services.** The essential-service shortage is no more than the status quo's plus a margin the reader sets.
5. **Expectations.** Earned pension rights are honoured; any shortfall is phased in over years.
6. **Prices.** Inflation is at most 4% from the third year on.
7. **Law.** No setting the lawyer's table marks as needing a constitutional change or contrary to EEA law, unless the
   reader asks for it.

Within those conditions, the objective is the reader's chosen value profile, and the result is shown as the set of
best trade-offs rather than one optimum. The search runs on the model, not only on the surface.

## 6. After the review: pay set by the market, and the shocks (2026-10-30)

The author's design premise, stated after the review: the reform ends collective agreements so that pay, public and
private, is set by how willing people are to do each job once the payment lets them refuse it. The public pay cut is
a first step, not a pay scale. Model runs test what the 2.0 model makes of this.

**The public cut never came off.** In 2.0 the cut was permanent and a shortage was met only by a premium above
market pay of about 1% a year at a tenth of posts unfilled, capped at 40%. `labour.public_offset_unwind` (EST
2.5) now removes a profession's cut where it leaves the state's posts unfilled. At 0 the 2.0 results come back
exactly. At 2.5, in 2035:

| Scenario | Balance, 2.0 rule | Balance, cut unwinds | Posts short, 2.0 rule | Posts short, cut unwinds |
|---|---|---|---|---|
| Reference reform | +369 | +173 | 4,101 | 3,576 |
| Reference, lawful (pensions paid, agreements kept) | +1 | −242 | 5,339 | 3,497 |
| The Guide's 350 þús. scenario | +192 | +43 | 4,976 | 3,278 |

Status quo: 1,797 (reference world) and 1,572 (Guide world) posts short. About 150-240 ma.kr. of the published
surplus was paid for by public posts left unfilled.

**Private pay could not clear either.** A profession's offer may sit at most 15% from what it already pays
(`labour.safety_wage_bound`), and contracts move only part of the way at renewal. Doctors, nurses, teachers and
managers sat at the top of that window every year from 2026 to 2035, in the status quo as well as the reform, so
their shortages never closed. The window was put in to stop a ratchet that walked pay down; it also stops pay going
up. Widened to 60% both ways, the shortages close (0-30 posts) but prices end 53-58% above the status quo and the
surplus is inflated with them: with one price index fed by every profession's pay and labour demand that follows
labour supply, nothing anchors the level of pay, only its spread. That run is not a result.

Under 2.0's settings, the spread already moves the way the premise says. By 2035 at 350 þús., against the status quo,
real market pay is +16-21% for cleaners, drivers, machine operators and other elementary work and −6 to −12% for
doctors, nurses, teachers, managers, lawyers and academics. Those results rest on each profession's disamenity and
meaning (`PROFESSION_TRAITS`), which are judgements, not data.

### The market reset, for 2.1

1. **One clearing round at the start.** Every contract, public and private, reopens at once. Each profession's pay is
   found in krónur, from zero up, by a root-find on supply against demand, not by percentage steps: from zero, any
   step is infinite. There is no window, floor or cap. Pay may come out at zero where people would do the work for
   the payment alone.
2. **A nominal anchor.** The central bank's target, or the króna, fixes the price level, so the round sets real and
   relative pay and cannot spiral.
3. **Demand per profession.** Firms' demand for each profession falls with its own unit cost, with an own-wage
   elasticity. Today demand answers only the economy-wide wage cost. The state buys essential services against a
   need-driven demand with a small elasticity. Automation substitutes where work becomes dear.
4. **Supply per person.** A person's reservation pay for each job is set by the payment, the job's disamenity, its
   meaning and the person's skills. That is the channel through which a larger payment strengthens the worker in the
   round, and it should be estimated per profession from working-conditions and job-satisfaction surveys (for
   example the European Working Conditions Survey and the ISSP work orientations module, which covers Iceland), not
   set by judgement.
5. **After the round.** Two rules, compared: pay indexed to prices (the author's proposal), and contract-by-contract
   renewal at the market rate (2.0's free market). The window survives only as a solver safeguard in later years,
   and it is reported whenever it binds.
6. **Prices by sector.** Each sector's price follows its own wage cost, through the input-output table, instead of
   one non-tradable price set by an average wage. Cleaning and care can then get dearer while managed and
   office-based services get cheaper.
7. **What it reports.** Pay by profession before and after the round, at payments of 200 to 500 þús. Who still
   works, and which work is done whatever the pay. Manager pay against the pay of the work managers organise. Unpaid
   care and household work alongside paid work.

### The shocks

The events on the long-view page are multipliers on a few prices and flows, ramped in. Two problems:

- **The page measures them wrongly.** "How each system takes the shock" compares 2029 with the worst of the next six
  years, so trend growth hides the shock. The comparison should be each system with the shock against the same system
  without it, and the charts should be able to show that difference.
- **AMOC is badly undersized.** Over ten years it removes 2% of output per worker, 30% of fish earnings and 20% of
  tourism, and adds 10% to import prices. Among the channels it leaves out are:
  - farming;
  - sea ice in harbours and on the fishing grounds (as in the hafís years of 1965-71);
  - hydropower and the smelters it feeds;
  - infrastructure and heating outside the geothermal areas;
  - recession in the trading partners, who are hit harder.

  It needs its own study, or at least a range from mild to severe.

The other shocks are sized on historical episodes (1967-69, 2008-10, 2020-22) and are more defensible, though each
still moves only a few channels.

**Done for 2.1:**

* **The table now compares each system with and without the shock.** It sets each system with the shock against
  the same system without it, at the largest gap in the six years from the onset. The runs without a shock were
  already in the timeline data.
* **AMOC is resized as the 1967-69 crisis made permanent.** Over the decade of the collapse:
  * fish earnings fall by half;
  * tourism falls by a third;
  * aluminium falls by 10%, as the rivers feed the power stations less;
  * trading partners' demand falls by 4%;
  * imports cost 15% more;
  * output per worker falls by 5%;
  * half as many people arrive, and half as many again leave.

  No economic study exists for Iceland. A spatial assessment model (Cruz et al. 2026) puts Scandinavia among the
  larger GDP losers. The first sizing stays on the page as "AMOC collapse, mild" so the two can be compared.

### The haggling round, first build (2026-10-30)

`policy.wage_reset` (off by default) runs the round in the reform's first year:
- every contract reopens and everyone decides again whether to work;
- each profession's pay is searched between 2% and 1,000% of what it paid, starting from half;
- public pay is set at market pay, with no cut and no premium;
- afterwards, pay follows the market (`wage_after_reset: "market"`) or prices alone (`"indexed"`, where the first
  year after the round follows the central bank's target rather than the round's own price jump).

At 350 þús., in 2035, the round inverts the pay structure. Under indexation, cooks, waiters, clerks and retail
workers are paid about five times their status-quo real pay, with 7-20 people for each post. Engineers, lawyers,
managers and academics are paid about 30% less, with 3-6 posts for each person. Unemployment reaches 36%.

The cause is that within the round people decide only whether to work in their own profession. Moving between
professions happens afterwards, slowly, and in response to pay alone. The round needs one choice of profession
and of whether to work, priced by pay, meaning and unpleasantness and limited by training (docs/JOB_TRAITS.md).
Until then the round is a mechanism under construction and gives no results.

Since then (docs/JOB_TRAITS.md): the round has a choice of profession; it is held before the first year, in a
space without time; the state leaves posts unfilled rather than pay any price; work gets lighter where posts
fill; and the sweeps of pay and choice now settle, which the quality check requires.
