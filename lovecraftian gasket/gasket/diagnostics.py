"""Headless diagnostics: snap + pack a config and dump a matplotlib PNG plus the
scalar terms that the search objective will later care about.

Run::

    python diagnostics.py seeds/irregular_frame.json [out.png]

Build this *before* the optimizer (plan step 4): a trustworthy diagnostic is what
lets the objective ``L`` be calibrated against visual judgement.
"""

from __future__ import annotations

import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle as MplCircle
from matplotlib.patches import Rectangle

from config import load
from packing import pack
from snap import snap

# Size bands (mm) - tune per paper.  Circles in [eye_min, eye_max] are usable eyes.
EYE_MIN, EYE_MAX = 6.0, 45.0


def analyse(cfg, circles):
    """Return the scalar terms a search objective would weigh.

    Coherence / size statistics are computed over **uncropped circles only**
    (those fully inside the clip).  This matters once the seed set includes one
    or more very large circles used as a flat-boundary (``k=0`` line)
    approximation: those croppable circles must shape the packing without
    polluting the coherence aggregation.
    """
    circles = [c for c in circles if cfg.clip.contains_disk(c)]
    if not circles:
        return {"n_circles": 0, "n_eye_band": 0, "logr_spread": 0.0,
                "r_min": 0.0, "r_max": 0.0, "eye_spatial_spread": 0.0, "gens": {}}
    radii = np.array([c.r for c in circles])
    logr = np.log(radii)
    by_gen = defaultdict(list)
    for c in circles:
        by_gen[c.depth].append(c.r)

    eye_band = [c for c in circles if EYE_MIN <= c.r <= EYE_MAX]
    centers = np.array([[c.z.real, c.z.imag] for c in eye_band]) if eye_band \
        else np.zeros((0, 2))
    spread = float(np.hypot(*centers.std(axis=0))) if len(centers) > 1 else 0.0

    return {
        "n_circles": len(circles),
        "n_eye_band": len(eye_band),
        "logr_spread": float(logr.std()),
        "r_min": float(radii.min()),
        "r_max": float(radii.max()),
        "eye_spatial_spread": spread,
        "gens": {g: len(v) for g, v in sorted(by_gen.items())},
    }


def plot(cfg, circles, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(8.27, 11.69))   # A4 inches
    clip = cfg.clip

    # paper + margin rect
    ax.add_patch(Rectangle((0, 0), 210, 297, fill=False, lw=0.5, ec="0.7"))
    ax.add_patch(Rectangle((clip.x0, clip.y0), clip.x1 - clip.x0,
                           clip.y1 - clip.y0, fill=False, lw=0.8, ec="0.4",
                           ls="--"))
    # enclosing circle (the packing boundary)
    out = cfg.outer_circle()
    ax.add_patch(MplCircle((out.z.real, out.z.imag), out.r, fill=False,
                           lw=0.8, ec="tab:red", ls=":"))

    depths = [c.depth for c in circles]
    dmax = max(depths) if depths else 1
    cmap = plt.get_cmap("viridis")
    for c in circles:
        col = cmap(c.depth / max(1, dmax))
        ax.add_patch(MplCircle((c.z.real, c.z.imag), c.r, fill=False,
                               lw=0.4, ec=col))

    ax.set_xlim(-5, 215)
    ax.set_ylim(302, -5)            # invert y -> plotter/screen orientation
    ax.set_aspect("equal")
    ax.set_title(f"{len(circles)} circles, depth 0..{dmax}")
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    print(f"wrote {out_path}")


def main(argv):
    path = argv[1] if len(argv) > 1 else "seeds/irregular_frame.json"
    out_path = argv[2] if len(argv) > 2 else "diagnostic.png"

    cfg = load(path)
    seeds = snap(cfg, verbose=True)
    outer = cfg.outer_circle()
    circles = pack(seeds, outer, cfg.clip, r_min=cfg.r_min)

    stats = analyse(cfg, circles)
    print("\n--- objective terms ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    plot(cfg, circles, out_path)


if __name__ == "__main__":
    main(sys.argv)
