# Lovecraftian Apollonian Eye-Packing

A pen-plotter (vsketch) project that fills an **Apollonian circle packing** and renders
each packed circle as a Lovecraftian feature: manga-style **eyes** (pupil + iris +
specular highlights), a simpler eye at mid scales, and **tooth-studded orifices**.
Several **shading variants** (hatch / stipple / contour / ringed) share one packing so a
sweep reads as a coherent series rather than unrelated drawings.

### The one visual trick
A manga eye reads as "manga" because its **specular highlights are negative space** — the
pupil and iris are hatched *around* the highlight discs rather than drawn. That single
convention (implemented by subtracting the highlight discs from the shaded region with
Shapely before hatching) carries the whole aesthetic, and the tooth-studded orifice reuses
it: the teeth and folds are blank paper carved out of a solid dark disc.

---

## Three sketches, one shared library

All three sketches build on the same pure-geometry packing engine and eye renderer in
[`gasket/`](gasket/); they differ in **where the circles come from**.

- **[`gasket/sketch_gasket.py`](gasket/sketch_gasket.py)** — the **renderer** and the
  finished-piece sketch. Loads a seed configuration, snaps it to tangency, packs the
  Apollonian gasket down to the smallest feature size, and draws every circle as an eye or
  orifice. This is where shading, feature mapping, and colour live.
- **[`search/sketch_search.py`](search/sketch_search.py)** — an interactive **arrangement
  finder**. Fix one anchor circle, scatter random circles, wire them into a tangency
  graph, snap/pack, and score the result; flip `refine` to run a short CMA-ES. Good
  arrangements are **saved to [`gasket/seeds/`](gasket/seeds/)**, where they appear in the
  gasket sketch's `seed_file` dropdown — this is how the finder feeds the renderer.
- **[`integral/sketch_integral.py`](integral/sketch_integral.py)** — an **integral-packing
  crop browser**. Integer-curvature ("integral") Apollonian gaskets are clean,
  self-consistent, and need no search or snapping; this sketch pans/zooms a page-sized
  window over a catalogued packing and renders the crop directly as eyes. It is
  self-contained — it uses the shared eye renderer but does not go through the seed
  interchange.

```
seed source                 shared library            output
────────────────────────    ──────────────────        ──────────────
search  ──writes seeds──►    gasket/  (geometry,   ──► sketch_gasket  → SVG
                             snap, packing,
integral ─(own crops)────►   features, style)      ──► sketch_integral → SVG
```

The full parameter reference for every sketch lives in
**[`gasket/README.md`](gasket/README.md)**; this file is the project overview.

---

## How it works

The pipeline is four largely independent stages. The packing engine is **pure geometry**
(no vsketch types), so it runs headless inside the search loop and is unit-testable.

1. **Geometry — the Descartes (Soddy) solver.** Apollonian packing fills the curvilinear
   triangle between three mutually tangent circles via Descartes' Circle Theorem, in its
   **complex** form so each step yields curvature *and* centre at once. Curvatures are
   signed: the enclosing boundary gets negative curvature (curving away), interior circles
   positive. (Getting that sign wrong spawns children outside the boundary — the classic
   bug in this kind of code.)
2. **Snap-to-tangent.** Hand-placed or randomly scattered seeds are generally *not*
   mutually tangent, but the recursion needs tangency. A deterministic least-squares
   pre-pass (`scipy.optimize.least_squares`) minimally nudges radii/positions to satisfy
   the declared tangencies, then packs. This keeps both hand-editing and the optimizer
   working in free ℝⁿ.
3. **Packing.** Recurse over triangles, emitting one Soddy circle each, until circles fall
   below the smallest feature size. The boundary is an **enclosing circle plus an A4
   margin clip**: circles that fall outside the margins are discarded, so the outer edge
   follows the seed arrangement rather than a hard circle.
4. **Feature mapping + style.** Each circle maps to a feature by radius: large → elaborate
   eye, mid → simple eye, and (with per-orifice probability in the integral sketch) large
   circles can instead become tooth-studded orifices. A single `Style` object holds every
   spacing/weight/specular convention so variants sweep only `shading_mode`.

