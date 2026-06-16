# boxes

A vsketch sketch that recursively subdivides a rectangle into smaller boxes (a
randomised guillotine / treemap split) and fills each box with a pattern. It
doubles as the testbed for the [`penfill`](../penfill/) fill library.

Run with `vsk run` from this directory (the sketch adds the repo root to
`sys.path` so `penfill` imports cleanly).

## How it works

1. **Split.** Starting from one box, repeatedly pop the largest box and cut it
   along a Poisson-biased position (cuts favour offsets near the edges, giving a
   mix of large and small boxes). Splitting stops once the largest remaining box
   falls below `area_threshold`.
2. **Fill.** Each surviving box becomes a polygon and is filled via `penfill`.
   In deterministic mode every box uses one fixed spec. In random/freeze mode
   each box gets a fill *type* (see below) with the remaining parameters sampled.
3. **Outline + colour.** An optional black outline is drawn on top, and a vpype
   `color` command assigns the per-layer palette for the GUI/preview.

### Random / freeze mode

When `random_fill` is on, fill *types* are assigned hierarchically over the split
tree so the result is a mix of coherent patches and noise:

- The first `freeze_after_splits` cuts are a warm-up — boxes there are not frozen.
- After that, each newly created box is **frozen** with probability `freeze_prob`
  to a random **fill type** — `solid`, `hatch`, or a single glyph — and *all its
  descendants inherit that type*.
- Within a frozen subtree the type is fixed but the other parameters still vary
  per box (hatch direction, spacing, square/hex/halton grid, glyph angle, size…).
- Boxes never caught by a freeze get an independent random type.

Because freezing is inherited, it is "sticky": `freeze_prob` mainly controls
*where* in the tree coherence begins — higher → freezes earlier → larger, fewer
patches; lower → freezes deeper → smaller patches and more independently-random
boxes.

## Parameters

### Layout / split
- `box_width`, `box_height` — initial box size (box units; see `scale`).
- `area_threshold` — stop splitting when the largest box is smaller than this.
- `split_lambda` — Poisson rate for cut placement (higher → cuts closer to an
  edge → more size contrast).
- `scale` — cm per box unit (e.g. `0.2` → a 90-unit box is 18 cm).
- `drop_probability` — chance each box is left empty.
- `split_seed` — seed for the split (0 = varies each run).

### Fill
- `fill_pattern` — `solid` (vsketch native fill), `hatch`, or `glyph_grid`.
  Used only in deterministic mode (ignored when `random_fill` is on).
- `random_fill` — when on, use random/freeze mode; when off, use one fixed spec
  built from the deterministic knobs below.
- `fill_seed` — seed for fill sampling / glyph jitter (0 = varies each run).
- `fill_spacing` — base grid / hatch spacing in box units.
- `draw_outline` — draw a black box border on top of the fill.

### Random / freeze knobs (used when `random_fill` is on)
- `freeze_after_splits` — number of warm-up cuts before freezing can begin.
- `freeze_prob` — probability each new box freezes to a random fill type.
- `spacing_var` — spacing varies ± this fraction of `fill_spacing` per box.

### Deterministic-mode knobs (ignored when `random_fill` is on)
- `grid_type` — `square`, `hex`, or `halton` (for `glyph_grid`).
- `glyph_type` — `dash`, `plus`, `circle`, `chevron`, `sine`, `sawtooth`,
  `triangle_wave`.
- `size_ratio` — glyph size as a fraction of `fill_spacing`.
- `grid_angle`, `glyph_angle` — rotation of the grid and of each glyph.
- `halton_base_x`, `halton_base_y` — Halton bases (used when `grid_type ==
  "halton"`); distinct coprime primes work best.
- `hatch_angle`, `hatch_cross` — angle and crosshatch toggle for `hatch`.

## Layers

Fills land on layers 2–4 (random per box); the outline is drawn on layer 6 so it
sits on top. The palette is set in `draw()` via vpype `color --layer …`.

> Note: the layer-6 outline is a deliberate quick-and-dirty way to keep the
> outline on top. More colours and reading pen settings from config are planned.

## Saved configs

`config/` holds vsketch parameter presets (e.g. `Cross.json`, `Eroded.json`)
saved from the GUI.
