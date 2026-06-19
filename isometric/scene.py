"""Render a voxel structure together with a ground heightfield, in isometric.

The structure (coarse voxels) and the terrain (a :class:`Heightfield`) are
assembled in one *fine* integer frame (subdivision factor ``subdiv``) and share a
single integer z-buffer (:func:`isometric.boxes._zbuffer`).  Terrain occlusion
uses the heightfield's terraced-column proxy, so structure↔terrain hidden-surface
removal is exact-to-½-cell with no Shapely booleans; the terrain is then *drawn*
as a smooth sloped mesh over its visible footprint.

Phase 4 adds ground shadows: an integer light-march (3D DDA) over the combined
occupancy marks shadowed terrain cells, emitted as a fill on a shadow layer.
"""
from __future__ import annotations

import itertools
import math
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from penfill import FillSpec, Geometry, fill_polygon

from .boxes import (Box, FaceTask, FillResolver, _cell_polygon, _outline,
                    _plane_key, _polygons, _resolve, _zbuffer)
from .heightfield import Heightfield
from .projection import project


# ── structure faces in the fine frame ────────────────────────────────────────

def _structure_faces(occ: set, m: int) -> Iterable[FaceTask]:
    """Exposed structure faces, each coarse voxel scaled to an ``m``-box and
    subdivided into unit faces on the fine lattice."""
    for (x, y, z) in occ:
        bx, by, bz = x * m, y * m, z * m
        box = Box(bx, by, bz, m, m, m, key=(x, y, z))
        if (x, y, z + 1) not in occ:                       # top
            zt = bz + m
            for i in range(m):
                for j in range(m):
                    yield ("S", x, y, z, "top", i, j), box, "top", [
                        (bx + i, by + j, zt), (bx + i + 1, by + j, zt),
                        (bx + i + 1, by + j + 1, zt), (bx + i, by + j + 1, zt)]
        if (x + 1, y, z) not in occ:                       # right
            xf = bx + m
            for j in range(m):
                for k in range(m):
                    yield ("S", x, y, z, "right", j, k), box, "right", [
                        (xf, by + j, bz + k), (xf, by + j + 1, bz + k),
                        (xf, by + j + 1, bz + k + 1), (xf, by + j, bz + k + 1)]
        if (x, y + 1, z) not in occ:                       # left
            yf = by + m
            for i in range(m):
                for k in range(m):
                    yield ("S", x, y, z, "left", i, k), box, "left", [
                        (bx + i, yf, bz + k), (bx + i + 1, yf, bz + k),
                        (bx + i + 1, yf, bz + k + 1), (bx + i, yf, bz + k + 1)]


# ── terrain drawing helpers ──────────────────────────────────────────────────

def _proj_poly(pts3, scale):
    return [project(x, y, z, scale) for (x, y, z) in pts3]


def _clip_line(p1, p2, region, layer) -> Geometry:
    inter = LineString([p1, p2]).intersection(region)
    out: Geometry = []
    if inter.is_empty:
        return out
    if inter.geom_type == "LineString":
        out.append(("S", layer, list(inter.coords), False))
    elif inter.geom_type in ("MultiLineString", "GeometryCollection"):
        for g in inter.geoms:
            if g.geom_type == "LineString" and not g.is_empty:
                out.append(("S", layer, list(g.coords), False))
    return out


def _relief(cells_ij, hf: Heightfield, scale, layer, region) -> Geometry:
    """Sloped mesh grid lines over the visible terrain, clipped to ``region``."""
    edges = set()
    for (i, j) in cells_ij:
        edges.add(((i, j), (i + 1, j)))
        edges.add(((i, j), (i, j + 1)))
        edges.add(((i + 1, j), (i + 1, j + 1)))
        edges.add(((i, j + 1), (i + 1, j + 1)))
    ox, oy, h = hf.ox, hf.oy, hf.h
    geom: Geometry = []
    for (a, b) in edges:
        p1 = project(ox + a[0], oy + a[1], h[a[0]][a[1]], scale)
        p2 = project(ox + b[0], oy + b[1], h[b[0]][b[1]], scale)
        geom += _clip_line(p1, p2, region, layer)
    return geom


# ── shadow march (phase 4) ───────────────────────────────────────────────────

