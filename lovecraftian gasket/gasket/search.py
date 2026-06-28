"""Arrangement search: find seed configs with good radius coherence.

CMA-ES (derivative-free) moves the ``free_ids`` seeds in free R^n; the
deterministic :mod:`snap` pre-pass projects each proposal back onto the declared
tangency manifold, then a *shallow* pack scores it.  The winning config is
serialized to ``seeds/*.json`` in the same schema the renderer consumes.

Objective (minimised), all terms over **uncropped** circles only::

    L =  w_coh   * coherence            # per-seed-triangle log-radius jump (agg)
       - w_eye   * n_eye_band           # reward usable eyes
       - w_spread* spatial_spread       # reward eyes spread across the frame
       + w_clip  * clip_overshoot       # keep seeds inside the margins

The coherence aggregation across seed triangles is a **90th-percentile vs max**
knob (``--agg``): a high quantile / worst-case, never a mean, so the optimiser
can't hide one ugly radius jump behind several smooth ones.  Large *croppable*
seeds (flat-boundary approximations) never enter the statistic because cropped
circles are excluded throughout.

Usage::

    python search.py seeds/irregular_frame.json --out seeds/searched.json \
        --iters 200 --agg p90
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, replace
from itertools import combinations
from pathlib import Path

import numpy as np

from config import Config, Seed, load
from geometry import Circle, descartes_pair, tangency_error
from packing import SEED_TANGENT_TOL, pack
from snap import snap

# Usable-eye size band (mm); circles here count toward `n_eye_band`.
EYE_MIN, EYE_MAX = 4.0, 45.0


@dataclass
class Weights:
    coh: float = 1.0
    eye: float = 0.05
    spread: float = 2.0
    clip: float = 0.5


# --------------------------------------------------------------------------- #
# Objective
# --------------------------------------------------------------------------- #
def _coherence(seed_circles, outer, clip, agg: str) -> float:
    """Aggregated per-seed-triangle radius jump (smaller == more coherent).

    For each mutually tangent triple among {outer} + seeds, the first interior
    (Soddy) circle's radius is compared to the *smallest* seed in the triple -
    that is what the Descartes jump is dominated by.  Cropped inner circles are
    skipped.  Aggregate as the 90th percentile (``p90``) or the worst case
    (``max``).
    """
    members = [outer, *seed_circles] if outer is not None else list(seed_circles)
    jumps = []
    for a, b, c in combinations(members, 3):
        if (tangency_error(a, b) > SEED_TANGENT_TOL
                or tangency_error(b, c) > SEED_TANGENT_TOL
                or tangency_error(a, c) > SEED_TANGENT_TOL):
            continue
        inner, _ = descartes_pair(a, b, c)
        if inner.k <= 0 or not clip.contains_disk(inner):
            continue
        pos = [m.r for m in (a, b, c) if m.k > 0]
        if not pos:
            continue
        jumps.append(abs(math.log(min(pos)) - math.log(inner.r)))
    if not jumps:
        return 10.0                      # no usable seed triangle -> heavy cost
    return float(np.max(jumps) if agg == "max" else np.quantile(jumps, 0.9))


def _clip_overshoot(seed_circles, clip) -> float:
    """Total distance seed disks poke past the clip (0 when all inside)."""
    over = 0.0
    for c in seed_circles:
        if c.k <= 0:
            continue
        over += max(0.0, clip.x0 - (c.z.real - c.r))
        over += max(0.0, (c.z.real + c.r) - clip.x1)
        over += max(0.0, clip.y0 - (c.z.imag - c.r))
        over += max(0.0, (c.z.imag + c.r) - clip.y1)
    return over


def evaluate(cfg: Config, *, agg: str = "p90", weights: Weights = Weights(),
             max_gen: int = 4):
    """Return ``(L, terms, snapped)`` for a config: snap, shallow-pack, score."""
    snapped = snap(cfg)
    outer = cfg.outer_circle()
    circles = pack(snapped, outer, cfg.clip, r_min=cfg.r_min, max_depth=max_gen)

    coh = _coherence(snapped, outer, cfg.clip, agg)
    band = [c for c in circles
            if EYE_MIN <= c.r <= EYE_MAX and cfg.clip.contains_disk(c)]
    n_eye = len(band)
    if len(band) > 1:
        P = np.array([[c.z.real, c.z.imag] for c in band])
        spread = float(np.hypot(*P.std(axis=0)))
    else:
        spread = 0.0
    diag = math.hypot(cfg.clip.x1 - cfg.clip.x0, cfg.clip.y1 - cfg.clip.y0)
    overshoot = _clip_overshoot(snapped, cfg.clip)

    L = (weights.coh * coh
         - weights.eye * n_eye
         - weights.spread * (spread / diag)
         + weights.clip * overshoot)
    terms = dict(L=L, coherence=coh, n_eye=n_eye,
                 spread=round(spread, 2), overshoot=round(overshoot, 3))
    return L, terms, snapped


# --------------------------------------------------------------------------- #
# Variable <-> config plumbing
# --------------------------------------------------------------------------- #
def _free_seeds(cfg: Config) -> list[Seed]:
    fset = set(cfg.free_ids())
    return [s for s in cfg.seeds if s.id in fset]


def _apply(cfg: Config, free_ids: list[str], x: np.ndarray) -> Config:
    """Config with the free seeds' (x, y, r) replaced by the vector ``x``."""
    pos = {fid: x[3 * j:3 * j + 3] for j, fid in enumerate(free_ids)}
    seeds = []
    for s in cfg.seeds:
        if s.id in pos:
            sx, sy, sr = pos[s.id]
            seeds.append(Seed(s.id, complex(float(sx), float(sy)),
                              max(0.5, float(sr)), s.fixed, s.feature))
        else:
            seeds.append(s)
    return replace(cfg, seeds=list(seeds))


