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

ANCHOR_FIXED = 5.0     # stiff pull for fixed seeds (they should barely move)
# Free seeds: keep the *radius* close to the sampled value (stiff) and satisfy
# tangency mainly by moving the *centre* (loose).  This stops circles ballooning
# to reach a distant/large neighbour - they shift instead, staying near the size
# they were drawn at.
ANCHOR_POS_FREE = 0.02   # centres move to meet tangencies (as before)
ANCHOR_RAD_FREE = 0.1    # mild radius pull toward the sampled value.  In a sparse
#  graph (star) this keeps sizes close to the samples; a dense Delaunay graph is a
#  Koebe packing whose radii must vary widely, so the pull is necessarily weak.
RAD_BAND_LO = 0.3        # free-seed radius stays within [0.3x, 6x] of its sample -
RAD_BAND_HI = 6.0        # a loose safety net against runaway ballooning (a small
#  circle inflating to bridge a far anchor) without breaking Delaunay's range.


def snap(cfg: Config, *, verbose: bool = False) -> list[Circle]:
    """Return seed circles adjusted to satisfy ``cfg.tangencies``.

    The returned list is parallel to ``cfg.seeds``.  ``cfg`` is not mutated.
    """
    seeds = cfg.seeds
    n = len(seeds)
    idx = {s.id: i for i, s in enumerate(seeds)}

    out = cfg.outer_circle()
    z_out, r_out = (out.z, out.r) if out is not None else (0j, 0.0)

    # initial parameter vector: [x0,y0,r0, x1,y1,r1, ...]
    p0 = np.empty(3 * n)
    for i, s in enumerate(seeds):
        p0[3 * i:3 * i + 3] = (s.z.real, s.z.imag, s.r)

    # A fixed seed is rigid in position AND radius - it is the reference the free
    # seeds adapt to, so the user's anchor keeps exactly the size/place they set.
    # Free seeds get a loose position anchor (centres move to meet tangencies) and
    # a stiff radius anchor (sizes stay near the sampled values).
    anchor = np.empty(3 * n)
    for i, s in enumerate(seeds):
        if s.fixed:
            anchor[3 * i:3 * i + 3] = ANCHOR_FIXED
        else:
            anchor[3 * i:3 * i + 2] = ANCHOR_POS_FREE   # x, y
            anchor[3 * i + 2] = ANCHOR_RAD_FREE          # r

    pairs = []
    for a, b in cfg.tangencies:
        pairs.append((a, b))

    def residuals(p: np.ndarray, target: np.ndarray) -> np.ndarray:
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
        # anchoring residuals keep the adjustment minimal (pull toward `target`)
        res.extend(list(anchor * (p - target)))
        return np.asarray(res)

    # Bounds: positions free; free-seed radii are hard-capped to a band around the
    # sampled value so they can flex enough to form a packing but never balloon
    # (e.g. to bridge the gap to a distant/huge anchor).  Fixed-seed radii are
    # pinned to their set value.
    lo = np.full(3 * n, -np.inf)
    hi = np.full(3 * n, np.inf)
    for i, s in enumerate(seeds):
        r0 = s.r
        if s.fixed:
            lo[3 * i + 2], hi[3 * i + 2] = r0 - 1e-6, r0 + 1e-6
        else:
            lo[3 * i + 2], hi[3 * i + 2] = max(0.5, RAD_BAND_LO * r0), RAD_BAND_HI * r0
    # Proximal iteration to a fully-tangent fixed point.  The anchor regularises
    # the solve toward `target`; with target = the sampled positions a single solve
    # leaves the anchor *fighting* tangency (~0.1 mm slack), and that slack is
    # amplified into a visibly different fill.  Re-anchoring each pass to the
    # current solution lets tangency win while staying near the samples, and -
    # crucially - makes snap *idempotent*: snapping an already-snapped config is a
    # no-op.  So the explorer (one snap from random) and sketch_gasket (snap of the
    # saved seeds) converge to the *same* arrangement, making the preview faithful.
    p = p0
    for _ in range(10):
        sol = least_squares(residuals, p, args=(p,), bounds=(lo, hi),
                            method="trf")
        if np.max(np.abs(sol.x - p)) < 1e-5:
            break
        p = sol.x

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
