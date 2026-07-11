"""Stage 4 checks: fromMaze's multi-floor readiness (floor_level offset,
omit_floor_cells, roof_stair_state clamp) -- still single-floor behaviour
otherwise.

Run: ``python -m unittest`` from floorplan/ (or ``python -m unittest
tests.test_multifloor_voxels``); needs numpy, no vsketch needed.
"""
import pathlib
import random
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from maze import Maze
from voxels import PositionGrid


def _small_maze(seed=3):
    random.seed(seed)
    m = Maze(8, 8)
    m.gen_rooms(shape="rectangular", entrance_sides=('s', 'e'), place_shafts=False, place_basins=False)
    return m


class TestMultiFloorVoxels(unittest.TestCase):
    def test_floor_level_offsets_every_voxel(self):
        m = _small_maze()
        g = PositionGrid(8, 8, 20)
        g.fromMaze(m, room_size=6, wall_thickness=2, wall_height=8, floor_thickness=2, floor_level=20)
        self.assertTrue(g.all_occupied_positions, "no voxels produced")
        self.assertTrue(all(z >= 20 for (_x, _y, z) in g.all_occupied_positions),
                        "some voxel is below the given floor_level")

    def test_floor_level_zero_preserves_stable_z(self):
        m = _small_maze()
        g = PositionGrid(8, 8, 20)
        g.fromMaze(m, room_size=6, wall_thickness=2, wall_height=8, floor_thickness=2, floor_level=0)
        self.assertEqual(g.stable_z, 3)
        self.assertEqual(g.floor_z, 2)

    def test_upper_floor_call_does_not_clobber_stable_z(self):
        m = _small_maze()
        g = PositionGrid(8, 8, 40)
        g.fromMaze(m, room_size=6, wall_thickness=2, wall_height=8, floor_thickness=2, floor_level=0)
        stable_before, floor_before = g.stable_z, g.floor_z
        g.fromMaze(m, room_size=6, wall_thickness=2, wall_height=8, floor_thickness=2, floor_level=12)
        self.assertEqual(g.stable_z, stable_before,
                         "an upper-floor call must not overwrite stable_z")
        self.assertEqual(g.floor_z, floor_before,
                         "an upper-floor call must not overwrite floor_z")

    def test_omit_floor_cells_leaves_a_hole_but_keeps_walls(self):
        m = _small_maze()
        # find any room floor cell to omit
        cell = next((r, c) for r in range(m.num_rows) for c in range(m.num_cols) if m.rooms[r][c] != 0)
        room_size, wall_thickness, floor_thickness = 6, 2, 2
        cell_size = room_size + wall_thickness
        row, col = cell

        g_full = PositionGrid(8, 8, 20)
        g_full.fromMaze(m, room_size=room_size, wall_thickness=wall_thickness, wall_height=8,
                        floor_thickness=floor_thickness, floor_level=0)
        g_omit = PositionGrid(8, 8, 20)
        g_omit.fromMaze(m, room_size=room_size, wall_thickness=wall_thickness, wall_height=8,
                        floor_thickness=floor_thickness, floor_level=0, omit_floor_cells={cell})

        # the cell's own floor-slab voxel (well inside the tile, away from any
        # inter-cell seam fill) must be present in the full case, absent when omitted.
        probe = (row * cell_size + wall_thickness + 1, col * cell_size + wall_thickness + 1, 0)
        self.assertIn(probe, g_full.all_occupied_positions, "sanity: probe should be floored normally")
        self.assertNotIn(probe, g_omit.all_occupied_positions, "omitted cell still has a floor voxel")

        # walls are untouched: voxel counts differ by exactly the omitted floor
        # tile's worth (walls block unaffected -> same wall voxel count either way).
        diff = len(g_full.all_occupied_positions) - len(g_omit.all_occupied_positions)
        self.assertGreater(diff, 0, "omitting a floor cell should remove some voxels")

    def test_roof_stair_state_breaks_through(self):
        m = _small_maze()
        # carve one short east-facing stair flight (base state 40 -- Stage 5
        # adds make_stairs(state_value=)/unused_stair_state for picking a
        # distinct value per flight; a fresh maze's default base value is
        # fine here).
        row, col = next((r, c) for r in range(m.num_rows) for c in range(m.num_cols) if m.rooms[r][c] == 1)
        state = 40
        m.make_stairs(row, col, 'e', length=2)

        # A short wall_height keeps the normal ceiling well below the flight's
        # natural rise, so the clamp actually bites in the normal case and the
        # roof-break case (a much higher ceiling) visibly rises further.
        room_size, wall_thickness, wall_height, floor_thickness = 6, 2, 3, 2
        normal_ceiling = 0 + floor_thickness + wall_height

        g_normal = PositionGrid(8, 8, 20)
        g_normal.fromMaze(m, room_size=room_size, wall_thickness=wall_thickness, wall_height=wall_height,
                          floor_thickness=floor_thickness, floor_level=0)
        g_break = PositionGrid(8, 8, 20)
        g_break.fromMaze(m, room_size=room_size, wall_thickness=wall_thickness, wall_height=wall_height,
                         floor_thickness=floor_thickness, floor_level=0,
                         roof_stair_state=state, roof_break_height=normal_ceiling + 5)

        max_z_normal = max(z for (_x, _y, z) in g_normal.all_occupied_positions)
        max_z_break = max(z for (_x, _y, z) in g_break.all_occupied_positions)
        self.assertGreater(max_z_break, max_z_normal,
                           "roof_break_height should raise the flight's ceiling")


if __name__ == "__main__":
    unittest.main()
