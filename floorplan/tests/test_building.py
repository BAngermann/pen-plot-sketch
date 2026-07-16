"""Stage 5 checks: Building orchestration, multi-floor stacking, and the
core correctness guarantee -- a stairway landing is never in a wall / never
isolated.

Run: ``python -m unittest`` from floorplan/ (or ``python -m unittest
tests.test_building``); needs numpy for the voxel-level checks.
"""
import pathlib
import random
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from maze import Building, Maze
from voxels import PositionGrid


class TestBuildingGeneration(unittest.TestCase):
    def test_floor2_appears_when_footprint_is_large_enough(self):
        random.seed(4)
        b = Building(11, 11).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                      floor2_area_threshold=20, stair_length=3)
        self.assertEqual(len(b.floors), 2)
        ground, upper = b.floors
        self.assertLessEqual(upper.footprint_cells(), ground.footprint_cells(),
                             "upper floor footprint must be a subset of the ground floor's")

    def test_floor2_skipped_when_threshold_too_high(self):
        random.seed(4)
        b = Building(11, 11).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                      floor2_area_threshold=10**9, stair_length=3)
        self.assertEqual(len(b.floors), 1)


class TestStairLandingCorrectness(unittest.TestCase):
    """The core guarantee: 'a stair leading upward must not end in a wall.'"""

    def test_landing_is_walkable_and_reachable_on_upper_floor(self):
        random.seed(4)
        b = Building(11, 11).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                      floor2_area_threshold=20, stair_length=3)
        self.assertEqual(len(b.floors), 2, "test needs floor2 to be generated")
        ground, upper = b.floors
        landing = b.stair_links[0]['landing']
        self.assertNotEqual(upper.rooms[landing[0]][landing[1]], 0,
                            "the landing cell must not be carved away on the upper floor")
        comps = upper._walkable_components()
        self.assertTrue(any(landing in comp for comp in comps),
                        "landing missing from any walkable component")
        self.assertEqual(len(comps), 1, "upper floor should be fully connected")

    def test_flight_cells_span_the_whole_stair_run(self):
        """flight_cells must cover every cell of the flight (not just the
        landing) -- that's what lets fromBuilding open the floor above across
        the whole climb, not just its top step."""
        random.seed(4)
        stair_length = 3
        b = Building(11, 11).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                      floor2_area_threshold=20, stair_length=stair_length)
        self.assertEqual(len(b.floors), 2, "test needs floor2 to be generated")
        link = b.stair_links[0]
        self.assertEqual(len(link['flight_cells']), stair_length)
        self.assertIn(link['landing'], link['flight_cells'])

    def test_landing_across_many_seeds_and_shapes(self):
        """Stress test across every shape/seed. Checks the landing
        specifically -- not "the whole upper floor is one component", which
        is a stronger property than what's guaranteed elsewhere in the
        pipeline: a corridor cell whose only in-footprint neighbour happens
        to be a lustral basin (excluded from the walkable graph by design,
        same as light shafts, so it can become a rare isolated 1-cell
        pocket) is a known, acceptable edge case unrelated to the landing --
        see test_shafts_basins.py for the analogous, explicitly-handled
        light-shaft case."""
        n_with_floor2 = 0
        for shape in Maze._SHAPES:
            for seed in range(10):
                with self.subTest(shape=shape, seed=seed):
                    random.seed(seed)
                    b = Building(11, 13).generate(shape=shape, entrance_sides=('s', 'e'),
                                                  floor2_area_threshold=25, stair_length=3)
                    if len(b.floors) < 2:
                        continue
                    n_with_floor2 += 1
                    ground, upper = b.floors
                    landing = b.stair_links[0]['landing']
                    self.assertNotEqual(upper.rooms[landing[0]][landing[1]], 0,
                                        "landing carved away")
                    comps = upper._walkable_components()
                    landing_comp = next((c for c in comps if landing in c), None)
                    self.assertIsNotNone(landing_comp, "landing missing from any component")
                    self.assertGreaterEqual(len(landing_comp), upper.footprint_area() // 2,
                                            f"landing stranded in a tiny component ({len(landing_comp)} cells)")
        self.assertGreater(n_with_floor2, 0, "no seed produced a 2nd floor -- test is vacuous")

    def test_voxel_landing_hole_and_treads(self):
        """At the voxel level: the landing column has no floor-slab voxel at
        the floor-2 level (the hole the stairs rise into), but does have
        tread voxels immediately below it."""
        random.seed(4)
        b = Building(11, 11).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                      floor2_area_threshold=20, stair_length=3)
        self.assertEqual(len(b.floors), 2, "test needs floor2 to be generated")
        room_size, wall_thickness, wall_height, floor_thickness = 6, 2, 8, 2
        floor_span = floor_thickness + wall_height
        cell_size = room_size + wall_thickness

        g = PositionGrid(11, 11, floor_span * 2)
        g.fromBuilding(b, room_size=room_size, wall_thickness=wall_thickness,
                       wall_height=wall_height, floor_thickness=floor_thickness)

        row, col = b.stair_links[0]['landing']
        probe_x = row * cell_size + wall_thickness + 1
        probe_y = col * cell_size + wall_thickness + 1

        hole_z = floor_span   # floor-2's own slab level
        self.assertNotIn((probe_x, probe_y, hole_z), g.all_occupied_positions,
                         "landing column should have no floor-2 slab voxel (the hole)")
        tread_below = any((probe_x, probe_y, z) in g.all_occupied_positions
                          for z in range(hole_z - 3, hole_z))
        self.assertTrue(tread_below, "expected stair tread voxels immediately below the landing hole")


class TestGroundFloorThickness(unittest.TestCase):
    def test_ground_floor_thickness_independent_of_upper(self):
        """ground_floor_thickness only affects the ground floor's own slab
        and where floor 2 starts; floor 2's own slab and the roof cap keep
        using the regular floor_thickness."""
        random.seed(4)
        b = Building(11, 11).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                      floor2_area_threshold=20, stair_length=3,
                                      place_shafts=False, place_basins=False)
        self.assertEqual(len(b.floors), 2, "test needs floor2 to be generated")
        ground, upper = b.floors
        room_size, wall_thickness, wall_height = 6, 2, 8
        floor_thickness, ground_floor_thickness = 3, 7   # deliberately different

        g = PositionGrid(11, 11, 60)
        g.fromBuilding(b, room_size=room_size, wall_thickness=wall_thickness,
                       wall_height=wall_height, floor_thickness=floor_thickness,
                       ground_floor_thickness=ground_floor_thickness)

        cell_size = room_size + wall_thickness
        # An interior wall cell present on both floors: continuous from z=0 up
        # through both floors, with floor 2 starting exactly at
        # ground_floor_thickness + wall_height (not floor_thickness + wall_height).
        row, col = next((r, c) for r in range(upper.num_rows) for c in range(upper.num_cols)
                        if upper.rooms[r][c] != 0 and c + 1 < upper.num_cols
                        and upper.get_wall(r, c, 'e') == 'wall')
        x = row * cell_size + 1
        y = (col + 1) * cell_size + 1
        zs = sorted(z for (xx, yy, z) in g.all_occupied_positions if xx == x and yy == y)
        floor2_start = ground_floor_thickness + wall_height
        self.assertTrue(zs and zs[0] == 0 and all(zs[i + 1] - zs[i] == 1 for i in range(len(zs) - 1)),
                        f"expected a continuous wall column, got {zs}")
        self.assertIn(floor2_start, zs,
                     f"floor 2 should start exactly at ground_floor_thickness+wall_height={floor2_start}")


if __name__ == "__main__":
    unittest.main()
