"""Point generators for fills.

Positioning is deliberately independent of the glyph drawn at each point, so any
grid can be paired with any glyph.  Every generator shares the signature

    grid(poly, spacing, *, angle, origin, jitter, seed) -> list[(x, y)]

and returns points lying inside ``poly`` (the caller passes a region already
padded outward so glyphs may overhang the true boundary).  ``square`` and
``hex`` are true lattices; ``halton`` is a low-discrepancy quasi-random fill at
matched density — all three swap in freely.
"""
from __future__ import annotations

import math
import random
from typing import List, Tuple

from shapely.geometry import Point

from .geometry import Pt, prep_poly

GRID_TYPES = ["square", "hex", "halton"]


def _lattice(poly, e1, e2, angle, origin, jitter, seed) -> List[Pt]:
    """Generic 2D lattice spanned by basis vectors e1, e2 (rotated by angle)."""
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)

    def rot(v):
        return (v[0] * ca - v[1] * sa, v[0] * sa + v[1] * ca)

    ax, ay = rot(e1)
    bx, by = rot(e2)
    det = ax * by - ay * bx
    if abs(det) < 1e-12:
        return []

    ox, oy = origin
    minx, miny, maxx, maxy = poly.bounds
    corners = [(minx - ox, miny - oy), (maxx - ox, miny - oy),
               (maxx - ox, maxy - oy), (minx - ox, maxy - oy)]
    inv = 1.0 / det
    is_ = [(px * by - py * bx) * inv for px, py in corners]
    js_ = [(py * ax - px * ay) * inv for px, py in corners]
    imin, imax = int(math.floor(min(is_))) - 1, int(math.ceil(max(is_))) + 1
    jmin, jmax = int(math.floor(min(js_))) - 1, int(math.ceil(max(js_))) + 1
    if (imax - imin + 1) * (jmax - jmin + 1) > 500_000:
        return []  # spacing too small for this region — refuse rather than hang

    prepared = prep_poly(poly)
    rng = random.Random((seed, "jitter")) if jitter else None
    pts: List[Pt] = []
    for i in range(imin, imax + 1):
        for j in range(jmin, jmax + 1):
            x = ox + i * ax + j * bx
            y = oy + i * ay + j * by
            if rng is not None:
                x += rng.uniform(-jitter, jitter)
                y += rng.uniform(-jitter, jitter)
            if prepared.contains(Point(x, y)):
                pts.append((x, y))
    return pts


def square_grid(poly, spacing, *, angle=0.0, origin=(0.0, 0.0), jitter=0.0, seed=0):
    return _lattice(poly, (spacing, 0.0), (0.0, spacing), angle, origin, jitter, seed)


def hex_grid(poly, spacing, *, angle=0.0, origin=(0.0, 0.0), jitter=0.0, seed=0):
    return _lattice(poly, (spacing, 0.0),
                    (spacing * 0.5, spacing * math.sqrt(3) / 2.0),
                    angle, origin, jitter, seed)


def _halton(i: int, base: int) -> float:
    f, r = 1.0, 0.0
    while i > 0:
        f /= base
        r += f * (i % base)
        i //= base
    return r


def halton_points(poly, spacing, *, angle=0.0, origin=(0.0, 0.0), jitter=0.0,
                  seed=0, bases=(2, 3)):
    """Halton quasi-random points at density matching a ``spacing`` grid.

    ``bases`` is the (x, y) pair of Halton bases; they should be distinct and
    coprime (small primes such as 2, 3, 5, 7 work well) — equal or non-coprime
    bases make the sequence visibly correlated.  ``angle``/``jitter`` are
    accepted for a uniform signature but unused (the sequence is already
    isotropic and aperiodic).  ``origin`` shifts the start index so two halton
    fills can be deliberately decorrelated.
    """
    bx, by = int(bases[0]), int(bases[1])
    if bx < 2 or by < 2:
        return []
    minx, miny, maxx, maxy = poly.bounds
    w, h = maxx - minx, maxy - miny
    if w <= 0 or h <= 0 or spacing <= 0:
        return []
    target = int(round(w * h / (spacing * spacing)))  # bbox-density target
    if target <= 0:
        return []
    if target > 500_000:
        return []
    prepared = prep_poly(poly)
    start = 1 + (abs(hash((seed, origin, bx, by))) % 100_000)
    pts: List[Pt] = []
    for i in range(start, start + target):
        x = minx + _halton(i, bx) * w
        y = miny + _halton(i, by) * h
        if prepared.contains(Point(x, y)):
            pts.append((x, y))
    return pts


GRIDS = {
    "square": square_grid,
    "hex": hex_grid,
    "halton": halton_points,
}
