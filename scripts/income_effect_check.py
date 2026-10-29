"""Does the model give up as much work for unearned income as the lottery evidence says people do?

    .venv/bin/python scripts/income_effect_check.py

The borgaralaun is unearned income paid for ever, so what the model must be checked against is the marginal
propensity to earn out of unearned income: how many krónur of pay a person gives up per króna received.

  Cesarini, Lindqvist, Notowidigdo and Östling (2017, AER, Swedish lotteries): pre-tax earnings fall by about
  1.1% of the prize a year, and their calibrated model implies a lifetime MPE from -0.17 at age 20 to -0.04 at 60.
  Golosov, Graber, Mogstad and Novgorodsky (2024, US lotteries): about -0.50 of a dollar in the period the money
  arrives, but -0.023 measured year by year — the same behaviour over different horizons, which is why the test
  is a range rather than a target.

  Vivalt, Rhodes, Bartik, Broockman, Miller and Elam (2024; QJE 2026, the OpenResearch trial): $1,000 a month for
  three years to low-income Americans cut their own income excluding the transfer by about $1,900 a year — 16
  cents per dollar — and their partners cut hours by a similar amount, so per household closer to 30.
  Gromadzki (2024, JPubE, Poland's universal child benefit): 25 of every 100 zloty given up in household earnings in
  the medium run, 32 spent and 43 saved.

A permanent flow should therefore cost somewhere between about 4 and 20 krónur of pay per 100 received, per
person. The trials of low-income households sit at or above the top of that range; lottery winners, who are more
like the whole population, sit inside it. In this test each partner receives the payment and responds to both, so
the figure is per króna paid to the household, closest to the trials' household numbers only if it nears 0.3.

Measured on the same people, not on the totals: both runs branch from one calibrated society, so person i is the
same person in each. The test looks only at those the reform hands money to and takes nothing from — working-age
adults who drew no benefits in the status quo. For them the payment is a windfall, which is what the lottery
studies measure. Read off the national totals it would mix in the benefits the payment replaces for everyone
else, and answer a different question. Prices are frozen on both sides, so this is the income effect alone —
and, since v9, so are wages: the payment run's new contracts are signed at the status quo's rates of the same year
(markets.freeze_wages). A lottery winner's pay rate is the market's and does not move because they work less; with
everyone paid, the market bid wages up as hours were withdrawn and offset most of the response, which is a
general-equilibrium outcome, not the income effect the evidence measures (found 2026-10-12). Each test is run on
four seeds, both runs of a pair sharing one, and the average is judged; a single path left the smallest payment's
figure noisy by about ±0.01.
"""
import pickle
import sys
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
from build_explorer_data import calibrated  # noqa: E402

EVIDENCE = (.04, .20)
YEARS = 3


def yearly_pay(soc, idx):
    """Pay in 2025 krónur a year, zero for those not working."""
    return soc.current_gross(idx) * 12 / soc.price


def yearly_state_money(soc, idx):
    """Benefits or the borgaralaun, 2025 krónur a year, at each person's own earnings."""
    A, p = soc.A, soc.p
    gross = soc.current_gross(idx)
    working = np.isin(A["status"][idx], [model.PART, model.FULL])
    n = model.pol_rules.net_income(A, idx, gross, working, p, price=soc.price)
    return (np.asarray(n["benefits"]) + np.asarray(n.get("ubi", 0.0))) * 12 / soc.price


SEEDS = (11, 12, 13, 14)


def main():
    base = calibrated(1.0, recalibrate=False)
    blob = pickle.dumps(base)
    frozen = {"markets": {"freeze_prices": True}}
    results = {a: [] for a in (100_000, 200_000, 300_000)}
    for seed in SEEDS:
        for amount, mpe, line in one_seed(base, blob, frozen, seed):
            results[amount].append(mpe)
    print(f"{'borgaralaun':>12} {'MPE, mean of ' + str(len(SEEDS)) + ' seeds':>24} {'sd':>7}   evidence says 0.04-0.20")
    for amount, v in results.items():
        mpe = float(np.mean(v))
        flag = "ok" if EVIDENCE[0] <= mpe <= EVIDENCE[1] else "OUTSIDE the evidence"
        print(f"{amount / 1000:11.0f}k {mpe:24.3f} {np.std(v, ddof=1):7.3f}   {flag}")


