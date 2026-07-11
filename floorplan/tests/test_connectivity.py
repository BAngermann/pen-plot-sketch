"""Stage 2 checks: room/corridor mixing, doors, guaranteed reachability.

Run: ``python -m unittest`` from floorplan/ (or ``python -m unittest
tests.test_connectivity``); no deps beyond maze.py.
"""
import pathlib
import random
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from maze import Maze

_SHAPES = Maze._SHAPES
_SEEDS = range(15)


class TestConnectivity(unittest.TestCase):
    def test_fully_connected_across_shapes_and_seeds(self):
        # Rooms/corridors/doors only -- shafts (Stage 3) can rarely form a pinch
        # point that the walkable-cell graph can't reflect as "1 component" even
        # after the fallback fixes real physical connectivity through the shaft
        # (see test_shafts_basins.py); keep this test scoped to what Stage 2 owns.
        for shape in _SHAPES:
            for seed in _SEEDS:
                with self.subTest(shape=shape, seed=seed):
                    random.seed(seed)
                    m = Maze(9, 9)
                    m.gen_rooms(shape=shape, entrance_sides=('s', 'e'),
                               place_shafts=False, place_basins=False)
                    comps = m._walkable_components()
                    self.assertEqual(len(comps), 1, f"{len(comps)} disconnected components")

    def test_multiple_rooms_placed(self):
        random.seed(3)
        m = Maze(11, 11)
        m.gen_rooms(shape="rectangular", entrance_sides=('s', 'e'))
        ids = {v for row in m.rooms for v in row if 2 <= v <= 8}
        self.assertGreaterEqual(len(ids), 2, f"expected multiple rooms, got ids={ids}")

    def test_sidewinder_fills_remaining_cells(self):
        random.seed(5)
        m = Maze(11, 11)
        m.gen_rooms(shape="rectangular", entrance_sides=('s', 'e'), max_explicit_rooms=2)
        # After explicit rooms + sidewinder, some cells remain plain corridor
        # (state 1) -- sidewinder carves boundaries but doesn't reassign state.
        unassigned = sum(1 for row in m.rooms for v in row if v == 1)
        self.assertGreater(unassigned, 0, "sidewinder should leave plain corridor cells as state 1")

    def test_doors_are_liberal_not_just_minimum(self):
        random.seed(9)
        m = Maze(11, 11)
        m.gen_rooms(shape="rectangular", entrance_sides=('s', 'e'), door_probability=0.5)
        door_count = sum(1 for row in m.horizontal_boundaries for b in row if b.boundary_type == 'door')
        door_count += sum(1 for row in m.vertical_boundaries for b in row if b.boundary_type == 'door')
        self.assertGreater(door_count, 3, "expected liberal doors with door_probability=0.5")

    def test_sidewinder_rng_does_not_clobber_global_state(self):
        random.seed(123)
        before = random.random()
        random.seed(123)
        m = Maze(6, 6)
        m.sidewinder(1, rng=random.Random(999))   # independent Random instance
        after_first = random.random()
        random.seed(123)
        after_reseed = random.random()
        self.assertEqual(after_first, before)
        self.assertEqual(after_reseed, before,
                         "sidewinder must not reseed/consume the global random module's state")

    def test_gen_rooms_zero_args_still_works(self):
        random.seed(1)
        m = Maze(8, 8)
        m.gen_rooms()   # today's only call pattern -- must still work with all defaults
        self.assertEqual(len(m._walkable_components()), 1)


if __name__ == "__main__":
    unittest.main()
