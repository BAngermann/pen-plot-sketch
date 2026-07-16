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

    def test_no_redundant_door_pairs(self):
        # High door_probability to make a redundant pair likely if the guard
        # weren't there. For every room, every pair of its own doors must be
        # "genuinely useful" together: either there's no route around the
        # room at all, or going around is at least _DOOR_USEFULNESS_MARGIN
        # tiles longer than cutting straight through it (see
        # _is_redundant_door_pair) -- otherwise the second door is just a
        # redundant hole (this subsumes and replaces the older, narrower
        # "two doors must never meet at a corner" rule: a corner with no
        # solid wall material was one symptom of a redundant pair, but a
        # pair on opposite sides of a room with a short way around is
        # another, and a corner pair with a genuinely long way around is
        # perfectly fine).
        for shape in _SHAPES:
            for seed in range(10):
                with self.subTest(shape=shape, seed=seed):
                    random.seed(seed)
                    m = Maze(9, 9)
                    m.gen_rooms(shape=shape, entrance_sides=('s', 'e'), door_probability=0.9)
                    groups = {m._room_group(r, c) for r in range(m.num_rows) for c in range(m.num_cols)
                             if m._is_walkable_state(m.rooms[r][c])}
                    for group in groups:
                        doors = m._doors_touching_group(group)
                        for i in range(len(doors)):
                            for j in range(i + 1, len(doors)):
                                cell_a, ext_group_a, ext_cell_a = doors[i]
                                cell_b, ext_group_b, ext_cell_b = doors[j]
                                with self.subTest(group=group, a=doors[i], b=doors[j]):
                                    self.assertFalse(
                                        m._is_redundant_door_pair(group, cell_a, ext_group_a, ext_cell_a,
                                                                  cell_b, ext_group_b, ext_cell_b),
                                        f"redundant door pair on room {group}: {doors[i]} / {doors[j]}")

    def test_no_avoidable_unanchored_colinear_conflicts(self):
        """A door should never sit right next to open air, or another door,
        continuing the same straight wall run *with no perpendicular wall
        anchoring the corner they share* (see _touches_colinear_air /
        _touches_colinear_door). Most commonly: a plain corridor tile's door
        into a room, with the corridor's own sidewinder-carved passage
        continuing as air along the very same unbroken wall; or two doors
        placed back to back with no wall material between them at all. A
        colinear neighbor where the shared corner *is* anchored by a
        perpendicular wall is a different, unrelated wall run meeting at a
        real corner pillar (e.g. a room's own doorway sitting beside an
        unrelated corridor passage, or a second unrelated doorway, one
        row/column over, separated by a real wall) -- not a problem, and not
        what this test checks; only the two _touches_colinear_* checks'
        actual verdicts matter here. ensure_connectivity/_add_extra_doors
        avoid the unanchored case whenever an alternative exists; the only
        acceptable exception is a door that's the sole remaining connector
        for its part of the maze (verified here directly: removing it must
        disconnect the graph), matching the same "connectivity always wins"
        carve-out as the redundant-door-pair rule above."""
        for shape in _SHAPES:
            for seed in range(15):
                with self.subTest(shape=shape, seed=seed):
                    random.seed(seed)
                    m = Maze(9, 9)
                    m.gen_rooms(shape=shape, entrance_sides=('s', 'e'), door_probability=0.5)
                    for row in range(m.num_rows):
                        for col in range(m.num_cols):
                            for d in 'nesw':
                                if m.get_wall(row, col, d) != 'door':
                                    continue
                                if not (m._touches_colinear_air(row, col, d)
                                       or m._touches_colinear_door(row, col, d)):
                                    continue
                                with self.subTest(row=row, col=col, d=d):
                                    m.set_wall(row, col, d, 'wall')
                                    still_connected = len(m._walkable_components()) == 1
                                    m.set_wall(row, col, d, 'door')
                                    self.assertFalse(still_connected,
                                                     "avoidable unanchored colinear conflict")

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
