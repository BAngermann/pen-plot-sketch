# Lovecraftian Apollonian Eye-Packing — vsketch Project Plan

A pen-plotter (vsketch) project: an over-the-top Lovecraftian composition built on
Apollonian circle packing, where circles are rendered as manga-style eyes (pupils,
irises, specular highlights), connective veins, bulging tissue at small scales, and
tooth-studded orifices.

This document is the seed for the work. It is deliberately written so a fresh
session (e.g. Claude Code) can pick up the project from this file alone, with no
reference to the originating chat.

---

## 1. Goal & aesthetic

- Base geometry: **Apollonian circle packing**, bounded, with support for
  **straight-line boundaries** (a rectangle, possibly plus large interior seed circles
  forming an irregular frame).
- Each packed circle maps to a **feature**:
  - large / low-depth → **manga eye** (pupil + iris + 1–2 specular highlights as negative space)
  - medium → smaller eye **or** **tooth-studded orifice**
  - small (near `r_min`) → **bulging tissue** + a single specular dot
  - interstitial gaps (curvilinear triangles between tangent circles) → **veins**
- **Several shading variants** that remain a coherent series: same packing, same seed
  config, same global style conventions; only a small named axis (e.g. `shading_mode`)
  varies between variants.
- Termination: stop recursion when circles fall below `r_min`; the smallest circles
  become tissue rather than eyes.

### Key visual trick
Manga-eye highlights are **negative space** — hatch *around* the specular spots rather
than drawing them. This single convention is what makes the eye read as "manga."

---

## 2. Architecture

Four largely independent subsystems. The packing engine is **pure geometry** (no
vsketch types) so it can run headless inside the search loop and be unit-tested.

1. **Packing engine** — produces a tree of circles `(center, curvature, depth, parent)`.
2. **Arrangement search** — offline optimizer finding seed configs with good radius coherence.
3. **Renderer** — maps each circle to a feature and emits vsketch strokes.
4. **Style controller** — global style object + per-variant shading dispatch.

### Suggested file layout
```
gasket/
  geometry.py      # Descartes solver, Circle/Triangle, pure functions
  packing.py       # recursion, r_min termination, boundary lines
  snap.py          # snap-to-tangent least-squares pre-pass
  search.py        # CMA-ES objective + runner, writes seeds/*.json
  features.py      # eye(), tissue(), orifice(), vein() -> vsketch calls
  style.py         # Style dataclass + variant presets
  sketch.py        # vsketch.SketchClass: load seed, pack, render, draw frame
  diagnostics.py   # headless matplotlib plot of a shallow packing + objective terms
  seeds/           # serialized good arrangements (JSON)
```

---

## 3. Geometry — the Descartes (Soddy) solver

Apollonian packing fills the curvilinear triangle between three mutually tangent
circles via **Descartes' Circle Theorem**. Use the **complex** form so each step yields
both curvature and center in one pass:

```
k4 = k1 + k2 + k3 ± 2*sqrt(k1*k2 + k2*k3 + k3*k1)
k4*z4 = k1*z1 + k2*z2 + k3*z3 ± 2*sqrt(k1*k2*z1*z2 + k2*k3*z2*z3 + k3*k1*z3*z1)
```

- `z_i` are centers as complex numbers; `k_i = 1/r_i` are **signed** curvatures.
- **Straight lines are circles with `k = 0`.** A rectangular boundary is four lines.
  A line needs an orientation so "inside the box" is consistent.
- **Sign convention:** the bounding circle/box gets negative curvature (curving away);
  interior circles positive. Getting this wrong spawns children *outside* the boundary —
  the most common bug in this kind of code. Verify visually on a trivial 3-circle gasket
  before doing anything else.

### Core data structures
```python
from dataclasses import dataclass, field

@dataclass
class Circle:
    z: complex          # center
    k: float            # signed curvature (1/r); sign tracks inside/outside
    depth: int
    feature: str = ""   # assigned later by renderer

    @property
    def r(self) -> float:
        return abs(1.0 / self.k)

@dataclass(frozen=True)
class Triangle:
    a: Circle
    b: Circle
    c: Circle
```

> Note for C++/R users: `@dataclass` ≈ a struct with an auto-generated constructor,
> `__eq__`, and `__repr__` (no boilerplate). `complex` is a builtin first-class type
> (no `std::complex<double>` needed), which keeps the Descartes algebra terse.

### Recursion shape
A gasket triangle is a triple of mutually tangent circles. Each spawns one inner Soddy
circle, which forms three new triangles. So recurse over **triangles**, emitting one
circle per triangle, carrying `depth`. Stop a branch when the Soddy radius `< r_min`.

**Two different packing depths for two purposes:**
- **Shallow** (a few generations, `max_gen_in_objective`) — used inside the search loop.
- **Full** (down to `r_min`) — used once, on the winning seed, at render time.

---

## 4. Seed JSON — the single source of truth

Both the optimizer and hand-edits write the **same schema**; the packing engine consumes
it. This is the stable interface for the whole project.

