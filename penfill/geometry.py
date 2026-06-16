"""Shapely-backed geometry helpers for polygon fills.

The whole package speaks one intermediate representation: a *Geometry* is a list
of tagged *primitives*:

* stroke    ``("S", layer, points, closed)`` — a polyline; ``closed`` marks a
  ring, and a 2-point open stroke is a line.
* filled    ``("F", layer, shell, holes)`` — a solidly filled polygon, ``shell``
  and each hole being a list of ``(x, y)``.  Rendered with vsketch's native
  fill; layer others on top of it.

Using Shapely for the polygon itself means concave shapes and holes work for
free: a fill region is just a ``shapely.geometry.Polygon`` (with interior rings
= holes), and clipping a glyph is ``line.intersection(poly)``.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple, Union

from shapely.geometry import LineString, Point, Polygon
from shapely.prepared import prep

Pt = Tuple[float, float]
Stroke = Tuple[str, int, List[Pt], bool]            # ("S", layer, points, closed)
Filled = Tuple[str, int, List[Pt], List[List[Pt]]]  # ("F", layer, shell, holes)
Primitive = Union[Stroke, Filled]
Geometry = List[Primitive]


def to_polygon(shell: Sequence[Pt], holes: Sequence[Sequence[Pt]] | None = None) -> Polygon:
    """Build a (possibly holed) polygon from a vertex shell and optional holes."""
    return Polygon(shell, holes or [])


def rect_polygon(x: float, y: float, w: float, h: float) -> Polygon:
    """Axis-aligned rectangle as a polygon — the common convex testbed shape."""
    return Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])


def prep_poly(poly: Polygon):
    """Prepared geometry for fast repeated ``contains`` during grid filtering."""
    return prep(poly)


def _to_polylines(geom, layer: int) -> Geometry:
    """Flatten a Shapely intersection result into layer-tagged polylines."""
    out: Geometry = []
    if geom.is_empty:
        return out
    gt = geom.geom_type
    if gt == "LineString":
        coords = list(geom.coords)
        if len(coords) >= 2:
            out.append(("S", layer, coords, False))
    elif gt in ("MultiLineString", "GeometryCollection"):
        for g in geom.geoms:
            out.extend(_to_polylines(g, layer))
    # Points / MultiPoints are degenerate touches — ignore.
    return out


def clip_polyline(points: Sequence[Pt], poly: Polygon, layer: int,
                  closed: bool = False) -> Geometry:
    """Clip an open or closed polyline to ``poly``.

    Clipping can split one polyline into several pieces (concave shapes, holes),
    so this returns zero or more polylines.
    """
    pts = list(points)
    if len(pts) < 2:
        return []
    if closed:
        pts = pts + [pts[0]]
    return _to_polylines(LineString(pts).intersection(poly), layer)


def place_and_clip(local: Sequence[Pt], px: float, py: float, poly: Polygon,
                   prepared, layer: int, closed: bool) -> Geometry:
    """Translate a glyph's local polyline to ``(px, py)`` and clip it to ``poly``.

    Fast path: if the translated polyline is wholly inside (checked against the
    prepared polygon) it is emitted untouched, skipping the intersection call.
    """
    world = [(px + x, py + y) for x, y in local]
    ring = world + [world[0]] if closed else world
    if prepared.contains(LineString(ring)):
        return [("S", layer, world, closed)]
    return clip_polyline(world, poly, layer, closed)


def fill_region(poly: Polygon, layer: int) -> Geometry:
    """Emit a solid-fill primitive for ``poly`` (shell + holes), for native fill."""
    shell = list(poly.exterior.coords)
    holes = [list(ring.coords) for ring in poly.interiors]
    return [("F", layer, shell, holes)]
