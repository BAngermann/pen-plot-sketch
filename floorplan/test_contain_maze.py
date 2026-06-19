import unittest
from maze import Maze

class TestContainMaze(unittest.TestCase):
    def setUp(self):
        # Helper to check boundaries
        self.wall = 'wall'
        self.air = 'air'

    def check_horizontal(self, maze, row, col, expected):
        self.assertEqual(maze.horizontal_boundaries[row][col].boundary_type, expected)

    def check_vertical(self, maze, row, col, expected):
        self.assertEqual(maze.vertical_boundaries[row][col].boundary_type, expected)

    def test_single_cell_center(self):
        maze = Maze(3, 3)
        maze.rooms = [[0,0,0],[0,1,0],[0,0,0]]
        maze.contain_maze()
        # All boundaries around center cell should be walls
        self.check_horizontal(maze, 1, 1, self.wall) # top
        self.check_horizontal(maze, 2, 1, self.wall) # bottom
        self.check_vertical(maze, 1, 1, self.wall)   # left
        self.check_vertical(maze, 1, 2, self.wall)   # right

    def test_single_cell_at_boundary(self):
        maze = Maze(2, 2)
        maze.rooms = [[1,0],[0,0]]
        maze.contain_maze()
        # Top left cell at boundary
        self.check_horizontal(maze, 0, 0, self.wall) # top
        self.check_horizontal(maze, 1, 0, self.wall) # bottom
        self.check_vertical(maze, 0, 0, self.wall)   # left
        self.check_vertical(maze, 0, 1, self.wall)   # right

    def test_row_of_cells_not_at_boundary(self):
        maze = Maze(3, 5)
        maze.rooms = [
            [0,0,0,0,0],
            [0,1,1,1,0],
            [0,0,0,0,0]
        ]
        maze.contain_maze()
        # Check leftmost cell
        self.check_vertical(maze, 1, 1, self.wall)
        self.check_horizontal(maze, 1, 1, self.wall)
        # Check rightmost cell
        self.check_vertical(maze, 1, 4, self.wall)
        self.check_horizontal(maze, 2, 3, self.wall)
        # Check middle cell
        self.check_horizontal(maze, 1, 2, self.wall)
        self.check_vertical(maze, 1, 2, self.air)

    def test_column_of_cells_at_boundary(self):
        maze = Maze(4, 3)
        maze.rooms = [
            [1,0,0],
            [1,0,0],
            [1,0,0],
            [0,0,0]
        ]
        maze.contain_maze()
        # Check top cell
        self.check_horizontal(maze, 0, 0, self.wall)
        # Check bottom cell
        self.check_horizontal(maze, 3, 0, self.wall)
        # Check left boundary for all
        for r in range(3):
            self.check_vertical(maze, r, 0, self.wall)

    def test_large_maze_various_positions(self):
        maze = Maze(5, 5)
        maze.rooms = [
            [0,0,0,0,0],
            [0,1,1,0,0],
            [0,1,0,1,0],
            [0,0,1,1,0],
            [0,0,0,0,0]
        ]
        maze.contain_maze()
        # Check some boundaries for non-boundary and boundary cells
        self.check_horizontal(maze, 2, 1, self.air) # cell (2,1) top
        self.check_vertical(maze, 2, 2, self.wall)   # cell (2,2) right
        self.check_horizontal(maze, 3, 2, self.wall) # cell (3,2) bottom
        self.check_vertical(maze, 1, 1, self.wall)   # cell (1,1) left

if __name__ == "__main__":
    unittest.main()
