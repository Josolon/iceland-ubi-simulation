"""2.0: the banks' and the pension funds' balance sheets, and what they add to the rates borrowers pay.

What there is (Hagstofa THJ10001, end of 2025, ma.kr.). The deposit-taking banks lent 4,929 against equity of 866;
households owed 3,477, of which the pension funds had lent 805 (23%); the funds held 2,809 of bonds against the
state's 2,035 issued. The policy rate is the central bank's (macro.py); this part adds what the balance sheets do
to the rates households, firms and the state pay on top of it.

Banks. Household loans follow the model's own mortgages, less what the funds lend; loans to firms follow the
business capital stock (capital.py). Equity earns the base year's return on loans (`return_on_equity`, EST) and
loses what borrowers fail to repay: `loss_rate` a year (EST), more as unemployment rises above the base year's and
as house prices fall (`loss_unemployment`, `loss_house_prices`, EST from the scale of the central bank's stress
tests: unemployment up five points and house prices down a third cost a few per cent of loans over two years).
Banks pay out what lifts equity above the base year's ratio to loans and keep everything while below it. Below it
they charge more: `capital_spread` on the shortfall in the ratio (EST 0.13, the steady-state effect of the Basel
Committee's assessment of 2010, 13 basis points per point of capital).

The pension funds. Their mortgage book and their bonds follow the assets in the funds' ledger (pensions.py) against
the ledger's base year. As far as a reform folds the funds into the state, the state holds the assets it takes,
bonds and members' loans among them, so nothing moves to the banks or onto the bond market when it takes them; what
changes is the flow: contributions no longer buy bonds or lend to members, and the banks lend what the funds would
have. A missing buyer weighs as an added seller: the yield rises
by `bond_premium` per unit of GDP of bonds the funds hold less than in the status quo (EST, the macro part's own
debt premium; Laubach 2009 finds 3-4 basis points per point of debt to GDP).

What it adds. The mortgage rate (macro.r_long, which firms' cost of capital also uses) by the banks' share of
household loans times their spread above the base year's, plus the bond premium; the state's coupons by the bond
premium. The status quo is its own reference for the bond premium; its banks move with its own cycle.

Not modelled: the central bank's balance sheet, banks' foreign funding, deposit flight, and a bank failing.
"""
import numpy as np

from ubisim.abm.population import FULL, INDEP, NONWORK, PART, VENTURE


def ensure(soc):
    st = getattr(soc, "financial", None)
    if st is None:
        c = soc.p.get("financial") or {}
        st = soc.financial = {} if not c else {
            "E": c["bank_equity"], "loans": c["bank_loans"], "H0": None, "price": None,
            "funds_loans": c["fund_loans"], "funds_bonds": c["fund_bonds"], "spread": 0.0, "bond": 0.0,
            "losses": 0.0, "dividends": 0.0}
    return st


def _mortgages(soc):
    A = soc.A
    return float(A["mortgage_debt"][A["alive"]].sum())


def _unemployment(soc):
    """As the snapshot reports it: those out of work against their will, of those working or wanting to."""
    A = soc.A
    ch = A["alive"] & A["chooser"]
    working = np.isin(A["status"], [PART, FULL, VENTURE, INDEP])
    return float((A["involuntary"] & ch & (A["status"] == NONWORK)).sum() / max(1, (ch & (working | A["involuntary"])).sum()))


def premium(soc):
    """What the balance sheets add to the mortgage rate and to the state's coupons, against the base year."""
    st = getattr(soc, "financial", None) or {}
    c = soc.p.get("financial") or {}
    if not st or not c:
        return 0.0, 0.0
    bank_share = 1 - st["funds_loans"] / max(st["households"], 1e-6) if "households" in st else 1 - c["fund_loans"] / c["household_loans"]
    return float(bank_share * st["spread"] + st["bond"]), float(st["bond"])


def update(soc, mk):
    """A year of the balance sheets, after the accounts; returns what to report (ma.kr., 2025 krónur)."""
    c = soc.p.get("financial") or {}
    st = ensure(soc)
    if not c:
        return {}
    # household loans: the model's mortgages against the base year's
    raw = _mortgages(soc)
    u = _unemployment(soc)
    if st["H0"] is None:
        first = soc.reference[0] if soc.reference else {}
        st["H0"], st["u0"] = first.get("fin_mortgages_raw") or raw, first.get("fin_unemployment", u)
    households = c["household_loans"] * raw / max(st["H0"], 1e-9)
    # the funds: their book and bonds follow the ledger's assets, the state keeping what it took
    L = getattr(soc, "pension_ledger", None) or {}
    pc = soc.p.get("pensions") or {}
    base = pc.get("assets_free", 0.0) + pc.get("assets_guaranteed", 0.0)
    held = (L["A"] + L["Ag"] + L["taken"]) / base if L and base else 1.0
    st["funds_loans"] = c["fund_loans"] * held
    st["funds_bonds"] = c["fund_bonds"] * held
    st["households"] = households
    # the banks
    firms = c["bank_loans"] - (c["household_loans"] - c["fund_loans"])
    K = (getattr(mk, "capital", None) or {}).get("K", 1.0)
    loans = max(households - st["funds_loans"], 0.0) + firms * K
    hp = float(mk.house_price)
    fall = max(0.0, 1 - hp / st["price"]) if st["price"] else 0.0
    st["price"] = hp
    rate = c["loss_rate"] + c["loss_unemployment"] * max(0.0, u - st["u0"]) \
        + c["loss_house_prices"] * fall
    losses = rate * loans
    profit = c["return_on_equity"] * c["bank_equity"] * loans / c["bank_loans"] + (c["loss_rate"] * loans - losses)
    E = st["E"] + profit
    target = c["bank_equity"] / c["bank_loans"] * loans
    st["dividends"] = max(0.0, E - target) if profit > 0 else 0.0
    st["E"], st["loans"], st["losses"] = E - st["dividends"], loans, losses
    short = max(0.0, c["bank_equity"] / c["bank_loans"] - st["E"] / max(loans, 1e-6))
    st["spread"] = c["capital_spread"] * short
    # the bond market: the funds' holdings against the status quo's, a year behind as the reference is
    ref = soc.reference_prev()
    theirs = ref.get("fin_fund_bonds") if ref else None
    st["bond"] = c["bond_premium"] * max(0.0, theirs - st["funds_bonds"]) / mk.GDP0 if theirs else 0.0
    return {"fin_mortgages_raw": raw, "fin_unemployment": u, "fin_fund_bonds": st["funds_bonds"], "fin_fund_loans": st["funds_loans"],
            "fin_household_loans": households, "fin_bank_loans": loans, "fin_bank_equity": st["E"],
            "fin_bank_losses": losses, "fin_bank_spread": st["spread"], "fin_bond_premium": st["bond"]}


def snapshot(soc):
    st = getattr(soc, "financial", None) or {}
    if not st:
        return {}
    return {"bank_capital_ratio": float(st["E"] / max(st["loans"], 1e-6)),
            "fund_share_of_household_loans": float(st["funds_loans"] / max(st.get("households", 1.0), 1e-6)),
            "bank_spread": float(st["spread"]), "bond_premium": float(st["bond"])}
