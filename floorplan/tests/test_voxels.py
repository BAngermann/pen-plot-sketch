"""Headless checks for the de-Blendered voxel pipeline (no Blender, no GUI).

Run: ``python -m unittest`` from floorplan/ (or ``python -m unittest
tests.test_voxels``); needs numpy, the maze/voxel code is otherwise
dependency-free.
"""
import pathlib
import random
import sys
import unittest

import numpy as np

from scipy import ndimage

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from maze import Maze
from voxels import (PositionGrid, drop, flood_fill_3d,
                    _NEIGHBOR_KERNEL, _BELOW_KERNEL)


def _solid_grid(nx, ny, nz, floor_thickness=2):
    """A solid block of voxels with stable_z/floor_z set, for erosion tests."""
    g = PositionGrid(nx, ny, nz)
    g.stable_z = floor_thickness + 1
    g.floor_z = floor_thickness
    g.fill_box(0, nx, 0, ny, 0, nz)
    return g


class TestFromMaze(unittest.TestCase):
    def test_from_maze_nonempty(self):
        random.seed(7)
        m = Maze(13, 13)            # make_foundation needs a reasonably large maze
        m.gen_rooms()
        g = PositionGrid(8, 8, 8)
        g.fromMaze(m, room_size=12, wall_thickness=3, wall_height=18, floor_thickness=10)
        self.assertTrue(g.all_occupied_positions, "fromMaze produced no voxels")
        self.assertTrue(all(isinstance(v, int) and v >= 0
                            for p in g.all_occupied_positions for v in p))


class TestFloodFill(unittest.TestCase):
    def test_flood_fill_connectivity(self):
        grid = np.zeros((3, 3, 4))
        grid[1, 1, 0] = 1          # floor voxel (connected)
        grid[1, 1, 1] = 1          # sits on the floor voxel
        grid[0, 0, 3] = 1          # floating, disconnected
        filled = flood_fill_3d(grid, seed_z=0, fill_value=2)
        self.assertEqual(filled[1, 1, 0], 2, "floor column not filled")
        self.assertEqual(filled[1, 1, 1], 2, "floor column not filled")
        self.assertEqual(filled[0, 0, 3], 1, "floating voxel should remain unfilled")


