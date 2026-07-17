"""Stage 6 checks: terrace_cells/parapet_boundaries geometry, and end-to-end
roof cap / roof-access modes at the voxel level.

Run: ``python -m unittest`` from floorplan/ (or ``python -m unittest
tests.test_roof``); needs numpy for the voxel-level checks.
"""
import pathlib
import random
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from maze import Building, Maze
from voxels import PositionGrid


class TestTerraceGeometry(unittest.TestCase):
    def test_terrace_cells_full_footprint_without_upper(self):
        m = Maze(3, 3)
        m.rooms = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]
        self.assertEqual(m.terrace_cells(None), m.footprint_cells())

    def test_terrace_cells_is_the_uncovered_part(self):
        ground = Maze(3, 3)
        ground.rooms = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]
        upper = Maze(3, 3)
        upper.rooms = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]   # only the centre cell covered
        terrace = ground.terrace_cells(upper)
        expected = {(0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1), (2, 2)}   # everything but centre
        self.assertEqual(terrace, expected)

    def test_parapet_boundaries_hand_built(self):
        """A 3x3 ground floor fully covered except the upper floor only
        occupies the centre cell -- the terrace ring should get a parapet on
        every edge facing true exterior or the maze boundary, but NOT on the
        4 edges facing the upper floor's own centre-cell footprint."""
        ground = Maze(3, 3)
        ground.rooms = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]
        upper = Maze(3, 3)
        upper.rooms = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
        terrace = ground.terrace_cells(upper)
        boundaries = set(ground.parapet_boundaries(upper, terrace))

        # Every terrace cell bordering the maze edge should get a parapet there.
        self.assertIn((0, 0, 'n'), boundaries)
        self.assertIn((0, 0, 'w'), boundaries)
        self.assertIn((2, 2, 's'), boundaries)
        self.assertIn((2, 2, 'e'), boundaries)
        # The 4 terrace cells directly adjacent to the upper floor's centre
        # cell must NOT get a parapet on the side facing it (already walled
        # by the upper floor's own exterior wall).
        self.assertNotIn((0, 1, 's'), boundaries, "should not parapet the side facing the upper floor")
        self.assertNotIn((1, 0, 'e'), boundaries)
        self.assertNotIn((1, 2, 'w'), boundaries)
        self.assertNotIn((2, 1, 'n'), boundaries)


class TestParapetVoxels(unittest.TestCase):
    def test_parapet_is_flush_with_the_wall_below_no_gap(self):
        """Regression test: the parapet used to start at terrace_level +
        roof_thickness (i.e. above the roof cap), but the roof cap never
        fills the outer boundary strip (only cell interiors + inter-cell
        seams -- that strip is normally covered by a full wall instead).
        That left a real gap of `roof_thickness` empty voxels between the
        top of the ground floor's own wall and the bottom of the parapet,
        making the upper structure look like it was floating a few voxels
        above the walls below it."""
        random.seed(4)
        b = Building(11, 11).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                      floor2_area_threshold=20, stair_length=3,
                                      place_shafts=False, place_basins=False)
        self.assertEqual(len(b.floors), 2, "test needs floor2 to be generated")
        ground, upper = b.floors
        room_size, wall_thickness, wall_height, floor_thickness = 6, 2, 8, 3
        floor_span = floor_thickness + wall_height
        parapet_height = 3

        g = PositionGrid(11, 11, floor_span * 2)
        g.fromBuilding(b, room_size=room_size, wall_thickness=wall_thickness,
                       wall_height=wall_height, floor_thickness=floor_thickness,
                       parapet_height=parapet_height)

        cell_size = room_size + wall_thickness
        terrace = ground.terrace_cells(upper)
        checked = 0
        for (row, col, d) in ground.parapet_boundaries(upper, terrace):
            # Skip any boundary that coincides with the building's own
            # entrance opening (a real doorway is legitimately open all the
            # way up).
            if ground.get_wall(row, col, d) == 'air':
                continue
            if d == 'n':
                x, y = row * cell_size, col * cell_size
            elif d == 's':
                x, y = (row + 1) * cell_size, col * cell_size
            elif d == 'w':
                x, y = row * cell_size, col * cell_size
            else:
                x, y = row * cell_size, (col + 1) * cell_size
            top_expected = floor_span + floor_thickness + parapet_height - 1
            zs = sorted(z for (xx, yy, z) in g.all_occupied_positions if xx == x and yy == y)
            with self.subTest(boundary=(row, col, d), column=(x, y)):
                self.assertTrue(zs and zs[0] == 0 and zs[-1] >= top_expected
                                and all(zs[i + 1] - zs[i] == 1 for i in range(len(zs) - 1)),
                                f"gap: {zs}")
            checked += 1
        self.assertGreater(checked, 0, "test found no non-entrance parapet boundaries to check")


