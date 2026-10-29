"""2.0: the informal economy — the part of their earnings people keep off the books, and how a reform moves it.

How much is hidden. Tax evasion in Iceland has held at about 3-5% of GDP, some 100 ma.kr. in 2017 (the finance
ministry's working group on tax evasion, June 2017): VAT, income tax on employees' pay, companies' income tax and
capital income. What people can hide depends on who reports their income. In Denmark's audit experiment evasion was
0.3% of income a third party reports and 37% of income people report themselves (Kleven, Knudsen, Kreiner, Pedersen
and Saez 2011, Econometrica). So the share of earnings kept off the books here is `self_share` for the
self-employed and founders, and `employee_share` for employees — cash work no employer reports (EST).

What moves it. The gain from hiding a króna is what declaring it would cost: income tax, contributions and the
benefit it would withdraw, which today can take most of it. The share hidden rises with that marginal rate, with
elasticity `elasticity` (EST from Clotfelter 1983, 0.5-0.8 on the US audits; Kleven et al. find the response to the
rate small against that to third-party reporting), and is damped by the norm that keeps most people honest, which
is in the levels. A payment that is not means-tested removes the withdrawal; higher flat rates raise the tax.

Against what. Each person is set against themselves under today's rules on the same earnings, so the status quo
is its own reference and nothing in it changes: the record's incomes are declared incomes. Under a reform, earnings
that come onto the books pay tax and leave less in hand; earnings that go off them do the reverse. The work itself
and the output it makes do not change.

Not modelled: people out of work who work off the books while claiming (the commonest case of benefit fraud), VAT
and companies' evasion (left in the enforcement section's 200 ma.kr.), and detection: the enforcement lever acts on
the static evasion figure, not on this.
"""
import numpy as np

from ubisim.abm import policy as pol_rules
from ubisim.abm.population import INDEP, VENTURE

STEP = .05     # a 5% rise in earnings, to read the marginal rate off the rules


def _marginal(A, idx, gross, working, p, pinc, price, bx):
    """The share of a little more pay that tax, contributions and withdrawn benefits take, person by person."""
    lo = pol_rules.net_income(A, idx, gross, working, p, pinc, price, bx)["net"]
    hi = pol_rules.net_income(A, idx, gross * (1 + STEP), working, p, pinc, price, bx)["net"]
    return np.clip(1 - (hi - lo) / np.maximum(gross * STEP, 1.0), 0.0, 1.0)


def shares(c, m, self_reported):
    """The share of earnings hidden at marginal rate m."""
    base = np.where(self_reported, c["self_share"], c["employee_share"])
    return np.clip(base * (np.maximum(m, 1e-3) / c["reference_rate"]) ** c["elasticity"], 0.0, c["max_share"])


def tax_change(soc, idx, gross, working, pinc):
    """The tax a reform's change in hidden earnings brings in, a month per person (positive: more declared), and the
    earnings hidden under today's rules and under the reform's."""
    c = soc.p.get("informal") or {}
    zero = np.zeros(len(idx))
    if not c or soc.p["policy"]["regime"] != "platform":
        return zero, zero, zero
    A, p = soc.A, soc.p
    on = working & (gross > 0)
    if not on.any():
        return zero, zero, zero
    j = idx[on]
    g = gross[on]
    bx = soc.benefit_index()
    sq = {**p, "policy": {**p["policy"], "regime": "status_quo"}}
    m_now = _marginal(A, j, g, working[on], p, pinc[on], soc.price, bx)
    m_sq = _marginal(A, j, g, working[on], sq, pinc[on], soc.price, bx)
    self_rep = A["self_employed"][j] | np.isin(A["status"][j], [INDEP, VENTURE])
    s_now, s_sq = shares(c, m_now, self_rep), shares(c, m_sq, self_rep)
    out, hid_now, hid_sq = zero.copy(), zero.copy(), zero.copy()
    # what comes onto the books pays the reform's marginal rate; what goes off saves it
    out[on] = (s_sq - s_now) * g * m_now
    hid_now[on], hid_sq[on] = s_now * g, s_sq * g
    return out, hid_now, hid_sq


def status_quo_hidden(soc, idx, gross, working, pinc):
    """Earnings hidden under today's rules, a month per person (for the status quo's own report)."""
    c = soc.p.get("informal") or {}
    if not c:
        return np.zeros(len(idx))
    on = working & (gross > 0)
    out = np.zeros(len(idx))
    if on.any():
        j = idx[on]
        m = _marginal(soc.A, j, gross[on], working[on], soc.p, pinc[on], soc.price, soc.benefit_index())
        self_rep = soc.A["self_employed"][j] | np.isin(soc.A["status"][j], [INDEP, VENTURE])
        out[on] = shares(c, m, self_rep) * gross[on]
        soc.informal_rate_sq = float((m * gross[on]).sum() / gross[on].sum())
    return out
