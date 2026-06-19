import unittest
from maze import Maze

class TestExpandRoom(unittest.TestCase):
    def test_expand_north_center_single_width(self):
        m = Maze(7,7)
        # all cells start as 1
        bbox = m.expand_room(center_row=4, center_col=3, width=1, direction='n', max_size=3, id=5)
        # expect rows 2..4, column 3..3
        self.assertEqual(bbox, (2, 4, 3, 3))
        self.assertEqual(m.rooms[4][3], 5)
        self.assertEqual(m.rooms[3][3], 5)
        self.assertEqual(m.rooms[2][3], 5)

    def test_expand_east_even_width(self):
        m = Maze(5,5)
        # choose center_row such that two rows (2,3) are used for width=2
        bbox = m.expand_room(center_row=3, center_col=1, width=2, direction='e', max_size=2, id=7)
        # expect columns 1..2, rows 2..3
        self.assertEqual(bbox, (2, 3, 1, 2))
        self.assertEqual(m.rooms[2][1], 7)
        self.assertEqual(m.rooms[3][1], 7)
        self.assertEqual(m.rooms[2][2], 7)
        self.assertEqual(m.rooms[3][2], 7)

    def test_stop_on_non1(self):
        m = Maze(5,5)
        # place a blocker below the center
        m.rooms[3][2] = 0
        bbox = m.expand_room(center_row=2, center_col=2, width=1, direction='s', max_size=5, id=9)
        # only center cell placed -> rows 2..2, cols 2..2
        self.assertEqual(bbox, (2, 2, 2, 2))
        self.assertEqual(m.rooms[2][2], 9)
        self.assertNotEqual(m.rooms[3][2], 9)

    def test_stop_on_edge(self):
        m = Maze(3,4)
        # expand west from column 1 with max_size large -> should stop at column 0
        bbox = m.expand_room(center_row=1, center_col=1, width=1, direction='w', max_size=5, id=6)
        # should place at columns 0..1, row 1
        self.assertEqual(bbox, (1, 1, 0, 1))
        self.assertEqual(m.rooms[1][1], 6)
        self.assertEqual(m.rooms[1][0], 6)

    def test_invalid_width_and_direction(self):
        m = Maze(4,4)
        self.assertEqual(m.expand_room(1,1,0,'n',3,2), 0)
        self.assertEqual(m.expand_room(1,1,1,'x',3,2), 0)

if __name__ == '__main__':
    unittest.main()
