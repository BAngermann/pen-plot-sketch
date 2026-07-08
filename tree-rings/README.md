# tree-rings

A `whiskers` (Rust) sketch that grows procedural tree-ring cross-sections —
closed polylines that bulge outward year by year under Perlin-noise-modulated
growth, then relax back toward even vertex spacing — and tiles several of
them across a squared dissection of the page.

Run with `cargo run --release` from this directory; it opens the whiskers GUI
with live parameter sliders.

## How it works

1. **Growing a ring.** Each ring starts as the previous year's polyline
   (`n_segments` vertices) and is pushed outward `growth_iterations` times per
   year: every vertex moves along its local normal (the average of the
   directions to its two neighbors, rotated 90°) by an amount that depends on
   both the year's overall thickness and a 3D Perlin sample at that vertex's
   position, so growth is irregular but spatially coherent from one
   iteration/year/tile to the next.
2. **Yearly thickness.** Before any vertex growth happens, one lognormal
   thickness is drawn per ring (`linear_thickness` scaled by
   `exp(N(0, 1/1.5))`), so some years are noticeably wider or narrower than
   others, independent of the finer per-vertex noise wobble.
3. **Relaxation.** After growth, `relaxation_iterations` passes even out
   vertex spacing: any edge shorter than the mean edge length borrows length
   from whichever of its two neighboring edges is longer, by nudging their
   shared vertex along that longer edge by `relaxation_increment` — this
   keeps the growing ring from bunching vertices where growth was locally
   small.
4. **Tiling.** `num_tiles` and `layout_index` pick one dissection of an
   `num_tiles x num_tiles` grid into differently sized square tiles (via the
   `grid` crate's exhaustive squaring search). Each tile grows its own
   independent tree cross-section — same parameters, different slice of the
   noise field — and afterward all tiles are rescaled together by one shared
   factor (derived from the single largest ring across every tile) so ring
   sizes stay comparable across differently sized tiles.

## Parameters

- `global_scale`, `margin_x`, `margin_y` — overall scale and page margins
  (cm).
- `n_segments` — vertex count of each ring's polyline.
- `n_rings` — number of yearly rings drawn per tree cross-section.
- `r_start` — radius of the very first ring, before any growth.
- `linear_thickness` — mean per-year radial growth, before the lognormal and
  per-vertex noise modifiers are applied.
- `relaxation_increment` — fraction of the gap a vertex closes toward its
  neighbor on each relaxation pass.
- `relaxation_iterations` — number of relaxation passes applied per year.
- `growth_iterations` — number of growth sub-steps within a single year
  (also the resolution at which the noise field is sampled along its third
  axis, see `slice_thickness`).
- `fixed_growth` — deterministic component of the per-vertex growth
  multiplier.
- `growth_noise` — weight of the Perlin noise term in the per-vertex growth
  multiplier.
- `noise_offset_x` — x-offset into the noise field, for sampling a different
  region without changing the seed.
- `slice_thickness` — spacing between successive samples along the noise
  field's third axis; each growth sub-step of each year of each tile advances
  one slice.
- `ring_scale` — final uniform scale applied to all rings within a tile,
  after the shared auto-fit scale.
- `num_tiles` — side length of the square grid to dissect for tiling (`1`
  places a single tile filling the whole page area).
- `layout_index` — which of the `num_tiles x num_tiles` grid's dissection
  solutions to use.
- `draw_outline` — draw each tile's bounding square before its rings.
