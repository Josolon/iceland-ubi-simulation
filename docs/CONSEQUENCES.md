# What would happen next: the haggling round's results, one at a time

The haggling round (policy.wage_reset, docs/JOB_TRAITS.md) sets each profession's pay at what it takes to fill it
once the payment lets anyone refuse a job. Each result it gives raises the question of what people and firms would
then do. People do not stop going to restaurants because nobody wants to wait tables for someone else; other forms
of the same service grow in its place. This note takes the round's results one at a time and says, for each, what the
model already does about it, what it lacks, and what has been added.

All figures are the Guide's 350 þús. settings with the commercial ownership cap, in the round and the first year
(model runs, 2026-10-30).

## 1. The round priced labour at today's spending

**Result.** The round cleared every profession within 1%, and the first year then fell short by 26-31% of the
work in restaurants and shops. Waiters: 413 full-time posts in the round, 602 asked for after the first year.

**Why.** The round has no time, so it priced labour against how much of their income households spent before the
reform. Under the reform they spend 46% more per króna of labour income: the payment goes largely to people who spend
most of what they get, and labour income falls. Demand for the work households buy follows that spending.

**Added.** Each sweep of the round now works out the spending its own choices would bring (one draw of the choices,
under a fixed seed, through the same household accounts the year uses), and labour demand reads that. The round now
clears waiters at 539 posts and the first year's shortfall in restaurants and shops is 4-12%.

## 2. The first year's prices ate the round's pay

**Result.** Prices rose 9-12% in the first year while the round's contracts were fixed in krónur.

**Why.** The round's pay rises are passed to prices over time, not at once (the price block's partial adjustment),
and the first year adds its trend inflation and the shortage's.

**Added.** The round's settlement is in real terms (labour.round_real_settlement). Its contracts follow prices
from the round to the end of the first year in place of that year's scheduled raise, at the price level expected
at the year's start; what prices did beyond that is made good from the second year, as the review clauses
(forsenduákvæði) of Icelandic agreements do.

**Still open.** Prices in the first year run past what was expected at its start, so real pay in the first year
is a few percent below the round's. Professionals and managers end the first year about a tenth short of the
round's staffing.

## 3. Employers in the consumer trades are priced out

**Result.** Restaurant, shop and cleaning employers whose staff cost more sell less: their margins are thin
(gross operating surplus 18% of labour cost in restaurants and bars).

**The model had** owner-run firms as a generic venture, not tied to any trade, which did not take up the
customers employers dropped.

**Added: the owner-run form** (ownrun.py). In the trades where it is common today, part of the work is done on own
account, and the share rises as employers are priced out. An owner's hour costs the customer less than an
employer's hour of the same pay, by the owner's return that an absentee owner used to take, so the trade's demand
for work falls less than employers' alone would. Work without a boss counts as less strain.
- Today's shares: Eurostat's labour-force survey for Iceland, 2022-24, by occupation. Service and sales workers
  5.6%, elementary 5.7%, machine operators and drivers 16.9%, craft workers 21.6%.
- Margins: Eurostat's business statistics for Iceland, 2023-24, gross operating surplus over labour cost.
  Restaurants and bars 0.18, retail and personal services 0.39, cleaning 0.23, land transport 0.52, construction
  0.53.
- Half the surplus is taken as the owner's return over capital costs; the share can rise to at most 40%, about
  where these trades stand in Greece and Italy. Both are estimates.

In the first year at 350 þús., about 2,700 more people work on their own account in these trades than today's
shares give. Cooks working for themselves rise from 5.6% to 10.9%, shop and personal-service workers to 11.8%.

**The headline count.** Everyone working for themselves, as the labour survey counts them, is now on the pages'
headline strip against the status quo: own account in a trade, running a firm, or in self-directed work.

## 4. Rents on the high street

**Result.** Rent is about a tenth of a restaurant's takings and a fifth of its value added, so it is a larger
share of an owner's margin than of the takings. Laugavegur, Hverfisgata, Bankastræti and Austurstræti are owned by
few, at a markup.

**The model had** the cap on owning commercial space adding 10% more firm starts in general, and a variety bonus.

**Added.** Cheaper commercial space now widens the owner-run margin by rent's share of value added times the fall
in rent, and raises the share who can make a go of it by as much. Rent's share is an estimate for restaurants and
shops (0.22 of value added) and small for cleaning, driving and crafts.

## 5. Arrivals take the jobs whose pay rose most

**Result.** Arrivals follow unfilled posts and rising pay, and non-EEA arrivals wait five years for the payment, so
they take jobs residents leave. In the first year they flow most to the professions the round raised most: cleaners,
refuse collectors and other elementary work end it 30-45% over-supplied.

**The model has** this channel. The next years' pay brings these professions down again.

**Measured over ten years** (the reference reform at 300 þús., a model run against the status quo, 2026-11-04; the
six trades of the owner-run form: cooks, waiters, retail and service, cleaners, drivers and crafts; people in work).
- By 2035, 7,570 fewer residents work in these trades than in the status quo: 35,264 against 42,834.
- 2,820 more people who arrived after 2025 work in them: 20,564, 36.8% of the trades' workers, against 17,744, or
  29.3%, in the status quo. Across all work the share is 28.7% against 22.1%.
- Arrivals therefore fill a little over a third of the work residents leave. The rest is not missed: the trades sell
  less at their higher prices, and part of the work moves to owners' hands at a lower price per hour.
- The trades are short of hands by 1.3% in the first year and 2.2% at most, in 2030. In 2035 the shortfall is
  0.2%, against none in the status quo.

Most of the work residents leave in these trades is not done by anyone else. Households buy less of it, which the
model counts as a cost in what incomes buy.

## 6. The state leaves teaching posts unsought

**Result.** At 350 þús. the state leaves about 700 teaching posts unsought rather than pay what filling them takes.

**What would follow:** larger classes, private schools or parents' cooperatives, or pressure on the state to pay
more at the next round. **None of these is in the model.** The posts count as unfilled, and the service the
pupils do not get as unmet.

## 7. Managers fewer, firms flatter

**Result.** Managers are a quarter fewer at today's pay.

**What would follow:** flatter firms, and owners running more themselves. The owner-run form covers part of it in
the consumer trades; elsewhere it is not modelled.

## 8. Cleaners: more people at more pay

**Result.** Cleaners get a fifth more people at a fifth more pay.

**What would follow:** households buying less cleaning and doing more of it themselves. **Home production is not
in the model** beyond the family care it already counts.

## 9. Fewer hours, higher prices

**Result.** Hours fall 18% and prices rise.

**The model has** this feedback: prices enter the next year's choices and pay.