```json
{
  "boundary": {
    "type": "rect",
    "lines": [
      {"point": [0, 0],   "normal": [0, 1]},
      {"point": [0, 0],   "normal": [1, 0]},
      {"point": [210, 0], "normal": [-1, 0]},
      {"point": [0, 297], "normal": [0, -1]}
    ]
  },
  "seeds": [
    {"id": "s0", "z": [70, 100],  "r": 45, "fixed": true,  "feature": "eye"},
    {"id": "s1", "z": [140, 120], "r": 40, "fixed": false, "feature": "eye"},
    {"id": "s2", "z": [105, 200], "r": 38, "fixed": false, "feature": "orifice"}
  ],
  "tangencies": [
    ["s0", "s1"], ["s1", "s2"], ["s0", "line:0"], ["s2", "line:3"]
  ],
  "search": {
    "free_ids": ["s1", "s2"],
    "bounds": {"r": [25, 55]},
    "r_min": 1.5,
    "max_gen_in_objective": 4
  }
}
```

Design decisions:
- **Centers as 2-element arrays in JSON, parsed to `complex` internally.** JSON has no
  complex type and the file must stay human-editable. Convert at the boundary
  (`complex(z[0], z[1])`), use `complex` everywhere downstream.
- **`fixed` (per-seed) and `free_ids` (flat list) are redundant on purpose:** `fixed`
  documents intent for a human reader; `free_ids` is what the optimizer iterates.
  Validate consistency on load.
- **`tangencies` is a declared adjacency list**, not inferred. Pairs may reference
  `line:<index>` for boundary tangency. This removes ambiguity about which contacts the
  snap step must satisfy.
- **Hand-edited seeds + JSON config are the workflow**: place/annotate circles by hand,
  let the search move only the `free_ids`. Deliberate placement (esp. of orifices) reads
  as more intentional than size-threshold assignment alone.

---

## 5. Snap-to-tangent pre-pass (load-bearing)

Hand-placed circles are generally **not** mutually tangent, but Apollonian recursion
requires tangency to seed each triangle.

**Chosen approach (Route B — relax & snap):** let the human place circles freely; a
deterministic pre-pass minimally adjusts radii/positions to achieve the declared
tangencies, *then* pack. This is far friendlier to both hand-editing and the optimizer
(which then works in free ℝⁿ, with the snap as a deterministic projection). Cost: the
rendered eyes drift slightly from where placed.

(The rejected alternative, Route A, enforces tangency as a hard constraint and moves
seeds along the tangency manifold — cleaner gaskets but fiddly to hand-edit.)

The snap is a small nonlinear least-squares over declared pairs:
- circle–circle term:  `(|z_i - z_j| - (r_i + r_j))^2`
- circle–line term:    `(dist(z_i, line) - r_i)^2`