# --------------------------------------------------------------------------- #
# CMA-ES runner
# --------------------------------------------------------------------------- #
def run(cfg: Config, *, iters: int = 150, sigma: float = 10.0, agg: str = "p90",
        weights: Weights = Weights(), max_gen: int = 4, seed: int = 0,
        verbose: bool = True):
    import cma

    free = _free_seeds(cfg)
    if not free:
        raise ValueError("config has no search.free_ids to optimise")
    free_ids = [s.id for s in free]

    rlo, rhi = cfg.search.get("bounds", {}).get("r", [5.0, 60.0])
    # Optional per-seed bound overrides (e.g. a fixed-ish anchor allowed to move
    # only +-N mm): search["bounds_by_id"][id] = {"x":[lo,hi],"y":..,"r":..}.
    by_id = cfg.search.get("bounds_by_id", {})
    clip = cfg.clip
    x0, lo, hi = [], [], []
    for s in free:
        b = by_id.get(s.id, {})
        xlo, xhi = b.get("x", [clip.x0, clip.x1])
        ylo, yhi = b.get("y", [clip.y0, clip.y1])
        srlo, srhi = b.get("r", [rlo, rhi])
        x0 += [min(max(s.z.real, xlo), xhi), min(max(s.z.imag, ylo), yhi),
               min(max(s.r, srlo), srhi)]
        lo += [xlo, ylo, srlo]
        hi += [xhi, yhi, srhi]

    es = cma.CMAEvolutionStrategy(x0, sigma, {
        "bounds": [lo, hi], "maxiter": iters, "seed": seed,
        "verbose": -9, "popsize": max(8, 4 + 3 * len(free)),
    })

    best_L, best_x = float("inf"), np.array(x0)
    gen = 0
    while not es.stop():
        X = es.ask()
        fs = []
        for x in X:
            L, _, _ = evaluate(_apply(cfg, free_ids, x), agg=agg,
                               weights=weights, max_gen=max_gen)
            fs.append(L)
        es.tell(X, fs)
        gen += 1
        i = int(np.argmin(fs))
        if fs[i] < best_L:
            best_L, best_x = fs[i], np.asarray(X[i])
        if verbose and gen % 10 == 0:
            _, terms, _ = evaluate(_apply(cfg, free_ids, best_x), agg=agg,
                                   weights=weights, max_gen=max_gen)
            print(f"  gen {gen:4d}  best L={best_L:7.3f}  {terms}")

    best_cfg = _apply(cfg, free_ids, best_x)
    _, terms, snapped = evaluate(best_cfg, agg=agg, weights=weights,
                                 max_gen=max_gen)
    return best_cfg, snapped, terms


