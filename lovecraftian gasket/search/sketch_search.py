"""Search-result visualizer / explorer.

A re-roll explorer for seed arrangements: fix one anchor circle, scatter ``n``
random circles (Gaussian centre & radius, configurable sd), wire them into a
tangency graph (Delaunay of the centres, or a star around the anchor), snap to
tangency, pack, and draw - with the objective score overlaid.  Change the
**seed** (GUI seed field / ``vsk save --seed``) / sds to explore; flip ``refine``
to run a short CMA-ES (which may
also nudge the anchor within ``anchor_move`` mm); flip ``save_seed`` to write the
current arrangement to ``seeds/<save_name>`` for use in ``sketch_gasket``.

    vsk run search/sketch_search.py   (from the project root)
"""

import pathlib
import random
import sys

import vsketch

_HERE = pathlib.Path(__file__).resolve().parent
_GASKET = _HERE.parent / "gasket"          # shared library + seed interchange
sys.path.insert(0, str(_GASKET))
_SEEDS = _GASKET / "seeds"

from config import Seed                                   # noqa: E402
from packing import a4_clip, pack                         # noqa: E402
from search import (Weights, evaluate, freed_anchor_config,  # noqa: E402
                    random_config, run, save)

TANGENCY_MODES = ["delaunay", "star"]


def _seed_flags(snapped):
    """Greedy non-overlap flags, matching ``packing.pack`` seed placement: a seed
    that overlaps one already kept is a conflict (``False``)."""
    kept, flags = [], []
    for c in snapped:
        ok = not any((d.r + c.r) - abs(d.z - c.z) > 0.3 + 0.03 * min(d.r, c.r)
                     for d in kept)
        flags.append(ok)
        if ok:
            kept.append(c)
    return flags


def _drop_conflicts(cfg, snapped, flags):
    """Return (config, snapped) with conflicting seeds and any tangency / free_id
    referencing them removed, so the saved file packs exactly as displayed."""
    from dataclasses import replace
    keep_ids = {s.id for s, ok in zip(cfg.seeds, flags) if ok}
    seeds = [s for s, ok in zip(cfg.seeds, flags) if ok]
    snap2 = [c for c, ok in zip(snapped, flags) if ok]
    tang = [(a, b) for a, b in cfg.tangencies
            if (a in keep_ids or a == "outer") and (b in keep_ids or b == "outer")]
    search = dict(cfg.search)
    search["free_ids"] = [i for i in search.get("free_ids", []) if i in keep_ids]
    return replace(cfg, seeds=seeds, tangencies=tang, search=search), snap2


