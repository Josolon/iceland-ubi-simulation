"""Fit a surrogate of the whole model, so the explorer can have continuous levers.

    .venv/bin/python scripts/build_emulator.py --draws 1200 --years 10
    .venv/bin/python scripts/build_emulator.py --refit        # refit the saved runs: minutes, no simulation

The problem: a run takes minutes, and there are thirty-odd levers. Precomputing every combination is impossible
and precomputing a few stops per lever gives coarse switches that cannot represent an interaction.

The approach: sample the lever space, run the model at each design point, and fit each output in each year.

  * The design is a Latin hypercube, the best of a few hundred by how little its columns correlate, because a
    regression cannot separate two levers that happened to be sampled together.
  * The surface is a quadratic in the levers centred on the middle of their range, every lever crossed with the
    borgaralaun, and — per output — the pairs among the levers that matter most to it. Pure budget lines enter
    only linearly. Columns are standardised and the ridge penalty is chosen by cross-validation, not fixed.
  * Where it measurably helps, a smooth correction is laid over what the quadratic misses: a Gaussian kernel over
    the runs, on the levers that matter to that output. Kept only if cross-validation says it predicts better.
  * Four outputs are mostly year-to-year noise (births, the income spread, income volatility). They are fitted
    as three-year averages, and the page says so.
  * Four are not fitted at all. The value a finite ownership term leaves, the upkeep it costs, and the spend and
    jobs of the infrastructure programmes follow from the levers by formula. The formula is checked against every
    run, and used only if it matches every one.

What this costs in honesty: a surrogate is an approximation. Five-fold cross-validated R² of the whole procedure is
shipped for every output and year, so the page can show how well the fit holds and refuse the ones that do not.

The raw runs are saved as they come in, so a crash costs only the runs since the last checkpoint, and refitting —
another basis, another penalty — costs minutes instead of a night.

Writes artifacts/explorer_v3/emulator.js, and the pay of each profession, fitted the same way, to
emulator_pay.js beside it (one file would pass the 16 MB a published file may be).

v3: AI is part of the world, like world prices — each status-quo run has the same pace of AI as the runs that use
it as their reference, so what AI does is no longer booked to the reform. The energy-and-transport subsidies are
three levers; health follows the Danish model; the internet is paid as infrastructure; the state's stake in new
firms is its own lever; teenagers can move out on their own borgaralaun; farm support can fund start-ups.
"""
import argparse
import json
import os
import pathlib
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

from ubisim.abm import model, params  # noqa: E402
from build_explorer_data import METRICS, calibrated  # noqa: E402

OUT = ROOT / "artifacts/explorer_v3/emulator.js"