class TestRoofAccessModes(unittest.TestCase):
    def test_roof_access_none_gives_a_solid_cap(self):
        # Disable light shafts here: they're always excluded from the cap by
        # design (open to the sky, independent of roof_access) -- this test
        # is specifically about roof_access="none" leaving no *other* opening.
        random.seed(2)
        b = Building(9, 9).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                    floor2_area_threshold=10**9, roof_access="none",
                                    place_shafts=False)
        self.assertEqual(len(b.floors), 1)
        self.assertFalse(b.roof_open_cells)
        room_size, wall_thickness, wall_height, floor_thickness = 6, 2, 8, 2
        g = PositionGrid(9, 9, floor_thickness + wall_height)
        g.fromBuilding(b, room_size=room_size, wall_thickness=wall_thickness,
                       wall_height=wall_height, floor_thickness=floor_thickness)
        roof_level = floor_thickness + wall_height
        top = b.floors[0]
        cell_size = room_size + wall_thickness
        n_capped = sum(1 for (r, c) in top.footprint_cells()
                      if (r * cell_size + wall_thickness + 1, c * cell_size + wall_thickness + 1, roof_level)
                      in g.all_occupied_positions)
        self.assertEqual(n_capped, len(top.footprint_cells()),
                         "roof_access=none should cap every footprint cell")

    def test_roof_access_hatch_leaves_exactly_one_open_column(self):
        # Disable shafts: they're also excluded from the cap independent of
        # roof_access, which would otherwise add extra open columns beyond
        # the hatch this test is specifically checking for.
        random.seed(2)
        b = Building(9, 9).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                    floor2_area_threshold=10**9, roof_access="hatch",
                                    place_shafts=False)
        self.assertEqual(len(b.roof_open_cells), 1, b.roof_open_cells)
        room_size, wall_thickness, wall_height, floor_thickness = 6, 2, 8, 2
        g = PositionGrid(9, 9, floor_thickness + wall_height)
        g.fromBuilding(b, room_size=room_size, wall_thickness=wall_thickness,
                       wall_height=wall_height, floor_thickness=floor_thickness)
        roof_level = floor_thickness + wall_height
        cell_size = room_size + wall_thickness
        top = b.floors[0]
        open_cells = [(r, c) for (r, c) in top.footprint_cells()
                     if (r * cell_size + wall_thickness + 1, c * cell_size + wall_thickness + 1, roof_level)
                     not in g.all_occupied_positions]
        self.assertEqual(set(open_cells), b.roof_open_cells)

    def test_roof_access_hatch_spans_a_multi_cell_block_when_requested(self):
        # A single maze cell is only room_size voxels wide, which can be tiny
        # at small room_size -- roof_hatch_cells lets the hatch span a solid
        # block of cells instead, so the opening has a real minimum size
        # independent of room_size.
        random.seed(2)
        b = Building(9, 9).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                    floor2_area_threshold=10**9, roof_access="hatch",
                                    roof_hatch_cells=3, place_shafts=False)
        self.assertGreater(len(b.roof_open_cells), 1, b.roof_open_cells)
        rows = {r for r, _c in b.roof_open_cells}
        cols = {c for _r, c in b.roof_open_cells}
        self.assertEqual(len(b.roof_open_cells), len(rows) * len(cols),
                         "hatch cells should form a solid rectangular block, not scattered cells")

    def test_roof_access_hatch_shrinks_block_to_fit_a_small_footprint(self):
        # Requesting a block bigger than the whole floor must not crash or
        # leave roof_open_cells empty -- it should shrink down to whatever fits.
        random.seed(2)
        b = Building(9, 9).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                    floor2_area_threshold=10**9, roof_access="hatch",
                                    roof_hatch_cells=99, place_shafts=False)
        self.assertTrue(b.roof_open_cells, "hatch should still place something on an oversized request")

    def test_roof_access_stairs_rise_into_the_opening(self):
        # Try a few seeds since "stairs" mode can fall back to "hatch" if no
        # straight run fits; we want a seed where the stairs path is
        # actually taken.
        for seed in range(20):
            random.seed(seed)
            b = Building(9, 9).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                        floor2_area_threshold=10**9, roof_access="stairs")
            if b.roof_stair_state is not None:
                break
        else:
            self.fail("no seed produced a roof stairway to test")

        room_size, wall_thickness, wall_height, floor_thickness = 6, 2, 3, 2
        roof_level = floor_thickness + wall_height

        g_stairs = PositionGrid(9, 9, roof_level * 2)
        g_stairs.fromBuilding(b, room_size=room_size, wall_thickness=wall_thickness,
                              wall_height=wall_height, floor_thickness=floor_thickness)
        max_z_stairs = max(z for (_x, _y, z) in g_stairs.all_occupied_positions)

        # Same maze, same seed's generated layout, but roof-sealed: rebuild
        # via roof_access="none" would be a different generation, so instead
        # directly re-cap the SAME building/maze as a solid roof for a fair
        # like-for-like comparison of "does the stairway rise past the
        # sealed roof line".
        b_sealed = Building(9, 9)
        b_sealed.floors = b.floors
        b_sealed.roof_floor_index = b.roof_floor_index
        b_sealed.roof_open_cells = set()
        b_sealed.roof_stair_state = None   # no break-through -> flight capped at the normal ceiling
        g_sealed = PositionGrid(9, 9, roof_level * 2)
        g_sealed.fromBuilding(b_sealed, room_size=room_size, wall_thickness=wall_thickness,
                              wall_height=wall_height, floor_thickness=floor_thickness)
        max_z_sealed = max(z for (_x, _y, z) in g_sealed.all_occupied_positions)

        self.assertGreater(max_z_stairs, max_z_sealed,
                           "roof stairway should rise above a sealed roof")


