# Lovecraftian Apollonian Eye-Packing

A pen-plotter (vsketch) sketch that fills an **Apollonian circle packing** and renders
each packed circle as a Lovecraftian feature: manga-style **eyes** (pupil + iris +
negative-space specular highlights), **tooth-studded orifices**, and **bulging tissue**
at the smallest scales. Several **shading variants** (hatch / stipple / contour / ringed) share
one packing so they read as a coherent series.

See [`../lovecraftian_apollonian_plan.md`](../lovecraftian_apollonian_plan.md) for the
full design rationale.

## Running

From this directory, using the vsketch environment:

```sh
vsk run sketch_gasket.py            # interactive GUI with all parameters
vsk save sketch_gasket.py           # render to output/ with default params
vsk save --param shading_mode hatch,stipple,contour sketch_gasket.py   # one SVG per mode
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

The packing region is bounded by an **enclosing circle of negative curvature** (not by
`k=0` lines — that path has a sign-pairing bug). The **A4 page minus a uniform margin**
is a separate rectangular **discard clip**: any disk extending past it is dropped. The
**irregular frame** emerges from this clipping. You can also add very large
positive-curvature circles as seeds to approximate flat edges / richer frames — they act
as boundary (cropped, never drawn) without being packed-in.

## Files

| File | Role |
|------|------|
| `geometry.py`    | Descartes solver in `(k, w=k·z)` coords; sign-free reflection recursion. `python geometry.py` self-checks against the classic gasket. |
| `packing.py`     | Recursion to `r_min`; `Rect` discard clip; `a4_clip(margin)`. |
| `config.py`      | Seed JSON schema, loader, validation. |
| `snap.py`        | Snap-to-tangent least-squares pre-pass. |
| `style.py`       | `Style` dataclass + shading / frame enums + feature-mapping defaults. |
| `features.py`    | `eye()`, `orifice()`, `tissue()`, shading dispatch. |
| `diagnostics.py` | Headless matplotlib plot + scalar objective terms. `python diagnostics.py seeds/x.json`. |
| `sketch_gasket.py` | vsketch entry point. |
| `seeds/*.json`   | Seed configurations. |

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

## Status

The geometry, packing, snap, renderer, and all four shading modes (`hatch`, `stipple`,
`contour`, `ringed`) are implemented and verified.

## Future directions

- **CMA-ES arrangement search** (`search.py`) — find seed configs with good radius
  coherence / eye-band counts. Per-triangle coherence should aggregate as a 90th-pctile
  vs max knob, over **uncropped circles only** (large croppable seeds may approximate a
  flat `k=0` boundary and must not pollute the statistic).
- **Veins** routed along the interstitial curvilinear-triangle gaps between tangent
  circles (wandering, branching Bézier paths).
- **Blended gaze + random offset** — let the `gaze` mode carry a little random scatter
  on top of the shared look-at vector, so the eyes converge on a point without looking
  too uniform. (Today `offset_mode` is one or the other.)