# Each lever, the span it is sampled over, and where it is written into the parameter tree. The label and note
# travel with it so the page can explain itself.
LEVERS = [
    ("ubi", "Borgaralaun", "þús. kr./mán.", 0, 800, "policy.ubi_adult", 1000,
     "Paid to every resident each month, the same again for each child, most of a child's share going into "
     "their start-of-life fund. Everything else on this page is read against it."),
    ("vat", "VAT", "%", 15, 32, "policy.vat_platform", .01,
     "One rate on everything. The reform sets 25%; today's mix of 24%, 11% and exemptions averages about 18%."),
    ("income_tax", "Income tax rates", "%", 70, 140, "policy.platform_income_tax_scale", .01,
     "The three bracket rates, moved together. Today they are 31.49, 37.99 and 46.29%, on monthly income above "
     "0, 498,122 and 1,398,450 krónur."),
    ("prop_tax", "Property tax", "% of value", 0, 400, "policy.prop_tax_extra_pp", .01,
     "The yearly tax as a share of a property's assessed value. Today's effective rate is 0.59%, which raises "
     "102.8 ma.kr. Owners pay it out of their income, and it capitalises into prices, so houses get cheaper as "
     "it rises."),
    ("corporate_tax", "Corporate tax", "%", 10, 35, "policy.corporate_tax_rate", .01,
     "On company profits, 20% today. It also reaches the income the model attributes to machines."),
    ("wealth_tax", "Net wealth tax", "%", 0, 200, "policy.net_wealth_tax_pct", .01,
     "On household net wealth above 100 m ISK. Iceland has none. Avoidance and emigration keep its yield below a static estimate."),
    ("minimum_wage", "Minimum wage", "þús. kr./mán.", 0, 700, "policy.minimum_wage", 1000,
     "A statutory floor. Iceland has none — the floor comes from collective agreements, around 425 þús."),
    ("hours", "Standard week", "hours", 75, 100, "policy.full_time_hours_factor", .01,
     "The full-time week, about 36 hours actually worked today (40 paid, breaks included); pay follows hours. FTE is measured in 2025 weeks, so shortening the week "
     "lowers FTE per adult by design; read hours per adult instead."),
    ("child_invested", "Child payment held in their fund", "%", 20, 90, "policy.child_invested_flat", .01,
     "The share of each child's payment that goes into their start-of-life fund instead of to the household, "
     "the same for every child and with nothing taken back however many children there are. How births "
     "respond is shown on the Children tab."),
    ("indexation", "Take indexation out of household loans", "% indexed", 0, 100, "policy.indexation_phaseout", .01,
     "Phases out CPI indexation of mortgages and consumer loans over five years, as the government plans to begin "
     "doing from 2026-27. Two in three mortgages are indexed today. A non-indexed loan pays inflation in cash, so "
     "payments rise when inflation is high, debt is paid down faster, and interest rates reach spending sooner — "
     "the stated reason for the change; its size is an estimate. Government bonds and pension assets stay indexed."),
    ("taper", "UBI withdrawal rate", "%", 0, 60, "policy.ubi_taper_rate", .01,
     "Withdraws the borgaralaun above 600 þús. of earnings, turning it into a negative income tax. Cheaper, but "
     "it raises the effective marginal rate on the people it is taken from."),
    ("payroll_cut", "Fewer public-sector jobs", "% of public jobs", 0, 40, "policy.public_payroll_cut", .01,
     "Removes this share of public-sector jobs; those who stay are paid as before, and the borgaralaun is not "
     "deducted from anyone's public pay. The public wage bill was 709.6 ma.kr. in 2025."),
    ("transition", "Years the reform takes", "years", 1, 6, "policy.transition_years", 1,
     "The payment and the new taxes start on the first day. Fewer public jobs and the folding-in of the pension "
     "funds advance evenly over these years, and anyone today's system pays a benefit keeps the part of their loss "
     "not yet phased in. A 20% cut to public jobs takes about three years at the public sector's yearly turnover. "
     "At 1 everything happens at once."),
    ("childcare", "Extra childcare places", "places", 0, 8000, "policy.childcare_places_added", 1,
     "Beyond today's roughly 19,000 full-day places, which already leave a waiting list in Reykjavík."),
    ("housing", "State-built dwellings", "per year", 0, 3000, "policy.public_dwellings_per_year", 1,
     "Built regardless of price. About 165,000 dwellings exist and the market adds roughly 1.1% a year."),
    ("retraining", "Retraining", "ma.kr./yr", 0, 40, "policy.retraining_bn_per_year", 1,
     "Speeds movement between professions."),
    ("fund", "Surplus into a fund", "%", 0, 100, "policy.sovereign_fund_share", .01,
     "Share of any surplus put aside at a real return rather than used to repay debt."),
    ("fx", "Pension funds hold the króna", "ma.kr./yr", 0, 300, "policy.pension_fx_support_bn", 1,
     "Foreign assets sold to finance imports. It works, but the fund shrinks and so does what it pays the UBI."),
    ("culture", "Culture support cut", "%", 0, 100, "policy.culture_support_cut", .01,
     "How much state support for the arts is withdrawn, leaving the rest to ticket sales."),
    ("ai", "AI progress", "%/yr", 0, 25, "automation.ai_progress_rate", .01,
     "How fast machines get cheaper and abler. Take-up still depends on what labour costs, so dearer labour "
     "automates faster."),
    ("clawback", "Levy on machine income", "%", 0, 50, "automation.levy_rate", .01,
     "Taken from the income attributed to machines, on top of corporate tax."),
    ("robot_stake", "State ownership of automation capital", "%", 0, 100, "automation.state_capital_share", .01,
     "The state's share in the machines that replace work, taken as dividends after corporate tax and any levy. "
     "With AI fast and the stake large, the machines' earnings become the public's: one proposed route to "
     "a large payment. The stake is bought at a fair price with borrowed money, so what the state gains is the "
     "return on the capital above what the borrowing costs, not the machines' whole income."),
    ("frontier", "Frontier programmes", "% of their size", 0, 100, "frontier.scale", .01,
     "Five state ventures on cheap power: indoor farming, cultivated protein, autonomous fishing, factory-built "
     "housing, carbon storage."),
    ("infrastructure", "Infrastructure", "% of their size", 0, 100, "infrastructure.scale", .01,
     "Light rail, a Keflavík link, countryside tunnels, a ring railway. They pay back in travel time as "
     "productivity. Ordinary road building is excluded: it continues either way."),
    ("windfall", "A resource windfall", "ma.kr./yr of rent", 0, 1000, "windfall.rent_bn", 1,
     "Oil, gas or minerals found and brought on stream within four years, reaching this rent a year after five "
     "more; the state takes 78% as Norway does. 500 ma.kr. is about Norway's scale at its height, a tenth of "
     "GDP. A what-if: Iceland's one search, the Dreki area, was given up in 2018. The world is the same with or "
     "without the reform, so the status quo gets it too."),
    ("tourism_price", "What tourism earns", "% of 2025", 60, 140, "trade.price.tourism", .01,
     "Iceland's largest export earner. A collapse and a boom are both within living memory, and neither is "
     "something the country controls. The world is the same with or without the reform, so the status quo "
     "it is compared with moves too."),
    ("marine_price", "Fish prices", "% of 2025", 60, 140, "trade.price.marine", .01,
     "What marine exports earn at world prices, net of general inflation: price and catch together. About a "
     "fifth of exports. The status quo it is compared with moves too."),
    ("aluminium_price", "Aluminium prices", "% of 2025", 60, 140, "trade.price.aluminium", .01,
     "World aluminium prices, which set what the smelter contracts are worth. The status quo it is compared "
     "with moves too."),
    ("import_price", "What imports cost", "% of 2025", 80, 130, "trade.import_price", .01,
     "Fuel, food and goods from abroad, net of partners' general inflation. It sets the price of tradable goods "
     "in the shops, and so the CPI and what wages buy, and the size of the import bill. Together with the three "
     "above this is the terms of trade. The status quo it is compared with moves too."),
    ("resi_cap", "Cap on owning homes to rent", "% of stock, 100 = no cap", 3, 100,
     "policy.residential_ownership_cap", .01,
     "The most any one company or affiliated group may own, as a share of total square metres. The reform "
     "sets 5%. A cap below what the largest owners hold today forces a sale, which adds competitors and "
     "takes the concentration premium out of rents over about four years."),
    ("comm_cap", "Cap on owning commercial space", "% of stock, 100 = no cap", 5, 100,
     "policy.commercial_ownership_cap", .01,
     "The same for commercial property, where concentration is higher. Rent is a fixed cost that decides "
     "whether a small business in Reykjavík is viable at all, so this feeds straight into how many get started."),
    ("dev_exempt", "New construction exempt from the caps", "% exempt", 0, 100, "policy.developer_exemption", .01,
     "Newly built property is exempt from the ownership cap, so the rule bites on buying existing stock rather "
     "than on construction. It cuts both ways and the model carries both: about 18% more building at full "
     "exemption, but the rent effect of the cap falls from -3.6% to -2.6% because concentration can rebuild "
     "through new stock. Which way it nets out depends on how much the extra supply lowers rents."),
    ("custodianship", "Custodianship instead of ownership", "%", 0, 100, "policy.custodianship", .01,
     "Whoever holds an asset — a home, a building, a firm, land, a quota — keeps it, and their heirs after them, "
     "for as long as they keep investing in it and it keeps earning. What is neglected goes back to the market "
     "for others to bid on. In the model: the housing stock wears "
     "out more slowly, empty and derelict dwellings return to use, output rises as neglected firms and assets "
     "change hands, prices carry a small risk discount, and the assessments cost money. Every size is an "
     "estimate: no country runs this for all property, and it would face Article 72 of the constitution."),
    ("sick_pay", "State stops paying sick leave", "ma.kr./yr", 0, 100, "policy.public_sick_pay_cut", .01,
     "The state stops carrying sick pay for its own employees and private insurance takes the risk. Worth "
     "about 39 ma.kr. a year. Not free: whoever falls "
     "ill without cover loses income, and the model carries that into health and wellbeing."),
    ("ubi_index", "The payment follows prices", "% of inflation", 0, 100, "policy.ubi_indexation", .01,
     "The borgaralaun is raised each year by this share of the price rise. At 100 it keeps its value; at 0 it is "
     "fixed in krónur and inflation wears it away, which is how child benefit and the tax thresholds lost their "
     "value in the past. Nothing else on this page can express letting the payment slip."),
    ("ubi_wage", "The payment also follows pay", "% of real wage growth", 0, 100, "policy.ubi_wage_indexation", .01,
     "On top of prices, the payment rises with this share of the growth in real wages — the rule today's "
     "pensions and benefits follow (about 80%). At 0 it keeps its value in goods but falls behind the pay "
     "around it: by a third over thirty-five years of ordinary growth, which the long view shows as a budget "
     "surplus."),
    ("security_spend", "Spending answers a guaranteed income", "% more spent", 0, 25, "wealth.security_mpc_gain", .01,
     "How much more of their income people spend once it is guaranteed rather than merely large. Saving against "
     "a bad year is saving against risk, not against poverty, so an income that cannot fall away is expected to be "
     "spent more freely. The direction is well evidenced (Carroll 1997; Carroll and Samwick 1998); the size for a "
     "permanent floor is not, so it is a lever and 0 switches the channel off."),
    ("prof_moves", "People change profession", "% a year", 0, 10, "labour.occupation_mobility", .01,
     "Workers who move to another profession in a year, following how its pay has moved against the base year "
     "and how many of its posts stand empty, within the education it asks for. At 0 nobody moves, and "
     "shortages can be met only by the hours of people already "
     "in the job. It applies to the status quo as well, so both sides are run with the same behaviour."),
    ("match_gain", "What work that fits is worth", "% more produced", 0, 5, "labour.match_quality_gain", .01,
     "What someone who moves to work that suits them better produces afterwards, for good. This is the channel "
     "behind the hypothesis that better matching of people to work raises output; its size is an estimate."),
    ("benefit_floor", "Pension top-up to today's level", "% of the gap", 0, 100,
     "policy.benefit_floor_topup", .01,
     "Today's disability pension is about 430 þús. before tax, some 370 net — more than a 300 þús. payment — and "
     "a full Tryggingastofnun pension is a little more too. At 100 the state tops up anyone on either to what "
     "today's system would pay them on the same earnings, untaxed like the payment, withdrawn as earnings rise "
     "as today's pensions are. At 0 the reform is as specified, and these are the people whose income falls."),
    ("net_indexation", "Agreements compensate prices net of the tax switch", "%", 0, 100,
     "policy.indexation_net_of_tax", .01,
     "Where collective agreements survive, they compensate price rises. The VAT that pays for the borgaralaun "
     "lifts prices once; if agreements compensate that too, pay chases it and prices rise again. At 100 the "
     "parties compensate prices net of the tax switch, as Denmark's agreements use the net price index "
     "(nettoprisindeks). The micro-macro study of a basic income for Scotland (Connolly et al. 2021) found this social contract decides more than any "
     "other single response whether the tax rise feeds a wage-price spiral."),
    ("birth_timing", "Births earlier in life", "years earlier", 0, 3, "demography.birth_timing_shift", 1,
     "How many years earlier births come when a secure income lets people study and raise a small child at the "
     "same time, at a 300 þús. payment and in proportion to it. A birth before a career costs a mother less of "
     "her later pay than one early in it (Herr 2011; Bach et al. 2025), but a baby slows a course (student mothers "
     "drop out more often), and a birth early in a career costs more than a later one (Miller 2011). The model "
     "carries all three, measured against today's timing; the size of the shift is an estimate and 0 switches "
     "it off."),
    ("staked_tax", "Corporate tax where the state holds a stake", "% of the normal tax", 0, 100,
     "policy.staked_corporate_tax_share", .01,
     "Every company that raises capital, old or new, is deemed to have taken one start-of-life fund from the "
     "public, which has paid for its founders' and investors' schooling, health care and payment — so the "
     "state holds shares worth one fund in each round. That is the premise of a corporate tax, held as "
     "ownership. At 0 the stake replaces the tax for the firms that carry one; at 100 they pay both."),
    ("leave_scheme", "Sick pay and parental leave to employers", "%", 0, 100, "policy.state_leave_ended", .01,
     "The state's sick pay and the parental leave fund end, because the borgaralaun is already the floor. "
     "Employers carry the period law and agreements give them, rising with seniority, and insure the rest, as "
     "occupational pensions are insured now. Nobody may be dismissed for taking leave. The state saves what it "
     "paid; employers pay more on wages, which the model charges against hiring."),
    ("leave_top_up", "What leave pays above the borgaralaun", "% of pay", 0, 100, "policy.leave_top_up", .01,
     "Left to bargaining in the reform, so the model makes an assumption: at 0, 80% of "
     "pay, as parental leave pays today, where agreements survive, and 55% where pay is set job by job. Any "
     "other setting overrides the assumption."),
    ("history_world", "The world as the last decade went", "0-1", 0, 1, "markets.history_like", 1.0,
     "A second status quo for comparison: consumer prices rising 4% a year rather than at the 2.5% target, the "
     "króna drifting a point a year weaker, and rents outrunning incomes by 1.5 points a year — the pattern of "
     "2016-25 rather than the forecasts. It applies to the reform and the status quo alike, because a calm "
     "baseline would favour neither."),
    ("church", "State funding of religious bodies ended", "ma.kr./yr", 0, 100, "policy.church_funding_cut", .01,
     "No religious body funded. Sóknargjöld are collected through the income tax system, so ending them simply "
     "leaves that money with the state — about 7.8 ma.kr. a year in all."),
    ("public_offset", "Public pay held at its old take-home", "%", 0, 100, "policy.public_wage_offset_ubi", .01,
     "A full-time public job pays, after tax and with the borgaralaun, what it paid "
     "before. Pay is cut by the borgaralaun grossed up at the employee's marginal tax rate. It saves payroll and "
     "holds down the wage costs that set prices. A professor who took home 700 þús. is paid 400 þús. and gets the "
     "300 þús. borgaralaun: the same 700. Not working pays the 300 alone, so the job still adds 400 — less than "
     "the 700 it added before, which is the change the model weighs."),
    ("customs", "Customs duties", "% of today", 0, 100, "policy.customs_kept", .01,
     "Tollar: 7.7 ma.kr. in 2025. The reform abolishes them, which lowers the price of imported goods in the "
     "shops and costs the treasury what they raised."),
    ("agri_cut", "Farm support cut", "% of 19.7 ma.kr.", 0, 100, "policy.agriculture_subsidy_cut", .01,
     "Búvörusamningar and other farm support, 19.7 ma.kr. (2024). The reform redirects support towards "
     "innovation rather than at established production. Cutting it saves the money, costs farm jobs and makes "
     "domestic food a little dearer."),
    ("sub_innovation", "Innovation and film subsidies cut", "% of 21.7 ma.kr.", 0, 100,
     "policy.subsidy_cut_innovation", .01,
     "R&D tax credits paid out to innovation firms (11.1 ma.kr. in 2024, Rannís), film reimbursements (about "
     "6) and R&D grants. The model counts the saving only; that firms would do less research and fewer films "
     "would be made in Iceland without them is not modelled."),
    ("sub_heating", "Rural heating support cut", "% of 4.5 ma.kr.", 0, 100, "policy.subsidy_cut_heating", .01,
     "Niðurgreiðsla húshitunar: homes without geothermal heat — about 9% of people, in the Westfjords, the East, "
     "the islands and parts of the North — heat with electricity or oil and are paid part of the difference. "
     "Cutting it saves 4.5 ma.kr. and puts the whole of it on those homes' heating bills, about 25 þús. a month "
     "each, not on everyone's prices."),
    ("sub_transition", "Energy-transition grants cut", "% of 7.2 ma.kr.", 0, 100, "policy.subsidy_cut_transition", .01,
     "Electric-car purchase grants and Orkusjóður's transition grants. Cutting them slows the switch from petrol "
     "in places without a charging network or cheap clean power first: by the tenth year about 0.12 Mt more CO2 "
     "a year from road transport, and some 4 ma.kr. more fuel imported."),
    ("sub_transport", "Bus and regional route support cut", "% of 6.0 ma.kr.", 0, 100, "policy.subsidy_cut_transport", .01,
     "The state's part of Strætó and the regional bus and ferry routes. Cutting it raises fares or closes routes: "
     "prices up about 0.4%, a little more driving."),
    ("sub_other", "Culture, media, waste and other subsidies cut", "% of 15.9 ma.kr.", 0, 100,
     "policy.subsidy_cut_other", .01,
     "Culture, sport and private media (5.7), waste handling (4.7), education (1.6), labour-market and "
     "business support (3.0), tourism (0.8). The saving only."),
    ("fish_rent", "Fisheries resource rent captured", "% of the rent", 0, 100, "fisheries.rent_capture", .01,
     "Quotas as 50-year leases, priced to capture the profit fishing makes above a normal return on capital — "
     "72.8 ma.kr. in 2023. Veiðigjald takes about 24% of it today (17.3 ma.kr. in 2026); the reform 80%."),
    ("vat_input", "VAT refunds only on value-chain inputs", "% of the full restriction", 0, 100,
     "policy.vat_input_restriction_gain", 4.595,
     "Input VAT reclaimable only on what goes into the product: the carpenter's lumber, not the saw. In full it "
     "raises 459.5 ma.kr. a year net of dearer government purchases and corporate tax (from the 997 ma.kr. firms "
     "reclaimed in 2025; range 385-574), and exporters bear about 135 ma.kr. of it. Applied in part, in proportion."),
    ("pension_return", "Pension-fund returns to the UBI", "% real a year", 0, 5, "policy.pension_fund_real_return", .01,
     "The pension funds, 187% of GDP, pay their real return to the UBI instead of to occupational pensions: "
     "about 93 ma.kr. for each percentage point. 3% is an estimate of the long-run real return."),
    ("personal_credit", "Personal tax credit", "þús. kr./mán.", 0, 72.5, "policy.platform_personal_credit", 1000,
     "Persónuafsláttur, 72.5 þús. a month today. The reform abolishes it, which raises tax on every earner "
     "by up to that amount."),
    ("inherit_rate", "Inheritance tax", "%", 0, 100, "policy.inheritance_tax_rate", .01,
     "10% today above the tax-free amount, with a surviving spouse paying nothing. At 100%, nothing passes "
     "above the tax-free amount. Taxable estates shrink as the rate rises — gifts, trusts, moving abroad."),
    ("gift_tax", "Gift and advance-inheritance tax", "%", 0, 100, "policy.gift_tax_rate", .01,
     "10% today, the same as inheritance. Set below the inheritance rate and estates move into gifts while the "
     "giver is alive; at the inheritance rate that way round is closed."),
    ("exit_tax", "Tax on moving assets abroad", "% of gains", 0, 50, "policy.exit_tax_rate", .01,
     "On the unrealised gains of people who emigrate with more than 50 m kr. in financial wealth, as Norway "
     "(about 38%) and Denmark (27-42%) tax them. Iceland has none. It raises little directly; its point is to "
     "close moving abroad as a way round the inheritance tax."),
    ("enforcement", "Staff moved to tax enforcement", "people", 0, 300, "policy.tax_enforcement_fte", 1,
     "A borgaralaun needs no one to check who is entitled to unemployment or other benefits. Those staff can "
     "work on tax enforcement instead, against evasion put at 80-100 ma.kr. a year in 2014, about 4% of GDP. Each investigator "
     "recovers less than the one before; they also narrow the ways round the inheritance tax."),
    ("prison_ubi", "Borgaralaun withheld in prison", "% of prison time", 0, 100, "policy.prison_ubi_withheld", .01,
     "Today benefits stop after four months in prison, about 60% of prison time. A prison day costs the state "
     "56,750 kr. The saving is small, and the evidence is that the certainty of being "
     "caught deters more than the severity of the sentence (Nagin 2013)."),
    ("ubi_protected", "Borgaralaun cannot back a loan", "%", 0, 100, "policy.ubi_protected", .01,
     "The payment cannot be pledged, assigned or seized by creditors, as benefits cannot be today, so no lender "
     "can treat it as collateral and people at risk cannot borrow against next month's. Protecting it does this "
     "without taking the payment from the borrower and their family."),
    ("gambling_block", "Payments to foreign gambling sites blocked", "%", 0, 100,
     "policy.gambling_payment_block", .01,
     "About 20 ma.kr. a year goes to foreign betting sites that pay no tax here. Norway blocks the payments "
     "(and, since 2025, the sites); it stops much of it, not all, and part moves to licensed domestic games."),
    ("free_health", "Free health care, GP first (Danish model)", "%", 0, 100, "policy.free_health_care", .01,
     "No charge for seeing a GP or a specialist, outpatient care, tests or physiotherapy — about 15 of the 65 "
     "ma.kr. households pay out of pocket — and a GP referral before a specialist, as in Denmark. Medicines and "
     "adult dental care stay paid, as they are in Denmark. A little more care is used once visits are free; "
     "referral trims specialist use, half of that saving going on extra GP time."),
    ("free_internet", "Internet as infrastructure", "%", 0, 100, "policy.free_internet", .01,
     "The state pays for the network on publicly laid lines and for the international capacity of Farice's "
     "cables — about 5 ma.kr. a year — and the connection is free. Households save the line part of their bill, "
     "about 60% of 13 ma.kr.; the difference is the margin private line owners earned. Companies go on selling "
     "phones, routers, installation and service."),
    ("teen_moveout", "Teenagers living on their own", "% of 16-17-year-olds", 0, 20, "policy.teen_moveout_share", .01,
     "A 16- or 17-year-old who moves out is paid their whole borgaralaun themselves, and nothing more goes into "
     "their fund — which they still get at 25. How many do is a guess: few do today."),
    ("agri_startups", "Farm support to agricultural start-ups", "ma.kr./yr", 0, 5, "agriculture.startup_bn", 1,
     "Part of what farm support cost goes to agricultural start-ups through RANNÍS instead, about 15 m kr. each: "
     "support for new ideas, not for established production. Half survive, with 1.5 jobs each once running."),
    ("residence", "Residence rules for new arrivals", "% strictness", 0, 100, "policy.residence_rules_strictness", .01,
     "Registering residence — and with it the borgaralaun — requires savings or an income, as Austria and "
     "Denmark require of new arrivals; the reform asks for about €30,000. In the model it reduces arrivals "
     "who would not work. EEA workers are eligible while they work, and everyone after five years."),
    ("capital_controls", "Capital controls", "% strictness", 0, 100, "policy.capital_controls", .01,
     "Part of the reform. Controls damp the risk premium a large debt would otherwise "
     "carry, and cost some foreign investment and output, as Iceland's did in 2008-2017."),
    ("inherit_floor", "Tax-free inheritance", "m kr.", 0, 150, "policy.inheritance_tax_floor", 1e6,
     "The part of an estate that passes untaxed, in 2025 krónur: 6.5 m today. Set it at the value of a family "
     "apartment and a family keeps its home whatever the rate."),
    ("smelters", "End smelter power contracts", "% of contracts", 0, 100, "energy.smelter_exit_share", .01,
     "The reform ends the aluminium smelters' power contracts and sells the electricity to data centres, "
     "e-fuels, aquaculture and greenhouses. Compensation, lost exports and jobs in the East and at "
     "Hvalfjörður against the higher price the power fetches."),
    ("pension_fold", "Pension funds folded into the UBI", "%", 0, 100, "policy.pension_fold", .01,
     "The reform turns the pension funds into the UBI's funds: contributions (15.5% of pay) go to the state as "
     "social security, the funds' returns go to the UBI, and occupational pensions stop — with a top-up for "
     "anyone whose pension was worth more than the UBI. At 0, pensions stay as they are and the UBI is paid on "
     "top of them."),
    ("pension_keep", "Earned pensions still paid", "off / on", 0, 1, "policy.pension_keep_earned", 1,
     "With the funds folded in, contributions still go to the state as social security, but the funds go on paying "
     "the pensions already earned, out of their assets: no top-up and no rights cancelled. Those retiring later "
     "have earned only the years before the reform. The funds' returns stay with them."),
    ("prop_defer", "Pensioners defer the extra property tax", "off / on", 0, 1, "policy.defer_pensioner_property_tax", 1,
     "Households with someone 67 or older pay the extra property tax only when the home is sold or inherited. About "
     "29 ma.kr. less cash in the first year. It is still owed: a claim on the home, repaid when it is sold or from "
     "the estate, so the accounts book it as revenue and the claim as lending."),
    ("floor_loan", "Pension top-up as a loan against the home", "off / on", 0, 1, "policy.floor_loan", 1,
     "For pensioners who own their home, the top-up to today's pension (benefit_floor) is a loan secured on the "
     "home, up to half its equity, carrying the state's long real rate and repaid when the home is sold or from the "
     "estate. They keep the home and the income; the state lends rather than spends, and books only what an estate "
     "cannot repay. Nothing changes for renters or for anyone without a top-up."),
    ("venture_stake", "State stake in new firms", "% if funded by the borgaralaun alone", 0, 50,
     "policy.state_venture_stake", .01,
     "The reform treats the state as an investor in its citizens — their upbringing, schooling, health and borgaralaun — and "
     "takes a share of the firms they found. The reform: half of a firm its founder built on the borgaralaun "
     "alone, falling in proportion to outside money (25% at half outside funding, 10% at 80%), never below 5%. No "
     "seed money is paid, and RANNÍS goes on funding ventures. A larger stake earns more and leaves founders "
     "less, so fewer start."),
    ("green_heat", "Local green heat for cold areas", "ma.kr./yr", 0, 3, "policy.green_heat_bn", 1,
     "Grants towards heat pumps, small hydro and wind that households and landowners in the cold areas install "
     "themselves — half of about 3 m kr. a home. A converted home needs 60% less bought heat, so less heating "
     "support, or a smaller bill if the support is cut."),
    ("per_diem", "Per diems abolished", "%", 0, 100, "policy.per_diem_cut", .01,
     "Dagpeningar: companies pay documented travel costs, and nothing is paid tax-free. About 13 ma.kr. a "
     "year, saved where the state pays them and taxed where it does not."),
    ("agreements", "Pay set without collective agreements", "off / on", 0, 1, "policy.wage_setting", 1,
     "In the reform, pay is no longer set by collective agreements (kjarasamningar) but contract by contract, on the premise that a guaranteed income lets anyone "
     "decline an offer. Off, wages follow today's agreements: price compensation and a share of productivity, renewed "
     "together. On, each contract renews at whatever the market for that profession pays."),
    # How people and markets respond: the uncertain elasticities the results lean on most, for sensitivity. Ranges
    # from uncertainty.RANGES. Not policy; the centre is the model's estimate.
    ("s_emigration", "How strongly emigration answers income", "elasticity", .8, 2.0,
     "migration.emigration_income_elasticity", 1,
     "How much more people leave when pay abroad beats pay plus borgaralaun at home. 1.5 is the model's estimate. It applies to the status quo as well, so both sides are run with the same behaviour."),
    ("s_fertility", "How strongly births answer child income", "elasticity", .1, 1.0,
     "demography.fertility_income_elasticity", 1,
     "Births per unit change in usable child income against household income. 0.5 is the estimate; the "
     "evidence runs from 0.1 to 1. It applies to the status quo as well, so both sides are run with the same behaviour."),
    ("s_labour_demand", "How strongly firms' hiring answers wages", "elasticity", .4, 1.2,
     "labour.demand_elasticity", 1,
     "How many fewer people firms employ when wages rise. It decides how far a borgaralaun that raises "
     "reservation wages costs jobs. It applies to the status quo as well, so both sides are run with the same behaviour."),
    ("s_tourism", "How strongly tourists answer prices", "elasticity", .3, 1.5, "links.tourism_price_elasticity", 1,
     "How much less tourists buy when a stay costs more — here, through VAT. It applies to the status quo as well, so both sides are run with the same behaviour."),
    ("s_avoidance", "How hard people avoid taxes on wealth", "× the estimate", .5, 2.0, "links.avoidance_scale", 1,
     "One multiplier on every avoidance response: gifts, moving wealth abroad, trusts and revaluation, under "
     "the inheritance and wealth taxes. It applies to the status quo as well, so both sides are run with the same behaviour."),
    ("s_downsizing", "How strongly older owners move for money", "× the income gap", 0, 6,
     "downsizing.income_gap_response", 1,
     "How much more often a household with room to spare sells and moves to a smaller home the further its income is "
     "below the poverty line: at 3, the estimate, a household 30% below it moves twice as often. Older owners in the "
     "evidence rarely move for money, mostly after a partner's death or ill health, so 0 is plausible too. It "
     "applies to the status quo as well, so both sides are run with the same behaviour."),
    ("governance", "Cuts to governing costs", "ma.kr./yr", 0, 100, "policy.governance_cut", .01,
     "Parliament, þingfararkaup, ministers' pay, party funding, rural travel support, the foreign service and "
     "a smaller presidential office. Worth about 6.5 ma.kr. a year together, small against the payment's "
     "cost. The presidential office alone is 0.4 of that, too little to carry a slider of its own."),
]

