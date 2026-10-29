"""Dynamic markets around the agents: goods prices, the króna, interest, housing, external balance, public debt.

All indices are 1.0 in the 2025 base year and evolve yearly with partial adjustment, so markets respond with
realistic lags instead of clearing instantly. Monetary amounts are bn ISK at 2025 prices.

Base-year data (Hagstofa THJ01102, THJ05181, THJ05132; HMS; Seðlabanki Íslands):
  GDP 4,941 · household consumption 2,440 · exports 1,997 · imports 2,103 · current account −124
  government liabilities 4,361 · interest paid 211.7 · property value 17,300 · recurrent property tax 102.8
"""
import numpy as np

from ubisim.abm import capital
from ubisim.abm import careers
from ubisim.abm import financial

from ubisim.abm import params as P

GDP0, C0, X0, M0, CA0 = 4941.2, 2439.6, 1997.4, 2102.8, -124.2
DEBT0, INTEREST0 = 4360.7, 211.7
REVENUE0, EXPENDITURE0 = 2125.0, 2255.9      # general government, 2025 (THJ05111)
# v9: HMS 2026 assessed value (fasteignamat 2026, register extract); the tax at the GFS figure for local government
# (101.5, THJ05132), as the rest of the budget is GFS
PROPERTY_VALUE0, PROPERTY_TAX0 = 17_467.6, 101.5
TREND0 = .025                   # the inflation built into 2025 interest rates: Seðlabanki's target
INFLATION0 = .0408              # CPI inflation in the base year (2025, VIS01000), at which its interest was paid


TARIFF0 = 7.7 / 1339.0          # customs over goods imports


BASE_DEFAULTS = {"GDP0": GDP0, "C0": C0, "X0": X0, "M0": M0, "CA0": CA0, "DEBT0": DEBT0, "INTEREST0": INTEREST0,
                 "PROPERTY_VALUE0": PROPERTY_VALUE0, "PROPERTY_TAX0": PROPERTY_TAX0, "TARIFF0": TARIFF0,
                 "REVENUE0": REVENUE0, "EXPENDITURE0": EXPENDITURE0,
                 "INFLATION0": INFLATION0}


