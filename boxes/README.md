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
- `pen_width` — pen width in mm (default `0.3`). Sets the spacing reference for
  solid/hatch/glyph fills and the line width used in the GUI preview.
- `drop_probability` — chance each box is left empty.
- `split_seed` — seed for the split (0 = varies each run).

### Fill
- `fill_pattern` — `solid` (vsketch native fill), `hatch`, or `glyph_grid`.
  Used only in deterministic mode (ignored when `random_fill` is on).
- `random_fill` — when on, use random/freeze mode; when off, use one fixed spec
  built from the deterministic knobs below.
- `fill_seed` — seed for fill sampling / glyph jitter (0 = varies each run).
- `fill_spacing` — base grid / hatch spacing in box units.
- `draw_outline` — draw a box border on top of the fill.

### Colours
- `color_1` … `color_6` — the fill palette, chosen from the pens loaded out of
  [`../pens/`](../pens/). The first slot set to `none` ends the palette, so to
  use fewer colours just set the next one to `none` (e.g. `color_4 = none` → a
  3-colour palette). Each box is assigned a random palette colour.
- `outline_color` — pen for the box outline (`none` → black).

Pens come from vpype pen-config TOML files in `../pens/`, converted from
DrawingBot presets with [`tools/drawingbot_to_vpype.py`](../tools/). Add more
presets there and they appear in the dropdowns — each with a colour swatch next
to its name in the GUI.

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

Fills land on layers `1..K`, where `K` is the number of selected palette colours;
the outline is drawn on layer `K+1` so it sits on top. Colours are applied in
`draw()` via vpype `color --layer …` from the selected pens.

## Saved configs

`config/` holds vsketch parameter presets (e.g. `Cross.json`, `Eroded.json`)
saved from the GUI.
