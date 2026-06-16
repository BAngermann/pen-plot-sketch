"""Fill patterns: a registry mapping a name to a (render, sample) pair.

* ``render(poly, params, layer) -> Geometry`` is pure: same params, same output.
  This makes results cacheable and reproducible, and lets the caller assign
  layers/colours and combine several fills.
* ``sample(rng, overrides) -> params`` draws a parameter dict, correlating the
  variables that need to move together (e.g. glyph size tracks grid spacing).
  Any key in ``overrides`` is passed through verbatim, so you can pin some
  parameters and randomise the rest.

Add a pattern by writing the two functions and registering them in PATTERNS.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Tuple

from shapely.geometry import Polygon

from .geometry import (Geometry, clip_polyline, fill_region, place_and_clip,
                       prep_poly)
from .glyphs import GLYPH_TYPES, glyph
from .grids import GRIDS, GRID_TYPES
from .rng import RandomLike


# ── solid ──────────────────────────────────────────────────────────────────────
# vsketch's native fill, wrapped as a pattern so it shares the interface.  It has
# no parameters; layer any other fill on top of it.

def render_solid(poly: Polygon, params: dict, layer: int) -> Geometry:
    return fill_region(poly, layer)


def sample_solid(rng: RandomLike, overrides: dict) -> dict:
    return {}


# ── hatch ──────────────────────────────────────────────────────────────────────
# Parallel lines clipped to the polygon — the in-model equivalent of vsketch's
# native fill, but returned as geometry so it composes with everything else.

def _hatch_dir(poly: Polygon, angle: float, spacing: float, origin, layer: int) -> Geometry:
    ca, sa = math.cos(angle), math.sin(angle)
    ox, oy = origin
    minx, miny, maxx, maxy = poly.bounds
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    # Rotate corners into the line frame (u along the lines, v across them).
    us = [(x - ox) * ca + (y - oy) * sa for x, y in corners]
    vs = [-(x - ox) * sa + (y - oy) * ca for x, y in corners]
    umin, umax = min(us), max(us)
    k0, k1 = math.floor(min(vs) / spacing), math.ceil(max(vs) / spacing)
    geom: Geometry = []
    for k in range(k0, k1 + 1):
        v = k * spacing
        p1 = (ox + umin * ca - v * sa, oy + umin * sa + v * ca)
        p2 = (ox + umax * ca - v * sa, oy + umax * sa + v * ca)
        geom += clip_polyline([p1, p2], poly, layer)
    return geom


def render_hatch(poly: Polygon, params: dict, layer: int) -> Geometry:
    spacing = params["spacing"]
    angle = math.radians(params.get("angle", 0.0))
    origin = tuple(params.get("origin", (0.0, 0.0)))
    geom = _hatch_dir(poly, angle, spacing, origin, layer)
    if params.get("cross", False):
        geom += _hatch_dir(poly, angle + math.pi / 2, spacing, origin, layer)
    return geom


def sample_hatch(rng: RandomLike, overrides: dict) -> dict:
    spacing = overrides.get("spacing", rng.uniform(0.1, 0.4))
    return {
        "spacing": spacing,
        "angle": overrides.get("angle", rng.uniform(0, 180)),
        "cross": overrides.get("cross", rng.random() < 0.3),
        "origin": overrides.get("origin", (0.0, 0.0)),
    }


# ── glyph_grid ─────────────────────────────────────────────────────────────────
# A grid (square/hex/halton) of glyphs.  Positioning and glyph choice are
# orthogonal; glyph size is correlated to grid spacing in the sampler.

def render_glyph_grid(poly: Polygon, params: dict, layer: int) -> Geometry:
    size = params["size"]
    grid_name = params.get("grid", "square")
    grid = GRIDS[grid_name]
    # Pad outward so glyphs near the edge appear (then get clipped to the edge).
    region = poly.buffer(size)
    gkwargs = dict(angle=params.get("angle", 0.0),
                   origin=tuple(params.get("origin", (0.0, 0.0))),
                   jitter=params.get("jitter", 0.0),
                   seed=params.get("seed", 0))
    if grid_name == "halton":
        gkwargs["bases"] = tuple(params.get("halton_bases", (2, 3)))
    pts = grid(region, params["spacing"], **gkwargs)
    prepared = prep_poly(poly)
    gkw = {
        "chevron_half": params.get("chevron_half", 60.0),
        "wave_periods": params.get("wave_periods", 1.0),
        "wave_amplitude": params.get("wave_amplitude", None),
    }
    geom: Geometry = []
    for px, py in pts:
        for local, closed in glyph(params.get("glyph", "dash"), size,
                                   params.get("glyph_angle", 0.0), **gkw):
            geom += place_and_clip(local, px, py, poly, prepared, layer, closed)
    return geom


_HALTON_PRIMES = [2, 3, 5, 7, 11, 13]


def _sample_bases(rng: RandomLike) -> tuple:
    bx = rng.choice(_HALTON_PRIMES)
    by = bx
    while by == bx:
        by = rng.choice(_HALTON_PRIMES)
    return (bx, by)


def sample_glyph_grid(rng: RandomLike, overrides: dict) -> dict:
    spacing = overrides.get("spacing", rng.uniform(0.15, 0.45))
    size_ratio = overrides.get("size_ratio", rng.uniform(0.25, 0.5))
    size = overrides.get("size", spacing * size_ratio)
    return {
        "grid": overrides.get("grid", rng.choice(GRID_TYPES)),
        "halton_bases": overrides.get("halton_bases", _sample_bases(rng)),
        "spacing": spacing,
        "size": size,
        "glyph": overrides.get("glyph", rng.choice(GLYPH_TYPES)),
        "angle": overrides.get("angle", rng.uniform(0, 90)),
        "glyph_angle": overrides.get("glyph_angle", rng.uniform(0, 360)),
        "jitter": overrides.get("jitter", 0.0),
        "origin": overrides.get("origin", (0.0, 0.0)),
        "seed": overrides.get("seed", rng.randint(0, 10 ** 9)),
        "chevron_half": overrides.get("chevron_half", rng.uniform(40, 80)),
        "wave_periods": overrides.get("wave_periods", 1.0),
        "wave_amplitude": overrides.get("wave_amplitude", size * 0.5),
    }


# ── registry ─────────────────────────────────────────────────────────────────

RenderFn = Callable[[Polygon, dict, int], Geometry]
SampleFn = Callable[[RandomLike, dict], dict]

PATTERNS: Dict[str, Tuple[RenderFn, SampleFn]] = {
    "solid": (render_solid, sample_solid),
    "hatch": (render_hatch, sample_hatch),
    "glyph_grid": (render_glyph_grid, sample_glyph_grid),
}

PATTERN_NAMES: List[str] = list(PATTERNS)