# Outputs the surrogate carries. Everything the page shows.
OUTPUTS = [
    "balance", "balance_op", "debt", "net_income", "net_income_sd", "net_income_p10", "net_income_p90", "own_net_income",
    *[f"net_d{i}" for i in range(1, 11)],
    "emp", "fte", "standard_weeks", "weekly_hours", "unemp", "part", "independent", "ventures", "tenure",
    "poverty", "poverty_anchored", "child_poverty", "gini", "p90_p10",
    "cpi", "infl", "fx", "rent", "house", "price_to_income", "ca", "output", "population", "emig", "imm",
    "births", "kids", "child_cost", "fund_assets",
    "income_tax", "vat", "property_tax", "public_payroll", "ubi_cost", "consumption", "sovereign_fund",
    "wellbeing", "struggling", "thriving", "wb_idle", "wb_worker",
    "students", "students_full_time", "tertiary", "graduates", "health", "health_cost", "childhood_poverty",
    "automated", "machine_income", "ptr", "replacement", "housing_burden", "housing_over_40", "real_income_median",
    "service_unmet", "workload", "health_unmet", "teaching_unmet", "shortage_premium", "shortage_pay", "leave_saved",
    "distress", "brain_drain", "essential_gap", "birth_age", "childcare_short",
    "inc_pensioners", "inc_disabled", "inc_students", "inc_out_of_work", "inc_in_work",
    "income_fell_20", "income_fell_40", "income_volatility", "no_buffer", "no_emergency",
    "crime", "crime_cost", "terms_of_trade", "exports", "imports", "emissions", "emissions_vs_2025",
    "schooling_cost", "sick_pay_saved", "commercial_rent", "term_value", "maintenance",
    "inheritance_tax", "fisheries_fee", "variety", "social_security", "pension_topup", "prisoners",
    "hardship", "poverty_gap", "forced_idle", "involuntary_part", "ownership_under35",
    "wb_pensioner", "wb_parent", "kg_gap", "parent_hours",
    "infra_capex", "infra_jobs",
    # v3
    "emissions_transition", "fuel_imports_extra", "heating_bill", "teens_moved_out", "ai_productivity",
    "ai_new_tasks", "state_equity", "green_heat",
    # v10: the housing ladder, older owners' moves, claims on homes
    "pensioner_poverty", *[f"h_size{j}" for j in range(6)], "studio_rent", "crowded", "spare_room", "downsizers",
    "equity_annuity", "claims", "first_homes",
    *[f"pp_{o}" for o in params.OCCUPATIONS],
]


