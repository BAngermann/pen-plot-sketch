# rolling_circles

A `whiskers` (Rust) sketch that traces the curve drawn by a pen fixed to the
last circle in a chain of circles rolling on one another without slipping —
a generalisation of epitrochoids/hypotrochoids from two circles to an
arbitrary chain.

Run with `cargo run --release` from this directory; it opens the whiskers GUI
with live parameter sliders.

## How it works

1. **Chain from a sequence.** `radii` is a comma-separated list of (possibly
   negative) integers. Term 0 is a fixed base circle; term *k* is a circle
   rolling on circle *k-1*. `radius` rescales the whole chain so the base
   circle has that physical size (mm).
2. **Roll without slipping.** For each angle `theta` the sketch walks the
   chain: circle *k*'s center orbits circle *k-1*'s center at radius
   `r_(k-1) + r_k`, and its own spin accumulates at `(r_(k-1)+r_k)/r_k` times
   `theta` (the no-slip condition). The traced point sits at distance `d *
   r_last` from the center of the last circle, at the accumulated spin angle.
3. **Closing the curve.** Each stage's spin is a rational multiple of
   `theta`, so the whole system returns to its starting configuration after a
   finite number of revolutions (`theta_max`). `num_points` samples are taken
   evenly across `[0, theta_max)` and joined into a closed polyline.

## Parameters

- `radii` — comma-separated integer sequence defining the chain (e.g.
  `1,-3,5`). Negative terms are handled per `use_phase_for_negatives` below.
- `use_phase_for_negatives` — two ways to turn the (possibly negative)
  sequence into radii: **off** shifts the whole sequence so the smallest term
  becomes 1 (radii stay relative to each other); **on** takes the absolute
  value as the radius directly and instead starts a negative term's contact
  point 180° around the previous circle.
- `radius` — physical size (mm) of the base circle; rescales the whole chain.
- `num_points` — vertex count of the highest-resolution shape (see grid
  below).
- `d_min`, `d_step`, `d_num` — the traced point's distance from the last
  circle's center, as a multiple of its radius. `d_num` curves are drawn, at
  `d_min + i * d_step` for `i` in `0..d_num` — like moving the stylus outward
  on a Spirograph wheel.
- `grid_rows`, `grid_cols`, `point_offset`, `cell_spacing` — the whole shape
  is redrawn once per grid cell, laid out `cell_spacing` mm apart. Point
  count increases across the grid (row-major) from `3 + point_offset` up to
  `num_points` at the last cell, so the grid doubles as a resolution sweep —
  useful for picking the sparsest vertex count that still reads as the
  intended shape.
- `layer_circles` — draw the shape as a stack of vpype layers, one per prefix
  of the chain: layer 1 uses only the center circle, layer 2 the first two
  circles, and so on until the final layer draws the whole chain. Each layer
  gets a distinct hue, and (by default) all layers share the same theta sweep
  and scaling so the partial curves stack directly on top of one another.
- `skip_layers` — when layering, omit the first *k* prefixes (e.g. `2` starts
  from the three-circle prefix). Clamped so the full chain is always drawn.
- `per_layer_period` — when layering, give each prefix its own minimal closing
  sweep instead of sharing the full chain's `theta_max`. Layers still overlay
  (same scale/origin), but each partial curve is traced once rather than
  retraced over the full chain's extra revolutions.

## Explored and discarded

A second generative multiples mode was tried where, instead of increasing vertex
count across the whole grid, each row shared the same point count and each
column instead offset the sampling start angle (`theta_start`, swept from 0
to `theta_max`) — so every column sampled the same underlying closed curve
at different points, producing a different straight-edge polyline through
it. In practice the resulting polylines didn't read as visually distinct or
interesting enough to justify the extra parameter, so it was dropped.
