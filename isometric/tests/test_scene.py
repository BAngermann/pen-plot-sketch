"""Headless checks for the heightfield + scene renderer (Phases 3 & 4).

Run: ``python -m unittest`` from isometric/ (or ``python -m unittest
tests.test_scene``); needs shapely + penfill, no GUI.
"""
import itertools
import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from shapely.geometry import Polygon
from shapely.ops import unary_union

from penfill import FillSpec
from isometric import Heightfield, render_scene
from isometric.boxes import _zbuffer
from isometric.scene import _structure_faces, _shadowed_cells


def _flat(W, H, v=0.0):
    return Heightfield([[float(v)] * (H + 1) for _ in range(W + 1)])


def _zbuf_tags(faces):
    zbuf, _ = _zbuffer(faces)
    s = sum(1 for _c, (_d, gid) in zbuf.items() if gid[0] == "S")
    gt = {(gid[1], gid[2]) for _c, (_d, gid) in zbuf.items() if gid[0] == "GT"}
    return s, gt


class TestHeightfield(unittest.TestCase):
    def test_terr_int(self):
        hf = Heightfield([[0.0, 0.0, 0.0], [0.0, 4.4, 0.0], [0.0, 0.0, 0.0]])  # W=H=2
        self.assertEqual(hf.terr_int(0, 0), round(4.4 / 4))   # one tall corner
        self.assertEqual(hf.terr_int(1, 1), round(4.4 / 4))
        flat = _flat(4, 4, 3.2)
        self.assertEqual(flat.terr_int(2, 2), 3)

    def test_terraced_faces_flat(self):
        hf = _flat(4, 4, 0.0)
        tops = [f for f in hf.terraced_faces() if f[0][0] == "GT"]
        walls = [f for f in hf.terraced_faces() if f[0][0] == "GW"]
        self.assertEqual(len(tops), 16)        # one top per cell, no steps on flat
        self.assertEqual(len(walls), 0)


class TestSceneOcclusion(unittest.TestCase):
    def test_structure_occludes_terrain(self):
        hf = _flat(6, 6, 0.0)
        _s0, gt0 = _zbuf_tags(hf.terraced_faces())
        self.assertEqual(len(gt0), 36)          # flat ground fully visible
        box = {(2, 2, 0), (2, 2, 1), (2, 2, 2)}  # a pillar standing on the ground
        faces = itertools.chain(_structure_faces(box, 1), hf.terraced_faces())
        s1, gt1 = _zbuf_tags(faces)
        self.assertGreater(s1, 0, "structure not rendered")
        self.assertLess(len(gt1), len(gt0))     # it hides ground behind it

    def test_terrain_occludes_structure(self):
        box = {(2, 2, 0)}                          # a single low block
        flat = _flat(7, 7, 0.0)
        sA, _ = _zbuf_tags(itertools.chain(_structure_faces(box, 1), flat.terraced_faces()))
        # A tall ridge in front of the block (larger x+y, much taller) should hide it.
        h = [[10.0 if (i >= 3 and j >= 3) else 0.0 for j in range(8)] for i in range(8)]
        ridge = Heightfield(h)
        sB, _ = _zbuf_tags(itertools.chain(_structure_faces(box, 1), ridge.terraced_faces()))
        self.assertLess(sB, sA)


class TestRenderScene(unittest.TestCase):
    def test_render_scene_smoke_subdiv2(self):
        hf = _flat(8, 8, 0.0)
        box = {(0, 0, 0), (1, 1, 1)}
        geom = render_scene(box, hf, subdiv=2,
                            fill_for=lambda b, k: FillSpec("solid", 1),
                            ground_top_fill=FillSpec("solid", 2),
                            scale=0.5, outline_layer=4, relief_layer=5)
        self.assertTrue(geom, "no geometry produced")
        self.assertTrue(any(p[0] == "F" for p in geom), "no fills")
        self.assertTrue(any(p[0] == "S" and p[1] == 4 for p in geom), "no outlines")

    def test_sloped_vs_terraced_ground(self):
        # A slanted terrain ramp: sloped and terraced surfaces should both
        # render but differ (the sloped silhouette is not the stair-stepped
        # terraced one).
        h = [[float(i) for _j in range(6)] for i in range(6)]   # height ramps with i
        hf = Heightfield(h)
        common = dict(ground_top_fill=FillSpec("solid", 2), scale=1.0, outline_layer=4)
        sloped = render_scene(set(), hf, sloped_ground=True, **common)
        terr = render_scene(set(), hf, sloped_ground=False, **common)
        self.assertTrue(sloped and terr, "both modes must produce geometry")

        def area(geom):
            polys = [Polygon(p[2]) for p in geom if p[0] == "S" and p[3]]
            return unary_union(polys).area if polys else 0.0

        self.assertFalse(math.isclose(area(sloped), area(terr), rel_tol=1e-6),
                         "sloped and terraced silhouettes should differ on a ramp")


class TestShadows(unittest.TestCase):
    def test_shadow_basic(self):
        hf = _flat(8, 8, 0.0)
        pillar = {(4, 4, z) for z in range(6)}     # tall pillar
        visible_ij = {(i, j) for i in range(8) for j in range(8)}
        light = (1, 0, 3)                          # toward +x and up
        shadowed = _shadowed_cells(visible_ij, hf, pillar, 1, light)
        self.assertIn((3, 4), shadowed, "cell just west of the pillar should be shadowed")
        self.assertNotIn((5, 4), shadowed, "cell east of the pillar (toward light) is lit")
        self.assertNotIn((0, 4), shadowed, "far cell clears the pillar top -> lit")

    def test_no_shadow_without_occluder(self):
        hf = _flat(6, 6, 0.0)
        visible_ij = {(i, j) for i in range(6) for j in range(6)}
        shadowed = _shadowed_cells(visible_ij, hf, set(), 1, (1, 0, 3))
        self.assertFalse(shadowed)


if __name__ == "__main__":
    unittest.main()
