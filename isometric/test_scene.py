"""Headless checks for the heightfield + scene renderer (Phases 3 & 4).

Run: ``python test_scene.py`` (needs shapely + penfill; no GUI).
"""
import itertools
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

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


def test_terr_int():
    hf = Heightfield([[0.0, 0.0, 0.0], [0.0, 4.4, 0.0], [0.0, 0.0, 0.0]])  # W=H=2
    assert hf.terr_int(0, 0) == round(4.4 / 4), hf.terr_int(0, 0)   # one tall corner
    assert hf.terr_int(1, 1) == round(4.4 / 4)
    flat = _flat(4, 4, 3.2)
    assert flat.terr_int(2, 2) == 3
    print("ok: terr_int = round(mean of corner heights)")


def test_terraced_faces_flat():
    hf = _flat(4, 4, 0.0)
    tops = [f for f in hf.terraced_faces() if f[0][0] == "GT"]
    walls = [f for f in hf.terraced_faces() if f[0][0] == "GW"]
    assert len(tops) == 16, len(tops)        # one top per cell, no steps on flat
    assert len(walls) == 0, len(walls)
    print("ok: flat terrain -> one top per cell, no walls")


def test_structure_occludes_terrain():
    hf = _flat(6, 6, 0.0)
    _s0, gt0 = _zbuf_tags(hf.terraced_faces())
    assert len(gt0) == 36, len(gt0)          # flat ground fully visible
    box = {(2, 2, 0), (2, 2, 1), (2, 2, 2)}  # a pillar standing on the ground
    faces = itertools.chain(_structure_faces(box, 1), hf.terraced_faces())
    s1, gt1 = _zbuf_tags(faces)
    assert s1 > 0, "structure not rendered"
    assert len(gt1) < len(gt0), (len(gt1), len(gt0))  # it hides ground behind it
    print(f"ok: structure occludes terrain ({len(gt0)} -> {len(gt1)} cells)")


def test_terrain_occludes_structure():
    box = {(2, 2, 0)}                          # a single low block
    flat = _flat(7, 7, 0.0)
    sA, _ = _zbuf_tags(itertools.chain(_structure_faces(box, 1), flat.terraced_faces()))
    # A tall ridge in front of the block (larger x+y, much taller) should hide it.
    h = [[10.0 if (i >= 3 and j >= 3) else 0.0 for j in range(8)] for i in range(8)]
    ridge = Heightfield(h)
    sB, _ = _zbuf_tags(itertools.chain(_structure_faces(box, 1), ridge.terraced_faces()))
    assert sB < sA, (sB, sA)
    print(f"ok: terrain occludes structure ({sA} -> {sB} structure cells)")


def test_render_scene_smoke_subdiv2():
    hf = _flat(8, 8, 0.0)
    box = {(0, 0, 0), (1, 1, 1)}
    geom = render_scene(box, hf, subdiv=2,
                        fill_for=lambda b, k: FillSpec("solid", 1),
                        ground_top_fill=FillSpec("solid", 2),
                        scale=0.5, outline_layer=4, relief_layer=5)
    assert geom, "no geometry produced"
    assert any(p[0] == "F" for p in geom), "no fills"
    assert any(p[0] == "S" and p[1] == 4 for p in geom), "no outlines"
    print("ok: render_scene runs at subdiv=2 with terrain + relief")


def test_sloped_vs_terraced_ground():
    # A slanted terrain ramp: sloped and terraced surfaces should both render but
    # differ (the sloped silhouette is not the stair-stepped terraced one).
    h = [[float(i) for _j in range(6)] for i in range(6)]   # height ramps with i
    hf = Heightfield(h)
    common = dict(ground_top_fill=FillSpec("solid", 2), scale=1.0, outline_layer=4)
    sloped = render_scene(set(), hf, sloped_ground=True, **common)
    terr = render_scene(set(), hf, sloped_ground=False, **common)
    assert sloped and terr, "both modes must produce geometry"

    def area(geom):
        polys = [Polygon(p[2]) for p in geom if p[0] == "S" and p[3]]
        return unary_union(polys).area if polys else 0.0

    assert not math.isclose(area(sloped), area(terr), rel_tol=1e-6), \
        "sloped and terraced silhouettes should differ on a ramp"
    print("ok: sloped_ground toggle changes the drawn surface")


def test_shadow_basic():
    hf = _flat(8, 8, 0.0)
    pillar = {(4, 4, z) for z in range(6)}     # tall pillar
    visible_ij = {(i, j) for i in range(8) for j in range(8)}
    light = (1, 0, 3)                          # toward +x and up
    shadowed = _shadowed_cells(visible_ij, hf, pillar, 1, light)
    assert (3, 4) in shadowed, "cell just west of the pillar should be shadowed"
    assert (5, 4) not in shadowed, "cell east of the pillar (toward light) is lit"
    assert (0, 4) not in shadowed, "far cell clears the pillar top -> lit"
    print(f"ok: pillar casts a shadow ({len(shadowed)} cells)")


def test_no_shadow_without_occluder():
    hf = _flat(6, 6, 0.0)
    visible_ij = {(i, j) for i in range(6) for j in range(6)}
    shadowed = _shadowed_cells(visible_ij, hf, set(), 1, (1, 0, 3))
    assert not shadowed, shadowed
    print("ok: flat empty terrain casts no shadow")


if __name__ == "__main__":
    test_terr_int()
    test_terraced_faces_flat()
    test_structure_occludes_terrain()
    test_terrain_occludes_structure()
    test_render_scene_smoke_subdiv2()
    test_sloped_vs_terraced_ground()
    test_shadow_basic()
    test_no_shadow_without_occluder()
    print("\nall scene tests passed")
