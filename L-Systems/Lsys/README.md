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
targets a portrait **A4** page in **cm**.

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

Note that `Draw` is a *set* of characters (e.g. `"FG"` means both `F` and `G`
draw), while `Move` is a single character.

| Param | Meaning |
|-------|---------|
| `Draw` | Characters that draw a line segment. |
| `Move` | Character that advances without drawing. |
| `TurnAngle` | Degrees turned by `+` / `-`. |
| `TransformScale` | Multiplier applied by `*` (used for self-similar branch tapering). |
| `Scale` | Overall scale of the whole figure on the page. |

### Variation & repetition

| Param | Meaning |
|-------|---------|
| `Angle__std_deviation` | Standard deviation of Gaussian noise added to every turn (degrees). `0` = exact. |
| `Length_std_deviation` | Standard deviation of Gaussian noise added to every segment/move length. `0` = exact. |
| `instances` | Number of overlaid copies of the figure (combine with the std-deviation params to draw a "bundle" of slightly different growths). |
| `Align_instances` | When on (and `instances > 1`), each copy is fitted onto the first by the rigid transform (rotation + translation) that minimizes the mean squared distance between corresponding endpoints — a Kabsch/Procrustes fit — rather than pinning them all to a shared start point. This clusters the bundle around a common shape. |
| `Fix_reference` | When on, instance 0 is drawn at its exact nominal (un-jittered) values, so it acts as a clean reference for `Align_instances`. |

### Placement

The drawing's bounding box is automatically centred on the A4 page (vsketch's
own auto-centring is disabled). It is then rotated about its centre and
translated by the global offset.

| Param | Meaning |
|-------|---------|
| `GlobalRotation` | Rotation of the whole drawing about its centre, in degrees. |
| `GlobalTranslateX` / `GlobalTranslateY` | Offset from the page centre, in cm. |

## Layers & output

Each instance is drawn on its own layer. This separates overlapping copies into
distinct plotter passes, giving the ink time to dry instead of piling strokes in
the same spot. Per layer:

- `linemerge --no-flip` is run scoped to that layer (`--layer N`), so each
  instance is merged only within itself and segment direction is preserved.
- the layer colour is set to black at 30% opacity (`#0000004d`), so overlapping
  passes read faint.

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
- For a tight, "sketchy" bundle, enable `Align_instances` (and usually
  `Fix_reference`) so the jittered copies overlap around a common form instead
  of fanning out from the start point.
