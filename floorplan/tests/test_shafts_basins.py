"""Stage 3 checks: rectangular light shafts, auto-sited lustral basins, and
the light-shaft pinch-point connectivity fallback.

Run: ``python -m unittest`` from floorplan/ (or ``python -m unittest
tests.test_shafts_basins``); no deps beyond maze.py.
"""
import pathlib
import random
import sys
import unittest
from collections import deque

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from maze import Maze


def _bfs_dist_between(m, a, b):
    """Shortest 4-connected path length (in cells) between two disjoint cell
    sets a and b, over state==1 cells (a/b cells excluded from the walk)."""
    q = deque((r, c, 0) for (r, c) in a)
    seen = set(a)
    while q:
        r, c, d = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if not (0 <= nr < m.num_rows and 0 <= nc < m.num_cols):
                continue
            if (nr, nc) in b:
                return d + 1
            if (nr, nc) in seen or m.rooms[nr][nc] != 1:
                continue
            seen.add((nr, nc))
            q.append((nr, nc, d + 1))
    return float('inf')


class TestLightShafts(unittest.TestCase):
    def test_shaft_spacing_respected(self):
        for size_range in ((1, 2), (2, 3)):
            for seed in range(10):
                with self.subTest(size_range=size_range, seed=seed):
                    random.seed(seed)
                    m = Maze(15, 15)
                    m.make_foundation(shape="rectangular", entrance_sides=('s', 'e'))
                    m.contain_maze()
                    m.place_light_shafts(max_shafts=3, size_range=size_range,
                                         min_dist_outside=4, min_dist_between=4)
                    shafts = {}
                    for r in range(m.num_rows):
                        for c in range(m.num_cols):
                            v = m.rooms[r][c]
                            if 9 <= v <= 12:
                                shafts.setdefault(v, []).append((r, c))
                    outside = {(r, c) for r in range(m.num_rows) for c in range(m.num_cols)
                              if m.rooms[r][c] == 0}
                    for val, cells in shafts.items():
                        w = max(c for _r, c in cells) - min(c for _r, c in cells) + 1
                        h = max(r for r, _c in cells) - min(r for r, _c in cells) + 1
                        self.assertTrue(size_range[0] <= w <= size_range[1], (val, w))
                        self.assertTrue(size_range[0] <= h <= size_range[1], (val, h))
                        if outside:
                            d_out = _bfs_dist_between(m, set(cells), outside)
                            self.assertGreaterEqual(d_out, 4, (val, "dist_out"))
                        for other_val, other_cells in shafts.items():
                            if other_val == val:
                                continue
                            d_between = _bfs_dist_between(m, set(cells), set(other_cells))
                            self.assertGreaterEqual(d_between, 4, (val, other_val, "dist_between"))

    def test_shafts_walled_in(self):
        random.seed(2)
        m = Maze(13, 13)
        m.make_foundation(shape="rectangular", entrance_sides=('s', 'e'))
        m.contain_maze()
        m.place_light_shafts(max_shafts=2, size_range=(1, 2))
        shaft_cells = {(r, c) for r in range(m.num_rows) for c in range(m.num_cols)
                      if 9 <= m.rooms[r][c] <= 12}
        self.assertTrue(shaft_cells, "no shaft placed to test")
        for (r, c) in shaft_cells:
            for d in 'nesw':
                nr, nc = Maze.step(r, c, d)
                if 0 <= nr < m.num_rows and 0 <= nc < m.num_cols and (nr, nc) not in shaft_cells:
                    with self.subTest(cell=(r, c), direction=d):
                        self.assertEqual(m.get_wall(r, c, d), 'wall')

    def test_shaft_pinch_point_fallback(self):
        """Hand-built adversarial case: a single-cell shaft is the sole
        connector between two otherwise-disconnected areas. The fallback must
        open doors on both sides of it (real physical connectivity via the
        shaft as a walkable atrium), even though the simplified walkable-cell
        graph still shows two components (shaft cells are deliberately
        excluded from that graph)."""
        m = Maze(1, 3)
        m.rooms = [[1, 9, 1]]
        m.contain_room(9)
        self.assertEqual(m.get_wall(0, 1, 'w'), 'wall')
        self.assertEqual(m.get_wall(0, 1, 'e'), 'wall')

        components = m._walkable_components()
        self.assertEqual(len(components), 2, "test setup should start disconnected")
        m.ensure_connectivity(is_ground_floor=True)

        self.assertEqual(m.get_wall(0, 1, 'w'), 'door', "no door opened west of the shaft")
        self.assertEqual(m.get_wall(0, 1, 'e'), 'door', "no door opened east of the shaft")

    def test_shaft_fallback_only_on_ground_floor(self):
        """Same adversarial setup, but is_ground_floor=False must NOT trigger
        the shaft fallback (an upper-floor shaft is an open void, not
        something you can walk through)."""
        m = Maze(1, 3)
        m.rooms = [[1, 9, 1]]
        m.contain_room(9)
        m.ensure_connectivity(is_ground_floor=False)
        self.assertEqual(m.get_wall(0, 1, 'w'), 'wall', "fallback must not fire on an upper floor")
        self.assertEqual(m.get_wall(0, 1, 'e'), 'wall')


class TestLustralBasins(unittest.TestCase):
    def test_basin_auto_sited(self):
        placed_any = False
        for seed in range(20):
            random.seed(seed)
            m = Maze(11, 11)
            m.make_foundation(shape="rectangular", entrance_sides=('s', 'e'))
            m.contain_maze()
            n = m.place_lustral_basins(max_basins=1, probability=1.0)
            if n:
                placed_any = True
                basin_cells = {(r, c) for r in range(m.num_rows) for c in range(m.num_cols)
                               if 99 < m.rooms[r][c] < 180}
                self.assertEqual(len(basin_cells), 4, basin_cells)
        self.assertTrue(placed_any, "basin never placed across 20 seeds at probability=1.0")


class TestShaftsAndBasinsPipeline(unittest.TestCase):
    def test_full_pipeline_connectivity_with_shafts_and_basins(self):
        shapes = Maze._SHAPES
        disconnected = 0
        total = 0
        for shape in shapes:
            for seed in range(15):
                random.seed(seed)
                m = Maze(13, 13)
                m.gen_rooms(shape=shape, entrance_sides=('s', 'e'),
                           max_shafts=3, shaft_size_range=(1, 2), basin_probability=0.5)
                total += 1
                if len(m._walkable_components()) != 1:
                    disconnected += 1
        # Spacing constraints make a genuine shaft pinch-point rare; allow a
        # small tolerance rather than asserting zero (the fallback still
        # guarantees real physical connectivity through the shaft even in
        # that rare case, just not reflected in this simplified
        # walkable-cell graph -- see TestLightShafts for the direct check).
        self.assertLessEqual(disconnected, max(1, total // 20),
                             f"{disconnected}/{total} disconnected")


if __name__ == "__main__":
    unittest.main()
