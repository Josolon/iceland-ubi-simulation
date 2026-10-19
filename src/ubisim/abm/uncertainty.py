"""Ranges for the estimated (EST) parameters, used by the Monte Carlo runner.

Each entry: dotted parameter path -> (low, high). Draws are uniform on the range, via Latin hypercube sampling.
Ranges express current uncertainty, not confidence intervals; narrow them as data arrives.

The labour-supply elasticity changes the calibration, so it is sampled on a few pre-calibrated levels instead.
"""
import numpy as np

ELASTICITY_LEVELS = [0.15, 0.25, 0.40]

RANGES = {
    # labour market
    "labour.demand_elasticity": (0.4, 1.2),
    "behaviour.independent_leisure_cost": (0.25, 0.85),
    "labour.renewal_bargaining": (0.6, 1.0),      # how fully a renewal moves to the market wage
    "labour.stability_value": (0.15, 0.60),       # what a secure contract is worth to a worker
    "labour.offer_length_sensitivity": (3.0, 10.0),  # how strongly a shortage lengthens the contracts offered
    "labour.occupational_mobility": (0.01, 0.06),
    "labour.export_cost_elasticity": (0.3, 1.0),
    # prices, króna, money
    "markets.labour_cost_passthrough": (0.6, 1.0),
    "markets.demand_pressure_passthrough": (0.2, 0.8),
    "markets.price_adjustment": (0.4, 0.8),
    "markets.export_price_elasticity": (0.5, 1.2),
    "markets.import_income_elasticity": (0.8, 1.4),
    "markets.import_price_elasticity": (0.3, 1.0),
    "markets.fx_current_account_response": (0.4, 1.2),
    "markets.fx_inflation_passthrough": (0.3, 0.8),
    "markets.taylor_inflation": (0.3, 1.0),
    "markets.debt_risk_premium": (0.02, 0.10),
    # housing
    "markets.housing_price_elasticity": (0.3, 0.8),
    "markets.housing_income_elasticity": (0.4, 0.9),
    "markets.construction_elasticity": (0.8, 2.0),
    # households
    "wealth.mpc_top": (0.70, 0.88),
    "wealth.mpc_bottom": (0.92, 1.00),
    "wealth.mpc_liquid_wealth": (0.02, 0.06),
    "wealth.consumption_rate_sensitivity": (0.5, 3.0),
    # migration, ventures, fertility
    "migration.immigration_income_elasticity": (0.5, 1.5),
    "migration.emigration_income_elasticity": (0.8, 2.0),
    "ventures.entry_selection_elasticity": (0.1, 0.5),
    "ventures.profit_scale": (1.5e6, 4.0e6),
    "demography.fertility_income_elasticity": (0.1, 1.0),
    # sectors
    "fisheries.labour_cost_elasticity": (0.05, 0.4),
    "energy.smelter_price_usd_mwh": (28.0, 42.0),
    "energy.contract_compensation_bn": (50.0, 300.0),
}


def latin_hypercube(n, rng):
    """n draws: dict of dotted path -> value, plus the elasticity level index."""
    k = len(RANGES)
    cells = np.array([rng.permutation(n) for _ in range(k + 1)]).T
    u = (cells + rng.random((n, k + 1))) / n
    draws = []
    for i in range(n):
        d = {path: lo + (hi - lo) * u[i, j] for j, (path, (lo, hi)) in enumerate(RANGES.items())}
        d["behaviour.target_extensive_elasticity"] = ELASTICITY_LEVELS[int(u[i, k] * len(ELASTICITY_LEVELS))]
        draws.append(d)
    return draws


def as_overrides(draw):
    out = {}
    for path, value in draw.items():
        if path.startswith("behaviour."):
            continue
        section, key = path.split(".", 1)
        out.setdefault(section, {})[key] = float(value)
    return out