class Macro:
    def __init__(self, p):
        m = p["markets"]
        # The base year's national figures. 2025 unless the parameters name another base year (the backcast).
        base = p.get("base") or {}
        for name, default in BASE_DEFAULTS.items():
            setattr(self, name, float(base.get(name, default)))
        self.p = p
        self.e = 1.0                 # exchange rate index (ISK per foreign currency; up = weaker króna)
        self.P_T = 1.0               # tradable goods prices
        self.P_N = 1.0               # non-tradable goods and services prices
        self.rent = 1.0              # market rents
        self.house_price = 1.0       # house prices
        self.stock = 1.0             # dwelling stock
        self.r = m["real_rate0"]     # real policy rate
        self.r_long = m["real_rate0"]  # real rate on housing loans: follows the policy rate in part, and slowly
        self.cpi = 1.0
        self.cpi_net = 1.0
        self.variety = 0.0          # how far commercial ownership has been spread out by a cap (0-1)
        # yearly CPI change. It starts at the trend: starting at zero read as a 2.5-point disinflation in year one,
        # which cut the policy rate and strengthened the króna in every run that had a trend, and the difference
        # compounded from there.
        self.inflation = m["trend_inflation"]
        self.gap = 0.0               # labour-market pressure (demand/supply − 1)
        self.output = 1.0            # real output index
        self.output_trend = 1.0      # output smoothed over the cycle: what the state's own purchases follow
        self.unmodelled_bn = 0.0     # growth of the revenue and spending the agents do not produce (see below)
        self.exports, self.imports = self.X0, self.M0
        self.ca_gdp = self.CA0 / self.GDP0
        self.debt = self.DEBT0
        # Average coupons on the debt stock, repricing gradually as it rolls over: a nominal one on the non-indexed
        # part, a real one on the indexed part, whose indexation is paid on top. The base year's interest is split
        # between them at that year's inflation, with the real coupon an estimate (markets.indexed_real_coupon0).
        # The nominal coupon starts with the premium this run's trend implies over the base year's inflation, or a
        # different trend is paid for years at the wrong rate.
        ind = m["debt_indexed_share"]
        rate0 = self.INTEREST0 / self.DEBT0
        self.coupon_r0 = m.get("indexed_real_coupon0", .025)
        self.coupon_n0 = (rate0 - ind * (self.coupon_r0 + self.INFLATION0)) / (1 - ind)
        self.coupon_n = self.coupon_n0 + (m["trend_inflation"] - self.INFLATION0)
        self.coupon_r = self.coupon_r0
        self.r_debt = (1 - ind) * self.coupon_n + ind * (self.coupon_r + m["trend_inflation"])
        self.interest0 = self.debt_interest(self.DEBT0, self.coupon_n0, self.coupon_r0, self.INFLATION0, ind)
        self.interest = self.debt_interest(self.debt, self.coupon_n, self.coupon_r, m["trend_inflation"], ind)
        self.exp_house_growth = 0.0
        self.niip = -60.0            # EST: net international investment position, % of GDP (2025)
        self.fund_payout = 0.0       # start-of-life fund principal paid out this year (bn)
        self.sovereign_fund = 0.0    # surplus put aside rather than used to repay debt (bn)
        self.property_tax_rate0 = self.PROPERTY_TAX0 / self.PROPERTY_VALUE0
        # pension funds' foreign assets, available to support the króna (EST: 40% of assets = 187% of GDP)
        self.pension_fx_assets = .4 * 1.87 * self.GDP0
        self.pension_fx_assets0 = self.pension_fx_assets
        self.fx_support_used = 0.0
        self.erosion_bn = 0.0            # real value of the debt inflation wore away this year
        self.absorbed = 1.0          # prices carried by shortfalls taken as lost purchasing power
        self.uc0 = self.user_cost(m["real_rate0"], self.property_tax_rate0, 0.0)

    # ---------------------------------------------------------------- helpers
    def platform(self):
        return self.p["policy"]["regime"] == "platform"

    def property_tax_rate(self):
        extra = self.p["policy"]["prop_tax_extra_pp"] / 100 if self.platform() else 0.0
        return self.property_tax_rate0 + extra

    def user_cost(self, r, tau, g_exp):
        m = self.p["markets"]
        return max(.01, r + tau + m["housing_depreciation_and_risk"] - g_exp)

    def vat_factor(self, vat, vat0):
        return (1 + vat) / (1 + vat0)

    def vat_share_factor(self, vat, vat0):
        """How much of the CPI the VAT change itself accounts for, as a multiplier on the whole index: the VAT
        factor on the taxed part of the basket (goods and services), none on housing."""
        m = self.p["markets"]
        taxed = m["w_tradable"] * self.P_T + m["w_nontradable"] * self.P_N
        housing = m["w_housing"] * self.rent
        return float((taxed * self.vat_factor(vat, vat0) + housing) / max(taxed + housing, 1e-9))

    def pension_asset_ratio(self):
        return self.pension_fx_assets / self.pension_fx_assets0 if self.pension_fx_assets0 else 1.0

    def cpi_for(self, wage_cost_index, vat, vat0):
        """CPI if this year's wage costs were `wage_cost_index` (used inside the labour-market clearing loop)."""
        m = self.p["markets"]
        P_N = 1.0 if m.get("freeze_prices") else self.nontradable_target(wage_cost_index, partial=True)
        tariff = self.tariff()
        P_T = self.e * self.import_price() * (1 + tariff) / (1 + self.TARIFF0)
        goods = m["w_tradable"] * P_T + m["w_nontradable"] * P_N
        return (goods * self.vat_factor(vat, vat0) + m["w_housing"] * self.rent) * self.agriculture_price_factor() \
            * self.absorbed * self.trend()

    def trend(self):
        """The nominal trend: prices rise even when nothing real changes. Everything the model reports in real
        terms is unaffected, but a wage fixed in krónur until its contract is renewed is not."""
        return (1 + self.p["markets"]["trend_inflation"]) ** getattr(self, "year", 0)

    def relative_wage_cost(self, wage_cost_index):
        """Wage cost in the same relative units as the króna and non-tradable prices.

        Wages are nominal — contracts are indexed to the CPI, and the CPI carries the trend — while the price
        block works relative to that trend and multiplies it in once, at the end. Setting a nominal wage against a
        relative price counted the trend twice: prices rose with it and again with the wages indexed to it, each
        renewal chased that, and real wages could not grow whatever productivity did."""
        return wage_cost_index / self.trend()

    def nonindexed_share(self):
        """Share of household mortgage debt not indexed to the CPI: a third today, rising as indexation is phased out."""
        m, pol = self.p["markets"], self.p["policy"]
        base = 1 - m["mortgage_indexed_share0"]
        if not self.platform() or not pol["indexation_phaseout"]:
            return base
        ramp = min(1.0, max(getattr(self, "year", 0), 0) / max(pol["indexation_phase_years"], 1))
        return base + (1 - base) * pol["indexation_phaseout"] * ramp

    def mortgage_payment_factor(self):
        """What a mortgage costs each year against today's mix of loans, at today's rates.

        An indexed loan pays the real rate and adds inflation to the balance; a non-indexed one pays inflation in
        cash, as part of a nominal rate. The same debt therefore costs more now and less later, and the more of it
        is non-indexed the harder high inflation bites a household's budget — which is also why interest rates
        work faster. Equal to 1 whenever the mix is today's."""
        m = self.p["markets"]
        r, a, pi = max(self.r, 0.0), m["mortgage_amortisation"], max(self.inflation, 0.0)
        pay = lambda s: s * (r + pi + a) + (1 - s) * (r + a)
        return pay(self.nonindexed_share()) / pay(1 - m["mortgage_indexed_share0"])

    def term_value_factor(self):
        """What a finite term of ownership is worth against owning for ever.

        A claim that ends in T years, discounted at r, is worth 1 - (1+r)^-T of a perpetual one. The market
        prices that the day the rule passes, so property values fall by the remainder immediately — 36% at a
        30-year term, 18% at 50, 8% at 75, 3% at 100.
        """
        po, pol = self.p["property_ownership"], self.p["policy"]
        T = pol["ownership_term_years"]
        # custodianship: a holder who keeps investing keeps the asset, so the price falls only by the risk
        cust = 1 - po["custodian_value_discount"] * self.custodianship()
        if not self.platform() or not T:
            return cust
        r = po["term_discount_rate"]
        return float(1 - (1 + r) ** (-T)) * cust

    def maintenance_factor(self):
        """Upkeep falls as a term runs down — the leasehold problem — which extensions for upgrades answer in
        part. Shows up as faster depreciation of the housing stock."""
        po, pol = self.p["property_ownership"], self.p["policy"]
        T = pol["ownership_term_years"]
        # custodianship makes upkeep the condition of holding on, so the stock wears out more slowly
        cust = 1 - po["custodian_upkeep_gain"] * self.custodianship()
        if not self.platform() or not T:
            return cust
        short = max(0.0, 1 - T / 100.0)
        return (1 + po["maintenance_decay"] * short * (1 - po["upgrade_extension_offset"])) * cust

    def ownership_markups(self, year):
        """What concentrated ownership adds to rent, and how much of it a cap removes.

        A cap below what the largest group currently holds forces a sale. That adds sellers and competitors, and
        the markup falls in proportion to how far the cap bites, phased over the years a divestment takes.
        Returns (residential, commercial) factors to multiply rent by.
        """
        po, pol = self.p["property_ownership"], self.p["policy"]
        out = []
        for side in ("residential", "commercial"):
            markup = po[f"{side}_markup"]
            top, cap = po[f"{side}_top_share"], pol[f"{side}_ownership_cap"]
            if self.platform() and cap < top:
                bite = min(1.0, (top - cap) / max(top, 1e-6))
                phase = min(1.0, max(0, year) / max(po["divestment_years"], 1))
                # a developer exemption aims the cap at accumulation rather than construction, but it also lets
                # concentration rebuild through new stock, so it takes part of the rent effect back
                dilution = 1 - po["exempt_stock_dilution"] * pol["developer_exemption"] * phase * .5
                markup = markup * (1 - bite * phase * max(dilution, 0))
                if side == "commercial":
                    # how far ownership of the high street has been spread out: the variety a cap is for
                    self.variety = float(bite * phase * max(dilution, 0))
            elif side == "commercial":
                self.variety = 0.0
            out.append(1 + markup)
        return out[0], out[1]

    def export_price_index(self):
        """What the world pays for what Iceland sells, weighted by what it actually sells."""
        tr = self.p["trade"]
        return float(sum(tr["shares"][k] * tr["price"][k] * (self.tourism_vat_factor() if k == "tourism" else 1.0)
                         for k in tr["shares"]))

    def tariff(self):
        """Customs duties as a share of goods imports: today's, or the share of them the reform keeps."""
        pol = self.p["policy"]
        if not self.platform() or not pol["abolish_tariffs"]:
            return self.TARIFF0
        return self.TARIFF0 * float(pol.get("customs_kept", 0.0))

    def agriculture_price_factor(self):
        """Prices the reform's subsidy cuts raise: domestic food when farm support goes, heating and fares when
        energy and transport support goes."""
        if not self.platform():
            return 1.0
        pol = self.p["policy"]
        es, cut = self.p["energy_split"], P.energy_cuts(self.p)
        energy = es["heating_cpi_at_full_cut"] * cut["heating"] + es["transition_cpi_at_full_cut"] * cut["transition"] \
            + es["transport_cpi_at_full_cut"] * cut["transport"]
        return (1 + self.p["agriculture"]["cpi_effect_at_full_cut"] * pol["agriculture_subsidy_cut"]) * (1 + energy)

    def transition_delay(self):
        """Extra road emissions (Mt CO2e) from slower electrification when the transition grants are cut."""
        if not self.platform():
            return 0.0
        es = self.p["energy_split"]
        ramp = min(1.0, getattr(self, "year", 0) / es["transition_years"])
        return es["transition_emissions_at_full_cut_mt"] * P.energy_cuts(self.p)["transition"] * ramp \
            + es["transport_emissions_at_full_cut_mt"] * P.energy_cuts(self.p)["transport"]

    def tourism_vat_factor(self):
        """What tourists buy, against today, when VAT on their stay changes: net of VAT the price is the same, so
        what the country earns follows the volume."""
        lk = self.p["links"]
        vat = self.p["policy"]["vat_platform"] if self.platform() else lk["tourism_vat_today"]
        rise = ((1 + vat) / (1 + lk["tourism_vat_today"])) ** lk["tourism_vatable_share"]
        return float(rise ** (-lk["tourism_price_elasticity"]))

    def custodianship(self):
        return float(self.p["policy"].get("custodianship", 0.0)) if self.platform() else 0.0

    def custodian_ramp(self):
        po = self.p["property_ownership"]
        return min(1.0, max(getattr(self, "year", 0), 0) / max(po["custodian_ramp_years"], 1))

    def import_price(self):
        """What the world charges for what Iceland buys, 1.0 = 2025, net of partners' general inflation. It sets
        the krónur price of tradable goods with the exchange rate, and so the CPI, and the value of the import bill."""
        return max(float(self.p["trade"]["import_price"]), .2)

    def terms_of_trade(self):
        """Export prices over import prices. A gain here raises real income without anyone working harder, and
        it is a large part of why Icelandic real wages have outrun productivity."""
        return self.export_price_index() / self.import_price()

    def productivity(self):
        """Output per hour. The trend rate is Iceland's own (THJ11011: +1.07%/yr, 2008-2025). Without it the model
        is a zero-growth economy: real wages have no source of growth, and a workforce that grows at all can only be
        absorbed by falling wages."""
        pol = self.p["policy"]
        base = 1.0 + (pol["low_value_jobs_productivity_gain"] if self.platform() else 0.0)
        trend = (1 + self.p["markets"]["productivity_growth"]) ** getattr(self, "year", 0)
        # time not spent travelling is time worked: finished infrastructure raises output per hour
        infra = 1 + getattr(self, "infra_gain", 0.0)
        # neglected firms and assets pass to people who run them better
        custodian = 1 + self.custodianship() * self.p["property_ownership"]["custodian_productivity"] \
            * self.custodian_ramp()
        # less research and fewer new firms without the innovation support
        innovation = 1 - (self.p["links"]["innovation_productivity_at_full_cut"]
                          * pol["subsidy_cut_innovation"] * self.custodian_ramp() if self.platform() else 0.0)
        controls = 1 - (self.p["links"]["capital_controls_productivity_cost"] * pol["capital_controls"]
                        if self.platform() else 0.0)
        # a year of the backcast: the productivity the record implies beyond the trend, identified so the status
        # quo reproduces measured output (scripts/backcast.py --identify), and applied to every run alike
        shock = float((self.p.get("history") or {}).get("productivity_level", 1.0))
        # less new equity under the state's deemed stake in every round, and with it a little less investment
        drag = 1 - getattr(self, "equity_drag", 0.0)
        # 2.0: capital per worker against the reference's (capital.py)
        return base * trend * infra * custodian * innovation * controls * getattr(self, "automation_factor", 1.0) \
            * shock * drag * capital.factor(self)

    def nontradable_target(self, wage_cost_index, partial):
        m = self.p["markets"]
        ulc = self.relative_wage_cost(wage_cost_index) / self.productivity()
        target = ulc ** m["labour_cost_passthrough"] * max(.5, 1 + self.gap) ** m["demand_pressure_passthrough"]
        if self.platform():
            # input VAT firms can no longer reclaim is a cost, and part of it reaches their prices
            target *= 1 + self.p["links"]["vat_input_price_per_100bn"] \
                * self.p["policy"]["vat_input_restriction_gain"] / 100
        if not partial:
            return target
        return self.P_N ** (1 - m["price_adjustment"]) * target ** m["price_adjustment"]

    # ---------------------------------------------------------------- start of year: housing
    def housing_costs(self):
        """Factors applied to households' housing costs: rent index, mortgage factor, extra monthly property tax
        per owner household (ISK)."""
        m = self.p["markets"]
        uc = self.user_cost(self.r_long, self.property_tax_rate(), self.exp_house_growth)
        mortgage = (1 + .3 * (self.rent - 1)) * (uc / self.uc0) ** .5 * self.mortgage_payment_factor()
        dwelling_value = self.PROPERTY_VALUE0 * 1e9 * m["residential_share"] / m["dwellings0"] * self.house_price
        owner_tax = (self.property_tax_rate() - self.property_tax_rate0) * dwelling_value / 12
        return self.rent, mortgage, owner_tax

    def update_housing(self, pop_index, income_index):
        """Rents clear against the dwelling stock; prices follow rents and the user cost of owning."""
        m = self.p["markets"]
        fund_demand = m["fund_housing_share"] * self.fund_payout / (self.PROPERTY_VALUE0 * m["residential_share"] * self.house_price)
        demand = pop_index * income_index ** m["housing_income_elasticity"] * (1 + fund_demand)
        rent_target = (demand / self.stock) ** (1 / m["housing_price_elasticity"])
        res_markup, com_markup = self.ownership_markups(getattr(self, "year", 0))
        self.commercial_rent = com_markup
        variety = self.variety   # the call for year 0 below would reset it
        base0, _ = self.ownership_markups(0) if getattr(self, "year", 0) else (res_markup, com_markup)
        self.variety = variety
        rent_target = rent_target * res_markup / (1 + self.p["property_ownership"]["residential_markup"]) \
            * (1 + m["history_like"] * m["history_rent_drift"]) ** getattr(self, "year", 0)
        self.rent = float(np.clip(self.rent ** (1 - m["rent_adjustment"]) * rent_target ** m["rent_adjustment"], .5, 3.0))
        if m.get("freeze_prices"):  # diagnostic: no market price reactions (VAT still applies)
            self.rent = self.house_price = 1.0
            return
        uc = self.user_cost(self.r_long, self.property_tax_rate(), self.exp_house_growth)
        price_target = self.rent * self.uc0 / uc * (1 + fund_demand)
        new_price = self.house_price ** .5 * price_target ** .5
        self.exp_house_growth = float(np.clip(.2 * (new_price / self.house_price - 1), -.01, .01))
        self.house_price = float(np.clip(new_price * self.term_value_factor(), .3, 3.0))

    # ---------------------------------------------------------------- end of year: goods, external, money, debt
    @staticmethod
    def debt_interest(debt, coupon_n, coupon_r, inflation, ind):
        """Interest in the year, in base-year krónur, as the national accounts book it: nominal coupons on the
        non-indexed debt, paid in the year's krónur; real coupons on the indexed debt and the indexation of its
        principal. The accounts count indexation as interest, so the budget balance carries it in full; the
        debt, held in base-year krónur, is then worn down by inflation as a whole (update_end_of_year)."""
        pi = max(inflation, 0.0)
        return debt * ((1 - ind) * coupon_n / (1 + pi) + ind * (coupon_r + pi / (1 + pi)))

    def update_end_of_year(self, soc, acc, S, D, balance_before_interest, interest_ref=None):
        m, pol = self.p["markets"], self.p["policy"]
        if interest_ref is None:
            interest_ref = self.INTEREST0
        lab = self.p["labour"]
        # labour-market pressure and output
        ref = soc.reference_prev()
        raw_gap = float(np.clip(D.sum() / max(S.sum(), 1) - 1, -.3, .3))
        self.raw_gap = raw_gap
        self.gap = raw_gap - (ref["raw_gap"] if ref and "raw_gap" in ref else 0.0)
        prod = soc.occ_median / soc.occ_median.mean()
        employed = np.minimum(S, D)
        self.automation_factor = soc.automation.productivity_factor()
        base_fte = soc.D0_pub + soc.D0_priv
        base = float((base_fte * prod).sum())
        # 1.1: and the experience of those working, against the base year's (careers.py)
        self.labour_input = float((employed * prod).sum() / base)
        self.output_labour = self.labour_input * self.productivity() * careers.output_factor(soc)
        # 1.1: what machines do in place of the work they took over is output too: the output of the work, less the
        # part of what running them costs that is bought abroad (automation.machine_value_added). Left out, a robot that
        # took over a post took its output with it, and automation could raise output only through the people it
        # left at work.
        va = self.p["automation"]["machine_value_added"]
        self.output_machines = float((soc.automation.automated * base_fte * prod).sum() / base) * va \
            * self.productivity()
        self.output = self.output_labour + self.output_machines
        # non-tradable prices
        old_cpi = self.cpi
        wci = soc.wage_cost_index(soc.omega)
        self.P_N = self.nontradable_target(wci, partial=True)
        # external balance
        export_capacity = float((soc.export_loading * employed).sum()
                                / (soc.export_loading * (soc.D0_pub + soc.D0_priv)).sum())
        # v9: what exporters bear, 135.3 ma.kr. at the full restriction (EST, see params.vat_input),
        # as a share of exports and in proportion to how much of the restriction is applied
        pol = soc.p["policy"]
        share = pol["vat_input_restriction_gain"] / max(pol.get("vat_input_restriction_full_bn", 459.5), 1.0)
        vat_input_cost = m["vat_input_export_burden_bn"] * share / max(self.X0, 1.0) \
            if (pol["regime"] == "platform") else 0.0
        competitiveness = self.e / (self.P_N * (1 + vat_input_cost))
        # external flows relative to the reference path (the status-quo run, or this run's own last year)
        self.export_capacity, self.competitiveness_x = export_capacity, competitiveness
        cap_ref = ref["export_capacity"] if ref and "export_capacity" in ref else export_capacity
        comp_ref = ref["competitiveness_x"] if ref and "competitiveness_x" in ref else 1.0
        rel_price = self.e / self.P_N
        rel_price_ref = ref["rel_price"] if ref and "rel_price" in ref else 1.0
        self.rel_price = rel_price
        cons_rel = acc["cons_pc"] / (ref["cons_pc"] if ref else 1.0)
        out_ref = ref["output"] if ref and "output" in ref else self.output
        fr = soc.frontier.state
        self.exports = self.X0 * (competitiveness / comp_ref) ** m["export_price_elasticity"] * (export_capacity / cap_ref) \
            * self.export_price_index() + soc.sectors.exports_change() + fr["exports_bn"]
        # A value: fewer imports when the world charges more, each one dearer — ip^(1 - elasticity), as a level.
        # The króna term answers the change against the reference path; the world price cannot go through that
        # term, since the status quo's reference is its own last year and the volume response would last a year
        # while the dearer bill lasted for ever, pushing the króna down year after year.
        ip = self.import_price()
        self.imports = self.M0 * cons_rel ** m["import_income_elasticity"] * (self.output / out_ref) ** .3 \
            * (rel_price / rel_price_ref) ** (-m["import_price_elasticity"]) * ip ** (1 - m["import_price_elasticity"]) \
            - fr["import_substitution_bn"] + getattr(soc, "gambling_abroad_bn", 0.0) / soc.price \
            + self.p["energy_split"]["fuel_imports_bn_per_mt"] * self.transition_delay()
        # Debt, deficits and external flows are all kept in 2025 krónur, so they are set against real GDP.
        # Against nominal GDP the ratios fell by the inflation rate every year whatever the debt did.
        gdp_real = self.GDP0 * self.output
        ca = self.exports - self.imports + (self.CA0 - (self.X0 - self.M0))
        self.ca_gdp = ca / self.GDP0
        # pension funds may sell foreign assets to finance the deficit, holding the króna up while they last
        want = pol["pension_fx_support_bn"] if self.platform() else 0.0
        self.fx_support_used = float(min(want, max(self.pension_fx_assets, 0)))
        self.pension_fx_assets = max(0.0, self.pension_fx_assets - self.fx_support_used)
        # Today the pension funds buy foreign assets every year — a steady outflow the króna carries. As far as the
        # the reform folds contributions into the state, that buying stops, which holds the króna up: counted as the
        # flow that no longer leaves. Answering the current account alone, the króna fell 22% in four years of the
        # counterfactual past for a deficit that the funds' repatriated buying would largely have covered.
        fold = float(pol.get("pension_fold", 0.0)) if self.platform() else 0.0
        kept_home = fold * m.get("pension_fx_outflow_bn", 0.0) * (self.p.get("base") or {}).get("static_scale", 1.0)
        ca_for_fx = (ca + self.fx_support_used + kept_home) / self.GDP0
        self.niip = float(self.niip + 100 * ca / max(gdp_real, 1))
        debt_ratio = self.debt / gdp_real
        controls = pol["capital_controls"] if self.platform() else 0.0
        premium = m["debt_risk_premium"] * max(0.0, debt_ratio - self.DEBT0 / self.GDP0) * (1 - controls)
        # `e` is a real exchange rate (the CPI carries the trend), so it answers inflation beyond the trend. Set
        # against partners' inflation it drifted with the trend itself — 2.5 points a year apart between a run with
        # the trend and one without, and a slow built-in depreciation even at the default.
        # The króna answers inflation net of a tax step: a VAT rise lifts the price level once and says nothing about
        # the value of the currency. Answering headline inflation, the reform's VAT step set off a 9% fall in the
        # króna, which fed more inflation and an 8% real rate — a recession made of arithmetic (found 2026-09-26).
        # With VAT unchanged the two are the same, so the status quo is untouched.
        look = m.get("policy_looks_through_tax", 1.0)
        pi_fx = (1 - look) * self.inflation + look * getattr(self, "inflation_net", self.inflation)
        dlog_e = m["fx_current_account_response"] * (self.CA0 / self.GDP0 - ca_for_fx) \
            + m["fx_inflation_passthrough"] * (pi_fx - m["trend_inflation"]) + premium \
            + m["history_like"] * m["history_fx_drift"] \
            + float((self.p.get("history") or {}).get("fx_shock", 0.0))
        # `fx_shock`: the backcast's identified capital-flow shock, the part of a year's move in the króna the current
        # account and inflation do not explain (the inflows of the 2016-17 tourism boom lifted it about a fifth).
        # Without it the model's prices ran 10% above the record by 2025 and real pay 11% below. 0 going forward.
        self.e = float(np.clip(self.e * np.exp(dlog_e), .5, 3.0))
        tariff = self.tariff()
        self.P_T = self.e * self.import_price() * (1 + tariff) / (1 + self.TARIFF0)
        vat, vat0 = soc.current_vat(), soc.p["policy"]["vat_effective_status_quo"]
        self.cpi = float(((m["w_tradable"] * self.P_T + m["w_nontradable"] * self.P_N) * self.vat_factor(vat, vat0)
                          + m["w_housing"] * self.rent) * soc.frontier.cpi_factor() * self.agriculture_price_factor()
                         * self.absorbed * self.trend())
        if m.get("freeze_prices"):
            self.e, self.P_N, self.P_T = 1.0, 1.0, self.import_price() * (1 + tariff) / (1 + self.TARIFF0)
            self.cpi = float(((m["w_tradable"] * self.P_T + m["w_nontradable"]) * self.vat_factor(vat, vat0)
                              + m["w_housing"]) * self.trend())
        # The same index with VAT at today's rate: what prices did apart from the tax itself. Denmark indexes to
        # exactly this (nettoprisindeks), and it is what a central bank means by looking through a tax change.
        old_net = getattr(self, "cpi_net", old_cpi)
        self.cpi_net = float(self.cpi / self.vat_share_factor(vat, vat0))
        self.inflation = self.cpi / old_cpi - 1
        self.inflation_net = self.cpi_net / max(old_net, 1e-9) - 1
        # Monetary policy (real rate): Taylor rule + risk premium. An inflation targeter looks through the first
        # round of a tax change — the price level steps up once and does not keep rising — and answers only what
        # follows from it through wages and expectations, which the net index still carries.
        look = m.get("policy_looks_through_tax", 1.0)
        pi = (1 - look) * self.inflation + look * self.inflation_net
        # what the bank did beyond its rule in a given year (identified in the backcast: the COVID cuts, the late
        # start in 2021-22), given to every run of that year alike, as the other identified shocks are
        rate_shock = float((self.p.get("history") or {}).get("rate_shock", 0.0))
        self.r = float(np.clip(m["real_rate0"] + m["taylor_inflation"] * (pi - m["trend_inflation"]) + m["taylor_gap"] * self.gap
                               + premium + rate_shock, -.06, .12))
        if m.get("freeze_prices"):
            self.r = m["real_rate0"]
        # What a house buyer pays is a mortgage rate, fixed for years at a time and mostly indexed, not the bank's
        # overnight rate: it moved about half as far, and later. On the policy rate the user cost of a home hit
        # its floor when real rates went to -3.7% in 2022, and house prices trebled in the backcast (2026-09-26).
        # 2.0: plus what the banks' capital and the bond market add (financial.py)
        mortgage_premium, bond_premium = financial.premium(soc)
        target = m["real_rate0"] + m.get("long_rate_passthrough", .5) * (self.r - m["real_rate0"]) + mortgage_premium
        self.r_long += (target - self.r_long) / m.get("long_rate_years", 3.0)
        # construction responds to price over cost
        trades = P.OCCUPATIONS.index("Other craft and trades")   # building costs follow the trades, not the professions
        # relative to the trend, like the house price it is set against
        build_cost = self.relative_wage_cost(soc.omega[trades]) * (1 + soc.employer_rate()) \
            / (1 + soc.p["policy"]["pension_contrib_employer"]) * fr["construction_cost_factor"]
        q = self.house_price / max(build_cost, .3)
        completions = m["construction0"] * q ** m["construction_elasticity"]
        # builders who may keep what they build, build more
        po, pol = self.p["property_ownership"], self.p["policy"]
        if self.platform() and pol["residential_ownership_cap"] < po["residential_top_share"]:
            completions *= 1 + po["developer_build_incentive"] * pol["developer_exemption"]
            if pol["developer_exemption"] and po["developer_term_years"]:
                # the exemption runs out per project, so staying at capacity means selling and building again
                completions *= 1 + po["forced_sale_build_incentive"]
        pol = soc.p["policy"]
        if pol["regime"] == "platform" and pol["public_dwellings_per_year"]:
            completions += pol["public_dwellings_per_year"] / m["dwellings0"]   # built whatever the price says
        # custodianship: dwellings left empty or derelict go back to the market and into use
        c = self.custodianship()
        if c and getattr(self, "year", 0) <= po["custodian_idle_years"]:
            completions += c * po["custodian_idle_share"] / max(po["custodian_idle_years"], 1)
        self.stock = self.stock * (1 - m["dwelling_depreciation"] * self.maintenance_factor()) + completions
        # public debt: coupons follow the rates new debt is issued at; debt accumulates deficits
        # New non-indexed debt is issued at a nominal rate — the real policy rate plus inflation — and indexed debt
        # at a long real rate that follows the policy rate only in part. Following the real rate alone, the whole
        # stock repriced to the negative real rates of 2021-22, when the nominal key rate was still 1-5% and
        # inflation 4-8%: the model's interest bill all but vanished while the record's rose (found 2026-09-26,
        # once the backcast imposed the bank's actual rate path).
        ind = m["debt_indexed_share"]
        # measured from the base year's rates: the stock keeps its base-year coupons while rates stay where they were
        i_now, i0 = self.r + self.inflation, m["real_rate0"] + self.INFLATION0
        target_n = self.coupon_n0 + (i_now - i0) + bond_premium
        target_r = self.coupon_r0 + m.get("indexed_rate_passthrough", .5) * (self.r - m["real_rate0"]) + bond_premium
        self.coupon_n += (target_n - self.coupon_n) / m["debt_maturity_years"]
        self.coupon_r += (target_r - self.coupon_r) / m["debt_maturity_years"]
        self.r_debt = (1 - ind) * self.coupon_n + ind * (self.coupon_r + self.inflation)
        self.interest = self.debt_interest(self.debt, self.coupon_n, self.coupon_r, self.inflation, ind)
        # The revenue and spending the agents do not produce — excises, customs, fees, property income; the state's
        # purchases, investment, subsidies — were held at their base-year level in real terms, while the economy
        # grew around them. Over 2015-25 both grew by about three-fifths in real terms in the record, and over thirty
        # years ahead a flat line reads as a steady, unannounced cut to the state's purchases and to its excises
        # alike. Revenue follows output; purchases follow output smoothed over the cycle, since the state does not
        # buy less in a recession. The same rule in every run.
        self.output_trend += m.get("purchases_smoothing", .3) * (self.output - self.output_trend)
        if hasattr(soc, "accounts0"):
            a0 = soc.accounts0
            rev_u = self.REVENUE0 - a0["revenue"] / a0.get("price", 1.0)
            exp_u = self.EXPENDITURE0 - self.INTEREST0 - a0["expenditure"] / a0.get("price", 1.0)
            self.unmodelled_bn = rev_u * (self.output - 1) - exp_u * (self.output_trend - 1)
        balance = balance_before_interest + self.unmodelled_bn - (self.interest - interest_ref)
        # inflation wears down the whole stock held in base-year krónur: the non-indexed part in fact, the indexed
        # part against the indexation the interest line has just paid for it
        erosion = max(self.inflation, 0)
        # a surplus can be put aside instead of repaying debt; the fund earns a real return that funds later years
        share = soc.p["policy"]["sovereign_fund_share"] if soc.p["policy"]["regime"] == "platform" else 0.0
        put_aside = max(0.0, balance) * share
        self.sovereign_fund = self.sovereign_fund * (1 + m["sovereign_fund_return"]) + put_aside
        self.erosion_bn = self.debt * erosion / (1 + erosion)
        # Net debt: once the debt is repaid, further surpluses are held as financial assets that earn what the debt
        # cost (the same coupons, with the sign turned). Floored at zero, as it was, a surplus beyond the debt
        # simply vanished and the budget of a run that repaid its debt stopped counting what it had saved.
        self.debt = self.debt / (1 + erosion) - (balance - put_aside)
        # 2.0: a year of business investment, at this year's profits and rates
        acc.update(capital.update(soc, self, soc.profit_index()))
        acc.update(financial.update(soc, self))
        return balance

    def snapshot(self):
        gdp_real = self.GDP0 * self.output          # debt and the fund are in 2025 krónur
        return {"unmodelled_growth_bn": self.unmodelled_bn,
                "pension_fx_assets": self.pension_fx_assets, "fx_support_used": self.fx_support_used,
                "cpi": self.cpi, "inflation": self.inflation, "exchange_rate": self.e, "real_rate": self.r,
                "rent_index": self.rent, "house_price_index": self.house_price, "dwelling_stock_index": self.stock,
                "exports_bn": self.exports, "imports_bn": self.imports,
                "terms_of_trade": self.terms_of_trade(), "export_prices": self.export_price_index(),
                "commercial_rent_index": getattr(self, "commercial_rent", 1.0),
                "variety_index": getattr(self, "variety", 0.0), "term_value_factor": self.term_value_factor(), "maintenance_factor": self.maintenance_factor(), "current_account_pct_gdp": 100 * self.ca_gdp,
                "debt_pct_gdp": 100 * self.debt / gdp_real, "interest_bn": self.interest,
                "output_index": self.output, "labour_gap": self.gap, "P_nontradable": self.P_N, "P_tradable": self.P_T,
                "property_tax_rate_pct": 100 * self.property_tax_rate(),
                "sovereign_fund_bn": self.sovereign_fund,
                "sovereign_fund_pct_gdp": 100 * self.sovereign_fund / gdp_real}
