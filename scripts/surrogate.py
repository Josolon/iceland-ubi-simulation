"""The explorer's fitted surface, in Python: the same evaluation the page does, for many settings at once.

    from surrogate import Surface
    s = Surface()                                   # artifacts/explorer_v3/emulator.js
    X = s.x_from({"ubi": 300, "vat": 25})           # lever levels -> design vector (others at the page's start)
    s.eval(X, ["balance", "cpi"])                   # {output: array (settings, years)}
    s.status_quo(X, ["balance"])                    # the status quo in the same world

Mirrors the page exactly: centred terms, per-output crosses, the Gaussian kernel correction over the runs, and
the status quo moved by the world-price surface. Used to search for scenarios; anything chosen this way is then
checked in the model itself.
"""
import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Surface:
    def __init__(self, path=ROOT / "artifacts/explorer_v3/emulator.js"):
        txt = pathlib.Path(path).read_text()
        self.E = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        # the kernel weights live in emulator_k*.js beside it (a published file may be at most 16 MB)
        for kp in sorted(pathlib.Path(path).parent.glob("emulator_k*.js")):
            kt = kp.read_text()
            for o, alpha in json.loads(kt[kt.index(", {") + 2:kt.rindex("}") + 1]).items():
                if o in self.E["coeffs"] and "kernel" in self.E["coeffs"][o]:
                    self.E["coeffs"][o]["kernel"]["alpha"] = alpha
        self.levers = self.E["meta"]["levers"]
        self.keys = [l["key"] for l in self.levers]
        self.idx = {k: i for i, k in enumerate(self.keys)}
        self.terms = [tuple(t) for t in self.E["meta"]["terms"]]
        self.X = np.array(self.E["X"]) if self.E.get("X") else None
        self.years = self.E["meta"]["years"]

    # -- lever levels <-> design vector
    def to_x(self, key, level):
        l = self.levers[self.idx[key]]
        return float(np.clip((level - l["lo"]) / (l["hi"] - l["lo"]), 0, 1))

    def level(self, key, x):
        l = self.levers[self.idx[key]]
        return l["lo"] + x * (l["hi"] - l["lo"])

    def x_from(self, levels, base=None):
        x = np.array(base if base is not None else [l["default"] for l in self.levers], float)
        for k, v in levels.items():
            x[self.idx[k]] = self.to_x(k, v)
        return x

    @staticmethod
    def _term(U, t):
        if not t:
            return np.ones(len(U))
        if len(t) == 1:
            return U[:, t[0]]
        if t[0] == t[1]:
            return U[:, t[0]] ** 2 - 1 / 12
        return U[:, t[0]] * U[:, t[1]]

    def eval(self, X, outputs):
        X = np.atleast_2d(np.asarray(X, float))
        U = X - .5
        base = np.column_stack([self._term(U, t) for t in self.terms])
        out = {}
        for key in outputs:
            c = self.E["coeffs"].get(key)
            if c is None:
                continue
            extra = [tuple(t) for t in c["terms"]]
            T = np.column_stack([base] + [self._term(U, t)[:, None] for t in extra]) if extra else base
            Y = np.full((len(X), self.years), np.nan)
            K = None
            if "kernel" in c:
                k = c["kernel"]
                rows = self.X if not k.get("rows") else self.X[k["rows"]]
                d2 = np.zeros((len(X), len(rows)))
                for a, w in zip(k["dims"], k["w"]):
                    d2 += w * (X[:, a, None] - rows[None, :, a]) ** 2
                K = np.exp(-d2 / (2 * k["ell"] ** 2))
            for y in range(self.years):
                b = c["beta"][y]
                if not b:
                    continue
                Y[:, y] = T @ np.array(b)
                if K is not None and c["kernel"]["alpha"][y]:
                    Y[:, y] += K @ np.array(c["kernel"]["alpha"][y])
            out[key] = Y
        return out

    def status_quo(self, X, outputs):
        """The status quo in each setting's world: the exact run at 2025 prices, moved by the world surface."""
        X = np.atleast_2d(np.asarray(X, float))
        sq0 = self.E["status_quo"]
        W = self.E.get("status_quo_world")
        # Measured from where the exact status-quo run was made, as the page does (sqWorld): on the world levers that
        # is the model's own default, not where the page opens. From the page's defaults, the search's status quo
        # stood in the last decade's world with its effect subtracted (found 2026-10-01).
        x0 = np.array([l["status_quo_at"] if l.get("status_quo_at") is not None
                       else (0.0 if l["key"] in ("history_world", "ai") else l["default"]) for l in self.levers], float)
        out = {}
        for k in outputs:
            base = np.tile(np.array([np.nan if v is None else v for v in sq0[k]], float), (len(X), 1))
            if W and k in W["beta"]:
                U, U0 = X - .5, np.atleast_2d(x0 - .5)
                d = np.column_stack([self._term(U, tuple(t)) - self._term(U0, tuple(t)) for t in W["terms"]])
                for y in range(self.years):
                    if W["beta"][k][y]:
                        base[:, y] += d @ np.array(W["beta"][k][y])
            out[k] = base
        return self._with_ai(X, out)

    def _world_has_ai(self):
        W = self.E.get("status_quo_world")
        return bool(W) and "ai" in self.idx and any(self.idx["ai"] in t for t in W["terms"])

    def _with_ai(self, X, out):
        """Only when the status quo's world fit has no AI: borrow the reform's response to it, as the page does
        (withAI, worldHasAI). With AI in the world fit, borrowing as well counted it twice — the search's status quo
        came out about 300 ma.kr. better over 2027-35 than its own runs, as the page's did until 2026-09-25."""
        if "ai" not in self.idx or self._world_has_ai():
            return out
        i = self.idx["ai"]
        none = self.to_x("ai", 0)
        X0 = X.copy()
        X0[:, i] = none
        if np.all(np.abs(X[:, i] - none) < 1e-9):
            return out
        a, b = self.eval(X, list(out)), self.eval(X0, list(out))
        return {k: v + np.nan_to_num(a[k] - b[k]) if k in a else v for k, v in out.items()}