# Where each lever sits when the reform is left as specified, in the lever's own units.
PLATFORM = {
    "ubi": 300, "child_invested": 50, "vat": 25, "income_tax": 100, "prop_tax": 100, "corporate_tax": 20,
    "wealth_tax": 0, "minimum_wage": 0, "hours": 100, "taper": 0, "indexation": 0, "payroll_cut": 10, "transition": 3, "childcare": 0,
    "housing": 0, "retraining": 0, "fund": 0, "fx": 0, "culture": 0, "ai": 0, "clawback": 0, "frontier": 0,
    "infrastructure": 0, "church": 100, "governance": 100, "sick_pay": 0, "resi_cap": 5, "comm_cap": 10,
    "dev_exempt": 100, "custodianship": 0,   # off: the option is not yet specified
    "tourism_price": 100, "marine_price": 100,
    "aluminium_price": 100, "import_price": 100,
    "public_offset": 100, "customs": 0, "agri_cut": 100, "sub_innovation": 0, "sub_heating": 100, "sub_transition": 100,
    "sub_transport": 100, "sub_other": 100, "fish_rent": 50, "vat_input": 100,
    "pension_return": 3.81, "personal_credit": 0, "inherit_rate": 10, "inherit_floor": 6.5, "smelters": 0,
    "pension_fold": 100, "pension_keep": 0, "prop_defer": 0, "floor_loan": 0, "venture_stake": 50, "per_diem": 100, "agreements": 1, "teen_moveout": 5, "agri_startups": 1.5,
    "green_heat": .5, "leave_scheme": 100, "leave_top_up": 0,
    # the reform's own settings (revised 2026-09-21)
    "robot_stake": 0, "windfall": 0, "ubi_wage": 0,
    "history_world": 1, "ubi_index": 100, "security_spend": 10, "prof_moves": 4, "match_gain": 2, "birth_timing": 1, "net_indexation": 0, "benefit_floor": 0,
    "staked_tax": 0,
    "gift_tax": 10, "exit_tax": 0, "enforcement": 100, "prison_ubi": 100, "ubi_protected": 100, "gambling_block": 100,
    "free_health": 100, "free_internet": 0, "residence": 50, "capital_controls": 50,
    # the backcast-tuned values (params.py), not the earlier estimates: until 2026-09-25 the page ran the reform
    # at 1.5 and .75 while its status quo ran at these
    "s_emigration": .825, "s_fertility": .5, "s_labour_demand": .471, "s_tourism": .8, "s_avoidance": 1.0,
    "s_downsizing": 3.0,
}
# Where each lever sits today. With the borgaralaun added and everything else here, the page shows the
# borgaralaun and nothing else; the rest of the reform can then be added one piece at a time. VAT 18 is today's
# effective rate on household spending, the 24%/11% mix; the world prices are not policy and stay where they are.
TODAY = {
    "vat": 18, "income_tax": 100, "prop_tax": 0, "corporate_tax": 20, "wealth_tax": 0, "minimum_wage": 0,
    "hours": 100, "taper": 0, "indexation": 0, "payroll_cut": 0, "childcare": 0, "housing": 0, "retraining": 0,
    "fund": 0, "fx": 0, "culture": 0, "clawback": 0, "frontier": 0, "infrastructure": 0, "church": 0,
    "governance": 0, "sick_pay": 0, "resi_cap": 100, "comm_cap": 100, "dev_exempt": 100, "custodianship": 0,
    "public_offset": 0, "customs": 100, "agri_cut": 0, "sub_innovation": 0, "sub_heating": 0, "sub_transition": 0,
    "sub_transport": 0, "sub_other": 0, "fish_rent": 24, "vat_input": 0,
    "personal_credit": 72.5, "inherit_rate": 10, "inherit_floor": 6.5, "smelters": 0, "pension_fold": 0, "pension_keep": 0, "prop_defer": 0,
    "floor_loan": 0, "venture_stake": 0, "per_diem": 0, "agreements": 0, "teen_moveout": 0, "agri_startups": 0, "green_heat": 0, "gift_tax": 10, "exit_tax": 0, "enforcement": 0,
    "prison_ubi": 60, "ubi_protected": 100, "gambling_block": 0, "free_health": 0, "free_internet": 0,
    "residence": 0, "capital_controls": 0,
}
# On or off: sampled at the two ends only, and fitted with no square.
BINARY = {"agreements", "pension_keep", "prop_defer", "floor_loan"}
KEYS = [l[0] for l in LEVERS]
# Budget lines: they move the accounts by a fixed amount per point and nothing else, so a square or a cross term
# would only fit noise. Three degrees of freedom each, handed back to the levers that need them.
LINEAR_ONLY = {"governance", "church", "sub_other", "pension_return", "per_diem", "prison_ubi", "free_internet"}
# Mostly noise from one year to the next. Fitted — and shown — as the average of the last three years.
SMOOTHED = ("births", "net_income_sd", "p90_p10", "income_volatility")
EXTRA_PAIRS_FROM = 6      # crosses among this many most important levers per output
KERNEL_DIMS = 8           # the kernel correction looks at this many levers per output
KERNEL_GAIN = .01         # cross-validated R² it must add, on average, to be kept
# ... or the share of the cross-validated squared error it removes, on average. An output the polynomial already fits
# to R² .98 could never gain .01, however much the kernel helped: the budget, debt, incomes, hours and prices went
# without one, and at the nine scenarios checked in the model the budget for 2035 was 150 ma.kr. below the model's
# on average; a kernel removes 36% of its error and leaves 30-50 (2026-10-13).
KERNEL_REL_CUT = .10
# v8: the kernel sits on this many of the runs (subset of regressors) rather than on all of them. On v7's 3,400 runs
# it kept cross-validated R² within 0.003 at a third of the page weight (scripts/surface_refit_study.py); its
# weights are more sensitive to rounding, so they are stored at 6 significant figures.
KERNEL_CENTRES = 1200
LAMBDAS = (1e-9, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1)
ELLS = (.15, .25, .4)
NUGGETS = (.1, .3, 1.0, 3.0)
FOLDS = 5
# The world, which the reform does not choose. Runs share a few dozen world-price points, and each point has its
# own status-quo run under the same prices: that run is both the reform's reference path and what the page
# compares it with. A status quo fixed at 2025 prices would book a fall in fish prices to the reform.
# Everything that describes the world rather than the policy, and so must be the same on both sides of the
# comparison: world prices, the pace of AI, the last-decade world — and, since v3.1, how strongly people and
# firms respond (the sensitivity levers) and how often people change profession, which the status quo has too.
# Leaving the sensitivities out ran the reform under one set of behaviours and its status quo under another.
WORLD_PRICES = ("tourism_price", "marine_price", "aluminium_price", "import_price", "ai", "history_world", "windfall")
WORLD = WORLD_PRICES + ("s_emigration", "s_fertility", "s_labour_demand", "s_tourism", "s_avoidance", "s_downsizing",
                         "prof_moves")
