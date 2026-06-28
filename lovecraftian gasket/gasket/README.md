# Lovecraftian Apollonian Eye-Packing

A pen-plotter (vsketch) sketch that fills an **Apollonian circle packing** and renders
each packed circle as a Lovecraftian feature: manga-style **eyes** (pupil + iris +
negative-space specular highlights), **tooth-studded orifices**, and **bulging tissue**
at the smallest scales. Several **shading variants** (hatch / stipple / contour / ringed) share
one packing so they read as a coherent series.

See [`../lovecraftian_apollonian_plan.md`](../lovecraftian_apollonian_plan.md) for the
full design rationale.

## Folder layout

vsketch keeps each sketch's saved UI configs in a `config/` dir *next to the sketch*, and
shows all of them in every sketch in the same folder — meaningless across different
sketches.  So each sketch lives in its own folder, while the shared library and the seed
interchange stay in `gasket/`:

```
lovecraftian gasket/
  gasket/      # this folder: library modules + sketch_gasket.py + seeds/ (interchange)
  search/      # sketch_search.py  + its config/
  integral/    # sketch_integral.py + its config/
```

`search/` and `integral/` bootstrap `../gasket` onto `sys.path` and read/write seeds in
`../gasket/seeds`, so a crop/arrangement saved in either appears in `sketch_gasket`'s
`seed_file` dropdown.

## Running

From the vsketch environment, run each sketch from the repo:

```sh
vsk run  gasket/sketch_gasket.py        # interactive GUI with all parameters
vsk save gasket/sketch_gasket.py        # render to output/ with default params
vsk run  search/sketch_search.py        # arrangement explorer
vsk run  integral/sketch_integral.py    # integral-packing crop browser
vsk save --param shading_mode hatch,stipple,contour gasket/sketch_gasket.py  # one SVG per mode
```

## Pipeline

```
seeds/*.json  ─load─►  snap-to-tangent  ─►  Apollonian pack  ─►  render features
 (config.py)          (snap.py, scipy)      (packing.py)         (features.py)
```

1. **Load** a seed config (`config.py`) — the boundary circle, hand-placed seed circles,
   and their declared tangencies.
2. **Snap** (`snap.py`) — a least-squares pre-pass nudges seed radii/positions so the
   declared tangencies are exactly met (hand-placed circles are never quite tangent).
3. **Pack** (`packing.py`) — Apollonian recursion fills every curvilinear triangle down
   to `r_min`, using the sign-free Descartes *reflection* identity. Any circle poking
   past the **A4 minus margins** rectangle is discarded.
4. **Render** (`features.py` + `style.py`) — each circle becomes an eye, orifice, or
   tissue patch; the specular highlights are left as **negative space** (the shading is
   drawn *around* them).

### Boundary & the irregular frame

The packing region is optionally bounded by an **enclosing circle of negative curvature**
(not by `k=0` lines — that path has a sign-pairing bug). The **A4 page minus a uniform
margin** is a separate rectangular **discard clip**: any disk extending past it is
dropped. The **irregular frame** emerges from this clipping.

The **boundary is optional** (`"type": "none"` or omit it). With no enclosing circle the
recursion fills only the curvilinear gaps *between* mutually tangent seed circles, so the
outer edge follows the seed arrangement rather than a fixed circle — a freer, non-circular
layout (seeds that snap outward past the margins are simply discarded). You can also add
very large positive-curvature circles as seeds to approximate flat edges / richer frames —
they act as boundary (cropped, never drawn) without being packed-in.

## Files

