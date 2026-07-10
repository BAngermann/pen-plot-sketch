# PenLayerTest

A vsketch test sketch that draws a grid of overlapping pen swatches, so you can
see how different pens (or different colours of the same pen) layer when
plotted on top of each other — useful for checking opacity, bleed-through, and
plotting order before committing to a pen set for a larger piece.

Run with `vsk run` from this directory.

## How it works

The page is split into an `numberOfPens` × `numberOfPens` grid. Each **row**
is assigned one pen and draws a group of horizontal line swatches across every
column; each **column** is assigned one pen and draws a group of vertical
line swatches down every row, using an increasing vpype `stroke` layer per
row/column. Because rows are drawn before columns, every grid cell ends up
with a horizontal swatch overlaid by a vertical swatch, showing the overlap
of that row's pen and that column's pen — across the whole grid this covers
every pairwise combination of the chosen pens, not just one pair. Row and
column labels are printed alongside the grid from `penNames`. `finalize()`
runs `linemerge linesimplify reloop linesort` to clean up and order the
paths for plotting.

## Parameters

- `numberOfPens` — grid size (rows = columns = number of pens under test).
- `numberOfLines` — how many parallel lines make up each swatch (thicker
  swatch = easier to judge overlap/bleed).
- `penNames` — pen labels, one per line, matched to grid rows/columns in
  order; used only for the printed labels; the actual pens/colours are
  assigned in the vsketch GUI per vpype `stroke` layer.
- `penWidth` — spacing between the parallel lines within a swatch (mm-ish
  units, scaled by `0.1`), i.e. how densely packed the swatch is.

## Config

[`config/`](config/) holds saved parameter presets (JSON) for specific pen
sets — e.g. `Pigma Brush.json` for the 9-colour Sakura Pigma Brush set. Load
one from the vsketch GUI to reproduce that test grid.

## Output

`output/` is a scratch folder for local renders (SVG/HPGL) and is git-ignored.
