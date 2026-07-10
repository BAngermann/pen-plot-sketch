# epitrochiod

A `whiskers` (Rust) sketch that draws epitrochoids and hypotrochoids —
Spirograph curves — pushed well past what a physical Spirograph toy can do:
instead of one wheel-and-pen combination, it can overlay many variants of the
same curve (different pen radii, rotated against each other) in a single
plot, and tile several independent renders across the page.

Run with `cargo run --release` from this directory; it opens the whiskers GUI
with live parameter sliders.

## How it works

A trochoid is traced by a rolling circle of radius `r = R * numerator /
denominator` rolling around (epitrochoid) or inside (hypotrochoid) a fixed
circle of radius `R`, with the pen held at distance `d * r` from the rolling
circle's center — `d = 1` is the classic epi/hypocycloid (pen on the rim),
`d < 1` sits inside the wheel, `d > 1` extends past it and starts looping.
`numerator`/`denominator` set the gear ratio (and therefore the number of
lobes); `winding` controls how much of the full period is swept.

### Stacking variants: the real point of this sketch

Rather than drawing one curve, the sketch draws `d_num` variants at once,
sweeping the pen radius from `d_min` in steps of `d_step` (`radius_step` can
grow/shrink `R` itself per variant too). Each variant can also be rotated by
its own extra phase via `angle_offset_per_d` (multiplied by the variant
index), so instead of a stack of concentric copies you get a fan of curves
rotated against one another. `d_values_layers_modulus` cycles the variants
through a small palette of vpype layers/colours, so related radii share a
colour instead of every variant getting its own.

At high `d_num` with a non-zero `angle_offset_per_d`, the overlapping curves
read as an almost solid mass — but because each variant is its own vpype
layer/colour, the plot decomposes that mass back into individual, much
lighter shapes when isolated by colour, revealing emergent structure that
isn't obvious in the combined image. The example below is a case in point:
the combined figure reads as a dense, near-solid form quite unlike a
textbook epitrochoid, but it's built entirely from the same simple curve
repeated with varying radius and phase.

<a href="../reference/epitrochoid.svg"><img src="../reference/epitrochoid.svg" width="500"></a>

### Tiling

Independently of the per-curve variants, the whole figure can be redrawn
across a grid of tiles (`num_tiles`, `layout_index`, via the [`grid`](../grid/)
library's `SquareGrid` layouts). `winding` is divided evenly across the
tiles and each tile's start angle advances by its share of the winding, so
adjacent tiles pick up where the previous one's sweep left off. `color_by_tile`
switches the per-layer colouring from "by pen-radius variant" to "by tile" when
comparing tiles matters more than comparing radii.

## Parameters

- `num_points` — vertex count of the curve (resolution).
- `numerator`, `denominator` — rolling/fixed circle ratio; sets lobe count
  and period.
- `winding` — fraction of the full period swept, divided across tiles.
- `hypotrochoid` — roll inside the fixed circle instead of outside.
- `close_path` — close the polyline into a loop.
- `radius_step` — change in the fixed circle radius `R` per pen-radius
  variant (`d_i`).
- `d_min`, `d_step`, `d_num` — pen offset (as a multiple of the rolling
  circle's radius) for each variant: `d_min + i * d_step` for `i` in
  `0..d_num`.
- `angle_offset_per_d` — extra rotation applied per variant (× variant
  index), fanning the variants out instead of stacking them concentrically.
- `angle_offset` — base rotation applied to the whole figure (and advanced
  further per tile by the winding split).
- `d_values_layers_modulus` — number of vpype layers/colours the pen-radius
  variants cycle through.
- `num_tiles`, `layout_index` — grid tiling of independent renders across
  the page, and which `SquareGrid` layout arranges them.
- `color_by_tile` — colour by tile instead of by pen-radius variant.
- `draw_bounding_box` — draw a frame around each tile.
- `top_margin`, `left_margin`, `relative_sketch_size` — page placement and
  overall scale.

## Presets

[`parameters/`](parameters/) holds saved parameter sets (JSON), loadable
from the GUI's save/load preset controls.