# --------------------------------------------------------------------------- #
# Serialization (writes the snapped seeds so load->snap is ~identity)
# --------------------------------------------------------------------------- #
def save(cfg: Config, snapped: list[Circle], path: str | Path) -> None:
    b = cfg.boundary
    margin = cfg.clip.x0
    boundary = ({"type": "circle", "z": [b.z.real, b.z.imag], "r": b.r,
                 "inside": True} if b is not None else {"type": "none"})
    data = {
        "paper": "a4",
        "margin": margin,
        "landscape": cfg.landscape,
        "boundary": boundary,
        "seeds": [
            {"id": s.id, "z": [round(c.z.real, 3), round(c.z.imag, 3)],
             "r": round(c.r, 3), "fixed": s.fixed, "feature": s.feature}
            for s, c in zip(cfg.seeds, snapped)
        ],
        "tangencies": [list(t) for t in cfg.tangencies],
        "search": cfg.search,
    }
    Path(path).write_text(json.dumps(data, indent=2))


# --------------------------------------------------------------------------- #
# Random config generation (one fixed anchor + random circles, two tangency modes)
# --------------------------------------------------------------------------- #
def _delaunay_tangencies(seeds: list[Seed], with_boundary: bool):
    """Tangencies from a Delaunay triangulation of the seed centres; when
    ``with_boundary`` the convex-hull seeds are also declared tangent to ``outer``."""
    from scipy.spatial import Delaunay

    pts = np.array([[s.z.real, s.z.imag] for s in seeds])
    if len(pts) < 3:
        return [(seeds[i].id, seeds[j].id)
                for i in range(len(pts)) for j in range(i + 1, len(pts))]
    tri = Delaunay(pts)
    edges = set()
    for s in tri.simplices:
        for i, j in ((0, 1), (1, 2), (0, 2)):
            a, b = sorted((int(s[i]), int(s[j])))
            edges.add((a, b))
    tang = [(seeds[a].id, seeds[b].id) for a, b in sorted(edges)]
    if with_boundary:
        hull = {int(i) for e in tri.convex_hull for i in e}
        tang += [(seeds[i].id, "outer") for i in sorted(hull)]
    return tang


