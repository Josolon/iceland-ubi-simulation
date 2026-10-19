"""How well-conditioned the fitted surface's kernel correction is, and whether another fit does as well with weights
that survive being stored (v8). Uses the saved runs only; nothing is simulated.

    .venv/bin/python scripts/surface_refit_study.py [--outputs balance house ...]

For each output the page fits with a kernel, against the fit v7 publishes:
  * cv   cross-validated R² (mean over years), as build_emulator.py scores it;
  * prec the largest change the stored 5 significant figures make to a prediction, in standard deviations of the
         output across runs (over 600 points, every year);
  * size the weights' bytes as the page stores them.
Variants: a larger nugget (×10), and a reduced set of centres (Nyström / subset of regressors, 800 and 1,200).
Writes data/processed/surface_refit_study.json.
"""
import argparse
import json
import pathlib
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_emulator as be  # noqa: E402

OUT = ROOT / "data/processed/surface_refit_study.json"


def g5(a):
    return np.array([float(f"{v:.5g}") for v in a.ravel()]).reshape(a.shape)


def poly_part(X, Y, folds):
    """The polynomial as fit_output makes it: returns A, beta and the per-year penalty."""
    n, k = X.shape
    terms = be.base_terms(k)
    A = be.columns(X, terms)
    imp = be.importance(A, terms, be.ridge(A, Y, 1e-4))
    lin = {be.KEYS.index(n_) for n_ in be.LINEAR_ONLY}
    top = [int(j) for j in np.argsort(-imp) if j not in lin][:be.EXTRA_PAIRS_FROM]
    extra = [(min(a, b), max(a, b)) for i, a in enumerate(top) for b in top[i + 1:] if 0 not in (a, b)]
    terms = terms + extra
    A = be.columns(X, terms)
    pred = {lam: np.zeros_like(Y) for lam in be.LAMBDAS}
    for f in folds:
        tr = np.setdiff1d(np.arange(n), f)
        for lam in be.LAMBDAS:
            pred[lam][f] = A[f] @ be.ridge(A[tr], Y[tr], lam)
    lam_y = [max(be.LAMBDAS, key=lambda l: be.r2_of(Y[:, y], pred[l][:, y])) for y in range(Y.shape[1])]
    beta = np.column_stack([be.ridge(A, Y[:, [y]], lam_y[y])[:, 0] for y in range(Y.shape[1])])
    return A, terms, beta, lam_y


def hyper(X, R, dims, w):
    best, h = np.inf, None
    n = len(X)
    for ell in be.ELLS:
        K = be.kernel(X, X, dims, w, ell)
        for nu in be.NUGGETS:
            Minv = np.linalg.inv(K + nu * np.eye(n))
            s = float(np.sum(((Minv @ R) / np.diag(Minv)[:, None]) ** 2))
            if s < best:
                best, h = s, (ell, nu)
    return h


def solve(Xc, X, res, dims, w, ell, nu):
    """Weights on the centres Xc. With every run as a centre this is the published fit; with fewer, subset of
    regressors: (Kcn Knc + nu Kcc) a = Kcn r."""
    if Xc is X:
        return np.linalg.solve(be.kernel(X, X, dims, w, ell) + nu * np.eye(len(X)), res)
    Kcn = be.kernel(Xc, X, dims, w, ell)
    Kcc = be.kernel(Xc, Xc, dims, w, ell)
    return np.linalg.solve(Kcn @ Kcn.T + nu * Kcc + 1e-8 * np.eye(len(Xc)), Kcn @ res)