WORLD_POINTS = 120

_PO = params.DEFAULTS["property_ownership"]
TERM_RATE = _PO["term_discount_rate"]
TERM_MIN = 30
PRESIDENCY_FULL = params.DEFAULTS["policy"]["presidency_cut"]
RAW = ROOT / "data/processed/emulator_runs.json"


def term_value(x):
    """The ownership-term lever is sampled evenly in what a finite claim is worth, from a 30-year term (x=0) to
    ownership for ever (x=1). In years the price moves steeply at short terms and hardly at all past a century,
    and 'for ever' sits at the far end rather than being coded as 0 years beside 1 — a cliff no smooth
    surface can follow."""
    f0 = 1 - (1 + TERM_RATE) ** -TERM_MIN
    return f0 + x * (1 - f0)


def term_years(x):
    """Years for a point on the lever; 0 means ownership for ever, as the model reads it."""
    f = term_value(x)
    if f >= 1 - 1e-9:
        return 0
    T = -np.log(1 - f) / np.log(1 + TERM_RATE)
    return 0 if T > 1000 else float(T)


def maintenance(x):
    T = term_years(x)
    if not T:
        return 1.0
    return 1 + _PO["maintenance_decay"] * max(0.0, 1 - T / 100.0) * (1 - _PO["upgrade_extension_offset"])


def default_x(key):
    lo, hi = next((l[3], l[4]) for l in LEVERS if l[0] == key)
    return float(np.clip((PLATFORM[key] - lo) / (hi - lo), 0, 1))


def status_quo_x(key):
    """Where the exact status-quo run sits on a world lever: the model's own default, which is not always where
    the reform's page opens (the last-decade world, for one). The page measures the status quo's world
    changes from here, so the two are never compared in different worlds."""
    _, _, _, lo, hi, path, scale, _ = LEVERS[KEYS.index(key)]
    node = params.DEFAULTS
    for part in path.split("."):
        node = node[part]
    return float(np.clip((float(node) / scale - lo) / (hi - lo), 0, 1))


def set_path(tree, dotted, value):
    parts = dotted.split(".")
    node = tree
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def overrides_for(x):
    """x: a vector in [0,1] per lever -> the parameter overrides it stands for."""
    # the stake lever carries the state's share; the easier start that comes with the borgaralaun is always on
    over = {"policy": {"regime": "platform", "wage_setting": "status_quo", "venture_support": 1.0}}
    for xi, (name, _, _, lo, hi, path, scale, _note) in zip(x, LEVERS):
        raw = lo + xi * (hi - lo)
        value = raw * scale
        if name == "ubi":
            over["policy"]["ubi_adult"] = value
            over["policy"]["ubi_child"] = value
        elif name == "governance":
            over["policy"]["governance_cut"] = value
            over["policy"]["presidency_cut"] = value * PRESIDENCY_FULL
        elif name == "taper":
            over["policy"]["ubi_taper_rate"] = value
            over["policy"]["ubi_taper_start"] = 600_000
        elif name in ("childcare", "housing", "retraining", "fx", "enforcement"):
            set_path(over, path, int(round(value)))
        elif name == "agreements":
            over["policy"]["wage_setting"] = "free_market" if xi >= .5 else "status_quo"
        elif name == "smelters":
            over.setdefault("energy", {})["smelter_exit_share"] = value
        elif name == "frontier":
            over.setdefault("frontier", {})["scale"] = value
            over["policy"]["frontier_programmes"] = [
                "controlled_environment_farming", "cultivated_protein", "autonomous_fisheries",
                "robotic_construction", "carbon_mineralisation"] if value > .02 else []
        elif name == "infrastructure":
            over.setdefault("infrastructure", {})["scale"] = value
            over["policy"]["infrastructure_programmes"] = [
                "city_light_rail", "keflavik_rail", "country_tunnels", "ring_railway"] if value > .02 else []
        elif name == "clawback":
            # the levy alone; the public stake has its own lever now (robot_stake), bought at a fair price
            over.setdefault("automation", {})["levy_rate"] = value
        else:
            set_path(over, path, value)
    return over


# ---------------------------------------------------------------- design

def latin_hypercube(n, k, rng):
    cells = np.array([rng.permutation(n) for _ in range(k)]).T
    return (cells + rng.random((n, k))) / n


def design(n, k, rng, candidates=300):
    """The Latin hypercube whose columns correlate least, of a few hundred drawn."""
    best, worst = None, np.inf
    for _ in range(candidates):
        X = latin_hypercube(n, k, rng)
        c = np.corrcoef(X.T)
        np.fill_diagonal(c, 0)
        if np.abs(c).max() < worst:
            best, worst = X, float(np.abs(c).max())
    return best, worst


_BASE = None


def load_base(blob):
    """Unpickle the calibrated society once per worker, into a module global the jobs then share."""
    global _BASE
    _BASE = pickle.loads(blob)


def run_point(job):
    i, x, years, reference = job
    soc = model.scenario(_BASE, overrides_for(x))
    soc.reference = reference
    rows = [soc.step() for _ in range(years)]
    out = {}
    for short in OUTPUTS:
        col = METRICS.get(short)
        if not col:
            continue
        out[short] = [None if (v := r.get(col)) is None or v != v else float(v) for r in rows]
    return i, out


def world_overrides(x):
    """Only the world-price part of a design point, for the status quo."""
    over = {}
    for name in WORLD:
        j = KEYS.index(name)
        _, _, _, lo, hi, path, scale, _ = LEVERS[j]
        set_path(over, path, (lo + x[j] * (hi - lo)) * scale)
    return over


def status_quo_run(job):
    """The status quo under one set of world prices: its series, and its history as a reference path."""
    w, x, years = job
    soc = model.scenario(_BASE, world_overrides(x) if x is not None else {})
    rows = [soc.step() for _ in range(years)]
    sq = {s: [None if (v := r.get(METRICS[s])) is None or v != v else float(v) for r in rows]
          for s in OUTPUTS if s in METRICS}
    return w, soc.own_history, sq


def status_quo_series(years):
    base = calibrated(1.0, recalibrate=False)
    load_base(pickle.dumps(base))        # in this process too: the same global the workers use
    _, hist, sq = status_quo_run((0, None, years))
    return base, hist, sq


def world_design(n, rng):
    """The world-price points: a Latin hypercube of their own, then each design run is given one of them."""
    W, _ = design(n, len(WORLD), rng)
    return W


