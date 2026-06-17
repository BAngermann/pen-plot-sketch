"""penfill — composable polygon fills for pen-plotter sketches.

Quick start (inside a vsketch ``draw``)::

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from penfill import rect_polygon, FillSpec, fill_polygon, sample_fill, draw_geometry

    poly = rect_polygon(x, y, w, h)

    # deterministic:
    spec = FillSpec("glyph_grid", layer=2,
                    params=dict(grid="hex", spacing=1.0, size=0.3, glyph="chevron"))
    draw_geometry(vsk, fill_polygon(poly, spec))

    # random (correlated params), pin spacing, vary the rest:
    import random
    spec = sample_fill("glyph_grid", random.Random(seed), layer=2, spacing=1.0)
    draw_geometry(vsk, fill_polygon(poly, spec))

Combine patterns by concatenating geometry on different layers::

    geom  = fill_polygon(poly, FillSpec("glyph_grid", 2, dict(grid="hex", glyph="dash", origin=(0, 0))))
    geom += fill_polygon(poly, FillSpec("glyph_grid", 3, dict(grid="hex", glyph="plus", origin=(0.5, 0))))
    draw_geometry(vsk, geom)

Fills return geometry rather than drawing, so they cache, compose, and stay
backend-agnostic.  Polygons are Shapely, so concave shapes and holes already
work via ``to_polygon(shell, holes=[...])``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import (Geometry, Primitive, Pt, clip_polyline, prep_poly,
                       rect_polygon, to_polygon)
from .glyphs import GLYPH_TYPES, glyph
from .grids import GRID_TYPES, GRIDS
from .patterns import PATTERN_NAMES, PATTERNS
from .pens import Pen, load_pen_config, load_pens
from .rng import RandomLike, VskRandom
from .swatches import install as install_swatches

__all__ = [
    "FillSpec", "fill_polygon", "sample_fill", "draw_geometry",
    "to_polygon", "rect_polygon", "VskRandom", "RandomLike",
    "Pen", "load_pens", "load_pen_config", "install_swatches",
    "PATTERN_NAMES", "GRID_TYPES", "GLYPH_TYPES",
    "Geometry", "Primitive", "Pt",
]


@dataclass
class FillSpec:
    """A fully-resolved fill: which pattern, which layer, and its parameters."""
    pattern: str
    layer: int = 1
    params: dict = field(default_factory=dict)


def fill_polygon(poly, spec: FillSpec) -> Geometry:
    """Render ``spec`` over ``poly`` and return layer-tagged geometry."""
    render, _ = PATTERNS[spec.pattern]
    return render(poly, spec.params, spec.layer)


def sample_fill(pattern: str, rng: RandomLike, layer: int = 1, **overrides) -> FillSpec:
    """Sample a FillSpec for ``pattern``; ``overrides`` pin individual params."""
    _, sample = PATTERNS[pattern]
    return FillSpec(pattern, layer, sample(rng, overrides))


def draw_geometry(vsk, geom: Geometry) -> None:
    """Replay geometry onto a vsketch instance.

    Sorted by layer so primitives on lower layers are drawn first (others stack
    on top — e.g. a glyph fill over a solid fill).  ``"S"`` strokes polylines;
    ``"F"`` draws a solidly filled polygon via vsketch's native fill.
    """
    cur = None
    for prim in sorted(geom, key=lambda g: g[1]):
        kind, layer = prim[0], prim[1]
        if kind == "F":
            _, _, shell, holes = prim
            vsk.fill(layer)
            vsk.stroke(layer)
            cur = layer
            vsk.polygon([p[0] for p in shell], [p[1] for p in shell],
                        holes=holes, close=True)
            vsk.noFill()
            continue
        _, _, pts, closed = prim
        if layer != cur:
            vsk.stroke(layer)
            cur = layer
        if len(pts) == 2 and not closed:
            (x1, y1), (x2, y2) = pts
            vsk.line(x1, y1, x2, y2)
        else:
            vsk.polygon([p[0] for p in pts], [p[1] for p in pts], close=closed)
