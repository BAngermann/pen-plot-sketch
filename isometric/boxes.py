"""Isometric rendering of integer-grid boxes with exact hidden-surface removal.

A pen plotter cannot paint over ink to hide geometry, so occluded faces must be
*removed* before drawing.  Because true 30° isometric maps the integer voxel
lattice onto a single shared triangular lattice (see :mod:`.projection`), every
visible face (top = +z, right = +x, left = +y) decomposes into unit equilateral
triangles that all align to that grid.  Hidden-surface removal is then an
analytic per-triangle z-buffer keyed by an *integer* view-depth — no Shapely
boolean ops.  Shapely is used only to *merge* the surviving same-face triangles
back into fill polygons (a coplanar union, never a cross-shape difference).

Output is the penfill Geometry IR, so it flows straight through
``penfill.draw_geometry``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Hashable, Iterable, List, Optional, Tuple

from shapely.geometry import Polygon
from shapely.ops import unary_union

from penfill import FillSpec, Geometry, fill_polygon

from .projection import C, S, lattice_to_screen

FaceKind = str  # "top" | "left" | "right"
FillResolver = Callable[["Box", FaceKind], Optional[FillSpec]]

# A triangular-lattice cell: (a, b, kind) where kind is "L" (lower) or "U" (upper).
#   L(a,b) = {(a,b), (a+1,b), (a+1,b+1)}
#   U(a,b) = {(a,b), (a+1,b+1), (a,b+1)}
Cell = Tuple[int, int, str]


@dataclass
class Box:
    """An axis-aligned box on the integer grid: min corner + integer sizes.

    ``key`` is handed to the fill resolver (so fills can depend on position /
    identity); ``fills`` optionally pins a FillSpec per face kind, overriding the
    resolver.
    """
    x: int
    y: int
    z: int
    dx: int
    dy: int
    dz: int
    key: Hashable = None
    fills: Optional[Dict[FaceKind, FillSpec]] = None


def face_type_resolver(specs: Dict[FaceKind, Optional[FillSpec]]) -> FillResolver:
    """Resolver that maps each face kind to a fixed FillSpec (missing -> None)."""
    def resolver(box: Box, kind: FaceKind) -> Optional[FillSpec]:
        return specs.get(kind)
    return resolver


# ── face / triangle decomposition ────────────────────────────────────────────

def _unit_faces(box: Box) -> Iterable[Tuple[FaceKind, List[Tuple[int, int, int]]]]:
    """Yield ``(kind, quad)`` for every unit sub-face of the 3 visible faces.

    ``quad`` is the 4 integer corners (X, Y, Z) in ring order.
    """
    x, y, z, dx, dy, dz = box.x, box.y, box.z, box.dx, box.dy, box.dz
    x2, y2, z2 = x + dx, y + dy, z + dz
    for i in range(dx):                                    # top (+z)
        for j in range(dy):
            yield "top", [(x + i, y + j, z2), (x + i + 1, y + j, z2),
                          (x + i + 1, y + j + 1, z2), (x + i, y + j + 1, z2)]
    for j in range(dy):                                    # right (+x)
        for k in range(dz):
            yield "right", [(x2, y + j, z + k), (x2, y + j + 1, z + k),
                            (x2, y + j + 1, z + k + 1), (x2, y + j, z + k + 1)]
    for i in range(dx):                                    # left (+y)
        for k in range(dz):
            yield "left", [(x + i, y2, z + k), (x + i + 1, y2, z + k),
                           (x + i + 1, y2, z + k + 1), (x + i, y2, z + k + 1)]


def _screen_len2(da: int, db: int) -> float:
    """Squared screen length of lattice vector (da, db)."""
    return (C * (da - db)) ** 2 + (S * (da + db)) ** 2


def _triangles(quad: List[Tuple[int, int, int]]) -> List[Tuple[Cell, int]]:
    """Split a unit face quad into its two lattice triangles.

    Returns ``[(cell, depth), (cell, depth)]`` where ``depth`` is the integer
    view-depth (sum of ``x+y+z`` over the triangle's 3 corners; larger = nearer).

    The quad is a ring (corners 0-1-2-3), so its two diagonals are (0,2) and
    (1,3).  Splitting along the *shorter screen diagonal* yields the two unit
    equilateral triangles that coincide with the global lattice triangulation —
    which diagonal that is depends on the face's orientation, so it must be
    measured, not assumed.
    """
    lat = [(X - Z, Y - Z) for (X, Y, Z) in quad]
    d02 = _screen_len2(lat[0][0] - lat[2][0], lat[0][1] - lat[2][1])
    d13 = _screen_len2(lat[1][0] - lat[3][0], lat[1][1] - lat[3][1])
    (i, j), others = ((0, 2), (1, 3)) if d02 <= d13 else ((1, 3), (0, 2))
    out: List[Tuple[Cell, int]] = []
    for k in others:
        idx = (i, j, k)
        verts = [lat[t] for t in idx]
        a0 = min(v[0] for v in verts)
        b0 = min(v[1] for v in verts)
        # L cells have a single vertex on the min-a column; U cells have two.
        kind = "L" if sum(1 for v in verts if v[0] == a0) == 1 else "U"
        depth = sum(quad[t][0] + quad[t][1] + quad[t][2] for t in idx)
        out.append(((a0, b0, kind), depth))
    return out


def _cell_polygon(cell: Cell, scale: float) -> Polygon:
    a, b, kind = cell
    verts = ([(a, b), (a + 1, b), (a + 1, b + 1)] if kind == "L"
             else [(a, b), (a + 1, b + 1), (a, b + 1)])
    return Polygon([lattice_to_screen(va, vb, scale) for va, vb in verts])


# ── assembly ─────────────────────────────────────────────────────────────────

FaceTask = Tuple[Hashable, Box, FaceKind, List[Tuple[int, int, int]]]


def _plane_key(box: Box, kind: FaceKind):
    """Identity of the plane a face lies in — coplanar same-kind faces share it.

    Faces in the same plane (same kind, same plane coordinate) are the same flat
    surface, so merging them dissolves the internal boundaries between adjacent
    unit faces while keeping the edges at steps (different heights/planes).
    """
    if kind == "top":
        return ("top", box.z + box.dz)
    if kind == "right":
        return ("right", box.x + box.dx)
    return ("left", box.y + box.dy)


def _resolve(box: Box, kind: FaceKind, fill_for: Optional[FillResolver]) -> Optional[FillSpec]:
    if box.fills and kind in box.fills:
        return box.fills[kind]
    if fill_for is not None:
        return fill_for(box, kind)
    return None


def _polygons(geom) -> List[Polygon]:
    if geom.is_empty:
        return []
    gt = geom.geom_type
    if gt == "Polygon":
        return [geom]
    if gt in ("MultiPolygon", "GeometryCollection"):
        return [g for g in geom.geoms if g.geom_type == "Polygon" and not g.is_empty]
    return []


def _outline(poly: Polygon, layer: int) -> Geometry:
    out: Geometry = [("S", layer, list(poly.exterior.coords), True)]
    for ring in poly.interiors:
        out.append(("S", layer, list(ring.coords), True))
    return out


def _zbuffer(faces: Iterable[FaceTask]) -> Tuple[Dict[Cell, Tuple[int, Hashable]],
                                                 Dict[Hashable, Tuple[Box, FaceKind]]]:
    """Resolve hidden-surface removal: nearest face per lattice cell.

    Returns ``(zbuf, group_meta)`` where ``zbuf`` maps each covered lattice cell
    to ``(depth, gid)`` of the winning (nearest) face and ``group_meta`` maps a
    ``gid`` to its ``(box, kind)``.  Pure integer comparison, no Shapely.
    """
    zbuf: Dict[Cell, Tuple[int, Hashable]] = {}     # cell -> (depth, gid)
    group_meta: Dict[Hashable, Tuple[Box, FaceKind]] = {}
    for gid, box, kind, quad in faces:
        group_meta[gid] = (box, kind)
        for cell, depth in _triangles(quad):
            cur = zbuf.get(cell)
            if cur is None or depth > cur[0]:
                zbuf[cell] = (depth, gid)
    return zbuf, group_meta


def _assemble(faces: Iterable[FaceTask], fill_for: Optional[FillResolver],
              scale: float, outline_layer: Optional[int],
              merge_coplanar: bool) -> Geometry:
    """Z-buffer the faces, reconstruct visible regions, fill and outline them.

    When ``merge_coplanar`` is true (the default), visible cells are regrouped by
    plane (kind + plane coordinate), so adjacent coplanar same-direction faces
    merge into one region and the boundaries between them are not drawn.
    """
    zbuf, group_meta = _zbuffer(faces)

    cells_by_group: Dict[Hashable, List[Cell]] = defaultdict(list)
    group_box: Dict[Hashable, Tuple[Box, FaceKind]] = {}
    for cell, (_depth, gid) in zbuf.items():
        box, kind = group_meta[gid]
        key = _plane_key(box, kind) if merge_coplanar else gid
        cells_by_group[key].append(cell)
        group_box.setdefault(key, (box, kind))

    geom: Geometry = []
    for key, cells in cells_by_group.items():
        box, kind = group_box[key]
        region = unary_union([_cell_polygon(c, scale) for c in cells])
        spec = _resolve(box, kind, fill_for)
        for poly in _polygons(region):
            if spec is not None:
                geom += fill_polygon(poly, spec)
            if outline_layer is not None:
                geom += _outline(poly, outline_layer)
    return geom


def render_boxes(boxes: List[Box], fill_for: Optional[FillResolver] = None, *,
                 scale: float = 1.0, outline_layer: Optional[int] = None,
                 merge_coplanar: bool = True) -> Geometry:
    """Render a collection of integer-grid boxes in isometric with HSR.

    ``fill_for(box, kind) -> FillSpec | None`` resolves the fill per face;
    ``box.fills[kind]`` overrides it.  ``outline_layer`` (if given) draws the
    visible silhouette / hidden-line edges on that layer.  With
    ``merge_coplanar`` (default), adjacent coplanar same-direction faces merge so
    the boundary between them is not drawn.
    """
    def faces() -> Iterable[FaceTask]:
        for bi, box in enumerate(boxes):
            for kind, quad in _unit_faces(box):
                yield (bi, kind), box, kind, quad
    return _assemble(faces(), fill_for, scale, outline_layer, merge_coplanar)


def render_voxels(occupied: Iterable[Tuple[int, int, int]],
                  fill_for: Optional[FillResolver] = None, *,
                  scale: float = 1.0, outline_layer: Optional[int] = None,
                  merge_coplanar: bool = True) -> Geometry:
    """Render a set of unit voxels, culling faces shared with a neighbour.

    The resolver receives a synthesised unit :class:`Box` per voxel whose
    ``key`` is the ``(x, y, z)`` tuple, so fills can vary by position/height.
    With ``merge_coplanar`` (default), adjacent coplanar same-direction faces
    merge so the boundary between them is not drawn (and the resolver is called
    with one representative voxel for the merged region).
    """
    occ = occupied if isinstance(occupied, (set, frozenset)) else set(occupied)

    def faces() -> Iterable[FaceTask]:
        for (x, y, z) in occ:
            box = Box(x, y, z, 1, 1, 1, key=(x, y, z))
            if (x, y, z + 1) not in occ:                  # top exposed
                yield ((x, y, z), "top"), box, "top", [
                    (x, y, z + 1), (x + 1, y, z + 1),
                    (x + 1, y + 1, z + 1), (x, y + 1, z + 1)]
            if (x + 1, y, z) not in occ:                  # right exposed
                yield ((x, y, z), "right"), box, "right", [
                    (x + 1, y, z), (x + 1, y + 1, z),
                    (x + 1, y + 1, z + 1), (x + 1, y, z + 1)]
            if (x, y + 1, z) not in occ:                  # left exposed
                yield ((x, y, z), "left"), box, "left", [
                    (x, y + 1, z), (x + 1, y + 1, z),
                    (x + 1, y + 1, z + 1), (x, y + 1, z + 1)]
    return _assemble(faces(), fill_for, scale, outline_layer, merge_coplanar)
