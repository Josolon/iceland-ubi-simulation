"""2.0: the business capital stock — what firms invest, and what more or less of it does to output per hour.

What there is. At the end of 2025 the business sector held 6,540 ma.kr. of fixed capital at current prices, 1.32
times GDP, and wrote off 576 ma.kr. of it, 8.8% (Statistics Iceland THJ03204, net stock at replacement cost, and
consumption of fixed capital). It grew 3.1% a year in real terms over 2015-25. Business investment ran at 11.4-17.7%
of GDP over 2016-25 and 17.7% in 2025 (THJ03106 against THJ01102). Homes are in the housing market and the state's
capital in its accounts; this is the rest.

How it moves. Firms invest to replace what wears out and to grow as they expect the economy to, and more or less as capital pays
more or less than it costs (Tobin's q, as in Hayashi 1982): the return after corporate tax on a króna of capital,
against the real interest rate plus depreciation plus the premium owners ask for risk, times the price of capital goods (dearer by the VAT a firm can no
longer reclaim, where a reform restricts refunds to value-chain inputs), each set against its value in
the base year. `adjustment` says how far a gap of one in q moves investment as a share of the stock in a year (EST,
0.1-0.15 from the q-literature's slow adjustment, e.g. Chirinko 1993: investment answers q weakly and with lags),
and what is put in place in a year was decided `build_years` before it (time to build: Kydland and Prescott 1982;
Koeva 2000 finds about two years from decision to completion on average).

What it does. Output per hour rises with capital per unit of labour with elasticity `elasticity`, capital's share
of income (EST, 0.33). Fewer hours worked need less capital: profits fall with output, q with them, and the stock
follows the hours down without costing output per hour. The status quo's own path carries capital's growth in the productivity trend, so a run is set against
its reference: a reform's capital against the status quo's in the same year. The status quo is set against itself
and nothing in it changes. Less capital also means more profit on each króna left, so the gap closes over time.

Not modelled: investment as demand (it is spent in part at home), the housing and public stock (each has its own
part of the model), and capital from abroad beyond what the real rate already carries.
"""


def ensure(mk):
    """The state at the start of a run: the base year's stock, in units of itself."""
    st = getattr(mk, "capital", None)
    if st is None:
        st = mk.capital = {"K": 1.0, "invest": 0.0, "q": 1.0, "factor": 1.0}
    return st


def _tax(soc):
    """The corporate tax rate firms pay on their profits, as in corporate_tax_economy."""
    p = soc.p
    if p["policy"]["regime"] != "platform":
        return p["capital"]["tax0"]
    covered = getattr(soc, "public_equity", {}).get("coverage", 0.0)
    kept = p["policy"].get("staked_corporate_tax_share", 1.0)
    return p["policy"]["corporate_tax_rate"] * (1 - covered * (1 - kept))


def vat_wedge(soc):
    """What VAT adds to the price of capital goods to firms: nothing today, when it is reclaimed; under the
    restriction of refunds to value-chain inputs, capital goods are not among them (every variant of the estimate),
    so they bear the reform's VAT as far as the lever applies the restriction."""
    pol = soc.p["policy"]
    if pol["regime"] != "platform":
        return 0.0
    share = pol["vat_input_restriction_gain"] / max(pol.get("vat_input_restriction_full_bn", 459.5), 1.0)
    return float(pol["vat_platform"] * share)


def investment_against_reference(soc):
    """Last year's business investment against the reference's: what the restricted VAT on capital goods is paid on."""
    ref = soc.reference_prev()
    own = soc.own_history[-1].get("business_investment_bn") if soc.own_history else None
    theirs = ref.get("business_investment_bn") if ref else None
    return float(own / theirs) if own and theirs else 1.0


def factor(mk):
    """Output per hour against the reference path's, from capital per worker: 1 in the status quo."""
    return ensure(mk)["factor"]


def set_factor(soc, mk):
    """At the start of a year: this run's capital per unit of labour against the reference's (the status-quo run's,
    a year behind as the other reference values are), raised to capital's share. Capital that falls in step with
    the hours worked leaves output per hour where it was."""
    c = soc.p.get("capital") or {}
    st = ensure(mk)
    if not c or not soc.reference:
        st["factor"] = 1.0
        return
    ref = soc.reference_prev()
    k_ref = ref.get("capital_per_labour") if ref else None
    own = soc.own_history[-1].get("capital_per_labour") if soc.own_history else None
    st["factor"] = float((own / k_ref) ** c["elasticity"]) if k_ref and own else 1.0


def _trend_growth(soc, mk, c):
    """What firms expect the economy to grow at. It starts at the record's 3.1% and moves each year a part of the
    way to the growth of the status quo's trend (output smoothed over the cycle). A reform reads the status quo's
    expectation of the same year: its own changes reach investment through q, and its own trend would count them
    twice."""
    h = soc.reference
    if h and len(h) >= soc.year and "capital_growth" in h[soc.year - 1]:
        return float(h[soc.year - 1]["capital_growth"])
    last = soc.own_history[-1] if soc.own_history else {}
    g = last.get("capital_growth", c["growth"])
    seen = mk.output_trend / last["output_trend"] - 1 if last.get("output_trend") else g
    return g + c["expectation_speed"] * (seen - g)


def update(soc, mk, profit_index):
    """A year of investment at the end of the year. `profit_index` is the corporate sector's profits against the
    base year's (1 there). Returns investment and the stock in ma.kr. of 2025."""
    c = soc.p.get("capital") or {}
    st = ensure(mk)
    if not c:
        return {}
    d, rho = c["depreciation"], c["risk_premium"]
    g = _trend_growth(soc, mk, c)
    # the return after tax on a króna of capital, and what it costs, each against the base year's
    ret = (1 - _tax(soc)) * profit_index / max(st["K"], 1e-6) / (1 - c["tax0"])
    cost = (mk.r_long + d + rho) * (1 + vat_wedge(soc)) / (c["real_rate0"] + d + rho)
    st["q"] = float(ret / max(cost, 1e-6))
    # what is put in place this year was decided `build_years` back: it takes time to build
    st.setdefault("decided", [])
    st["decided"].append(st["q"])
    q = st["decided"][-1 - int(c.get("build_years", 0))] if len(st["decided"]) > c.get("build_years", 0) else 1.0
    rate = max(0.0, d + g + c["adjustment"] * (q - 1))
    st["invest"] = rate * st["K"]
    st["K"] = st["K"] * (1 - d) + st["invest"]
    k0 = c["stock_to_gdp"] * mk.GDP0
    return {"capital_k": st["K"], "capital_per_labour": st["K"] / max(getattr(mk, "labour_input", 1.0), 1e-6),
            "capital_q": st["q"], "capital_growth": g, "output_trend": float(mk.output_trend), "capital_stock_bn": st["K"] * k0,
            "business_investment_bn": st["invest"] * k0}


def snapshot(mk):
    st = getattr(mk, "capital", None)
    if not st:
        return {}
    return {"capital_q": float(st["q"]), "capital_factor": float(st["factor"])}
