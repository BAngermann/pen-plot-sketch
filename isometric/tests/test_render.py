"""Headless checks for the isometric renderer.

Run: ``python -m unittest`` from isometric/ (or ``python -m unittest
tests.test_render``). No vsketch / GUI needed -- only shapely + penfill.
Exercises the projection, the triangle decomposition, and the integer
z-buffer occlusion.
"""
import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

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


class TestLatticeGeometry(unittest.TestCase):
    def test_unit_face_triangles(self):
        """The 3 visible faces of voxel (0,0,0) tile 6 distinct lattice cells."""
        cells = {}
        for kind, quad in _unit_faces(Box(0, 0, 0, 1, 1, 1)):
            cells[kind] = {c for c, _d in _triangles(quad)}
        self.assertEqual(cells["top"], {(-1, -1, "L"), (-1, -1, "U")})
        self.assertEqual(cells["right"], {(0, 0, "L"), (0, -1, "U")})
        self.assertEqual(cells["left"], {(-1, 0, "L"), (0, 0, "U")})
        allcells = cells["top"] | cells["right"] | cells["left"]
        self.assertEqual(len(allcells), 6)

    def test_occlusion_depth(self):
        """A voxel along +(1,1,1) is nearer and wins the shared lattice cell."""
        back = next(q for k, q in _unit_faces(Box(0, 0, 0, 1, 1, 1)) if k == "top")
        front = next(q for k, q in _unit_faces(Box(1, 1, 1, 1, 1, 1)) if k == "top")
        db = dict(_triangles(back))
        df = dict(_triangles(front))
        shared = set(db) & set(df)
        self.assertTrue(shared, "front/back tops should share lattice cells")
        for cell in shared:
            with self.subTest(cell=cell):
                self.assertGreater(df[cell], db[cell])


class TestRenderVoxels(unittest.TestCase):
    def test_single_voxel_area(self):
        """One voxel -> 3 visible face regions covering the full hexagon."""
        geom = render_voxels({(0, 0, 0)}, outline_layer=1)
        polys = _outline_polys(geom)
        self.assertEqual(len(polys), 3, f"expected 3 face regions, got {len(polys)}")
        for p in polys:
            with self.subTest(poly=p):
                self.assertTrue(math.isclose(p.area, RHOMBUS_AREA, rel_tol=1e-9))
        total = unary_union(polys).area
        self.assertTrue(math.isclose(total, HEX_AREA, rel_tol=1e-9))

    def test_occlusion_render(self):
        """Two voxels, one occluding the other, cover less than two full hexagons."""
        # Separated along +x (not along the view direction (1,1,1)) so they don't overlap.
        two_apart = render_voxels({(0, 0, 0), (5, 0, 0)}, outline_layer=1)
        # (1,1,0) is nearer and partially (not fully) overlaps (0,0,0) on screen.
        overlapping = render_voxels({(0, 0, 0), (1, 1, 0)}, outline_layer=1)
        area_apart = unary_union(_outline_polys(two_apart)).area
        area_overlap = unary_union(_outline_polys(overlapping)).area
        self.assertTrue(math.isclose(area_apart, 2 * HEX_AREA, rel_tol=1e-9))
        self.assertTrue(HEX_AREA < area_overlap < 2 * HEX_AREA)

    def test_interior_face_culling(self):
        """A face shared by two stacked voxels is never emitted."""
        geom = render_voxels({(0, 0, 0), (0, 0, 1)}, outline_layer=1, merge_coplanar=False)
        # 2 voxels * 3 faces = 6, minus the buried top of the lower voxel = 5
        # regions (no occlusion between these two on screen, so all
        # surviving faces show).
        self.assertEqual(len(_outline_polys(geom)), 5)

    def test_merge_coplanar(self):
        """Coplanar same-direction faces merge; their shared boundary is dropped."""
        merged = render_voxels({(0, 0, 0), (0, 0, 1)}, outline_layer=1)
        unmerged = render_voxels({(0, 0, 0), (0, 0, 1)}, outline_layer=1,
                                 merge_coplanar=False)
        # Stacked voxels: the two right faces (plane x=1) and the two left
        # faces (plane y=1) each merge -> top(upper) + right + left = 3
        # regions, not 5.
        self.assertEqual(len(_outline_polys(merged)), 3)
        self.assertEqual(len(_outline_polys(unmerged)), 5)
        # Merging only removes internal seams, so the covered area is unchanged.
        a_m = unary_union(_outline_polys(merged)).area
        a_u = unary_union(_outline_polys(unmerged)).area
        self.assertTrue(math.isclose(a_m, a_u, rel_tol=1e-9))

    def test_fills_emitted(self):
        """Resolver fills produce filled / stroked primitives on the right layers."""
        resolver = face_type_resolver({
            "top": FillSpec("solid", 1),
            "left": FillSpec("hatch", 2, dict(spacing=0.2, angle=45.0)),
        })
        geom = render_boxes([Box(0, 0, 0, 1, 1, 1)], resolver)
        self.assertTrue(any(p[0] == "F" and p[1] == 1 for p in geom), "top solid fill missing")
        self.assertTrue(any(p[0] == "S" and p[1] == 2 for p in geom), "left hatch missing")
        self.assertFalse(any(p[1] == 3 for p in geom), "right should be unfilled")


if __name__ == "__main__":
    unittest.main()
