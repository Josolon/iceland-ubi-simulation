"""Fisheries and energy (hydropower + aluminium smelters) as real sectors.

Both sectors earn in foreign currency, employ people in specific occupations, generate resource rent and exports,
and respond to the króna and to domestic wage costs. The reform levers act here: quota leases capture fisheries
rent; smelter contracts are wound down and the freed power is reallocated to alternative uses.

Base data (bn ISK, 2025 prices unless noted):
  Fisheries (Hagstofa SJA08109, fishing + processing, 2023): revenue 303.6, intermediate 79.3, compensation 113.5,
    EBITDA 110.8, depreciation 19.0, 6% cost of capital 38.0 → profit after capital cost 72.8
  Electricity: production 19.6 TWh (Orkustofnun 2024), smelters ~12.9 TWh (~65%)
  Aluminium + silicon exports 442 bn (23% of exports, Hagstofa 2024); Landsvirkjun core profit ~36 bn (2025)
Estimates are marked EST in params.py ("fisheries", "energy").
"""
import numpy as np

from ubisim.abm import params as P
from ubisim.abm.params import N_OCC

USD_ISK = 138.0


class Sectors:
    def __init__(self, p):
        self.p = p
        f, e = p["fisheries"], p["energy"]
        w = [pr["weight"] or 0 for pr in P.PROFESSIONS]
        # fisheries jobs sit with fishers and fish processing; the rest spread across their groups by size
        self.fish_mix = np.array(P.by_name({"Fishers and farm workers": .45, "Fish processing workers": .30,
                                            "Other machine operators": .10, "Other elementary": .08,
                                            "Other craft and trades": .04, "Managers": .03}))
        self.fish_mix /= self.fish_mix.sum()
        self.smelter_mix = np.array(P.expand_mix(e["smelter_occupation_mix"], w))
        self.alt_mix = np.array(P.expand_mix(e["alternative_occupation_mix"], w))
        self.windfall_mix = np.array(P.expand_mix((p.get("windfall") or P.DEFAULTS["windfall"])["occupation_mix"], w))
        self.state = {}
        self.update(year=0, fx=1.0, wage_index=np.ones(N_OCC), p_nontradable=1.0, real_rate=p["markets"]["real_rate0"])
        self.base = dict(self.state)

    def platform(self):
        return self.p["policy"]["regime"] == "platform"

    # ------------------------------------------------------------------ fisheries
    def fisheries(self, fx, wage_index, p_nontradable, real_rate, frontier=None):
        f = self.p["fisheries"]
        labour_factor = frontier["fisheries_labour_factor"] if frontier else 1.0
        revenue_factor = frontier["fisheries_revenue_factor"] if frontier else 1.0
        w = float((self.fish_mix * wage_index).sum())
        # what the world pays for fish sets what the catch earns, and so the rent a quota lease can capture
        marine = float(self.p["trade"]["price"]["marine"])
        revenue = f["revenue0"] * fx * f["catch_index"] * revenue_factor * marine
        # fuel, gear and the rest bought abroad cost what the world charges for them, in krónur
        imported = fx * float(self.p["trade"]["import_price"])
        intermediate = f["intermediate0"] * (f["imported_input_share"] * imported
                                             + (1 - f["imported_input_share"]) * p_nontradable)
        # processing labour responds (weakly) to wage costs relative to world prices
        labour = (w / fx) ** (-f["labour_cost_elasticity"])
        compensation = f["compensation0"] * w * labour * labour_factor
        capital_cost = f["capital_cost0"] * (1 + (real_rate - self.p["markets"]["real_rate0"]) / .06)
        rent = revenue - intermediate - compensation - capital_cost  # EBITDA less a 6% normal return (SJA08109 definition)
        capture = f["rent_capture"] if self.platform() else f["rent_capture_status_quo"]
        fee = capture * max(rent, 0.0)
        return {"fish_revenue": revenue, "fish_rent": rent, "fish_fee": fee,
                # exports at 2025 world prices: the price itself is carried by the export price index
                "fish_exports": revenue / max(marine, .2) * f["export_share"],
                "fish_fte": f["fte0"] * labour * labour_factor}

    # ------------------------------------------------------------------ energy
    def energy(self, year, fx):
        e = self.p["energy"]
        exit_share = e["smelter_exit_share"] if self.platform() else 0.0
        start, dur = e["exit_start_year"], max(1, e["exit_years"])
        wound_down = exit_share * float(np.clip((year - start + 1) / dur, 0, 1)) if year >= start else 0.0
        smelter_twh = e["smelter_twh0"] * (1 - wound_down)
        freed = e["smelter_twh0"] - smelter_twh
        # power revenue (USD) and exports
        # part of the smelter power contracts is linked to the aluminium price
        al = float(self.p["trade"]["price"]["aluminium"])
        power_revenue_usd = smelter_twh * e["smelter_price_usd_mwh"] * (1 + e["aluminium_price_link"] * (al - 1))
        alt_twh = alt_revenue_usd = alt_exports = alt_fte = 0.0
        for use in e["alternative_uses"]:
            ramp = float(np.clip((year - start + 1) / max(1, use["ramp_years"]), 0, 1)) if year >= start else 0.0
            twh = min(freed * use["share"], e["smelter_twh0"] * exit_share * use["share"] * ramp)
            alt_twh += twh
            alt_revenue_usd += twh * use["price_usd_mwh"]
            alt_exports += twh * use["net_export_bn_per_twh"]
            alt_fte += twh * use["jobs_per_twh"]
        power_revenue = (power_revenue_usd + alt_revenue_usd) * 1e6 * USD_ISK / 1e9 * fx  # TWh = 1e6 MWh → bn ISK
        generation_cost = (smelter_twh + alt_twh) * e["generation_cost_usd_mwh"] * 1e6 * USD_ISK / 1e9
        smelter_exports = smelter_twh * e["smelter_net_export_bn_per_twh"] * fx
        compensation = 0.0
        if self.platform() and exit_share > 0 and start <= year < start + dur:
            compensation = e["contract_compensation_bn"] * exit_share / dur
        return {"smelter_twh": smelter_twh, "alt_twh": alt_twh, "spilled_twh": freed - alt_twh,
                "energy_rent": power_revenue - generation_cost, "energy_exports": smelter_exports + alt_exports * fx,
                "smelter_fte": e["smelter_fte0"] * smelter_twh / e["smelter_twh0"], "alt_fte": alt_fte,
                "contract_compensation": compensation}

    # ------------------------------------------------------------------ a resource windfall (params "windfall")
    def windfall(self, year, fx):
        w = self.p.get("windfall") or P.DEFAULTS["windfall"]
        ramp = float(np.clip((year - w["start_year"] + 1) / max(1, w["ramp_years"]), 0, 1)) if w["rent_bn"] else 0.0
        rent = w["rent_bn"] * ramp * fx          # sold abroad, so worth more in krónur when the króna is weak
        return {"windfall_rent": rent, "windfall_take": w["state_take"] * rent,
                "windfall_exports": w["rent_bn"] * ramp / max(w["rent_share_of_revenue"], .1) * fx,
                "windfall_fte": w["fte_per_100bn"] * w["rent_bn"] * ramp / 100}

    # ------------------------------------------------------------------ yearly
    def update(self, year, fx, wage_index, p_nontradable, real_rate, frontier=None):
        self.state = {**self.fisheries(fx, wage_index, p_nontradable, real_rate, frontier), **self.energy(year, fx),
                      **self.windfall(year, fx)}
        self.year = year
        return self.state

    def agri_startup_fte(self):
        """Work in the agricultural start-ups RANNÍS funds from redirected farm support, once they are running."""
        ag, pol = self.p["agriculture"], self.p["policy"]
        if not self.platform() or not pol["agriculture_subsidy_cut"]:
            return 0.0
        per_year = ag["startup_bn"] * 1e3 / ag["startup_grant_m"] * min(1.0, pol["agriculture_subsidy_cut"] / .5)
        running = max(0, getattr(self, "year", 0) - ag["startup_years"] + 1)
        return per_year * running * ag["startup_survival"] * ag["startup_fte"]

    def job_change_by_occupation(self):
        """FTE demand change vs the 2025 base, by occupation (feeds labour demand)."""
        s, b = self.state, self.base
        farm = np.zeros(N_OCC)
        if self.platform():
            ag = self.p["agriculture"]
            pol, lk = self.p["policy"], self.p["links"]
            share = ag["jobs_lost_at_full_cut"] * pol["agriculture_subsidy_cut"] \
                + lk["farm_jobs_lost_without_customs"] * (1 - pol["customs_kept"])
            farm[P.OCCUPATIONS.index("Fishers and farm workers")] = -ag["fte0"] * min(share, .8) \
                + self.agri_startup_fte()
            # upkeep as the condition of holding property is work for the trades
            cust = float(pol.get("custodianship", 0.0))
            farm[P.OCCUPATIONS.index("Other craft and trades")] += lk["custodian_upkeep_fte"] * cust
        return (s["fish_fte"] - b["fish_fte"]) * self.fish_mix \
            + (s["smelter_fte"] - b["smelter_fte"]) * self.smelter_mix + (s["alt_fte"] - b["alt_fte"]) * self.alt_mix \
            + (s["windfall_fte"] - b["windfall_fte"]) * self.windfall_mix + farm

    def fiscal(self):
        """Change vs base in public revenue (bn ISK): quota fees, state energy dividends; and compensation cost."""
        s, b = self.state, self.base
        payout = self.p["energy"]["state_dividend_share"]
        return {"fisheries_fee": s["fish_fee"], "energy_dividend_change": payout * (s["energy_rent"] - b["energy_rent"]),
                "contract_compensation": s["contract_compensation"],
                "windfall_take": s["windfall_take"] - b["windfall_take"]}

    def exports_change(self):
        s, b = self.state, self.base
        return (s["fish_exports"] - b["fish_exports"]) + (s["energy_exports"] - b["energy_exports"]) \
            + (s["windfall_exports"] - b["windfall_exports"])