def simulate(a):
    """Run the design, saving as it goes; with --resume, pick up the runs already saved."""
    t = time.time()
    base, _, status_quo = status_quo_series(a.years)
    print(f"status quo done ({time.time() - t:.0f}s)", flush=True)
    rng = np.random.default_rng(a.seed)
    X, _ = design(a.draws, len(LEVERS), rng)
    for name in BINARY:
        j = KEYS.index(name)
        X[:, j] = (X[:, j] >= .5).astype(float)
    # the world columns are taken from a few dozen points, each shared by about draws/points runs
    W = world_design(a.world_points, rng)
    world_of = rng.permutation(np.arange(a.draws) % a.world_points)
    wj = [KEYS.index(n) for n in WORLD]
    # The page's own world — the forecasts, behaviour at its central estimates — as one more world point (v10). Every
    # scenario and the Guide sit there, and several of its values lie at an end of their range (no windfall, the
    # forecasts' history, the lower emigration response), where the 120 drawn worlds left the surface extrapolating:
    # at the nine scenarios its 2035 budget was 26-212 ma.kr. below the model's even after a second near round,
    # while it fitted the near runs themselves to within 13 (2026-10-15). Only the --near3 round uses it.
    if a.near3 and a.near3_centers:
        page = json.loads(pathlib.Path(a.near3_centers).read_text())[-1]["x"]
        W = np.vstack([W, [page.get(k, default_x(k)) if isinstance(page, dict) else page[KEYS.index(k)] for k in WORLD]])
    X[:, wj] = W[world_of]
    # Anchors: the page opens with most levers at their defaults, many of them at an end of their range (a policy
    # off), and the scenarios sit there too. A Latin hypercube almost never lands in that corner — the nearest of
    # 2,500 runs was 3.4 apart in 60 dimensions — and the surface extrapolated into it, understating the public
    # balance by some 800 ma.kr. a year where the full model was checked (found 2026-10-06; v6 had it too). Each
    # anchor starts at the defaults and varies each lever with a probability of its own, 10-60%.
    if a.anchors:
        ra = np.random.default_rng(a.seed + 1)
        x0 = np.array([default_x(k) for k in KEYS])
        A = np.tile(x0, (a.anchors, 1))
        vary = ra.random(A.shape) < ra.uniform(.1, .6, (a.anchors, 1))
        A[vary] = ra.random(int(vary.sum()))
        for name in BINARY:
            j = KEYS.index(name)
            A[:, j] = (A[:, j] >= .5).astype(float)
        of = ra.integers(0, a.world_points, a.anchors)
        A[:, wj] = W[of]
        X = np.vstack([X, A])
        world_of = np.concatenate([world_of, of])
    # An adaptive round: runs around settings already found — the scenarios and the page's own picture — where the
    # surface is relied on most. All of them lay in one region the anchors still left thin, and the surface's
    # budget there was ~400 ma.kr. below the model's own runs (found 2026-10-06). Each varies 5-30% of its levers.
    if a.local and a.centers:
        rl = np.random.default_rng(a.seed + 2)
        sc = json.loads(pathlib.Path(a.centers).read_text())
        C = [np.array([default_x(k) for k in KEYS])]
        for c_ in sc:
            v = c_["x"]
            C.append(np.asarray(v if isinstance(v, list) else [v.get(k, default_x(k)) for k in KEYS], float))
        C = np.array(C)
        L = C[np.arange(a.local) % len(C)].copy()
        vary = rl.random(L.shape) < rl.uniform(.05, .3, (a.local, 1))
        L[vary] = rl.random(int(vary.sum()))
        for name in BINARY:
            j = KEYS.index(name)
            L[:, j] = (L[:, j] >= .5).astype(float)
        # each in one of the drawn worlds, whose status-quo run is its reference
        of = rl.integers(0, a.world_points, a.local)
        L[:, wj] = W[of]
        X = np.vstack([X, L])
        world_of = np.concatenate([world_of, of])
    # A near round, after the adaptive one: re-drawing 5-30% of 87 levers put only 3 of 300 runs within L1 4 of a
    # scenario, and at the scenarios found on that surface the model's budget for 2035 was 150-300 ma.kr. above the
    # surface's in all nine, while seeds moved it ±15 (2026-10-13). These runs re-draw 2-10% of the levers, half of
    # them in the drawn world nearest the scenario's own world prices. Appended, so --resume keeps every earlier run.
    def near_round(count, centres_file, offset, worlds=None):
        """Runs close to the settings in a scenarios file: each re-draws 2-10% of the levers, half of them in the drawn
        world nearest the scenario's own world prices (among the first `worlds` world points; all of them if None)."""
        nonlocal X, world_of
        rn = np.random.default_rng(a.seed + offset)
        sc = json.loads(pathlib.Path(centres_file).read_text())
        C = np.array([np.asarray(c_["x"] if isinstance(c_["x"], list) else [c_["x"].get(k, default_x(k)) for k in KEYS],
                                 float) for c_ in sc])
        pick = np.arange(count) % len(C)
        L = C[pick].copy()
        vary = rn.random(L.shape) < rn.uniform(.02, .1, (count, 1))
        L[vary] = rn.random(int(vary.sum()))
        for name in BINARY:
            j = KEYS.index(name)
            L[:, j] = (L[:, j] >= .5).astype(float)
        Wn = W if worlds is None else W[:worlds]
        nearest = np.array([np.abs(Wn - C[i][wj]).sum(1).argmin() for i in pick])
        of = np.where(np.arange(count) % 2 == 0, nearest, rn.integers(0, a.world_points, count))
        L[:, wj] = W[of]
        X = np.vstack([X, L])
        world_of = np.concatenate([world_of, of])
    # A near round, after the adaptive one: re-drawing 5-30% of 87 levers put only 3 of 300 runs within L1 4 of a
    # scenario, and at the scenarios found on that surface the model's budget for 2035 was 150-300 ma.kr. above the
    # surface's in all nine, while seeds moved it ±15 (2026-10-13). These runs re-draw 2-10% of the levers. A second
    # round (--near2) centres on the scenarios found after the first: v10's moved away from the first round's centres
    # and the surface's 2035 budget was again 14-229 ma.kr. below the model's at all nine (2026-10-15). Each round is
    # appended, so --resume keeps every earlier run.
    if a.near and a.near_centers:
        near_round(a.near, a.near_centers, 3, a.world_points)
    if a.near2 and a.near2_centers:
        near_round(a.near2, a.near2_centers, 4, a.world_points)
    if a.near3 and a.near3_centers:
        # every run in the world nearest its scenario's, the page's own for all but the robot and windfall ones
        nonlocal_W = W
        near_round(a.near3, a.near3_centers, 5)
        Xn = X[-a.near3:]
        C3 = json.loads(pathlib.Path(a.near3_centers).read_text())
        Cw = np.array([[c_["x"].get(k, default_x(k)) for k in WORLD] for c_ in C3])
        best = np.array([np.abs(nonlocal_W - Cw[i % len(C3)]).sum(1).argmin() for i in range(a.near3)])
        X[-a.near3:, wj] = nonlocal_W[best]
        world_of[-a.near3:] = best
    n = len(X)
    c = np.corrcoef(X[:a.draws].T)
    np.fill_diagonal(c, 0)
    print(f"design: {a.draws} points + {a.anchors} anchors on {a.world_points} world-price points, largest correlation between two "
          f"levers {np.abs(c).max():.3f}", flush=True)
    blob = pickle.dumps(base)
    sq_jobs = []
    for w in range(len(W)):
        x = np.full(len(KEYS), .5)
        x[wj] = W[w]
        sq_jobs.append((w, x, a.years))
    # These runs are the same every time for a given design, and they cost half an hour. Cached, so that
    # restarting a long build — which happens — does not pay for them again.
    refs, sq_world = [None] * len(W), [None] * len(W)
    tag = f"{a.world_points}x{a.years}x{a.seed}x{len(KEYS)}"
    cache = RAW.with_name("emulator_world.pkl")
    cached = pickle.loads(cache.read_bytes()) if cache.exists() else None
    have = len(cached["W"]) if cached else 0
    if cached and cached.get("tag") == tag and have <= len(W) and np.allclose(cached["W"], W[:have]):
        refs[:have], sq_world[:have] = cached["refs"], cached["sq_world"]
        print(f"world-price status quo runs taken from {cache.name} ({have} of {len(W)})", flush=True)
    todo_w = [j for j in sq_jobs if refs[j[0]] is None]
    if todo_w:
        with ProcessPoolExecutor(a.workers, initializer=load_base, initargs=(blob,)) as ex:
            for w, hist, sq in ex.map(status_quo_run, todo_w, chunksize=1):
                refs[w], sq_world[w] = hist, sq
        cache.write_bytes(pickle.dumps({"tag": tag, "W": W, "refs": refs, "sq_world": sq_world}))
        print(f"status quo under {a.world_points} world-price points done ({time.time() - t:.0f}s)", flush=True)
    Y = [None] * n
    if a.resume and RAW.exists():
        old = json.loads(RAW.read_text())
        m = len(old["X"])
        # the runs saved are kept if they are the start of this design (anchors are added after the hypercube)
        same = old["levers"] == KEYS and old["years"] == a.years and m <= n and np.shape(old["X"])[1] == X.shape[1]
        if same and np.allclose(old["X"], X[:m]):
            Y = old["Y"][:m] + [None] * (n - m)
            print(f"resuming: {sum(y is not None for y in Y)} runs already saved", flush=True)

    def save():
        RAW.write_text(json.dumps({"X": X.tolist(), "Y": Y, "levers": KEYS, "years": a.years,
                                   "status_quo": status_quo, "world": {"W": W.tolist(), "of": world_of.tolist(),
                                                                       "status_quo": sq_world},
                                   "generated": time.strftime("%Y-%m-%d")},
                                  separators=(",", ":")))

    todo = [i for i in range(n) if Y[i] is None]
    jobs = [(i, X[i], a.years, refs[world_of[i]]) for i in todo]
    with ProcessPoolExecutor(a.workers, initializer=load_base, initargs=(blob,)) as ex:
        for done, (i, out) in enumerate(ex.map(run_point, jobs, chunksize=1)):
            Y[i] = out
            if done % 20 == 19:
                print(f"  {done + 1}/{len(jobs)} ({time.time() - t:.0f}s)", flush=True)
            if done % 50 == 49:
                save()
    save()
    print(f"raw runs kept in {RAW.name}", flush=True)
    return X, Y, status_quo, {"W": W.tolist(), "of": world_of.tolist(), "status_quo": sq_world}


# ---------------------------------------------------------------- fitting

def base_terms(k):
    lin = {KEYS.index(n) for n in LINEAR_ONLY}
    t = [()] + [(j,) for j in range(k)]
    binary = {KEYS.index(n) for n in BINARY}
    t += [(j, j) for j in range(k) if j not in lin and j not in binary]
    t += [(0, j) for j in range(1, k) if j not in lin]
    return t


def columns(X, terms):
    """Levers centred on the middle of their range, so a lever and its square are not near-copies of each other."""
    U = X - .5
    cols = []
    for t in terms:
        if not t:
            cols.append(np.ones(len(X)))
        elif len(t) == 1:
            cols.append(U[:, t[0]])
        elif t[0] == t[1]:
            cols.append(U[:, t[0]] ** 2 - 1 / 12)
        else:
            cols.append(U[:, t[0]] * U[:, t[1]])
    return np.column_stack(cols)


