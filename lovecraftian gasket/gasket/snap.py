"""Snap-to-tangent pre-pass (Route B - relax & snap).

Hand-placed circles are generally *not* mutually tangent, but the Apollonian
recursion needs tangency to seed each triangle.  This deterministic least-squares
pre-pass minimally nudges seed positions/radii to satisfy the declared
tangencies, then packing can proceed.

Each seed contributes three free variables ``(x, y, r)``.  The boundary circle is
held fixed.  Residuals:

* circle-circle tangency:   ``|z_i - z_j| - (r_i + r_j)``
* circle-boundary tangency: ``(r_out - r_i) - |z_i - z_out|``  (internal contact)
* anchoring:                ``w * (var - var0)``  keeps the move minimal; ``fixed``
  seeds get a much stiffer anchor so they barely budge.

Levenberg-Marquardt via :func:`scipy.optimize.least_squares` (same idea as R's
``nls``).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from config import Config
from geometry import Circle

ANCHOR_FREE = 0.02     # gentle pull back to hand-placed values for free seeds
ANCHOR_FIXED = 5.0     # stiff pull for fixed seeds (they should barely move)


def snap(cfg: Config, *, verbose: bool = False) -> list[Circle]:
    """Return seed circles adjusted to satisfy ``cfg.tangencies``.

    The returned list is parallel to ``cfg.seeds``.  ``cfg`` is not mutated.
    """
    seeds = cfg.seeds
    n = len(seeds)
    idx = {s.id: i for i, s in enumerate(seeds)}

    out = cfg.outer_circle()
    z_out, r_out = out.z, out.r

    # initial parameter vector: [x0,y0,r0, x1,y1,r1, ...]
    p0 = np.empty(3 * n)
    for i, s in enumerate(seeds):
        p0[3 * i:3 * i + 3] = (s.z.real, s.z.imag, s.r)

    # Fixed seeds are pinned in *position* but their radius stays free so they
    # can still resize to meet a declared tangency (otherwise an over-stiff
    # radius leaves the seed-boundary contact unsatisfiable).
    anchor = np.empty(3 * n)
    for i, s in enumerate(seeds):
        pos = ANCHOR_FIXED if s.fixed else ANCHOR_FREE
        anchor[3 * i:3 * i + 2] = pos          # x, y
        anchor[3 * i + 2] = ANCHOR_FREE         # r

    pairs = []
    for a, b in cfg.tangencies:
        pairs.append((a, b))

    def residuals(p: np.ndarray) -> np.ndarray:
        xs = p[0::3]
        ys = p[1::3]
        rs = p[2::3]
        res = []
        for a, b in pairs:
            if b == "outer" or a == "outer":
                sid = a if b == "outer" else b
                i = idx[sid]
                d = np.hypot(xs[i] - z_out.real, ys[i] - z_out.imag)
                res.append((r_out - rs[i]) - d)        # internal tangency
            else:
                i, j = idx[a], idx[b]
                d = np.hypot(xs[i] - xs[j], ys[i] - ys[j])
                res.append(d - (rs[i] + rs[j]))         # external tangency
        # anchoring residuals keep the adjustment minimal
        res.extend(list(anchor * (p - p0)))
        return np.asarray(res)

    # radii must stay positive
    lo = np.full(3 * n, -np.inf)
    hi = np.full(3 * n, np.inf)
    lo[2::3] = 1e-3
    sol = least_squares(residuals, p0, bounds=(lo, hi), method="trf")

    if verbose:
        r = residuals(sol.x)
        tang = r[:len(pairs)]
        print(f"snap: {len(pairs)} tangencies, max residual = "
              f"{np.max(np.abs(tang)):.4g} mm, cost = {sol.cost:.4g}")

    circles = []
    for i, s in enumerate(seeds):
        x, y, r = sol.x[3 * i:3 * i + 3]
        circles.append(Circle.from_center(complex(x, y), float(r),
                                          feature=s.feature))
    return circles


if __name__ == "__main__":
    import sys
    from config import load
    from geometry import tangency_error

    cfg = load(sys.argv[1] if len(sys.argv) > 1 else "seeds/irregular_frame.json")
    circles = snap(cfg, verbose=True)
    out = cfg.outer_circle()
    by_id = {s.id: circles[i] for i, s in enumerate(cfg.seeds)}
    print("post-snap tangency residuals:")
    for a, b in cfg.tangencies:
        ca = out if a == "outer" else by_id[a]
        cb = out if b == "outer" else by_id[b]
        print(f"  {a:>6} - {b:<6}: {tangency_error(ca, cb):.4g} mm")