class TestInterFloorStairHeadroom(unittest.TestCase):
    def test_whole_flight_is_open_above_not_just_the_landing(self):
        """A flat slab at a fixed height above a rising staircase gives
        shrinking headroom over the run -- the floor above must be opened
        across the entire flight, not just its top step, so clearance stays
        a full room height throughout the climb."""
        random.seed(4)
        stair_length = 3
        b = Building(11, 11).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                      floor2_area_threshold=20, stair_length=stair_length)
        self.assertEqual(len(b.floors), 2, "test needs floor2 to be generated")
        link = b.stair_links[0]
        self.assertEqual(len(link['flight_cells']), stair_length,
                         "test needs a multi-cell flight to be meaningful")

        room_size, wall_thickness, wall_height, floor_thickness = 6, 2, 8, 3
        g = PositionGrid(11, 11, wall_height)
        g.fromBuilding(b, room_size=room_size, wall_thickness=wall_thickness,
                       wall_height=wall_height, floor_thickness=floor_thickness)

        cell_size = room_size + wall_thickness
        floor1_ceiling_z = floor_thickness + wall_height
        for (row, col) in link['flight_cells']:
            cx = row * cell_size + wall_thickness + room_size // 2
            cy = col * cell_size + wall_thickness + room_size // 2
            with self.subTest(cell=(row, col)):
                self.assertNotIn((cx, cy, floor1_ceiling_z), g.all_occupied_positions,
                                 "floor above must be open over the whole flight, not just the landing")

    def test_flight_is_capped_at_the_roof_not_open_to_the_sky(self):
        """Regression test: the stair flight's non-landing cells are excluded
        from floor2's own footprint entirely (for headroom -- see the test
        above), which used to also drop them out of the roof cap, leaving
        the stairwell open all the way from the ground floor through the
        roof to the sky instead of being closed off at floor2's own ceiling
        like any other floor2 space."""
        random.seed(4)
        stair_length = 3
        b = Building(11, 11).generate(shape="rectangular", entrance_sides=('s', 'e'),
                                      floor2_area_threshold=20, stair_length=stair_length)
        self.assertEqual(len(b.floors), 2, "test needs floor2 to be generated")
        link = b.stair_links[0]

        room_size, wall_thickness, wall_height, floor_thickness = 6, 2, 8, 3
        g = PositionGrid(11, 11, wall_height)
        g.fromBuilding(b, room_size=room_size, wall_thickness=wall_thickness,
                       wall_height=wall_height, floor_thickness=floor_thickness)

        cell_size = room_size + wall_thickness
        roof_level = 2 * (floor_thickness + wall_height)
        for (row, col) in link['flight_cells']:
            cx = row * cell_size + wall_thickness + room_size // 2
            cy = col * cell_size + wall_thickness + room_size // 2
            with self.subTest(cell=(row, col)):
                self.assertIn((cx, cy, roof_level), g.all_occupied_positions,
                             "the stair shaft must be capped at the roof, not left open to the sky")


if __name__ == "__main__":
    unittest.main()