def ridge(A, Y, lam):
    """Ridge on standardised columns, every year at once. Returns coefficients on the unstandardised columns."""
    mu, sd = A[:, 1:].mean(0), A[:, 1:].std(0)
    sd[sd == 0] = 1
    Z = (A[:, 1:] - mu) / sd
    ym = Y.mean(0)
    G = Z.T @ Z + lam * len(Y) * np.eye(Z.shape[1])
    g = np.linalg.solve(G, Z.T @ (Y - ym))
    beta = g / sd[:, None]
    return np.vstack([ym - mu @ beta, beta])        # terms × years


def r2_of(y, pred):
    v = float(np.sum((y - y.mean()) ** 2))
    return 1 - float(np.sum((y - pred) ** 2)) / v if v > 0 else 0.0


def kernel(Xa, Xb, dims, w, ell):
    d2 = np.zeros((len(Xa), len(Xb)))
    for a, wa in zip(dims, w):
        d2 += wa * (Xa[:, a, None] - Xb[None, :, a]) ** 2
    return np.exp(-d2 / (2 * ell * ell))


def importance(A, terms, beta):
    """How much of an output's movement each lever carries: the spread of every term that involves it."""
    spread = np.abs(beta[1:]) * A[:, 1:].std(0)[:, None]
    imp = np.zeros(len(KEYS))
    for (t, s) in zip(terms[1:], spread.sum(1)):
        for j in set(t):
            imp[j] += s
    return imp


def fit_output(X, Y, folds):
    """One output, every year. Y: runs × years, finite."""
    n, k = X.shape
    terms = base_terms(k)
    A = columns(X, terms)
    imp = importance(A, terms, ridge(A, Y, 1e-4))
    lin = {KEYS.index(n_) for n_ in LINEAR_ONLY}
    top = [int(j) for j in np.argsort(-imp) if j not in lin][:EXTRA_PAIRS_FROM]
    extra = [(min(a, b), max(a, b)) for i, a in enumerate(top) for b in top[i + 1:] if 0 not in (a, b)]
    terms = terms + extra
    A = columns(X, terms)

    # the penalty, per year, by cross-validation
    pred = {lam: np.zeros_like(Y) for lam in LAMBDAS}
    for f in folds:
        tr = np.setdiff1d(np.arange(n), f)
        for lam in LAMBDAS:
            pred[lam][f] = A[f] @ ridge(A[tr], Y[tr], lam)
    years = Y.shape[1]
    lam_y = [max(LAMBDAS, key=lambda l: r2_of(Y[:, y], pred[l][:, y])) for y in range(years)]
    r2_poly = [r2_of(Y[:, y], pred[lam_y[y]][:, y]) for y in range(years)]
    beta = np.column_stack([ridge(A, Y[:, [y]], lam_y[y])[:, 0] for y in range(years)])
    poly_cv = np.column_stack([pred[lam_y[y]][:, y] for y in range(years)])

    # the kernel correction, on what the polynomial leaves
    imp = importance(A, terms, beta)
    dims = list(np.argsort(-imp)[:KERNEL_DIMS])
    w = imp[dims] / max(imp[dims].sum(), 1e-12)
    res = Y - A @ beta
    scale = res.std(0)
    scale[scale == 0] = 1
    R = res / scale
    best, hyper = np.inf, None
    for ell in ELLS:
        K = kernel(X, X, dims, w, ell)
        for nu in NUGGETS:
            Minv = np.linalg.inv(K + nu * np.eye(n))
            loo = (Minv @ R) / np.diag(Minv)[:, None]
            score = float(np.sum(loo ** 2))
            if score < best:
                best, hyper = score, (ell, nu)
    ell, nu = hyper
    m = min(KERNEL_CENTRES, n)
    centres = np.sort(np.random.default_rng(11).choice(n, m, replace=False))

    def sor(Xc, Xn, r):
        """Weights on the centres Xc fitted to the residuals r at Xn: (Kcn Knc + nu Kcc) a = Kcn r."""
        Kcn = kernel(Xc, Xn, dims, w, ell)
        return np.linalg.solve(Kcn @ Kcn.T + nu * kernel(Xc, Xc, dims, w, ell) + 1e-8 * np.eye(len(Xc)), Kcn @ r)
    both_cv = np.zeros_like(Y)
    for f in folds:
        tr = np.setdiff1d(np.arange(n), f)
        B = np.column_stack([ridge(A[tr], Y[tr][:, [y]], lam_y[y])[:, 0] for y in range(years)])
        r_tr = Y[tr] - A[tr] @ B
        c_tr = np.intersect1d(centres, tr)
        alpha = sor(X[c_tr], X[tr], r_tr)
        both_cv[f] = A[f] @ B + kernel(X[f], X[c_tr], dims, w, ell) @ alpha
    r2_both = [r2_of(Y[:, y], both_cv[:, y]) for y in range(years)]
    gain = float(np.mean(np.array(r2_both) - np.array(r2_poly)))
    cut = float(np.mean([1 - (1 - b) / (1 - p) for b, p in zip(r2_both, r2_poly) if 1 - p > 1e-4] or [0.0]))
    out = {"terms": [list(t) for t in extra],
           "beta": [[float(f"{b:.6g}") for b in beta[:, y]] for y in range(years)]}
    if gain >= KERNEL_GAIN or cut >= KERNEL_REL_CUT:
        alpha = sor(X[centres], X, res)
        out["kernel"] = {"dims": [int(d) for d in dims], "w": [round(float(v), 5) for v in w], "ell": ell,
                         "alpha": [[float(f"{v:.6g}") for v in alpha[:, y]] for y in range(years)],
                         "centres": [int(c) for c in centres]}
        return out, r2_both, r2_poly
    return out, r2_poly, r2_poly


KERNEL_FILES = ("emulator_k.js", "emulator_k2.js", "emulator_k3.js")


def write_kernels(path, K):
    """The kernel weights, spread over KERNEL_FILES so that none passes the 16 MB a published file may be; the page
    loads them all straight after emulator.js. With 35 years at fifteen points and 2,500 runs the weights alone are
    about 27 MB."""
    path = pathlib.Path(path)
    parts = [{} for _ in KERNEL_FILES]
    sizes = [0] * len(KERNEL_FILES)
    for o, rows in sorted(K.items(), key=lambda kv: -len(json.dumps(kv[1]))):
        i = sizes.index(min(sizes))
        parts[i][o] = rows
        sizes[i] += len(json.dumps(rows, separators=(",", ":")))
    for name, part in zip(KERNEL_FILES, parts):
        path.with_name(name).write_text(
            "(function (E, K) { for (const o in K) E.coeffs[o].kernel.alpha = K[o]; })(window.UBI_EMU, "
            + json.dumps(part, separators=(",", ":")) + ");\n")


def split_kernels(path):
    """Move the kernel weights out of emulator.js into KERNEL_FILES."""
    path = pathlib.Path(path)
    t = path.read_text()
    E = json.loads(t[t.index("{"):t.rindex("}") + 1])
    K = {}
    for o, c in E["coeffs"].items():
        if "kernel" in c and "alpha" in c["kernel"]:
            # whole numbers written without a trailing ".0": the same values, about a tenth smaller
            K[o] = [[int(v) if v == int(v) else v for v in row] for row in c["kernel"].pop("alpha")]
    path.write_text("window.UBI_EMU = " + json.dumps(E, separators=(",", ":")) + ";\n")
    write_kernels(path, K)


def smooth(M):
    """Trailing three-year mean along the last axis, the same for runs and for the status quo."""
    M = np.array([[np.nan if v is None else v for v in row] for row in np.atleast_2d(np.array(M, dtype=object))],
                 dtype=float)
    out = np.column_stack([np.nanmean(M[:, max(0, y - 2):y + 1], axis=1) for y in range(M.shape[1])])
    return out


EXACT = {
    # output -> (what the page computes, how to compute it here for the check)
}
LINEAR_IN = {"infra_capex": "infrastructure", "infra_jobs": "infrastructure"}


def exact_checks(X, Y, years):
    """Outputs that follow from the levers by formula. Used only if the formula matches every run."""
    spec = {}
    for o, (kind, fn) in EXACT.items():
        vals = np.array([Y[i][o] for i in range(len(X))], dtype=float)
        want = np.array([[fn(X[i], y) for y in range(years)] for i in range(len(X))])
        err = float(np.nanmax(np.abs(vals - want)))
        ok = err < 1e-6
        print(f"  exact {o}: largest miss {err:.2e} {'— used' if ok else '— NOT used, fitted instead'}", flush=True)
        if ok:
            spec[o] = {"kind": kind, "rate": TERM_RATE, "min_years": TERM_MIN,
                       "decay": _PO["maintenance_decay"], "offset": _PO["upgrade_extension_offset"]}
    for o, lever in LINEAR_IN.items():
        j = KEYS.index(lever)
        lo, hi, scale = LEVERS[j][3], LEVERS[j][4], LEVERS[j][6]
        s = (lo + X[:, j] * (hi - lo)) * scale
        vals = np.array([Y[i][o] for i in range(len(X))], dtype=float)
        on = s > .02
        per = np.median(vals[on] / s[on, None], axis=0)
        want = np.where(on[:, None], s[:, None] * per[None, :], 0.0)
        err = float(np.nanmax(np.abs(vals - want) / (1 + np.abs(vals))))
        ok = err < 1e-6
        print(f"  exact {o}: largest relative miss {err:.2e} {'— used' if ok else '— NOT used, fitted instead'}",
              flush=True)
        if ok:
            spec[o] = {"kind": "linear", "lever": lever, "scale": scale, "threshold": .02,
                       "per_unit": [float(v) for v in per]}
    return spec


def world_terms():
    """A quadratic in the world, fitted to the status quo at each world point: 40 terms."""
    wj = [KEYS.index(n) for n in WORLD]
    pj = [KEYS.index(n) for n in WORLD_PRICES]
    t = [()] + [(j,) for j in wj] + [(j, j) for j in wj]
    # crosses only among the prices and AI, which do interact; with the behavioural levers as well a full
    # quadratic would have 91 terms for 120 points
    t += [(a, b) for i, a in enumerate(pj) for b in pj[i + 1:]]
    return t


