# v8: the fisheries from the quota system's start, and a counterfactual past with its own levers

Research notes behind the fisheries history built in v8 (`scripts/fisheries_history.py`), written 2026-10-03.

## The question

What would have happened if a larger share of the fisheries' resource rent had been paid out to every resident from
the start of the quota system?

The model must carry the costs as well: any harm a higher take might have done to investment, quota prices and the
industry's debt. On the page, the counterfactual past comes with levers of its own.

## Timeline of the system

* **1984:** vessel quotas in the demersal fisheries.
* **1990:** the Fisheries Management Act made individual quotas transferable from 1991. Herring had been under
  quotas from 1979 and capelin from 1984.
* **The fee:**
  * 2002-03: management-cost fees only.
  * 2004: a fishing fee on top.
  * 2007-08: the fee suspended for cod when the cod quota was cut.
  * 2012: a special fee added.
  * 2018: the fee law reset (nr. 145/2018), at 33% of the fishing profit.
  * 2025: the basis revised.

## What the data say

**Profitability.** Rent here is profit after a normal return on capital. Hagstofa's "annuity approach" net profit
is after a 6% imputed cost of capital.

| Years | Fishing and processing, net profit after the capital cost, % of revenue | Source |
|---|---|---|
| 1980-1990 | losses of 1-9% of revenue every year | Althingi 121/s/1175 (Þjóðhagsstofnun figures) |
| 1990-1996 | gross share of capital 17-21%; net about 2-4% (1993-96) | Icelandic Fisheries in Figures 2008; SJA08107 |
| 1997-2000 | about −1.4 to +3.3% | SJA08107 |
| 2001-2007 | 6-18% | SJA08107 |
| 2008-2023 | 14-26% | SJA08107 |
| 2024 | 16% | SJA08107 |

**Rent in krónur** (fishing's net profit after the capital cost plus processing's net profit, SJA08101/08103,
nominal):
* 0-22 ma.kr. a year in 1997-2007;
* 32-60 ma.kr. in 2008-16;
* 13-85 ma.kr. in 2017-24, with 85 in 2022.

This is after the fees actually paid, so the fees are added back for the counterfactual base.

**Marine exports** (SJA04902), 1984-98: 16 ma.kr. in 1984, 72 in 1990 and 102 in 1998, nominal. They give the
revenue base before 1997.

**Fees paid:**
* 2002-14 calendar years: the general fee in Althingi 144/s/1558 — 0.2-0.8 ma.kr. a year to 2006, 1.0-4.9 in
  2009-14.
* From 2012: the central government's "1415 Rent" line (THJ05232), which includes the special fee — 14.3 ma.kr. in
  2012, 7.8-26.5 since.
* That line includes some other rents, so it is an upper bound in earlier years.
* Checks: 2014 about 52 m EUR, 6% of catch value (Gunnlaugsson et al. 2018); 2023 10 ma.kr. collected.

**Where the rent went.** For 2008-17, rent averaged about 380 m USD a year, roughly 17% of fishery exports
(Agnarsson et al. 2020). Of it:
* about 20% went to the public, through fees and corporate tax;
* about 40% to quota sellers, mostly those first allocated the quota;
* about 40% to the active firms.

**Quota and debt.**
* Rising quota prices were financed by borrowing, mostly in foreign currency.
* The sector's net debt went from about 300 to 500 ma.kr. within 2008, and was 465 at the year's end.
* Net debt rose from 3.7 times EBITDA in 2001 to 9.8 in 2008.
* About 90% of the debt was in foreign currency when the króna fell.

**The market's own price** for a year's quota: the cod lease price was about 233 kr/kg in 2014/15 and 482 kr/kg in
October 2023 (Fiskistofa's exchange market). These are marginal prices, so they bound the average rent from above.

## Design

1. **A history layer, 1984-2015** (`scripts/fisheries_history.py`, accounting, not agents). Every year:
   * **Revenue:**
     * marine exports before 1997;
     * Hagstofa's accounts after.
   * **The rent:**
     * the net-profit margin times revenue, plus the fees actually paid;
     * 1984-1989 at the recorded losses — negative, so nothing to share;
     * 1990-92 from the gross share of capital.
   * **The levers act on that rent.**
     * The start year: 1984 or 1991.
     * The share captured, 0-100%.
     * What is done with it: paid out each year, held in a fund paying a share each year, or a mix.
   * **The fishery's response — "might"** (EST, a range, never a point):
     * **Rent base.** A tax on pure rent changes no decision in theory. In practice a higher take can slow
       consolidation and investment: the rent base grows less by `η × capture`, with η from 0 to about 0.2.
     * **Fleet renewal.** The 2012 fee was followed by heavy fleet renewal in 2015-20, which argues for the low end.
     * **Quota prices.** They capitalise expected rent, so a high take lowers them. Less is borrowed to buy quota, the
       sector's debt and 2008 currency exposure shrink, and the rent that went to those selling quota (about 40%) is
       not drained.
   * **Output:** the dividend per adult each year in 2025 krónur, the fund's assets, and the industry's profit
     after the take.
   * **Data still needed:** the CPI, population 18+ and GDP back to 1980 (fetched: VIS01005, MAN00101,
     THJ01401).
2. **The agent model from 2015** (the existing counterfactual past, `counterfactual_past.py`). The fisheries history
   enters as:
   * the fund's assets at 2015, which earn the sovereign fund's return;
   * the yearly dividend, as a payment to every adult on top of today's system (the "borgaralaun alone" variant);
   * the rent captured from 2016 (`fisheries.rent_capture`).

   The other past levers: the reform from 2016 (its amount and main financing), and COVID answered as it was or
   by shielding.
3. **A past surface:** a fitted surface over ~600 such 2016-2025 runs, about 2 hours, with its own lever panel on
   the page behind a switch ("The past, had…"). The record is always drawn beside it.

## What can be said already

At Hagstofa's rent measure, a dividend from the quota system's start would have paid almost nothing until the
2000s and little before 2008, because the industry made losses through the 1980s and thin margins in the 1990s.
After 2008, a full capture would have been 35-85 ma.kr. a year: roughly 10-25 þús. a month per adult. A fund
started in 1991 would have reached a sizeable share of GDP by 2025 and paid on that scale indefinitely.

The largest rents appear in the 2010s and 2020s, and in what quota sellers took out of the industry, which a
higher take would have reduced.

## Sources

* Agnarsson, Gunnlaugsson, Sævaldsson, Kristófersson (2020). Resource rent and its distribution in Iceland's
  fisheries. *Marine Resource Economics* 35(2): 113-135. doi:10.1086/708507
* Gunnlaugsson, Kristófersson, Agnarsson (2018). Fishing for a fee: resource rent taxation in Iceland's fisheries.
  *Ocean & Coastal Management* 163: 141-150. doi:10.1016/j.ocecoaman.2018.06.001
* Gunnlaugsson (2021). Icelandic fisheries: profitability, resource rent, rent taxation and development. PhD thesis,
  University of Iceland.
* Arnason (2008). Rents and rents drain in the Icelandic cod fishery. In *The Rent Drain*, World Bank / FAO.
* Hagstofa Íslands: SJA08101, SJA08103, SJA08104, SJA08107, SJA04902, SJA09005, THJ05132, THJ05232, VIS01005,
  MAN00101, THJ01401.
* Ministry of Fisheries and Agriculture (2008). *Icelandic Fisheries in Figures*, "Financial performance".
* Althingi: 121/s/1175 (1980s losses), 144/s/1558 (fees 2002-14), 156/s/0434 (2025 fee bill).
* Fiskistofa: quota exchange-market prices.