class SearchSketch(vsketch.SketchClass):
    landscape = vsketch.Param(False)
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2, unit="mm")
    margin = vsketch.Param(20.0, min_value=0)            # mm
    use_boundary = vsketch.Param(False)                  # enclosing circle on/off
    boundary_r = vsketch.Param(90.0, min_value=10)       # mm, enclosing circle

    # --- the one fixed anchor circle (mm)
    anchor_x = vsketch.Param(105.0)
    anchor_y = vsketch.Param(120.0)
    anchor_r = vsketch.Param(38.0, min_value=2)
    anchor_move = vsketch.Param(10.0, min_value=0)       # CMA may move centre +-this
    anchor_r_move = vsketch.Param(10.0, min_value=0)     # ... and radius +-this

    # --- the random circles (re-rolled by vsketch's seed: GUI seed field / --seed)
    n_circles = vsketch.Param(7, min_value=0, max_value=60)
    center_sd = vsketch.Param(40.0, min_value=1)         # mm, centre spread
    radius_mean = vsketch.Param(28.0, min_value=2)       # mm
    radius_sd = vsketch.Param(9.0, min_value=0)          # mm
    tangency_mode = vsketch.Param("delaunay", choices=TANGENCY_MODES)

    # --- packing / scoring
    r_min = vsketch.Param(2.0, min_value=0.5)            # mm
    display_depth = vsketch.Param(10, min_value=1)
    agg = vsketch.Param("p90", choices=["p90", "max"])
    w_coh = vsketch.Param(1.0, decimals=2)
    w_eye = vsketch.Param(0.05, decimals=3)
    w_spread = vsketch.Param(2.0, decimals=2)
    w_clip = vsketch.Param(0.5, decimals=2)

    # --- CMA-ES refine (optional)
    refine = vsketch.Param(False)
    refine_iters = vsketch.Param(10, min_value=2)

    # --- save
    save_seed = vsketch.Param(False)
    save_name = vsketch.Param("searched_explore.json")

    def _build(self, seed: int):
        clip = a4_clip(margin=self.margin, landscape=self.landscape)
        boundary = Seed("outer", complex((clip.x0 + clip.x1) / 2,
                                         (clip.y0 + clip.y1) / 2),
                        self.boundary_r, True, "boundary") \
            if self.use_boundary else None
        rng = random.Random(seed)
        cfg = random_config(
            rng, clip=clip, boundary=boundary, n=int(self.n_circles),
            anchor_z=complex(self.anchor_x, self.anchor_y), anchor_r=self.anchor_r,
            center_sd=self.center_sd, radius_mean=self.radius_mean,
            radius_sd=self.radius_sd, tangency=self.tangency_mode,
            r_min=self.r_min, max_gen=int(self.display_depth))
        weights = Weights(self.w_coh, self.w_eye, self.w_spread, self.w_clip)

        if self.refine:
            ref = freed_anchor_config(cfg, move=self.anchor_move,
                                      r_move=self.anchor_r_move)
            cfg, snapped, terms = run(ref, iters=int(self.refine_iters),
                                      agg=self.agg, weights=weights,
                                      max_gen=int(self.display_depth),
                                      seed=seed, verbose=False)
        else:
            _, terms, snapped = evaluate(cfg, agg=self.agg, weights=weights,
                                         max_gen=int(self.display_depth))
        return cfg, snapped, terms

    def draw(self, vsk: vsketch.Vsketch) -> None:
        # center=False: use absolute mm coordinates (page top-left = 0,0) so the
        # margin box and circles sit at their true positions and a large off-page
        # anchor doesn't shove the whole composition around.
        vsk.size("a4", landscape=self.landscape, center=False)
        vsk.penWidth(self.pen_width)
        vsk.scale("mm")

        # Use vsketch's own seed (GUI seed field / `vsk save --seed`) to drive the
        # random arrangement and the CMA-ES refine.
        cfg, snapped, terms = self._build(vsk.random_seed)
        clip = cfg.clip
        outer = cfg.outer_circle()
        circles = pack(snapped, outer, clip, r_min=self.r_min,
                       max_depth=int(self.display_depth))

        # layer 4: boundary (if any) + margin frame
        vsk.stroke(4)
        if outer is not None:
            vsk.circle(outer.z.real, outer.z.imag, radius=outer.r)
        vsk.rect(clip.x0, clip.y0, clip.x1 - clip.x0, clip.y1 - clip.y0)

        # layer 1: Apollonian fill (everything the recursion added)
        seed_keys = {(round(c.z.real, 2), round(c.z.imag, 2)) for c in snapped}
        vsk.stroke(1)
        for c in circles:
            if (round(c.z.real, 2), round(c.z.imag, 2)) in seed_keys:
                continue
            vsk.circle(c.z.real, c.z.imag, radius=c.r)

        # Classify seeds exactly as `pack` does: a seed that overlaps one already
        # placed is dropped from the packing (snap can overlap non-adjacent seeds
        # when the tangency graph is degenerate, e.g. a tiny anchor ringed by big
        # circles).  Draw placed seeds blue/red; flag conflicting ones (layer 6).
        flags = _seed_flags(snapped)
        n_conflict = flags.count(False)
        for (s, c), ok in zip(zip(cfg.seeds, snapped), flags):
            vsk.stroke((3 if s.id == "anchor" else 2) if ok else 6)
            vsk.circle(c.z.real, c.z.imag, radius=c.r)

        # layer 5: score overlay (top-left margin)
        vsk.stroke(5)
        txt = (f"L={terms['L']:.3f}  coh={terms['coherence']:.3f}  "
               f"eyes={terms['n_eye']}  spread={terms['spread']}  "
               f"over={terms['overshoot']}  mode={self.tangency_mode}"
               f"{'  [refined]' if self.refine else ''}"
               f"{'  CONFLICTS=%d' % n_conflict if n_conflict else ''}")
        vsk.text(txt, clip.x0, clip.y0 - 7, size=3.2)   # size in mm (scaled space)
        print("score:", terms, "conflicts:", n_conflict)

        vsk.vpype("color --layer 1 #999999 color --layer 2 #1f77b4 "
                  "color --layer 3 #d62728 color --layer 4 #cccccc "
                  "color --layer 5 black color --layer 6 #ff7f0e")

        if self.save_seed:
            name = self.save_name if self.save_name.endswith(".json") \
                else self.save_name + ".json"
            out = _SEEDS / name
            # Save a *clean* config: drop conflicting seeds (and any tangency /
            # free_id that references them) so the saved file packs identically.
            cfg2, snapped2 = _drop_conflicts(cfg, snapped, flags)
            save(cfg2, snapped2, out)
            print(f"saved seed -> {out}"
                  + (f"  (dropped {n_conflict} conflicting seed(s))" if n_conflict else ""))

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    SearchSketch.display()