### Seed configs — the single source of truth

Both the search optimizer and hand-edits write the **same JSON schema**
([`gasket/config.py`](gasket/config.py) loads it): a boundary, a list of seed circles
(centre, radius, `fixed` flag, optional `feature` tag such as `"orifice"`), and a declared
tangency adjacency list. Centres are 2-element arrays in JSON (human-editable) and parsed
to `complex` internally. Deliberately hand-tagging a seed as an orifice reads as more
intentional than size-threshold assignment alone.

---

## Repository layout

vsketch stores each sketch's saved UI configs in a `config/` dir *next to the sketch* and
shows them in every sketch in that folder, so each sketch gets its own folder while the
shared library and seed interchange stay in `gasket/`:

```
lovecraftian gasket/
  README.md          # this overview
  gasket/            # shared library + sketch_gasket.py
    README.md        # full parameter reference for all three sketches
    geometry.py      # Descartes solver, Circle (pure functions)
    packing.py       # recursion, margin-clip discard, termination
    snap.py          # snap-to-tangent least-squares pre-pass
    search.py        # CMA-ES objective + runner (library side)
    integral.py      # catalogue of integral root quadruples
    features.py      # eye(), simple_eye(), orifice() -> vsketch strokes
    style.py         # Style dataclass + feature dispatch
    eyestyle.py      # build a Style from a sketch's params
    config.py        # seed-JSON schema + loader/validation
    diagnostics.py   # headless matplotlib plot + objective terms
    seeds/           # serialized arrangements (the interchange)
  search/            # sketch_search.py + its config/
  integral/          # sketch_integral.py + its config/
```

## Running the sketches

```
vsk run  gasket/sketch_gasket.py        # interactive GUI with all parameters
vsk save gasket/sketch_gasket.py        # render to output/ with default params
vsk run  search/sketch_search.py        # arrangement explorer / finder
vsk run  integral/sketch_integral.py    # integral-packing crop browser
vsk save --param shading_mode hatch,stipple,contour gasket/sketch_gasket.py  # one SVG per mode
```

Per-eye randomization (size/offset jitter, stipple, orifice teeth) uses vsketch's own RNG,
so a render is reproducible for a given **seed** (the GUI seed field or `vsk save --seed N`).

## Dependencies

- `vsketch`, `vpype` — plotter sketch framework + geometry/pipeline.
- `numpy` — array math.
- `scipy` — `optimize.least_squares` for snap-to-tangent.
- `cma` — CMA-ES for arrangement search.
- `shapely` — negative-space carving for eyes/orifices (via the shared
  [`penfill`](../penfill/) fill library).
- `matplotlib` — headless diagnostics only.

(`complex` arithmetic is builtin, so the Descartes algebra needs no extra package.)

---

## Future directions

Open items, roughly in priority order:

- **Veins.** The interstitial gaps between tangent circles (the curvilinear triangles) are
  the natural place for connective **veins** — wandering, noise-perturbed paths hugging the
  gaps with occasional branching. The renderer already reserves the smallest circles as a
  `vein` feature and floors the recursion there, but the feature is a placeholder and is
  not yet drawn. This is the main unimplemented piece from the original design.
- **Bulging tissue.** A distinct small-scale texture (bulging tissue + a single specular
  dot) was envisaged separate from the simple eye; currently mid/small circles are all
  eyes, and sub-threshold space is reserved for veins.
- **Richer boundaries.** Straight-line boundaries (`k = 0` circles, e.g. a rectangular
  frame) and irregular frames built from a few very large interior seed circles were part
  of the original plan; the current approach uses an enclosing circle plus a margin clip.
  Large cropped seed circles already approximate flat edges, but explicit line support is
  unimplemented.
- **Search-objective knobs.** The coherence term should aggregate the per-triangle jump as
  a worst-case / high quantile (90th percentile vs. max) rather than a mean, so the
  optimizer can't hide one ugly size jump behind several smooth triangles; exposing that
  choice and recalibrating the eye-size band per paper size are open tuning tasks.
```