class TestDecayTexture(unittest.TestCase):
    def test_decay_texture_reproducible(self):
        def run(seed):
            g = _solid_grid(6, 6, 6)
            g.decay_texture(2, np.random.default_rng(seed), lambda x, y: 0.0,
                            noise_influence=2.0)
            return g.all_occupied_positions

        self.assertEqual(run(123), run(123), "decay_texture not reproducible for a fixed seed")

    def test_neighbor_kernel_matches_reference(self):
        """The convolution neighbour count must equal the old per-voxel reference."""
        occ = np.random.default_rng(0).random((6, 6, 6)) < 0.5
        g = PositionGrid(6, 6, 6)
        g.all_occupied_positions = {(int(x), int(y), int(z))
                                    for x, y, z in np.argwhere(occ)}
        occf = occ.astype(float)
        total = (ndimage.correlate(occf, _NEIGHBOR_KERNEL, mode="constant", cval=0.0)
                 + 6.0 * (ndimage.correlate(occf, _BELOW_KERNEL, mode="constant", cval=0.0) > 8.5))
        for (x, y, z) in g.all_occupied_positions:
            with self.subTest(voxel=(x, y, z)):
                n, b = g._count_neighbors((x, y, z))
                ref = n + (6 if b == 9 else 0)
                self.assertLess(abs(total[x, y, z] - ref), 1e-9)

    def test_decay_terrain_rest_no_foundation(self):
        """Debris with no structural floor rests on the terrain, not the
        (unrelated, and here higher) structural floor_z."""
        g = PositionGrid(6, 6, 10)
        g.stable_z = 3
        g.floor_z = 2
        # A solid structure only for x in [0, 3): floor slab (z=0,1) + walls above.
        g.fill_box(0, 3, 0, 5, 0, 2)
        g.fill_box(0, 3, 0, 5, 2, 6)
        # A lone piece of rubble with no support at all, out past the wall
        # where there is no structural floor (x=4).
        g.all_occupied_positions.add((4, 2, 5))
        terrain_h = 1   # lower than floor_z=2

        class _ZeroRNG:
            """Deterministic stand-in for np.random.default_rng: always 0."""
            def random(self, size=None):
                return 0.0 if size is None else np.zeros(size)

        g.decay_texture(1, _ZeroRNG(), lambda x, y: 0.0, noise_influence=0.0,
                        noise_offset=0.0, neighbor_baseline=50,
                        terrain_z=lambda x, y: terrain_h)

        unfloored = [p for p in g.all_occupied_positions if p[0] >= 3]
        self.assertTrue(unfloored, "debris with no foundation vanished instead of landing")
        self.assertTrue(all(z == terrain_h for (_x, _y, z) in unfloored), unfloored)

    def test_decay_keeps_floor(self):
        g = _solid_grid(6, 6, 8, floor_thickness=2)
        before = len(g.all_occupied_positions)
        floor = {p for p in g.all_occupied_positions if p[2] <= g.stable_z}
        # Sketch-like regime: the floor's +30 stability bonus dominates, so
        # the floor survives while exposed surface voxels erode.
        g.decay_texture(3, np.random.default_rng(1), lambda x, y: 0.0,
                        noise_influence=3.5, noise_offset=-0.8, neighbor_baseline=-9)
        self.assertLessEqual(floor, g.all_occupied_positions, "floor voxels were eroded away")
        self.assertLess(len(g.all_occupied_positions), before, "nothing eroded")


class TestDrop(unittest.TestCase):
    def test_drop_rests_on_floor(self):
        """A floating voxel in an empty column lands exactly on the floor, no gap."""
        floor_z = 3
        grid = np.zeros((3, 3, 12))
        # Wall off the centre column so the voxel can't tumble: it falls straight.
        for x in range(3):
            for y in range(3):
                if (x, y) != (1, 1):
                    grid[x, y, :] = 1
        grid[1, 1, 9] = 1
        drop(1, 1, 9, grid, floor_z, rng=lambda: 0.0)
        self.assertEqual(grid[1, 1, 9], 0, "voxel not removed from its old position")
        self.assertEqual(grid[1, 1, floor_z], 3, "voxel did not rest on the floor")
        self.assertFalse(any(grid[1, 1, z] == 3 for z in range(floor_z)), "voxel fell below floor")

    def test_drop_rests_on_solid(self):
        """A floating voxel stacks directly on top of solid below it."""
        floor_z = 1
        grid = np.zeros((3, 3, 10))
        for x in range(3):
            for y in range(3):
                if (x, y) != (1, 1):
                    grid[x, y, :] = 1
        grid[1, 1, 0] = 1       # solid support at z=0
        grid[1, 1, 7] = 1       # floating voxel above it
        drop(1, 1, 7, grid, floor_z, rng=lambda: 0.0)
        self.assertEqual(grid[1, 1, 1], 3, "voxel did not stack on the solid cell below")

    def test_drop_array_floor_recomputes_after_tumble(self):
        """Tumbling into a neighbouring column rests at THAT column's own floor."""
        # 2x1 footprint: column x=0 has a high floor (5); column x=1 (the only
        # possible tumble target, since y has no room to move) has a low floor (1).
        floor = np.array([[5], [1]])
        grid = np.zeros((2, 1, 10))
        drop(0, 0, 8, grid, floor, rng=lambda: 0.0)   # i=int(0*8)=0 -> the sole candidate
        self.assertEqual(grid[0, 0, :].sum(), 0, "should have left its origin column")
        self.assertEqual(grid[1, 0, 1], 3, "did not rest at the destination column's own floor")


if __name__ == "__main__":
    unittest.main()