def fit_status_quo(world, status_quo, years):
    """How the status quo moves with world prices. The page adds the change from 2025 prices to the exact
    status-quo run, so at 2025 prices it is that run exactly."""
    wj = [KEYS.index(n) for n in WORLD]
    Xw = np.full((len(world["W"]), len(KEYS)), .5)
    Xw[:, wj] = np.array(world["W"])
    terms = world_terms()
    A = columns(Xw, terms)
    n = len(Xw)
    folds = np.array_split(np.random.default_rng(7).permutation(n), FOLDS)
    out, r2s = {}, {}
    for s in status_quo:
        M = np.array([[np.nan if v is None else v for v in sq.get(s, [None] * years)] for sq in world["status_quo"]],
                     dtype=float)
        if s in SMOOTHED and not _PRESMOOTHED:
            M = smooth(M)
        if not np.isfinite(M).all():
            continue
        best, lam_b = -np.inf, None
        for lam in LAMBDAS:
            pred = np.zeros_like(M)
            for f in folds:
                tr = np.setdiff1d(np.arange(n), f)
                pred[f] = A[f] @ ridge(A[tr], M[tr], lam)
            sc = np.mean([r2_of(M[:, y], pred[:, y]) for y in range(years)])
            if sc > best:
                best, lam_b = sc, lam
        beta = ridge(A, M, lam_b)
        out[s] = [[float(f"{b:.6g}") for b in beta[:, y]] for y in range(years)]
        r2s[s] = round(float(best), 3)
    return {"terms": [list(t) for t in terms], "beta": out, "r2": r2s}


def year_list(years, first=2026, yearly=10, step=5):
    """The calendar years the surface carries: every year for the first ten, then every fifth year — a 35-year
    run is fitted at 2026-2035 and 2040, 2045, ... 2060, which keeps the page loadable while the year slider reaches
    the long run."""
    idx = list(range(min(yearly, years))) + list(range(yearly - 1 + step, years, step))
    return [first + i for i in idx]


_PRESMOOTHED = False


def thin(series, idx, key):
    """One run's series kept at the surface's years; a three-year average is taken over the full years first."""
    if series is None:
        return None
    if key in SMOOTHED:
        series = smooth([series])[0].tolist()
    return [series[i] if i < len(series) else None for i in idx]


def fit_all(X, Y, status_quo, years, draws, world=None):
    global _PRESMOOTHED
    t = time.time()
    years_kept = year_list(years)
    if len(years_kept) < years:
        idx = [y - 2026 for y in years_kept]
        Y = [None if y is None else {k: (thin(v, idx, k) if isinstance(v, list) else v) for k, v in y.items()}
             for y in Y]
        status_quo = {k: thin(v, idx, k) for k, v in status_quo.items()}
        if world:
            world = {**world, "status_quo": [{k: thin(v, idx, k) for k, v in sq.items()} for sq in world["status_quo"]]}
        years = len(idx)
        _PRESMOOTHED = True
    rng = np.random.default_rng(99)
    folds = np.array_split(rng.permutation(len(X)), FOLDS)
    exact = exact_checks(X, Y, years)
    coeffs, r2, r2_poly = {}, {}, {}
    kernels = 0
    for s in OUTPUTS:
        if s not in METRICS or s in exact:
            continue
        M = np.array([[np.nan if v is None else v for v in (Y[i] or {}).get(s, [None] * years)]
                      for i in range(len(X))], dtype=float)
        if s in SMOOTHED and not _PRESMOOTHED:
            M = smooth(M)
        ok_years = np.isfinite(M).mean(0) >= .9
        rows = np.isfinite(M[:, ok_years]).all(1)
        if not ok_years.any() or rows.sum() < 300:
            print(f"  {s}: too few finite runs, skipped", flush=True)
            continue
        sub_folds = [np.flatnonzero(np.isin(np.flatnonzero(rows), f)) for f in folds]
        out, score, poly = fit_output(X[rows], M[rows][:, ok_years], sub_folds)
        # years that could not be fitted stay empty, as before
        full_beta, full_r2, full_poly, full_alpha, it = [], [], [], [], 0
        for y in range(years):
            if ok_years[y]:
                full_beta.append(out["beta"][it]); full_r2.append(round(score[it], 3))
                full_poly.append(round(poly[it], 3))
                if "kernel" in out:
                    full_alpha.append(out["kernel"]["alpha"][it])
                it += 1
            else:
                full_beta.append([]); full_r2.append(0.0); full_poly.append(0.0)
                if "kernel" in out:
                    full_alpha.append([])
        out["beta"] = full_beta
        if "kernel" in out:
            out["kernel"]["alpha"] = full_alpha
            # the page reads the centres as rows of X (kernelAt): indices among all runs
            out["kernel"]["rows"] = [int(r) for r in np.flatnonzero(rows)[out["kernel"].pop("centres")]]
            kernels += 1
        coeffs[s], r2[s], r2_poly[s] = out, full_r2, full_poly

    sq = {k: ([float(v) for v in smooth([s_])[0]] if k in SMOOTHED and not _PRESMOOTHED else s_)
          for k, s_ in status_quo.items()}
    lev_meta = []
    for key, lab, u, lo, hi, _p, _s, note in LEVERS:
        m = {"key": key, "label": lab, "unit": u, "lo": lo, "hi": hi, "note": note, "default": default_x(key),
             "linear_only": key in LINEAR_ONLY, "binary": key in BINARY,
             "today": float(np.clip((TODAY[key] - lo) / (hi - lo), 0, 1)) if key in TODAY else None,
             "status_quo_at": status_quo_x(key) if key in WORLD else None}
        lev_meta.append(m)
    meta = {
        "levers": lev_meta,
        "outputs": [s for s in OUTPUTS if s in METRICS],
        "years": years, "year_list": years_kept, "base_year": 2025, "draws": draws,
        "basis": "centred", "terms": [list(t) for t in base_terms(len(KEYS))],
        "smoothed": list(SMOOTHED), "exact": exact,
        "generated": time.strftime("%Y-%m-%d"),
    }
    sq_world = fit_status_quo(world, status_quo, years) if world else None
    if sq_world:
        moving = {s: v for s, v in sq_world["r2"].items()}
        print(f"status quo against world prices: {len(moving)} outputs, median cross-validated R² "
              f"{np.median(list(moving.values())):.2f}", flush=True)
    def r7(o):
        """Seven significant figures: the fit is not better than that, and full floats doubled the file."""
        if isinstance(o, float):
            return float(f"{o:.7g}")
        if isinstance(o, list):
            return [r7(v) for v in o]
        if isinstance(o, dict):
            return {k: r7(v) for k, v in o.items()}
        return o
    pay = {k: v for k, v in coeffs.items() if k.startswith("pp_")}
    main = {k: v for k, v in coeffs.items() if not k.startswith("pp_")}
    payload = {"meta": meta, "coeffs": r7(main), "r2": r2, "r2_poly": r2_poly, "status_quo": sq,
               "status_quo_world": r7(sq_world),
               "X": [[round(float(v), 5) for v in row] for row in X] if kernels else None}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.UBI_EMU = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    split_kernels(OUT)
    PAY = OUT.with_name("emulator_pay.js")
    PAY.write_text("window.UBI_EMU_PAY = " + json.dumps({"coeffs": r7(pay)}, separators=(",", ":")) + ";\n")
    print(f"wrote {PAY} ({PAY.stat().st_size / 1e6:.1f} MB)")
    med = {s: float(np.median(v)) for s, v in r2.items()}
    print(f"\nwrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, fitted in {time.time() - t:.0f}s)")
    print(f"kernel correction kept for {kernels} outputs; exact formulas for {len(exact)}")
    bands = {"≥0.95": 0, "0.85–0.95": 0, "0.5–0.85": 0, "<0.5": 0}
    for v in med.values():
        bands["≥0.95" if v >= .95 else "0.85–0.95" if v >= .85 else "0.5–0.85" if v >= .5 else "<0.5"] += 1
    print("median cross-validated R² by band: " + ", ".join(f"{k} {v}" for k, v in bands.items()))
    print("weakest fits: " + ", ".join(f"{s} {v:.2f}" for s, v in sorted(med.items(), key=lambda kv: kv[1])[:10]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=1200)
    ap.add_argument("--anchors", type=int, default=0, help="extra runs around the page's defaults (see simulate)")
    ap.add_argument("--local", type=int, default=0, help="extra runs around the settings in --centers (see simulate)")
    ap.add_argument("--centers", default=None, help="a scenarios file whose settings the --local runs centre on")
    ap.add_argument("--near", type=int, default=0, help="extra runs close to the settings in --near-centers, after --local")
    ap.add_argument("--near-centers", default=None, help="a scenarios file whose settings the --near runs centre on")
    ap.add_argument("--near2", type=int, default=0, help="a second near round, after --near")
    ap.add_argument("--near2-centers", default=None, help="a scenarios file whose settings the --near2 runs centre on")
    ap.add_argument("--near3", type=int, default=0, help="a third near round, in the page's own world (the last entry "
                    "of --near3-centers)")
    ap.add_argument("--near3-centers", default=None, help="a scenarios file whose settings the --near3 runs centre on")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--seed", type=int, default=12)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--world-points", type=int, default=WORLD_POINTS)
    ap.add_argument("--out", default=None, help="write the page data and raw runs elsewhere (a smoke test)")
    ap.add_argument("--refit", action="store_true", help="fit the saved runs without simulating")
    ap.add_argument("--resume", action="store_true", help="keep the runs already saved for this design")
    a = ap.parse_args()
    if a.out:
        global OUT, RAW
        OUT, RAW = pathlib.Path(a.out) / "emulator.js", pathlib.Path(a.out) / "emulator_runs.json"
    if a.refit:
        raw = json.loads(RAW.read_text())
        if raw["levers"] != KEYS:
            sys.exit("the saved runs were made with different levers; they cannot be refitted")
        X = np.array(raw["X"])
        Y = raw["Y"]
        if any(y is None for y in Y):
            keep = [i for i, y in enumerate(Y) if y is not None]
            print(f"refitting the {len(keep)} of {len(Y)} runs that finished", flush=True)
            X, Y = X[keep], [Y[i] for i in keep]
        fit_all(X, Y, raw["status_quo"], raw["years"], len(X), raw.get("world"))
        return
    X, Y, status_quo, world = simulate(a)
    fit_all(X, Y, status_quo, a.years, len(X), world)


if __name__ == "__main__":
    main()
