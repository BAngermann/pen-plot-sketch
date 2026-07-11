"""Stage 1 checks: building-shape carving + south/east-only entrance facing.

Run: ``python -m unittest`` from floorplan/ (or ``python -m unittest
tests.test_shapes``); no deps beyond maze.py itself.
"""
import pathlib
import random
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from maze import Maze

_SHAPES = Maze._SHAPES
_SEEDS = range(20)


class TestShapeGeneration(unittest.TestCase):
    def test_all_shapes_face_south_or_east(self):
        for shape in _SHAPES:
            for seed in _SEEDS:
                with self.subTest(shape=shape, seed=seed):
                    random.seed(seed)
                    m = Maze(9, 9)
                    entrance = m.make_foundation(shape=shape, entrance_sides=('s', 'e'))
                    self.assertIsNotNone(entrance, "no entrance placed")
                    _row, _col, facing = entrance
                    self.assertIn(facing, ('s', 'e'))

    def test_random_shape_dispatches_to_a_real_shape(self):
        random.seed(0)
        m = Maze(9, 9)
        entrance = m.make_foundation(shape="random", entrance_sides=('s', 'e'))
        self.assertIsNotNone(entrance)

    def test_rectangular_has_no_cutout(self):
        random.seed(0)
        m = Maze(9, 9)
        m.make_foundation(shape="rectangular", entrance_sides=('s', 'e'))
        footprint = sum(1 for row in m.rooms for v in row if v != 0)
        self.assertEqual(footprint, 9 * 9)

    def test_courtyard_has_interior_hole(self):
        random.seed(1)
        m = Maze(9, 9)
        m.make_foundation(shape="courtyard", entrance_sides=('s', 'e'))
        footprint = sum(1 for row in m.rooms for v in row if v != 0)
        self.assertLess(footprint, 9 * 9, "courtyard should cut an interior hole")

    def test_gen_rooms_with_shape_still_smoke_tests(self):
        random.seed(7)
        m = Maze(9, 9)
        m.gen_rooms(shape="l_shape", entrance_sides=('s', 'e'))
        self.assertTrue(any(v == 2 for row in m.rooms for v in row), "no room placed")


if __name__ == "__main__":
    unittest.main()
