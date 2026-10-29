"""2.0: the pension funds' balance sheet — assets against the rights already earned, and the rule that settles a gap.

What the funds hold and owe. At the end of 2025 the mutual (samtrygging) divisions held 7,854 ma.kr. and owed
9,090 ma.kr. in rights already earned, valued at the law's 3.5% real rate (Central Bank of Iceland, pension fund
statistics, part III a). Almost all of the gap is in the divisions an employer guarantees — the state's LSR B and
the municipal Brú divisions, closed to new members since 1997-98: 345 ma.kr. of assets against 1,485 of rights, the
rest paid by the state and municipalities as it falls due (57 ma.kr. of special payments in 2025). The funds no
employer guarantees held 7,528 against 7,606, a gap of 1.0%.

How it moves. Each year a pool's assets earn the funds' real return (3.81%, the geometric mean of 1997-2025) and
take in contributions, and pay out pensions; its rights grow at the 3.5% they are valued at, by what this year's
contributions buy, and fall by what is paid. Contributions buy rights at their value (the funds' tables are set so
they do), so the gap moves with the return against 3.5% and with nothing else the model knows: ageing is priced in.

The rule. A fund whose total position — assets and the present value of its members' future contributions against
the rights earned and to be earned — is out by more than 10%, or by more than 5% five years running, must change its
rules (law 129/1997, 39. gr.). Here it restores the balance by cutting or raising
everyone's rights alike — pensions now paid and pensions to come — unless the state covers the shortfall instead
(`state_cover`, a budget cost). Guaranteed rights are never cut: the employer pays.

The reform. As far as the pension system is folded into the scheme (policy.pension_fold) the rights end and the
state takes the returns on the matching share of the assets; pensions already earned stay in the funds where
policy.pension_keep_earned says so. The state's special payments end with what they pay for (`guarantee_saving`):
57 ma.kr. a year to the guaranteed divisions as their rights end, 13 to LSR A and for disability equalisation as
contributions stop.

Payouts and contributions follow the model's own: each is the 2025 record times the model's flow against its
base year's, so the ledger moves with the population, its pay and the reform's rules.

Not modelled: the funds' own costs, a future position out of balance (LIVE's was -4.7% of its future
contributions in 2025, from an accrual table the fund means to replace), mortality beyond what the funds'
tables project, and each fund on its own — one pool stands for 20-odd funds.
"""
import numpy as np


def _cancelled(p):
    """Share of the rights the reform ends: folded in, and not kept in the funds."""
    pol = p["policy"]
    if pol["regime"] != "platform":
        return 0.0
    return float(pol.get("pension_fold", 1.0) * (1 - pol.get("pension_keep_earned", 0.0)))


def _contribution_share(p):
    """Share of today's contributions that still reach the funds."""
    pol = p["policy"]
    if pol["regime"] != "platform":
        return 1.0
    return float(1 - pol.get("pension_fold", 1.0))


def ensure(soc):
    """Set up the ledger at the end of 2025, once."""
    if getattr(soc, "pension_ledger", None) is not None:
        return soc.pension_ledger
    c = soc.p.get("pensions") or {}
    soc.pension_ledger = {} if not c else {
        "A": c["assets_free"], "L": c["rights_free"], "Ag": c["assets_guaranteed"], "Lg": c["rights_guaranteed"],
        "taken": 0.0, "gone": 0.0, "gaps": [], "accrued": [], "factor": 1.0, "cut": 0.0, "support": 0.0,
        "saved": 0.0, "special": 0.0}
    return soc.pension_ledger


def _end_rights(L, gone):
    """The reform ends rights as far as it folds them in; the transition can raise the share year by year. The
    state takes the returns on the assets that backed them."""
    if gone <= L["gone"]:
        return
    k = (1 - gone) / (1 - L["gone"]) if L["gone"] < 1 else 0.0
    L["taken"] += (L["A"] + L["Ag"]) * (1 - k)
    for key in ("A", "L", "Ag", "Lg"):
        L[key] *= k
    L["gone"] = gone


def _return(soc, c):
    path = c.get("return_path")
    if path and soc.year - 1 < len(path):
        return float(path[soc.year - 1])
    return float(soc.p["policy"]["pension_fund_real_return"])