def _occupied_pred(occ: set, m: int, hf: Heightfield):
    """Combined fine-voxel solidity: structure ∪ terraced terrain."""
    def occupied(x, y, z):
        if z < 0:
            return True                       # nothing is lit from below ground
        if (x // m, y // m, z // m) in occ:
            return True
        return hf.occupied(x, y, z)
    return occupied


def _in_shadow(px, py, pz, light, occupied, zmax) -> bool:
    """3D DDA from (px,py,pz) toward the light; True if it hits occupancy first."""
    dx, dy, dz = light
    x, y, z = math.floor(px), math.floor(py), math.floor(pz)

    def setup(p, d, c):
        if d > 0:
            return (c + 1 - p) / d, 1.0 / d, 1
        if d < 0:
            return (c - p) / d, -1.0 / d, -1
        return math.inf, math.inf, 0

    tMaxX, tDX, sX = setup(px, dx, x)
    tMaxY, tDY, sY = setup(py, dy, y)
    tMaxZ, tDZ, sZ = setup(pz, dz, z)
    for _ in range(4 * (zmax + 2)):           # bounded number of steps
        if tMaxX < tMaxY and tMaxX < tMaxZ:
            x += sX; tMaxX += tDX
        elif tMaxY < tMaxZ:
            y += sY; tMaxY += tDY
        else:
            z += sZ; tMaxZ += tDZ
        if z > zmax:                          # left the scene going up → lit
            return False
        if occupied(x, y, z):
            return True
    return False


def _shadowed_cells(cells_by_ij, hf: Heightfield, occ, m, light) -> set:
    """Which visible terrain cells (i,j) are in shadow."""
    occupied = _occupied_pred(occ, m, hf)
    terr_max = max((max(row) for row in hf._col), default=0)
    struct_max = (max((z for _x, _y, z in occ), default=-1) + 1) * m
    zmax = max(terr_max, struct_max) + 1
    shadowed = set()
    for (i, j) in cells_by_ij:
        H = hf.terr_int(i, j)
        px, py, pz = hf.ox + i + 0.5, hf.oy + j + 0.5, H + 0.5
        if _in_shadow(px, py, pz, light, occupied, zmax):
            shadowed.add((i, j))
    return shadowed


# ── main entry ───────────────────────────────────────────────────────────────

def render_scene(voxels, heightfield: Heightfield, *, subdiv: int = 1,
                 fill_for: Optional[FillResolver] = None,
                 ground_top_fill: Optional[FillSpec] = None,
                 ground_wall_fill: Optional[FillSpec] = None,
                 scale: float = 1.0, outline_layer: Optional[int] = None,
                 relief_layer: Optional[int] = None, merge_coplanar: bool = True,
                 sloped_ground: bool = True,
                 light: Optional[Tuple[float, float, float]] = None,
                 shadow_fill: Optional[FillSpec] = None) -> Geometry:
    """Render a coarse voxel structure over a ground heightfield in isometric.

    ``fill_for`` resolves structure face fills (as for ``render_boxes``);
    ``ground_top_fill``/``ground_wall_fill`` fill the terrain surface and its
    edge cliffs.  ``relief_layer`` draws the sloped mesh grid as relief lines.
    If ``light`` (an integer-ish 3-vector toward the light) and ``shadow_fill``
    are given, ground cells shadowed along ``light`` get filled too.

    Occlusion always uses the heightfield's terraced-column proxy. The drawn
    ground *surface* is the true sloped mesh when ``sloped_ground`` is True
    (smooth silhouette, clipped against the structure), or the terraced footprint
    when False (stair-stepped, exactly on the occlusion boundary).
    """
    m = subdiv
    occ = voxels if isinstance(voxels, (set, frozenset)) else set(voxels)
    faces = itertools.chain(_structure_faces(occ, m), heightfield.terraced_faces())
    zbuf, meta = _zbuffer(faces)

    struct_cells: Dict = defaultdict(list)
    struct_meta: Dict = {}
    wall_cells: Dict = defaultdict(list)
    top_cells_by_ij: Dict = defaultdict(list)
    for cell, (_d, gid) in zbuf.items():
        tag = gid[0]
        if tag == "S":
            box, kind = meta[gid]
            key = _plane_key(box, kind) if merge_coplanar else gid
            struct_cells[key].append(cell)
            struct_meta.setdefault(key, (box, kind))
        elif tag == "GT":
            top_cells_by_ij[(gid[1], gid[2])].append(cell)
        elif tag == "GW":
            box, kind = meta[gid]
            key = _plane_key(box, kind) if merge_coplanar else gid
            wall_cells[key].append(cell)

    geom: Geometry = []

    # structure faces (collect their silhouette to clip the sloped terrain against)
    struct_polys: List = []
    for key, cells in struct_cells.items():
        box, kind = struct_meta[key]
        region = unary_union([_cell_polygon(c, scale) for c in cells])
        spec = _resolve(box, kind, fill_for)
        for poly in _polygons(region):
            struct_polys.append(poly)
            if spec is not None:
                geom += fill_polygon(poly, spec)
            if outline_layer is not None:
                geom += _outline(poly, outline_layer)

    # terrain edge cliffs (terraced)
    for key, cells in wall_cells.items():
        region = unary_union([_cell_polygon(c, scale) for c in cells])
        for poly in _polygons(region):
            if ground_wall_fill is not None:
                geom += fill_polygon(poly, ground_wall_fill)
            if outline_layer is not None:
                geom += _outline(poly, outline_layer)

    # terrain top: occlusion is always terraced; the drawn surface is either the
    # terraced footprint or the true sloped mesh (clipped against the structure).
    if top_cells_by_ij:
        struct_sil = unary_union(struct_polys) if (sloped_ground and struct_polys) else None

        def ground_region(ijs, cells):
            if sloped_ground:
                reg = unary_union([Polygon(_proj_poly(heightfield.sloped_quad(i, j), scale))
                                   for (i, j) in ijs])
                if struct_sil is not None and not reg.is_empty:
                    reg = reg.difference(struct_sil)
                return reg
            return unary_union([_cell_polygon(c, scale) for c in cells])

        all_cells = [c for cells in top_cells_by_ij.values() for c in cells]
        region = ground_region(top_cells_by_ij.keys(), all_cells)
        for poly in _polygons(region):
            if ground_top_fill is not None:
                geom += fill_polygon(poly, ground_top_fill)
            if outline_layer is not None:
                geom += _outline(poly, outline_layer)
        if light is not None and shadow_fill is not None:
            shadowed = _shadowed_cells(top_cells_by_ij.keys(), heightfield, occ, m, light)
            if shadowed:
                sh_cells = [c for ij in shadowed for c in top_cells_by_ij[ij]]
                sregion = ground_region(shadowed, sh_cells)
                for poly in _polygons(sregion):
                    geom += fill_polygon(poly, shadow_fill)
        if relief_layer is not None:
            geom += _relief(top_cells_by_ij.keys(), heightfield, scale, relief_layer, region)

    return geom
