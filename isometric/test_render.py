"""Headless checks for the isometric renderer (run: ``python test_render.py``).

No vsketch / GUI needed — only shapely + penfill.  Exercises the projection, the
triangle decomposition, and the integer z-buffer occlusion.
"""
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from shapely.geometry import Polygon
from shapely.ops import unary_union

from penfill import FillSpec
from isometric import Box, render_boxes, render_voxels, face_type_resolver
from isometric.boxes import _triangles, _unit_faces
from isometric.projection import C, S

RHOMBUS_AREA = 2 * C * S          # area of one projected unit face ≈ 0.866
HEX_AREA = 3 * RHOMBUS_AREA       # one fully visible voxel ≈ 2.598


def _outline_polys(geom):
    """Rebuild shapely polygons from the closed 'S' outline primitives."""
    return [Polygon(prim[2]) for prim in geom if prim[0] == "S" and prim[3]]


def test_unit_face_triangles():
    """The 3 visible faces of voxel (0,0,0) tile 6 distinct lattice cells."""
    cells = {}
    for kind, quad in _unit_faces(Box(0, 0, 0, 1, 1, 1)):
        cells[kind] = {c for c, _d in _triangles(quad)}
    assert cells["top"] == {(-1, -1, "L"), (-1, -1, "U")}, cells["top"]
    assert cells["right"] == {(0, 0, "L"), (0, -1, "U")}, cells["right"]
    assert cells["left"] == {(-1, 0, "L"), (0, 0, "U")}, cells["left"]
    allcells = cells["top"] | cells["right"] | cells["left"]
    assert len(allcells) == 6, allcells
    print("ok: unit-face triangle decomposition")


def test_single_voxel_area():
    """One voxel -> 3 visible face regions covering the full hexagon."""
    geom = render_voxels({(0, 0, 0)}, outline_layer=1)
    polys = _outline_polys(geom)
    assert len(polys) == 3, f"expected 3 face regions, got {len(polys)}"
    for p in polys:
        assert math.isclose(p.area, RHOMBUS_AREA, rel_tol=1e-9), p.area
    total = unary_union(polys).area
    assert math.isclose(total, HEX_AREA, rel_tol=1e-9), total
    print("ok: single-voxel area == hexagon")


def test_occlusion_depth():
    """A voxel along +(1,1,1) is nearer and wins the shared lattice cell."""
    back = next(q for k, q in _unit_faces(Box(0, 0, 0, 1, 1, 1)) if k == "top")
    front = next(q for k, q in _unit_faces(Box(1, 1, 1, 1, 1, 1)) if k == "top")
    db = dict(_triangles(back))
    df = dict(_triangles(front))
    shared = set(db) & set(df)
    assert shared, "front/back tops should share lattice cells"
    for cell in shared:
        assert df[cell] > db[cell], (cell, df[cell], db[cell])
    print("ok: nearer voxel has strictly greater depth on shared cells")


def test_occlusion_render():
    """Two voxels, one occluding the other, cover less than two full hexagons."""
    # Separated along +x (not along the view direction (1,1,1)) so they don't overlap.
    two_apart = render_voxels({(0, 0, 0), (5, 0, 0)}, outline_layer=1)
    # (1,1,0) is nearer and partially (not fully) overlaps (0,0,0) on screen.
    overlapping = render_voxels({(0, 0, 0), (1, 1, 0)}, outline_layer=1)
    area_apart = unary_union(_outline_polys(two_apart)).area
    area_overlap = unary_union(_outline_polys(overlapping)).area
    assert math.isclose(area_apart, 2 * HEX_AREA, rel_tol=1e-9), area_apart
    assert HEX_AREA < area_overlap < 2 * HEX_AREA, area_overlap
    print("ok: occlusion removes hidden area")


def test_interior_face_culling():
    """A face shared by two stacked voxels is never emitted."""
    geom = render_voxels({(0, 0, 0), (0, 0, 1)}, outline_layer=1, merge_coplanar=False)
    # 2 voxels * 3 faces = 6, minus the buried top of the lower voxel = 5 regions
    # (no occlusion between these two on screen, so all surviving faces show).
    assert len(_outline_polys(geom)) == 5, len(_outline_polys(geom))
    print("ok: interior shared face culled")


def test_merge_coplanar():
    """Coplanar same-direction faces merge; their shared boundary is dropped."""
    merged = render_voxels({(0, 0, 0), (0, 0, 1)}, outline_layer=1)
    unmerged = render_voxels({(0, 0, 0), (0, 0, 1)}, outline_layer=1,
                             merge_coplanar=False)
    # Stacked voxels: the two right faces (plane x=1) and the two left faces
    # (plane y=1) each merge -> top(upper) + right + left = 3 regions, not 5.
    assert len(_outline_polys(merged)) == 3, len(_outline_polys(merged))
    assert len(_outline_polys(unmerged)) == 5, len(_outline_polys(unmerged))
    # Merging only removes internal seams, so the covered area is unchanged.
    a_m = unary_union(_outline_polys(merged)).area
    a_u = unary_union(_outline_polys(unmerged)).area
    assert math.isclose(a_m, a_u, rel_tol=1e-9), (a_m, a_u)
    print("ok: coplanar same-direction faces merge (no internal boundary)")


def test_fills_emitted():
    """Resolver fills produce filled / stroked primitives on the right layers."""
    resolver = face_type_resolver({
        "top": FillSpec("solid", 1),
        "left": FillSpec("hatch", 2, dict(spacing=0.2, angle=45.0)),
    })
    geom = render_boxes([Box(0, 0, 0, 1, 1, 1)], resolver)
    assert any(p[0] == "F" and p[1] == 1 for p in geom), "top solid fill missing"
    assert any(p[0] == "S" and p[1] == 2 for p in geom), "left hatch missing"
    assert not any(p[1] == 3 for p in geom), "right should be unfilled"
    print("ok: fills emitted per face")


if __name__ == "__main__":
    test_unit_face_triangles()
    test_single_voxel_area()
    test_occlusion_depth()
    test_occlusion_render()
    test_interior_face_culling()
    test_merge_coplanar()
    test_fills_emitted()
    print("\nall isometric tests passed")
