# crack

A vsketch sketch that renders a **cracked mosaic**: it recursively subdivides a
rectangle into shards (a randomised guillotine split), fills each with a random
palette colour, then carves a single jagged crack that runs from the top edge to
the bottom edge by deleting a connected chain of boxes.

It is a stripped-down, solid-fill descendant of the [`boxes`](../boxes/) sketch
(which is the general testbed for the [`penfill`](../penfill/) library). Where
`boxes` supports hatch/glyph fills and a random/freeze mode, `crack` keeps only
solid (or no) fill and adds the crack.

Run with `vsk run` from this directory (the sketch adds the repo root to
`sys.path` so `penfill` imports cleanly).

## How it works

1. **Split.** Starting from one box, repeatedly pop the largest box and cut it
   along a Poisson-biased position (cuts favour offsets near the edges, giving a
   mix of large and small boxes). Splitting stops once the largest remaining box
   falls below `area_threshold`.
2. **Crack.** Pick the top-row shard straddling the horizontal midline and
   delete it, then step down to a random shard sharing its bottom edge and delete
   that too, repeating until the bottom edge of the page is reached. The deleted
   chain is a connected fissure from top to bottom (its exact route varies with
   the seed). The crack is then optionally **widened** over `widen_iterations`
   passes: each pass walks the crack's current outer edge and, for every shard on
   it, deletes one neighbouring shard — left with probability `widen_left_prob`,
   otherwise right — so the fissure grows a ragged edge (a neighbour already
   deleted is left as-is and doesn't extend the edge further). Widening can
   occasionally nibble away every neighbour of some shard, cutting it off from
   both page edges; if `remove_islands` is on, one final pass finds and drops
   any such **islands** (checked by flood-filling from the left and right page
   boundaries through surviving shards).
3. **Fill + outline + colour.** Each surviving shard becomes a polygon filled
   with a random palette colour (`solid`) or left empty (`none`); an optional
   outline is drawn on top, and a vpype `color` command assigns the per-layer
   palette for the GUI/preview.

## Randomness

There is no seed parameter — splitting, the crack route, and colour assignment
all draw from vsketch's own RNG. Use the **seed control in the vsketch GUI** to
reproduce or reshuffle a result; each fresh run without pinning the seed varies.

## Parameters

### Layout
- `box_width`, `box_height` — figure size in abstract box units; the sketch
  scales this to the page automatically (see margins), so only the *aspect
  ratio* and the split granularity matter.
- `area_threshold` — stop splitting when the largest box is smaller than this.
- `split_lambda` — Poisson rate for cut placement (higher → cuts closer to an
  edge → more size contrast).
- `page_size` — page format string passed straight to vsketch's `size()`
  (portrait; default `a4`). Either a known page name (`a6`, `a5`, `a4`, `a3`,
  `a2`, `a1`, `a0`, `letter`, `legal`, `executive`, `tabloid`) or an explicit
  `WxH` spec with units, e.g. `10cmx10cm`.
- `widen_iterations` — number of crack-widening passes, `0`–`4` (default `1`;
  `0` leaves the crack at its unwidened, single-shard-wide route).
- `widen_left_prob` — probability, `0`–`1` (default `0.5`), that a given
  widening pick grows the crack to the **left** rather than the right.
- `remove_islands` — drop shards left disconnected from both page boundaries by
  widening (default `on`).
- `margin_x`, `margin_y` — symmetric left/right and top/bottom page margins in
  **centimetres** (default `1.0`). The figure is scaled to fit the chosen
  `page_size` (portrait) minus the margins; because the page and figure aspect
  ratios differ, the tighter axis lands exactly on its requested margin and the
  other axis ends up with a larger one.
- `pen_width` — pen width in mm (default `0.3`); also the line width in the GUI
  preview.

### Fill
- `fill_pattern` — `solid` (vsketch native fill) or `none` (unfilled: outline
  only, or nothing if `draw_outline` is off).
- `draw_outline` — draw a shard border on top of the fill.

### Colours
- `left_color_1` … `left_color_3` / `right_color_1` … `right_color_3` — two
  independent palettes (up to 3 pens each), one for shards on the **left** of the
  crack and one for the **right**, chosen from the pens loaded out of
  [`../pens/`](../pens/). Within each palette the first slot set to `none` ends
  it (e.g. `left_color_2 = none` → a single left colour). Each shard is assigned
  a random colour from its side's palette. The two palettes default to the same
  three colours; change one side to tint the halves differently. Listing the
  same pen twice in a palette weights the random pick (e.g. `[purple, purple,
  blue]` → a 2:1 purple/blue mix).
- `outline_color` — pen for the shard outline (`none` → black).

Pens come from vpype pen-config TOML files in `../pens/`, converted from
DrawingBot presets with [`tools/drawingbot_to_vpype.py`](../tools/). Add more
presets there and they appear in the dropdowns — each with a colour swatch next
to its name in the GUI.

## Layers

Layers are keyed by **colour, not by side or slot**: every distinct colour used
across both palettes gets exactly one layer, so all same-coloured shards plot in
a single pen pass (a plotter optimisation — fewer pen lifts, better path
sorting). Duplicate entries within a palette collapse onto that colour's layer
while still weighting the random pick. The outline is drawn on the next layer up
so it sits on top. Colours are applied in `draw()` via vpype `color --layer …`.
With the default identical palettes this is 3 fill layers + 1 outline layer.