Use `scipy.optimize.least_squares` (Levenberg–Marquardt, same idea as R's `nls`).

---

## 6. Arrangement search

The "no huge jump between seeds and first interior" constraint is really a constraint on
**initial curvatures**. For three tangent seeds, the first interior circle has
`k4 = k1 + k2 + k3 + 2*sqrt(...)`. Very unequal seeds ⇒ large `k4` ⇒ tiny circle ⇒
abrupt jump.

### Objective (work in `log r`)
Radii span orders of magnitude; you care about ratios, so log-transform.

```
L =  coherence_term                       # spread of log r across early generations
   + lambda1 * |r_seed / r_child - rho*|  # hit a target seed:child ratio
   - lambda2 * count_in_eye_band          # reward enough usable eyes
   ( + optional spatial-spread term )
```

Three properties, in tension — all belong in `L`:
1. **Radius coherence** across early generations (the stated constraint).
2. **Eye count in the usable size band** — a coherent packing that yields 3 eyes and a
   sea of dots is useless.
3. **Spatial spread** — eyes across the frame, not clustered with dead boundary regions.

### Critical aggregation subtlety
`k4` is dominated by the **largest seed curvature (smallest seed)** in each triangle, so
the jump is controlled **per-triangle, not globally**. A config can be smooth in one
triangle and jump badly in another. Aggregate the coherence term as a **worst-case or
high quantile (e.g. 90th percentile / max) over all seed triangles**, not a mean/variance
— otherwise the optimizer hides one ugly jump behind several smooth ones. **Lock this
down before writing the objective.** (Make 90th-percentile-vs-max a config/UI knob.)

**Aggregate over uncropped circles only.** Seeds may include one or more *very large*
circles that get cropped — used as an approximation to the `k=0` line / flat-boundary
case (and more general frames). Such a circle participates as a tangency boundary but is
not emitted (it fails `clip.contains_disk`); it must likewise be **excluded from the
coherence aggregation** so it cannot pollute the statistic. (`diagnostics.analyse()`
already filters to in-clip circles.)

### Optimizer
- **CMA-ES** (`cma` package) — derivative-free, robust to the non-convex landscape from
  tangency. First choice.
- Penalty method for any soft constraints so the optimizer stays in ℝⁿ.
- The objective calls the (shallow) packing engine thousands of times → engine must be
  fast and side-effect-free.
- Run offline; serialize winning seed configs to `seeds/*.json`; render stage just loads one.

### Instrument before optimizing
Build a **headless diagnostic renderer** first (`diagnostics.py`): take a seed config,
snap, pack shallow, dump a matplotlib plot (circles colored by generation) + print the
scalar objective terms separately. Per config, log:
- histogram of `log r` by generation (the coherence story),
- count in the eye-size band `[r_eye_min, r_eye_max]`,
- a spatial-coverage proxy (e.g. std-dev of eye-band centers, or covered-area fraction).

**Calibrate `L` against your own visual judgment on ~10 hand-made configs.** Once `L` is
trustworthy, the optimizer is almost an afterthought.

---

## 7. Renderer — feature assignment

| Circle role        | Size regime   | Feature                                            |
|--------------------|---------------|----------------------------------------------------|
| Large, low depth   | big           | manga eye (pupil + iris + 1–2 speculars)           |
| Medium             | mid           | smaller eye **or** tooth-studded orifice           |
| Small (near r_min) | small         | bulging tissue + specular dot                      |
| Interstitial gaps  | —             | veins routed along tangency arcs                   |

- **Manga eye** = concentric vsketch primitives: outer circle (sclera, = the packed
  circle), iris (~0.6r), pupil (~0.3r, "filled" black via dense hatching since plotters
  don't fill), 1–2 **specular highlights left as negative space** (hatch around them).
- **Veins** = connective tissue routed along the curvilinear triangles between tangent
  circles (exactly where vasculature looks natural). Wandering / noise-perturbed Bézier
  paths hugging the gaps, with occasional branching (simple L-system or recursive branch).
- **Tooth-studded orifices** (the ambitious bit): a circle whose interior is dark
  (hatched), with **teeth as inward-pointing triangles** from the rim, irregular in
  size/angle, plus a radial gum line. Implement as a parametrized **ring generator** so
  the same code serves any orifice circle.

---

## 8. Style coherence

Share a **global style object** across all features; variants sweep only a small named
axis. "Coherent style, different shading" = `shading_mode` changes (hatch vs stipple vs
contour-following the curvature) while spacing/weight/specular conventions stay fixed.
Generate all variants from **one** packing + **one** seed config so they are literally
the same eyes shaded differently.

```python
from dataclasses import dataclass

@dataclass
class Style:
    hatch_spacing: float
    hatch_angle: float
    stroke_weight: float
    specular_count: int
    vein_density: float
    shading_mode: str    # "hatch" | "stipple" | "contour"
```

The top-level entry point is a `vsketch.SketchClass` (its `draw`/`finalize` lifecycle,
`param()` for interactive sweeps). Everything beneath it is plain, testable Python.

---

## 9. Build order

Revised so the load-bearing, search-adjacent pieces and the JSON interface come first;
style is tuned last on already-good packings.

1. **Descartes solver + line support**, verified visually on a trivial 3-circle gasket
   (no features). Nail the sign conventions here in isolation.
2. **Seed JSON schema + loader + validation** (`fixed`/`free_ids` consistency,
   `tangencies` references resolve).
3. **Snap-to-tangent solver** (`scipy.optimize.least_squares`) — both search and render
   depend on it.
4. **Shallow packing + headless diagnostic plot** (`diagnostics.py`) so configs can be
   eyeballed and `L` calibrated.
5. **Full recursion to `r_min`** with the rectangular boundary.
6. **Search**: define `L` (with per-triangle worst-case coherence), wire CMA-ES, run
   offline, write `seeds/*.json`. Identify a handful of suitable packings.
7. **Feature assignment** by size threshold + deliberate per-seed `feature` tags; render
   plain circles → eyes.
8. **Veins and tooth-studded orifices.**
9. **Style variants** — tune shading on the good packings from step 6.

> Stage-one focus (per current plan): **identify suitable packings first** (steps 1–6),
> *then* tune visual style on them (steps 7–9).

---

## 10. Open decisions to settle early

- **Boundary shape:** pure rectangle, or rectangle + a few large interior seed circles
  forming an irregular frame?
- **Per-triangle coherence aggregation:** confirm max vs. 90th-percentile before writing `L`.
- **Eye-size band** `[r_eye_min, r_eye_max]` and `r_min` values for the target paper size
  (defaults above assume A4 ≈ 210×297 mm).
- **Orifice placement:** deliberate (hand-tagged in JSON) is preferred over size-threshold
  alone, but confirm whether *any* size-based fallback is wanted.

---

## 11. Dependencies

- `vsketch`, `vpype` — plotter sketch framework + geometry/pipeline.
- `numpy` — array math.
- `scipy` — `optimize.least_squares` for snap-to-tangent.
- `cma` — CMA-ES for arrangement search.
- `matplotlib` — headless diagnostics only.

(`complex` arithmetic is builtin; no extra package needed for the Descartes algebra.)
