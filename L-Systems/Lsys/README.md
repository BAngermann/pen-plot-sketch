# Lsys — L-System Turtle Plotter

A [vsketch](https://github.com/abey79/vsketch) sketch that grows
[L-systems](https://en.wikipedia.org/wiki/L-system) (Lindenmayer systems) and
renders them with a turtle, ready for pen plotting. A library of presets lives
in [`config/`](config/).

## What it does

An L-system starts from a short **axiom** string and repeatedly rewrites it by
substituting symbols according to **production rules**. The resulting (often
very long) string is then read left-to-right by a **turtle** that draws lines,
moves, turns, and branches. This combination of simple rules and geometric
interpretation produces fractals and plant-like forms.

This sketch supports up to two production rules, branching via a matrix stack,
optional mid-string scaling, and Gaussian jitter on lengths and angles for an
organic, hand-grown look. Jittered copies can be overlaid as a "bundle" and
optimally aligned, and the whole drawing can be repositioned on the page. It
targets a page set by `page_size` / `landscape` (default portrait A4), in **cm**.

## Parameters

### Rewriting (string generation)

| Param | Meaning |
|-------|---------|
| `Axiom` | Initial string the rewriting starts from. |
| `Pred1` / `Suc1` | Rule 1: every occurrence of the predecessor symbol `Pred1` is replaced by the successor string `Suc1` each iteration. |
| `Pred2` / `Suc2` | Rule 2: a second optional predecessor → successor rule. Leave blank to disable. |
| `iterations` | How many rewrite passes to apply. String length typically grows exponentially — raise carefully. |

Each iteration, every character is checked: if it matches `Pred1` it becomes
`Suc1`, if it matches `Pred2` it becomes `Suc2`, otherwise it is copied
unchanged.

### Turtle interpretation (drawing)

After rewriting, the final string is walked symbol by symbol:

| Symbol | Action |
|--------|--------|
| any char in `Draw` | Draw a line one unit forward and advance. |
| the `Move` char | Move one unit forward **without** drawing. |
| `+` | Turn by `+TurnAngle`. |
| `-` | Turn by `-TurnAngle`. |
| `[` | Push the current turtle state (start a branch). |
| `]` | Pop the turtle state (return to the branch point). |
| `*` | Scale subsequent motion by `TransformScale` (compounds; usually placed inside a branch). |
| `#` | Increase the stroke weight by 1. |
| `!` | Decrease the stroke weight by 1 (never below 1). |
| `'` | Increment the colour index (only used when `color_mode` is `symbol`). |
| `"` | Decrement the colour index (may go negative; see [Pen colours](#pen-colours)). |

Note that `Draw` is a *set* of characters (e.g. `"FG"` means both `F` and `G`
draw), while `Move` is a single character.

| Param | Meaning |
|-------|---------|
| `Draw` | Characters that draw a line segment. |
| `Move` | Character that advances without drawing. |
| `TurnAngle` | Degrees turned by `+` / `-`; fractional values are allowed (3 decimals in the GUI). |
| `TransformScale` | Multiplier applied by `*` (used for self-similar branch tapering). |
| `Scale` | Overall scale of the whole figure on the page. |
| `StrokeWeight` | Initial integer stroke weight (≥ 1) at the start of the string. |
| `pen_width` | Physical pen width in mm. |
| `shorten_strokes` | Pull both ends of every stroke in so heavy strokes keep their nominal length (see below). |

#### Stroke weight

Stroke weight uses vsketch's `strokeWeight`: a weight of *n* draws *n* parallel
lines per segment, spaced by `pen_width` so the pen strokes sit side by side and
build up a thicker line (as in the Takagi sketch). Set `pen_width` to your
actual pen's nib width.

The weight lives on the turtle state alongside position, heading and scale, so
`[` pushes it and `]` restores it: a `#` or `!` inside a branch only affects
that branch. Unlike `*`, the weight is an integer that changes additively and
is **not** multiplied by `Scale`, and the jitter parameters don't affect it.
With `shorten_strokes` on, each end of a weight-*n* stroke is pulled in by
(*n*−1)/2 pen widths, which is exactly how far the extra lines poke out past
that end (the stroke grows by *n*−1 pen widths in total). The outer extent then
matches the unweighted segment. Segments shorter than the total reduction
shrink to a dot rather than flipping around. Note this leaves small gaps at
corners where heavy strokes meet.

Example: `F[#F][!F]` draws the stem, a thicker branch and a thinner one.

### Variation & repetition

| Param | Meaning |
|-------|---------|
| `Angle__std_deviation` | Standard deviation of Gaussian noise added to every turn (degrees). `0` = exact. |
| `Length_std_deviation` | Standard deviation of Gaussian noise added to every segment/move length. `0` = exact. |
| `instances` | Number of overlaid copies of the figure (combine with the std-deviation params to draw a "bundle" of slightly different growths). |
| `AlignStart` / `AlignEnd` | Vertex-index range each copy is aligned on. With `instances > 1`, every copy is fitted onto the first by the rigid transform (rotation + translation) that minimizes the mean squared distance between corresponding endpoints — a Kabsch/Procrustes fit — computed over the endpoints in `[AlignStart, AlignEnd)`. See [Alignment range](#alignment-range). |
| `Fix_reference` | When on, instance 0 is drawn at its exact nominal (un-jittered) values, so it acts as a clean alignment reference. |

#### Alignment range

The alignment is a single control with two extremes, selected by the vertex
index range:

- **First vertex only → pin at the shared start point.** This is the default
  (`AlignStart = AlignEnd = 0`) and what any empty range falls back to. Since
  every instance starts at the same origin, aligning on just the first vertex is
  a no-op, so the bundle fans out from the start.
- **All vertices → best whole-shape fit.** Clusters the bundle around a common
  shape.
- **Any sub-range in between** aligns the copies on that stretch of the path
  (e.g. align the tips, or a middle section) and lets the rest drift.

Index handling: `AlignStart` is clamped to `≥ 0`; an `AlignEnd` past the last
vertex **or** negative means "all vertices"; an empty range (start ≥ end) falls
back to the first vertex only.

### Placement

The drawing's bounding box is automatically centred in its panel (the whole page by default) (vsketch's
own auto-centring is disabled). It is then rotated about its centre and
translated by the global offset.

| Param | Meaning |
|-------|---------|
| `GlobalRotation` | Rotation of the whole drawing about its centre, in degrees. |
| `GlobalTranslateX` / `GlobalTranslateY` | Offset from the page centre, in cm. |

### Panel layout

Several copies of the L-system can share one page, e.g. a triptych. The page is
divided into a `panels_x` × `panels_y` grid of equal panels, numbered row by row
from the top left.

| Param | Meaning |
|-------|---------|
| `panels_x` / `panels_y` | Number of columns / rows (default 1 × 1 = the old single-drawing behaviour). |
| `margin_x` / `margin_y` | Exterior margin around the whole grid, in cm. |
| `gap_x` / `gap_y` | Space between neighbouring panels, in cm (may differ from the margins and between x and y). |
| `panel_fit` | Scale each drawing uniformly so it fills its panel (`Scale` is then irrelevant). Off: `Scale` is used as is and the drawing is only centred, so a large figure can overflow its panel. |
| `panel_anchor` | What is pinned to the panel. `center` (default): the drawing's bounding box is centred, so drawings of different size have different start points. `start`: the turtle's starting point is placed at the same spot in every panel and the drawing is rotated and scaled about it, so e.g. tree roots line up horizontally across panels of different height. |
| `anchor_x` / `anchor_y` | Where the start point goes in `start` mode, as a fraction of the panel (0 = left/top, 1 = right/bottom, default 0.5 / 0.5). `GlobalTranslateX/Y` is added on top. |
| `panel_rotation_step` | Rotates panel *k*'s whole virtual page by *k* × `panel_rotation_step` degrees about the panel centre — the drawing **and** its anchor position move together, unlike `GlobalRotation`, which only turns the drawing. E.g. with `anchor_y = 0.95` (root near the bottom) a 180° panel has its root the same distance below the top edge and grows downward; a step of 60 gives 0°, 60°, 120°. Non-multiples of 90° (and 90° in non-square panels) swing the panel's corners outside its cell. |
| `panel_seed` / `panel_seed_step` | With more than one panel, panel *k* reseeds the jitter with `panel_seed + k × panel_seed_step`. Step 0 gives every panel the same jitter. |
| `panel_iterations_step` | Panel *k* uses `iterations + k × panel_iterations_step` rewrite passes (never below 0). |

The panel size is `(page − 2 × margin − (n − 1) × gap) / n` in each direction;
an error is raised if margins and gaps leave no room. `GlobalRotation` and
`GlobalTranslateX/Y` apply within every panel (the translation is relative to
the panel centre). With a single panel nothing is reseeded, so the GUI seed
works as before; with several panels the seed comes from `panel_seed` instead.

All panels share the same layers: instance *i* (and pen, in `symbol` colour
mode) is one layer across the whole page, so the plot is organised by pen/pass
rather than by panel, and `linemerge` runs over the whole layer.

With `panel_anchor = start` and `panel_fit` on, each drawing gets the largest
scale that keeps it inside the panel around the fixed anchor. If the anchor sits
exactly on a panel edge there is no room on that side, so the drawing may
overhang there rather than collapse; keep the anchor slightly inside (e.g.
`anchor_y = 0.95` for roots near the bottom). Note that, as before, `Tall Tree`
needs `GlobalRotation = 180` to grow upwards.

Example (triptych of the Tall Tree preset on A4 landscape): `panels_x = 3`,
`landscape = on`, `margin_x = margin_y = 1.5`, `gap_x = 1`, `panel_fit = on`,
`panel_anchor = start` with `anchor_x = 0.5`, `anchor_y = 0.95`, and
`panel_iterations_step = 1` for growing trees or `panel_seed_step = 1` for
three random variants.

## Layers & output

Each instance is drawn on its own layer. This separates overlapping copies into
distinct plotter passes, giving the ink time to dry instead of piling strokes in
the same spot. Per layer:

- `linemerge --no-flip` is run scoped to that layer (`--layer N`), so each
  instance is merged only within itself and segment direction is preserved.
  This can be switched off with the `linemerge` param (on by default). It is by
  far the slowest step (roughly 60% of the run time on large figures), so turn
  it off while tuning in the preview and back on before exporting for the
  plotter. The drawn lines are the same; merging only joins them (and snaps near-coincident endpoints), which shortens the total pen travel slightly.
- the layer colour is assigned (see below).

### Single-path mode

`single_path` (off by default) draws the turtle path as continuous polylines
instead of separate segments. It only applies when the axiom and rules contain
no `[` / `]` and no `Move` symbol, because then the turtle never jumps and the
whole path is one connected line (otherwise a note is printed and the normal
drawing is used). Consequences:

- no pen lifts, and `linemerge` is skipped — the path is already a single line;
- segments the path retraces (common in e.g. Dragon or Koch curves) are simply
  drawn again each time it passes, which builds up darker lines with
  low-opacity pens — a deliberate layering effect, not a bug;
- weight changes (`#` / `!`) and, in `symbol` colour mode, colour changes split
  the line into one polyline per run (a pen change needs a lift anyway); each
  run of weight > 1 is buffered as one stroke, so corners get real joins
  instead of per-segment end caps;
- with several panels (or instances) each gets its own polyline;
- `shorten_strokes` has no effect, since there are no stroke ends inside a path.

### Pen colours

`color_1`–`color_7` pick up to seven pens (the same DrawingBot-derived palette
as the boxes sketch, with colour swatches shown in the GUI dropdowns). The first
slot set to `none` ends the palette. Selected pens are **cycled across the
instance layers** — instance *i* uses palette entry `i mod len(palette)`.

#### Colour mode

| Param | Meaning |
|-------|---------|
| `color_mode` | `instance` (default): the palette is cycled across instances as described above. `symbol`: the string chooses the pen. |
| `ColorStart` | Colour index at the start of the string (symbol mode). |

In `symbol` mode the turtle carries a **colour index**, which `'` increments and
`"` decrements. Segments are drawn with pen `index mod number-of-selected-pens`
(negative indices wrap around, so `"` at index 0 selects the last pen). Like
the stroke weight, the index is part of the turtle state on the `[ ]` stack, so
a change inside a branch is undone when the branch closes. It is not affected
by `Scale` or jitter.

Each instance is split into one layer per selected pen (layer numbers
`instance × pens + pen + 1`), so plotter passes stay per-pen and pens that are
never used produce no layer. Instances still get separate layers, so overlapping
copies keep their drying-time separation. With no pens selected, the index has no
effect and the figure falls back to one faint-black layer per instance.

Example with two pens selected: `F['F][F]` draws the stem in pen 1 and the
first branch in pen 2.

If no colours are selected (all `none`), layers fall back to black at 30%
opacity (`#0000004d`) so overlapping passes read faint.

## Preset library

[`config/`](config/) contains ready-to-load presets, in a few families:

- **Classic fractals** — `Dragon Curve`, `Sierpinski Triangle`,
  `Sierpinski Arrowhead`, `Quadratic Koch Curve`, `Quadratic Koch Island`,
  `Hexagonal Gosper`, `Islands and Lakes`.
- **Plants & growth** — `Anabaena catenula` (a filament-growth model using the
  two-rule system), `Bracket` / `Bracket 2` / `Bracket exploration` (bracketed
  branching plants), `Hex` / `Hex 2` / `HexGaps`.
- **TABoP figures** — `TABoP 1.9 a`–`d` and variants. These reproduce figures
  from *The Algorithmic Beauty of Plants* (Prusinkiewicz & Lindenmayer,
  figure 1.9), including a few angle tweaks (e.g. `83 degree`, `89 degree`,
  `91 degree`) and fold variants.

## Tips

- Increasing `iterations` grows the string exponentially; a curve that looks
  fine at 6 iterations may be enormous at 10. Tune `Scale` to keep it on the
  page.
- For branching plants, make sure your successor strings are balanced in `[`
  and `]`, and put a draw symbol before the branch so there's a stem.
- Use `*` together with `[ ]` to taper branches as they recurse, and
  `TransformScale` to control how quickly they shrink.
- Small `Angle__std_deviation` / `Length_std_deviation` values (a few percent)
  with several `instances` give natural-looking variation.
- For a tight, "sketchy" bundle, set `AlignEnd` high (e.g. larger than the
  vertex count, which means "all") — usually with `Fix_reference` — so the
  jittered copies overlap around a common form instead of fanning out from the
  start point. Narrow the `AlignStart`/`AlignEnd` range to pin only part of the
  path.