| File | Role |
|------|------|
| `geometry.py`    | Descartes solver in `(k, w=k·z)` coords; sign-free reflection recursion. `python geometry.py` self-checks against the classic gasket. |
| `packing.py`     | Recursion to `r_min`; `Rect` discard clip; `a4_clip(margin)`. |
| `config.py`      | Seed JSON schema, loader, validation. |
| `snap.py`        | Snap-to-tangent least-squares pre-pass. |
| `style.py`       | `Style` dataclass + shading / frame enums + feature-mapping defaults. |
| `features.py`    | `eye()`, `orifice()`, `tissue()`, shading dispatch. |
| `eyestyle.py`    | Shared eye-shading plumbing: pen palette, `build_style(sk)` (maps a sketch's params → `Style`), `layer_colors(sk)`. Used by `sketch_gasket` and `sketch_integral`. |
| `diagnostics.py` | Headless matplotlib plot + scalar objective terms. `python diagnostics.py seeds/x.json`. |
| `search.py`      | CMA-ES arrangement search over the `free_ids` seeds; random-config + tangency-graph helpers; writes `seeds/*.json`. |
| `integral.py`    | Integral Apollonian root quadruples (sequential family + Wikipedia) and their placement. `python integral.py` self-checks. |
| `sketch_gasket.py` | vsketch entry point (final eye render). |
| `../search/sketch_search.py` | Interactive search-result **explorer**: anchor + random seeds, snap/pack, score overlay, save. |
| `../integral/sketch_integral.py` | **Integral-packing crop browser**: pick a packing, zoom/pan, recurse, save a crop. Has the full eye-shading UI (`as_eyes`). |
| `seeds/*.json`   | Seed configurations (shared interchange). |

> The two finder sketches live in sibling folders (`../search`, `../integral`) so each has
> its own vsketch `config/`; they import the library from `gasket/` and share `seeds/`.

## Parameters

### Input / output
| Param | Default | Meaning |
|-------|---------|---------|
| `seed_file`  | first in `seeds/` | Which seed configuration to pack. |
| `landscape`  | `False` | A4 portrait vs landscape. |
| `pen_width`  | `0.3 mm` | Stroke width (also drives `linemerge` in finalize). |
| `snap_seed`  | `0` | RNG seed for stipple/orifice jitter (`0` = vary each run). |

### Packing
| Param | Default | Meaning |
|-------|---------|---------|
| `r_min`     | `2.0 mm` | Stop recursion below this radius; smaller circles become tissue. |
| `max_depth` | `40` | Hard recursion-depth cap. |

The page size (A4) and margin (2 cm) come from the seed JSON (`paper`, `margin`); circles
outside `page − margin` are discarded.

### Coherent-series axis + frame
| Param | Choices | Meaning |
|-------|---------|---------|
| `shading_mode` | `hatch` / `stipple` / `contour` / `ringed` | How eyes (pupils/iris) and orifice/tissue throats are shaded. The only axis that should vary across a coherent series. |
| `frame_style`  | `none` / `circle` / `rect` / `circle+rect` | Whether to ink the enclosing circle and/or the margin rectangle. |

`hatch` / `stipple` / `contour` differ only in how the pupil is filled (disc
highlights left as negative space). **`ringed`** is a distinct manga look: the pupil
is hatched with a **negative-space sector specular** (a blunted wedge), and part of
the iris is shaded with **concentric arc-rings** filling a wider sector in the same
direction. For `ringed`, tissue/orifice throats fall back to plain hatch so the
series stays coherent.

### Feature mapping (millimetre radii)
| Param | Default | Meaning |
|-------|---------|---------|
| `eye_big` | `9.0 mm` | `r ≥ eye_big` → full manga eye. |
| `eye_min` | `3.5 mm` | `eye_min ≤ r < eye_big` → small eye; `r < eye_min` → tissue. |

A circle's explicit `feature` tag in the JSON (e.g. `"orifice"`) overrides size-based
assignment.

### Eye proportions
| Param | Default | Meaning |
|-------|---------|---------|
| `iris_ratio`     | `0.62` | Iris radius / circle radius. |
| `pupil_ratio`    | `0.36` | Pupil radius / circle radius. |
| `specular_count` | `2` | Number of negative-space highlights (0–2). |

### Per-eye randomization & gaze
The sclera stays centered; the iris+pupil group is jittered in size and position. All
offsets are auto-clamped so the iris never pokes past the sclera. Reproducible when
`snap_seed` is non-zero.
| Param | Default | Meaning |
|-------|---------|---------|
| `size_jitter_sd` | `0.05` | Pupil & iris size each ×`(1 + N(0, sd))` (independent draws). |
| `offset_mode` | `random` | `random`: independent per-eye jitter. `gaze`: all pupils slide toward a page point. |
| `offset_sd` | `0.05` | `random` mode: offset magnitude as a fraction of `r` (2-D Gaussian). |
| `gaze_x`, `gaze_y` | `0.5, 0.4` | `gaze` mode: the page point all eyes look at, as fractions of width/height. |
| `gaze_strength` | `0.08` | `gaze` mode: pupil shift per unit distance to the point (offset = strength·(point − eye); far eyes shift more, clamped per eye). |

### Shading detail
| Param | Default | Meaning |
|-------|---------|---------|
| `hatch_spacing`   | `0.5 mm` | Line spacing in `hatch` mode (and `ringed` pupil). |
| `hatch_angle`     | `35°` | Hatch direction. |
| `contour_spacing` | `0.6 mm` | Ring spacing in `contour` mode. |
| `stipple_density` | `0.9` | Dots per mm² in `stipple` mode. |

### Ringed-eye style (only when `shading_mode = ringed`)
| Param | Default | Meaning |
|-------|---------|---------|
| `specular_angle`        | `225°` | Direction of the specular wedge and iris arcs (screen degrees; y points down, so 225° ≈ upper-left). |
| `specular_sector_deg`   | `42°` | Angular width of the negative-space specular wedge. |
| `specular_inner_ratio`  | `0.18` | Inner radius of the wedge (fraction of pupil radius); `0` = sharp pie, `>0` blunts the apex. |
| `specular_reach`        | `1.0` | Wedge outer radius ÷ pupil radius. `1.0` = ends at the pupil edge; `>1` extends past it, breaking the pupil outline and carving a notch into the iris rings (all negative space). |
| `iris_sector_deg`       | `150°` | Angular width of the iris arc-rings (wider than the specular). |
| `iris_ring_outer_ratio` | `0.88` | Iris arcs reach this fraction of the sclera radius. |
| `iris_ring_count`       | `6` | Number of concentric arcs (a count, not a spacing, so density is consistent across eye sizes). |
| `iris_ring_taper_deg`   | `0°` | Shorten each ring inward by this many degrees (outermost stays full length) → a tapered fan. `0` = all arcs equal length. |

### Orifice
A solid dark (cross-hatched) disc; the **teeth** and irregular **radial streaks** are
negative space (paper) carved out of the fill, so the pale teeth read in stark contrast.
| Param | Default | Meaning |
|-------|---------|---------|
| `tooth_count` | `14` | Inward-pointing teeth around the rim. |
| `tooth_depth` | `0.34` | Tooth reach inward, as a fraction of radius. |
| `tooth_width_frac` | `0.45` | Angular fraction of each slot a tooth fills (narrower → more distinct fangs, more dark between them). |
| `orifice_line_reach` | `0.33` | Inner end of the white streaks, as a fraction of radius. |
| `orifice_line_width` | `0.035` | Max streak width, as a fraction of radius. |
| `orifice_lines_per_gap` | `2` | Streak density (placed at random angles around the rim, not literally per-gap). |
| `orifice_cross_hatch` | `True` | Cross-hatch the fill so it reads stark/dark. |

### Colours
| Param | Default | Meaning |
|-------|---------|---------|
| `line_color`  | first pen | Layer 1 (line work). `none` → black. |
| `shade_color` | `none` | Layer 2 (dark shading). `none` → same as line colour. |

Pens are loaded from the repo `pens/` directory (DrawingBot presets), same convention as
the `boxes` sketch.

## Seed JSON schema

```json
{
  "paper":  "a4",
  "margin": 20,
  "landscape": false,
  "boundary": { "type": "circle", "z": [105, 148.5], "r": 90, "inside": true },
  "_boundary_none": "use { \"type\": \"none\" } (or omit) to drop the enclosing circle",
  "seeds": [
    { "id": "s0", "z": [105, 100], "r": 42, "fixed": true,  "feature": "eye" },
    { "id": "s1", "z": [63, 173],  "r": 42, "fixed": false, "feature": "eye" },
    { "id": "s2", "z": [147, 173], "r": 42, "fixed": false, "feature": "orifice" }
  ],
  "tangencies": [ ["s0","s1"], ["s1","s2"], ["s0","s2"],
                  ["s0","outer"], ["s1","outer"], ["s2","outer"] ],
  "search": { "free_ids": ["s1","s2"], "r_min": 1.5, "max_gen_in_objective": 4 }
}
```

- Centres are `[x, y]` arrays in **millimetres** (parsed to `complex` internally).
- `"outer"` in a tangency pair refers to the boundary circle.
- `fixed` documents intent for a human reader; `free_ids` is what the (future) optimizer
  moves — validation checks the two agree.
- `feature` deliberately tags a seed (e.g. `"orifice"`); otherwise features are assigned
  by size.

## Arrangement search

`search.py` runs CMA-ES over the `free_ids` seeds (each as `x, y, r`); every proposal is
projected back onto the tangency manifold by `snap`, shallow-packed, and scored. The
objective (minimised) weighs **per-seed-triangle radius coherence** (aggregated as a
90th-percentile or max knob, over **uncropped circles only**), **usable-eye count**, and
**spatial spread**, with a penalty keeping seeds inside the margins. The winner is written
back in the same seed-JSON schema (snapped seeds, so `load`→`snap` is ~identity):

```sh
python search.py seeds/irregular_frame.json --out seeds/searched.json \
    --iters 200 --agg p90        # --agg max for worst-case coherence
# weights: --w-coh --w-eye --w-spread --w-clip
```

Richer seed sets (more free seeds, looser tangencies) give the optimiser more room; a
3-seeds-in-a-circle config is nearly geometrically determined, so it mostly fine-tunes
radii.

### Explorer (`sketch_search.py`)

An interactive way to *find* arrangements: `vsk run search/sketch_search.py`. Fix one **anchor**
circle (`anchor_x/y/r`), scatter `n_circles` random circles (Gaussian centre & radius,
sds `center_sd` / `radius_sd`), wire them into a tangency graph, snap, pack, and draw with
the objective score overlaid. It's a **re-roll explorer**: change `random_seed` / the sds
to browse arrangements instantly.

| Param | Meaning |
|-------|---------|
| `use_boundary` | Off by default — no enclosing circle, so the layout is free (fills seed gaps only). On = pack inside a `boundary_r` circle. |
| `tangency_mode` | `delaunay` (triangulate the centres) or `star` (each circle tangent to the anchor; chained into a ring when there's no boundary). |
| `random_seed` | Re-rolls the random circles (reproducible). |
| `anchor_move`, `anchor_r_move` | How far CMA-ES may nudge the anchor's centre / radius (mm) when refining. |
| `refine` | Run a short CMA-ES (`refine_iters`) on the current draw — also frees the anchor within its move bounds. |
| `save_seed`, `save_name` | Write the current arrangement to `seeds/<save_name>` (snapped seeds) for use in `sketch_gasket`. |

Layers in the explorer: gray = Apollonian fill, blue = seed circles, red = anchor,
**orange = a conflicting seed** (one that snap overlapped with another — common with a
degenerate graph like a tiny anchor ringed by big circles; the score shows `CONFLICTS=N`),
light gray = boundary + margin frame, black = the score text. Conflicting seeds are
dropped from the packing (and from a saved seed file) so the result never has intersecting
circles — re-roll or adjust (bigger anchor, fewer circles) to clear them.

Random circles are rejection-sampled to be disjoint, and `pack` rejects any circle that
significantly overlaps an already-placed one — auto-generated seed graphs aren't globally
consistent packings, so without these guards the Descartes recursion produces intersecting
circles. (Tangency reads as ~0 overlap, so valid packings are untouched.)

### Integral-packing crop browser (`sketch_integral.py`)

A second finder, for **integral Apollonian packings** (all-integer curvatures —
[wiki](https://en.wikipedia.org/wiki/Apollonian_gasket#Integral_Apollonian_circle_packings)).
These are clean, self-consistent gaskets, so there's no snapping or overlap-fixing: pick a
catalogued packing and frame a crop. `integral.py` holds the root quadruples — the
**sequential family** `(-n, n+1, n(n+1), n(n+1)+1)` (n=1…14) first, then curated Wikipedia
primitives (29 in all, each Descartes-validated and placed tangent).

| Param | Meaning |
|-------|---------|
| `packing_index` | Browse the catalogue (`0…28`); the overlay shows the quadruple + circle count. |
| `enclosing_x`, `enclosing_y` | Page-space position (mm) of the **enclosing circle** — pan the gasket under the page window. |
| `enclosing_r` | Enclosing-circle radius (mm). Usually **larger than the page**, so the page is a *crop*; raise to zoom in, lower to see the whole gasket. |
| `r_min`, `max_depth` | Smallest circle drawn / recursion cap. |
| `recursion_depth` | Recursively re-pack the **largest** circle (always a root seed, *even if it is cropped by the page*): treat it as the enclosing circle of a fresh packing with the *same* quadruple, and repeat into that sub-packing's largest circle. The sub-packing is clipped to the page like everything else. `0` = off. Only the single largest is recursed (the other large circles stay plain). In `as_eyes` mode an on-page encloser is drawn as a plain outline (its interior holds the sub-packing); a cropped encloser is filled but its outline isn't drawn. |
| `as_eyes` | Preview the crop rendered as gasket eyes (else plain circles). |
| `save_seed`, `save_name` | Write the crop to `seeds/<save_name>` (boundary = the huge enclosing circle + the 3 root circles) — `sketch_gasket` regenerates the same crop and renders it as eyes. *Captures the base packing only*; for a recursive crop, render it directly here with `as_eyes`. |

The page is a window: move `enclosing_x/y` and change `enclosing_r` to hunt for an
appealing region, then save it for `sketch_gasket`.

**Off-page / infinite-radius anchor.** The anchor may sit far off the page with a huge
radius to approximate a flat `k=0` boundary: place its *edge* near a page margin (e.g.
anchor centre `(190+R, y)`, radius `R` large ⇒ left edge ≈ x=190 ≈ a vertical line). The
sketch uses `vsk.size(..., center=False)`, so absolute mm coordinates are kept and a big
off-page anchor doesn't shove the composition around. If the anchor's *edge* is far from
the page (not just its centre), the circles tangent to it land off-page too.

**Sizes vs the sampled distribution.** Sampled radii are starting guesses; snap then
satisfies tangency by moving centres while keeping radii close to the samples (mild radius
anchor; radii hard-bounded to `[0.3×, 6×]` so nothing balloons to bridge a distant
neighbour). But tangent-circle geometry constrains sizes: a dense **Delaunay** graph is a
Koebe packing whose radii must vary several-fold, and a **star** ring must "close" around
the anchor — so sampled sizes are honoured only where the geometry allows.

## Status

The geometry, packing, snap, renderer (all four shading modes), and the CMA-ES search are
implemented and verified.

## Future directions

- **Veins** routed along the interstitial curvilinear-triangle gaps between tangent
  circles (wandering, branching Bézier paths).
- **Blended gaze + random offset** — let the `gaze` mode carry a little random scatter
  on top of the shared look-at vector, so the eyes converge on a point without looking
  too uniform. (Today `offset_mode` is one or the other.)