def random_config(rng, *, clip, boundary: Seed | None, n: int,
                  anchor_z: complex, anchor_r: float,
                  center_sd: float, radius_mean: float, radius_sd: float,
                  tangency: str = "delaunay", r_min: float = 2.0,
                  max_gen: int = 4, r_bounds=(5.0, 60.0),
                  features=("eye",)) -> Config:
    """Build a config: one fixed anchor + ``n`` random circles.

    Centres are Gaussian about the clip centre (sd ``center_sd``); radii Gaussian
    (mean ``radius_mean``, sd ``radius_sd``).  ``tangency`` is "delaunay" (triangulate
    the centres) or "star" (every circle tangent to the anchor).  When ``boundary``
    is None the enclosing circle is dropped and only the seed-gaps are packed - a
    freer, non-circular layout; "star" then chains the circles into a ring around
    the anchor so the wedges between neighbours still fill.
    """
    has_b = boundary is not None
    cx0 = (clip.x0 + clip.x1) / 2
    cy0 = (clip.y0 + clip.y1) / 2
    anchor = Seed("anchor", anchor_z, anchor_r, fixed=True, feature=features[0])
    seeds = [anchor]
    # Pre-draw a fixed candidate pool *before* any anchor-dependent decision, so
    # the random draws (and thus every circle's size/place) don't depend on the
    # anchor.  Then place greedily, keeping circles disjoint: an arrangement with
    # overlapping seeds isn't a valid packing and snapping it produces
    # intersecting fill.  Moving the anchor only displaces circles it conflicts
    # with - the rest stay put.
    pool = []
    for _ in range(n * 5):                     # oversample so enough fit
        r = max(2.0, rng.gauss(radius_mean, radius_sd))
        x = min(max(rng.gauss(cx0, center_sd), clip.x0 + r), clip.x1 - r)
        y = min(max(rng.gauss(cy0, center_sd), clip.y0 + r), clip.y1 - r)
        feat = features[rng.randrange(len(features))]
        pool.append((r, complex(x, y), feat))
    placed = 0
    for r, z, feat in pool:
        if placed >= n:
            break
        if all(abs(z - s.z) >= r + s.r for s in seeds):
            seeds.append(Seed(f"c{placed}", z, r, fixed=False, feature=feat))
            placed += 1

    if tangency == "star":
        ring = seeds[1:]
        tang = [("anchor", s.id) for s in ring]
        if has_b:
            tang += [("anchor", "outer")] + [(s.id, "outer") for s in ring]
        else:
            # No boundary: chain neighbours (by angle) so the wedges still fill.
            ring = sorted(ring, key=lambda s: math.atan2(s.z.imag - anchor_z.imag,
                                                         s.z.real - anchor_z.real))
            for k in range(len(ring) - 1):
                tang.append((ring[k].id, ring[k + 1].id))
            if len(ring) > 2:
                tang.append((ring[-1].id, ring[0].id))
    else:
        tang = _delaunay_tangencies(seeds, has_b)

    search = {
        "free_ids": [s.id for s in seeds if not s.fixed],
        "bounds": {"r": list(r_bounds)},
        "r_min": r_min,
        "max_gen_in_objective": max_gen,
    }
    return Config(clip=clip, boundary=boundary, seeds=seeds,
                  tangencies=tang, search=search)


def freed_anchor_config(cfg: Config, *, move: float, r_move: float,
                        anchor_id: str = "anchor") -> Config:
    """A copy where the anchor may move +-``move`` mm in x/y and +-``r_move`` in r
    (so CMA-ES can nudge the otherwise-fixed anchor)."""
    a = cfg.by_id()[anchor_id]
    seeds = [Seed(s.id, s.z, s.r, False if s.id == anchor_id else s.fixed,
                  s.feature) for s in cfg.seeds]
    search = dict(cfg.search)
    search["free_ids"] = list(dict.fromkeys(search.get("free_ids", [])
                                            + [anchor_id]))
    bbi = dict(search.get("bounds_by_id", {}))
    bbi[anchor_id] = {"x": [a.z.real - move, a.z.real + move],
                      "y": [a.z.imag - move, a.z.imag + move],
                      "r": [max(0.5, a.r - r_move), a.r + r_move]}
    search["bounds_by_id"] = bbi
    return replace(cfg, seeds=seeds, search=search)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("config")
    p.add_argument("--out", default=None, help="output seed JSON (default: print only)")
    p.add_argument("--iters", type=int, default=150)
    p.add_argument("--sigma", type=float, default=10.0)
    p.add_argument("--agg", choices=["p90", "max"], default="p90",
                   help="per-triangle coherence aggregation")
    p.add_argument("--max-gen", type=int, default=4, help="shallow pack depth")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--w-coh", type=float, default=1.0)
    p.add_argument("--w-eye", type=float, default=0.05)
    p.add_argument("--w-spread", type=float, default=2.0)
    p.add_argument("--w-clip", type=float, default=0.5)
    args = p.parse_args(argv)

    cfg = load(args.config)
    weights = Weights(args.w_coh, args.w_eye, args.w_spread, args.w_clip)

    _, before, _ = evaluate(cfg, agg=args.agg, weights=weights,
                            max_gen=args.max_gen)
    print("initial:", before)

    best_cfg, snapped, terms = run(cfg, iters=args.iters, sigma=args.sigma,
                                   agg=args.agg, weights=weights,
                                   max_gen=args.max_gen, seed=args.seed)
    print("best:   ", terms)

    if args.out:
        save(best_cfg, snapped, args.out)
        print(f"wrote {args.out}")
    else:
        print("(no --out; not written)")


if __name__ == "__main__":
    main()