def one_seed(base, blob, frozen, seed):
    """One pair of runs per amount, the status quo first: its wages are the payment run's."""
    def seeded(over):
        soc = model.scenario(pickle.loads(blob), over)
        soc.rng = np.random.default_rng(seed)
        return soc
    sq = seeded({"policy": {"regime": "status_quo"}, **frozen})
    for _ in range(YEARS):
        sq.step()
    # Chosen on the society both runs start from, never on what happened in one of them: picking people who
    # turn out to be working in the status quo would select, in the other run, people who happened not to be —
    # and the payment would be blamed for the difference.
    A = pickle.loads(blob).A
    idx = np.flatnonzero(A["alive"] & (A["age"] >= 25) & (A["age"] <= 60) & ~A["disabled"]
                         & np.isin(A["status"], [model.PART, model.FULL]))
    # in work before either run starts, so the payment is a windfall and nothing is taken away
    clean = idx
    sq_pay = yearly_pay(sq, clean)
    if seed == SEEDS[0]:
        print(f"{len(clean):,} people aged 25-60 were in work before either run started; in the status quo they earn "
              f"{sq_pay.mean() / 1e6:.2f} m.kr. a year on average")
    # Children keep what they have today: the average child benefit per child, paid out in full. Left at the
    # platform's default, every parent in the group was also handed 300,000 a month per child that the test never
    # counted as given, and the MPE read a third too high, highest at the smallest payment (found 2026-10-05).
    kids = A["alive"] & (A["age"] < 18)
    per_child = float(base.child_transfers()[0].sum() / max(kids.sum(), 1) / base.price)
    out = []
    for amount in (100_000, 200_000, 300_000):
        pol0 = base.p["policy"]
        soc = seeded({
            "policy": {"regime": "platform", "ubi_adult": amount, "ubi_child": per_child, "child_invested_flat": 0.0,
                       # nothing else moves: no tax change, no pay offset, no job cuts, pensions left alone —
                       # and today's VAT and personal allowance, which the reform's defaults change. With them,
                       # a VAT rise the frozen price level still carries cut real pay by the same 5.6% at every
                       # amount, and 100 þús. read as an MPE of 0.41 (found 2026-09-25)
                       "pension_fold": 0.0, "public_wage_offset_ubi": 0.0, "public_payroll_cut": 0.0,
                       "platform_income_tax_scale": 1.0, "state_leave_ended": 0.0,
                       "vat_platform": pol0["vat_effective_status_quo"], "vat_platform_capture": 1.0,
                       "platform_personal_credit": pol0["personal_credit"], "prop_tax_extra_pp": 0.0},
            # and the reform's other behavioural channels, which move pay for reasons other than the payment
            "demography": {"birth_timing_shift": 0.0},
            "labour": {"occupation_mobility_security": 0.0},
            # 2.0: and peers as the status quo has them: a lottery winner's neighbours did not win (model.norm_term)
            "behaviour": {"freeze_peers": True},
            "markets": {"freeze_prices": True, "freeze_wages": True}})
        soc.reference = sq.own_history      # whose wages it is paid
        for _ in range(YEARS):
            soc.step()
        pay = yearly_pay(soc, clean)
        given = amount * 12.0        # this group had no benefits to lose, so the payment is the whole change
        mpe = (sq_pay.mean() - pay.mean()) / given
        out.append((amount, mpe, f"seed {seed}: {amount / 1000:.0f}k pay {pay.mean() / 1e6:.2f}m, MPE {mpe:.3f}"))
    return out


if __name__ == "__main__":
    main()