def update(soc, acc):
    """A year of the ledger, from this year's accounts; returns (state support, special payments saved), 2025 kr."""
    L = ensure(soc)
    c = soc.p.get("pensions") or {}
    if not L:
        return 0.0, 0.0
    ref = soc.accounts0
    price, price0 = max(acc.get("price", soc.price), .1), max(ref.get("price", 1.0), .1)
    # the record's flows times the model's own against its base year
    paid = c["payouts_2025"] * (acc["occupational_pensions"] / price) / max(ref["occupational_pensions"] / price0, 1e-9)
    wage = acc["labour_income_real"] / max(ref["labour_income_real"], 1e-9)
    contrib = c["contributions_2025"] * wage * _contribution_share(soc.p)
    r, d = _return(soc, c), c["discount_rate"]
    sg = c["guaranteed_payout_share"]
    gone = _cancelled(soc.p)
    L["taken"] *= 1 + r
    _end_rights(L, gone)
    # the guaranteed divisions: the employer pays what the assets do not
    pg = paid * sg
    special = c["special_guaranteed_2025"] * (1 - gone)
    L["Ag"] = L["Ag"] * (1 + r) + special - pg
    L["Lg"] = max(L["Lg"] * (1 + d) - pg, 0.0)
    # the rest
    pf = paid - pg
    L["A"] = L["A"] * (1 + r) + contrib - pf
    # contributions buy rights at the table as cut or raised so far
    L["L"] = max(L["L"] * (1 + d) + contrib * L["factor"] - pf, 0.0)
    L["cut"] = L["support"] = 0.0
    # The law's test is the total position: the accrued one with the future contributions of today's members and
    # the rights they will buy (LIVE's review for 2025: 742 ma.kr. of future contributions, 46% of its accrued
    # rights, against 777 of future rights). The future part is taken as balanced, so it dampens the accrued gap;
    # it goes as contributions to the funds stop. After a cut the same contributions buy fewer rights, and the
    # future part holds what the cut saved.
    F = c["future_share"] * L["L"] * _contribution_share(soc.p)
    total = lambda: (L["A"] + F - L["L"] - F * L["factor"]) / (L["L"] + F) if L["L"] > 0 else 0.0
    gap = total()
    L["gaps"].append(gap)
    run = L["gaps"][-c["persistent_years"]:]
    persistent = len(run) == c["persistent_years"] and (all(g < -c["gap_persistent"] for g in run)
                                                        or all(g > c["gap_persistent"] for g in run))
    if L["L"] > 0 and (abs(gap) > c["gap_now"] or persistent):
        ro = c["restore_to"]
        if gap < ro and c.get("state_cover", 0.0):
            L["support"] = c["state_cover"] * ((1 + ro) * (L["L"] + F) - L["A"] - F)
            L["A"] += L["support"]
        # rights accrued and to come alike, so that the total position comes back to `restore_to`
        k = (L["A"] + F) / ((L["L"] + F * L["factor"]) * (1 + ro))
        L["L"] *= k
        L["cut"] = 1 - k
        L["factor"] *= k
        L["gaps"][-1] = total()
        # the pensions paid now, from the part of them the free funds pay
        A = soc.A
        A["occ_pension"] *= (1 - sg) * k + sg
    L["accrued"].append(L["A"] / L["L"] - 1 if L["L"] > 0 else 0.0)
    # the state's special payments end with the rights they pay for: to the guaranteed divisions as far as their
    # rights end, and to LSR A and for disability equalisation as far as contributions stop
    L["saved"] = (c["special_guaranteed_2025"] * gone + c["special_free_2025"] * (1 - _contribution_share(soc.p))) \
        * c.get("guarantee_saving", 1.0)
    L["special"] = special
    return L["support"], L["saved"]


def new_pension_factor(soc):
    """What a pension set at 67 is worth after the cuts or raises so far (the guaranteed part is never cut)."""
    L = getattr(soc, "pension_ledger", None) or {}
    if not L:
        return 1.0
    sg = soc.p["pensions"]["guaranteed_payout_share"]
    return (1 - sg) * L["factor"] + sg


def snapshot(soc):
    L = getattr(soc, "pension_ledger", None) or {}
    if not L:
        return {}
    return {"pension_assets_bn": float(L["A"]), "pension_rights_bn": float(L["L"]),
            "pension_position": float(L["gaps"][-1]) if L["gaps"] else 0.0,      # the law's total position
            "pension_position_accrued": float(L["accrued"][-1]) if L["accrued"] else 0.0,
            "pension_rights_factor": float(L["factor"]), "pension_rights_cut": float(L["cut"]),
            "pension_state_support_bn": float(L["support"]),
            "pension_guaranteed_unfunded_bn": float(L["Lg"] - L["Ag"]),
            "pension_special_payments_bn": float(L["special"]),
            "pension_special_saved_bn": float(L["saved"]),
            "pension_assets_taken_bn": float(L["taken"])}