def study(X, Y, folds, P, rng):
    n = len(X)
    A, terms, beta, lam_y = poly_part(X, Y, folds)
    imp = be.importance(A, terms, beta)
    dims = list(np.argsort(-imp)[:be.KERNEL_DIMS])
    w = imp[dims] / max(imp[dims].sum(), 1e-12)
    res = Y - A @ beta
    sc = res.std(0); sc[sc == 0] = 1
    ell, nu = hyper(X, res / sc, dims, w)
    ysd = Y.std(0); ysd[ysd == 0] = 1
    out = {"ell": ell, "nu": nu}
    variants = {"v7": (None, nu), "nugget_x10": (None, 10 * nu), "centres_1200": (1200, nu), "centres_800": (800, nu)}
    for name, (m, nu_v) in variants.items():
        centre_idx = np.sort(rng.choice(n, m, replace=False)) if m else None
        cv = np.zeros_like(Y)
        for f in folds:
            tr = np.setdiff1d(np.arange(n), f)
            B = np.column_stack([be.ridge(A[tr], Y[tr][:, [y]], lam_y[y])[:, 0] for y in range(Y.shape[1])])
            r_tr = Y[tr] - A[tr] @ B
            Xtr = X[tr]
            Xc = Xtr if m is None else X[np.intersect1d(centre_idx, tr)]
            a = solve(Xc if m else Xtr, Xtr, r_tr, dims, w, ell, nu_v)
            cv[f] = A[f] @ B + be.kernel(X[f], Xc, dims, w, ell) @ a
        Xc = X if m is None else X[centre_idx]
        a = solve(Xc if m else X, X, res, dims, w, ell, nu_v)
        kp = be.kernel(P, Xc, dims, w, ell)
        prec = float((np.abs(kp @ g5(a) - kp @ a) / ysd).max())
        out[name] = {"cv": float(np.mean([be.r2_of(Y[:, y], cv[:, y]) for y in range(Y.shape[1])])),
                     "prec": prec, "max_abs_w_sd": float((np.abs(a) / ysd).max()),
                     "bytes": len(json.dumps(g5(a).T.tolist(), separators=(",", ":")))}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs", nargs="*", default=None)
    a = ap.parse_args()
    t0 = time.time()
    raw = json.loads(be.RAW.read_text())
    X = np.array(raw["X"])
    keep = [i for i, y in enumerate(raw["Y"]) if y is not None]
    X, Yall = X[keep], [raw["Y"][i] for i in keep]
    years = raw["years"]
    idx = [y - 2026 for y in be.year_list(years)]
    Yall = [{k: (be.thin(v, idx, k) if isinstance(v, list) else v) for k, v in y.items()} for y in Yall]
    be._PRESMOOTHED = True
    years = len(idx)
    page = json.loads((lambda s: s[s.index("{"):s.rindex("}") + 1])((ROOT / "artifacts/explorer_v3/emulator.js").read_text()))
    with_kernel = [o for o, c in page["coeffs"].items() if "kernel" in c]
    outs = a.outputs or with_kernel
    rng = np.random.default_rng(7)
    folds = np.array_split(rng.permutation(len(X)), be.FOLDS)
    results = {}
    print(f"{len(X)} runs, {years} years, {len(outs)} outputs ({time.time() - t0:.0f}s to load)", flush=True)
    for o in outs:
        M = np.array([[np.nan if v is None else v for v in (Yall[i] or {}).get(o, [None] * years)]
                      for i in range(len(X))], dtype=float)
        ok_years = np.isfinite(M).mean(0) >= .9
        rows = np.isfinite(M[:, ok_years]).all(1)
        Xo, Yo = X[rows], M[rows][:, ok_years]
        sub = [np.flatnonzero(np.isin(np.flatnonzero(rows), f)) for f in folds]
        P = np.vstack([Xo[rng.choice(len(Xo), 300, replace=False)], rng.random((300, X.shape[1]))])
        t = time.time()
        r = study(Xo, Yo, sub, P, np.random.default_rng(11))
        results[o] = r
        print(f"{o:24s} " + "  ".join(f"{k}: cv {v['cv']:.3f} prec {v['prec']:.4f} w/sd {v['max_abs_w_sd']:.0f} "
                                      f"{v['bytes'] // 1024}KB" for k, v in r.items() if isinstance(v, dict))
              + f"  ({time.time() - t:.0f}s)", flush=True)
        OUT.write_text(json.dumps(results, indent=1))
    print(f"wrote {OUT} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
