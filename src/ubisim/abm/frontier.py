"""Frontier programmes: state-funded automation built on Iceland's power, water and sea.

Each programme is a switchable public investment. While it is being built the state pays capital costs; once
running it uses electricity, employs relatively few people, produces exports or replaces imports, and in some
cases changes the cost structure of a whole sector (food prices, fisheries labour, building costs).

Numbers are deliberately round EST magnitudes: these are policy options, not engineering estimates. Each
programme's parameters sit in params.py ("frontier"), so they can be argued with and swept in the Monte Carlo.
"""
import numpy as np

from ubisim.abm import params as P
from ubisim.abm.params import N_OCC


class Frontier:
    def __init__(self, p):
        self.p = p
        self.weights = [pr["weight"] or 0 for pr in P.PROFESSIONS]
        self.state = {}
        self.update(0)

    def enabled(self):
        pol = self.p["policy"]
        if pol["regime"] != "platform":
            return []
        return [n for n in pol["frontier_programmes"] if n in self.p["frontier"]["programmes"]]

    def progress(self, prog, year):
        """0 → 1 as a programme is built, after its start year."""
        start, build = prog["start_year"], max(1, prog["build_years"])
        return float(np.clip((year - start + 1) / build, 0, 1)) if year >= start else 0.0

    def update(self, year):
        f = self.p.get("frontier", {})
        scale = f.get("scale", 1.0)
        out = {"capex_bn": 0.0, "exports_bn": 0.0, "import_substitution_bn": 0.0, "state_return_bn": 0.0,
               "twh": 0.0, "fte": 0.0, "jobs_by_occ": np.zeros(N_OCC), "food_price_factor": 1.0,
               "construction_cost_factor": 1.0, "fisheries_labour_factor": 1.0, "fisheries_revenue_factor": 1.0,
               "active": []}
        for name in self.enabled():
            prog = f["programmes"][name]
            r = self.progress(prog, year) * scale
            if r <= 0:
                continue
            out["active"].append(name)
            building = year < prog["start_year"] + prog["build_years"]
            out["capex_bn"] += prog["capex_bn_per_year"] * scale if building else prog["upkeep_bn_per_year"] * r
            out["exports_bn"] += prog["exports_bn"] * r
            out["import_substitution_bn"] += prog["import_substitution_bn"] * r
            out["state_return_bn"] += prog["state_return_bn"] * r * f.get("success_rate", 1.0)
            out["twh"] += prog["twh"] * r
            out["fte"] += prog["fte"] * r
            mix = np.array(P.expand_mix(prog["occupation_mix"], self.weights), float)
            out["jobs_by_occ"] += prog["fte"] * r * mix / mix.sum()
            out["food_price_factor"] *= 1 - prog.get("food_price_cut", 0) * r
            out["construction_cost_factor"] *= 1 - prog.get("construction_cost_cut", 0) * r
            out["fisheries_labour_factor"] *= 1 - prog.get("fisheries_labour_cut", 0) * r
            out["fisheries_revenue_factor"] *= 1 + prog.get("fisheries_revenue_gain", 0) * r
        self.state = out
        return out

    def cpi_factor(self):
        """Effect on consumer prices: cheaper food feeds straight into the basket (food is 15.4% of the CPI)."""
        food_weight = self.p["markets"]["cpi_food_weight"]
        return 1 - food_weight * (1 - self.state["food_price_factor"])


class Infrastructure(Frontier):
    """Public works: tunnels, a rail link to Keflavík, light rail in the city, a railway around the country.

    They behave differently from the frontier programmes. There is no export revenue and no state return — the
    payback is travel time, which shows up as productivity once a thing is finished, plus the construction work
    while it is being built. Ordinary road building is not modelled: it continues at about the same level either
    way, so it nets out of any comparison.
    """

    def enabled(self):
        pol = self.p["policy"]
        if pol["regime"] != "platform":
            return []
        return [n for n in pol["infrastructure_programmes"] if n in self.p["infrastructure"]["programmes"]]

    def update(self, year):
        f = self.p.get("infrastructure", {})
        scale = f.get("scale", 1.0)
        out = {"capex_bn": 0.0, "fte": 0.0, "jobs_by_occ": np.zeros(N_OCC), "productivity_gain": 0.0,
               "construction_cost_factor": 1.0, "active": [], "finished": []}
        for name in self.enabled():
            prog = f["programmes"][name]
            r = self.progress(prog, year) * scale
            if r <= 0:
                continue
            out["active"].append(name)
            building = year < prog["start_year"] + prog["build_years"]
            out["capex_bn"] += prog["capex_bn_per_year"] * scale if building else prog["upkeep_bn_per_year"] * r
            out["fte"] += prog["fte"] * r if building else 0.0
            if building:
                mix = np.array(P.expand_mix(prog["occupation_mix"], self.weights), float)
                out["jobs_by_occ"] += prog["fte"] * r * mix / mix.sum()
            else:
                out["finished"].append(name)
            # the travel time only starts paying once the thing is actually open
            out["productivity_gain"] += prog.get("productivity_gain", 0) * (r if not building else 0.0)
            out["construction_cost_factor"] *= 1 - prog.get("construction_cost_cut", 0) * r
        self.state = out
        return out
