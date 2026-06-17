# penfill

Composable polygon fills for pen-plotter sketches (vsketch / vpype).

A fill takes a polygon and returns **geometry** — a flat list of tagged
primitives — rather than drawing directly. That keeps fills cacheable,
composable across layers/colours, and independent of any particular drawing
backend. Polygons are [Shapely](https://shapely.readthedocs.io/) geometry, so
concave shapes and holes work today; clipping a glyph is just
`line.intersection(poly)`.

## Install / import

The package lives at the repo root. Sketches run inside vsketch's pipx venv, so
each sketch makes it importable with a two-line bootstrap (no install needed):

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # repo root
from penfill import FillSpec, fill_polygon, sample_fill, draw_geometry, rect_polygon
```

(`parents[1]` for a sketch one level below the root, e.g. `boxes/`; use
`parents[2]` for `modulo_multiplication/<name>/`.)

Requires `shapely` — already present in the vsketch environment because vpype
depends on it.

## Core concepts

- **Geometry / primitives.** The intermediate representation is a list of tagged
  tuples:
  - `("S", layer, points, closed)` — a stroked polyline (`closed` marks a ring;
    a 2-point open stroke is a line).
  - `("F", layer, shell, holes)` — a solidly filled polygon (native vsketch
    fill), `shell` and each hole being a list of `(x, y)`.
- **FillSpec.** `FillSpec(pattern, layer, params)` fully describes one fill:
  which pattern, which layer, and its parameters.
- **`fill_polygon(poly, spec) -> Geometry`.** Renders a spec over a polygon.
  Pure: same params → same geometry (cache-friendly).
- **`sample_fill(pattern, rng, layer=1, **overrides) -> FillSpec`.** Draws a
  spec, correlating the variables that must move together (e.g. glyph size
  tracks grid spacing). Any key in `overrides` is passed through verbatim, so you
  can pin some parameters and randomise the rest. `rng` is anything `RandomLike`
  — `random.Random`, or `VskRandom(vsk)` to draw from vsketch's seeded stream.
- **`draw_geometry(vsk, geom)`.** Replays geometry onto a vsketch instance,
  sorted by layer so lower layers draw first (others stack on top).

## Patterns

| name         | what it draws                                   | key params |
|--------------|-------------------------------------------------|------------|
| `solid`      | vsketch native fill of the polygon (with holes) | *(none)* |
| `hatch`      | parallel lines (optional crosshatch)            | `spacing`, `angle`, `cross`, `origin` |
| `glyph_grid` | a grid of glyphs                                | `grid`, `spacing`, `size`, `glyph`, `angle`, `glyph_angle`, `jitter`, `origin`, `seed`, `halton_bases`, glyph extras |

**Grids** (positioning, independent of the glyph): `square`, `hex`, `halton`.
Halton accepts a `bases=(bx, by)` pair (distinct, coprime small primes work
best) for control over the quasi-random distribution.

**Glyphs**: `dash`, `plus`, `circle`, `chevron`, `sine`, `sawtooth`,
`triangle_wave`. Chevron and the waves take extra shape params
(`chevron_half`, `wave_periods`, `wave_amplitude`).

## Examples

Deterministic:

```python
poly = rect_polygon(x, y, w, h)
spec = FillSpec("glyph_grid", layer=2,
                params=dict(grid="hex", spacing=1.0, size=0.3, glyph="chevron"))
draw_geometry(vsk, fill_polygon(poly, spec))
```

Random, with spacing pinned and the rest sampled:

```python
spec = sample_fill("glyph_grid", VskRandom(vsk), layer=2, spacing=1.0)
draw_geometry(vsk, fill_polygon(poly, spec))
```

Combine patterns on separate layers (e.g. a solid base with glyphs on top, or
two shifted hex grids with different glyphs for two colours):

```python
geom  = fill_polygon(poly, FillSpec("solid", 2))
geom += fill_polygon(poly, FillSpec("glyph_grid", 3, dict(grid="hex", glyph="dash", origin=(0, 0))))
geom += fill_polygon(poly, FillSpec("glyph_grid", 4, dict(grid="hex", glyph="plus", origin=(0.5, 0))))
draw_geometry(vsk, geom)
```

Concave / holed regions work via `to_polygon(shell, holes=[...])`.

## Module layout

- `geometry.py` — the primitive IR, Shapely clipping (`clip_polyline`,
  `place_and_clip`), `to_polygon` / `rect_polygon`, `fill_region`.
- `grids.py` — point generators: `square_grid`, `hex_grid`, `halton_points`
  (shared signature; `GRIDS` registry, `GRID_TYPES`).
- `glyphs.py` — glyph generators returning local oriented polylines
  (`GLYPH_TYPES`).
- `patterns.py` — the `(render, sample)` registry (`PATTERNS`, `PATTERN_NAMES`).
- `pens.py` — load vpype pen-config TOML (`load_pens`, `load_pen_config`, `Pen`).
- `rng.py` — `RandomLike` protocol and the `VskRandom` adapter.
- `__init__.py` — public API (`FillSpec`, `fill_polygon`, `sample_fill`,
  `draw_geometry`, …).

## Extending

Add a pattern by writing `render(poly, params, layer) -> Geometry` and
`sample(rng, overrides) -> params`, then registering the pair in
`PATTERNS` (`patterns.py`). It immediately appears in `PATTERN_NAMES` and any UI
driven by it.

## Pen configurations

`load_pens(directory)` reads every vpype pen-config `*.toml` in a directory and
returns an ordered `{pen name: "#rrggbb"}` map — handy for populating a UI of
colour choices and resolving a chosen name to a hex value. `load_pen_config(path)`
returns the full `{config: [Pen, …]}` (name, color, width). These TOML files are
produced by [`tools/drawingbot_to_vpype.py`](../tools/) from DrawingBot presets
and live in [`pens/`](../pens/); they are also usable directly by vpype's `pens`
command.

## Roadmap

More layer colours and reading pen settings from config; gradients via error
diffusion combined with glyphs; further tuning of the halton/grid distributions.
Expect on-screen results to need re-tuning once plotted on paper.
