"""Voxelise a :class:`maze.Maze` and erode it into ruins — Blender-free.

This is the portable core of the old Blender ``floorplan.py``: it turns a maze
into a set of occupied integer voxel positions (:meth:`PositionGrid.fromMaze`)
and erodes that mass to mimic ruins (:meth:`PositionGrid.decay_texture`).  All
Blender mesh/IO code is gone; the occupancy set feeds ``isometric.render_voxels``
directly.

Randomness and noise are *injected* so a sketch can drive them from vsketch's
seeded streams (``vsk.random`` / ``vsk.noise``) for reproducibility:

* ``rng()``            -> float in ``[0, 1)``
* ``noise_fn(x, y)``   -> float (spatial noise; caller controls the scale)
"""
from collections import defaultdict
import random

import numpy as np
from scipy import ndimage

# 6-connected structuring element for connected-component labelling.
_CONN6 = ndimage.generate_binary_structure(3, 1)

# 3x3x3 weight kernel reproducing _count_neighbors: base 1 at every offset
# (incl. centre = the voxel's own +1); the cell directly above gets the +6 roof
# bonus (-> 7); the four above-diagonals get +1 (-> 2).  Index k=2 is the +z
# (above) neighbour under scipy's centred correlate.
_NEIGHBOR_KERNEL = np.ones((3, 3, 3))
_NEIGHBOR_KERNEL[1, 1, 2] = 7.0
for _di in (0, 2):
    for _dj in (0, 2):
        _NEIGHBOR_KERNEL[_di, _dj, 2] = 2.0

# Sums the 9 cells directly below (z-1 plane); used for the "full floor" +6 bonus.
_BELOW_KERNEL = np.zeros((3, 3, 3))
_BELOW_KERNEL[:, :, 0] = 1.0


def _grounded_mask(occ: np.ndarray, seed_z: int) -> np.ndarray:
    """Boolean mask of occupied voxels connected (6-conn) to the floor slab.

    A component is grounded if its label appears anywhere in ``z <= seed_z``.
    """
    lbl, _n = ndimage.label(occ, structure=_CONN6)
    floor_labels = np.unique(lbl[:, :, : seed_z + 1])
    floor_labels = floor_labels[floor_labels > 0]
    return np.isin(lbl, floor_labels) & occ


def flood_fill_3d(grid: np.ndarray, seed_z: int, fill_value: int = 2) -> np.ndarray:
    """Mark the component of ``1`` voxels connected to the foundation.

    Seeds from every ``1`` voxel at ``z <= seed_z`` (the floor) via 6-connected
    labelling.  Returns a copy where the connected component is set to
    ``fill_value``; any ``1`` voxels left over are "floating" (disconnected).
    """
    out = grid.copy()
    out[_grounded_mask(grid == 1, seed_z)] = fill_value
    return out


def drop(x: int, y: int, z: int, grid: np.ndarray, floor_z, rng, stop_drop=False) -> np.ndarray:
    """Let a floating voxel fall, then maybe tumble once into an adjacent column.

    ``floor_z`` is the lowest z a voxel may occupy (the first free cell above the
    floor).  The voxel falls straight down until it rests on a solid cell or on
    the floor, optionally tumbles once sideways off a ledge, and is always placed
    (marked ``3``) at a valid resting cell — never below ``floor_z`` and never
    discarded.
    """
    if z < floor_z:
        z = floor_z
    grid[x, y, z] = 0
    # Fall straight down to rest on the first solid cell (or the floor).
    while z > floor_z and grid[x, y, z - 1] == 0:
        z -= 1
    # Maybe tumble once into a random adjacent empty cell at the rest level,
    # which then falls and settles in its own column.
    if not stop_drop:
        cands = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < grid.shape[0] and 0 <= ny < grid.shape[1] \
                        and grid[nx, ny, z] == 0:
                    cands.append((nx, ny))
        i = int(rng() * 8)
        if i < len(cands):
            nx, ny = cands[i]
            return drop(nx, ny, z, grid, floor_z, rng, stop_drop=True)
    grid[x, y, z] = 3
    return grid


class PositionGrid:
    """A set of occupied integer voxel positions, built from a maze and eroded."""

    def __init__(self, size_x, size_y, size_z):
        self.size_x = size_x
        self.size_y = size_y
        self.size_z = size_z
        self.all_occupied_positions = set()
        self.stable_z = 0

    def fill_box(self, xmin, xmax, ymin, ymax, zmin, zmax):
        for x in range(xmin, xmax):
            for y in range(ymin, ymax):
                for z in range(zmin, zmax):
                    self.all_occupied_positions.add((x, y, z))

    def clear_box(self, xmin, xmax, ymin, ymax, zmin, zmax):
        discard = {(x, y, z)
                   for x in range(xmin, xmax)
                   for y in range(ymin, ymax)
                   for z in range(zmin, zmax)}
        self.all_occupied_positions -= discard

    def shift(self, n):
        """Add a shift of (n, n, n) to all occupied positions."""
        self.all_occupied_positions = {
            (x + n, y + n, z + n) for (x, y, z) in self.all_occupied_positions}

    def bounding_box(self):
        xs = [p[0] for p in self.all_occupied_positions]
        ys = [p[1] for p in self.all_occupied_positions]
        zs = [p[2] for p in self.all_occupied_positions]
        return [min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)]

    def fromMaze(self, theMaze, room_size=12, wall_thickness=3, wall_height=16, floor_thickness=1):
        self.stable_z = floor_thickness + 1
        # First free cell above the floor (floor voxels occupy z in [0, floor_thickness)).
        # This is where dropped debris should come to rest.
        self.floor_z = floor_thickness
        cell_size = room_size + wall_thickness
        floor_level = 0

        for row in range(theMaze.num_rows):
            for col in range(theMaze.num_cols):
                # room floor tiles
                if theMaze.rooms[row][col] != 0:
                    self.fill_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                  col * cell_size + wall_thickness, (col + 1) * cell_size,
                                  floor_level, floor_level + floor_thickness)
                    # floor tiles between rooms
                    if col < theMaze.num_cols - 1 and theMaze.rooms[row][col + 1] != 0:
                        if row < theMaze.num_rows - 1 and row > 0 and theMaze.rooms[row + 1][col] != 0 and theMaze.rooms[row - 1][col] != 0:
                            self.fill_box(row * cell_size, (row + 1) * cell_size + wall_thickness,
                                          (col + 1) * cell_size, (col + 1) * cell_size + wall_thickness,
                                          floor_level, floor_level + floor_thickness)
                        else:  # still not quite correct, needs separate cases for either row direction
                            self.fill_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                          (col + 1) * cell_size, (col + 1) * cell_size + wall_thickness,
                                          floor_level, floor_level + floor_thickness)
                    if row < theMaze.num_rows - 1 and theMaze.rooms[row + 1][col] != 0:
                        if col < theMaze.num_cols - 1 and col > 0 and theMaze.rooms[row][col + 1] != 0 and theMaze.rooms[row][col - 1] != 0:
                            self.fill_box((row + 1) * cell_size, (row + 1) * cell_size + wall_thickness,
                                          col * cell_size, (col + 1) * cell_size + wall_thickness,
                                          floor_level, floor_level + floor_thickness)
                        else:  # still not quite correct, needs separate cases for either column direction
                            self.fill_box((row + 1) * cell_size, (row + 1) * cell_size + wall_thickness,
                                          col * cell_size + wall_thickness, (col + 1) * cell_size,
                                          floor_level, floor_level + floor_thickness)
        # walls
        for row in range(theMaze.num_rows + 1):
            for col in range(theMaze.num_cols):
                btype = theMaze.horizontal_boundaries[row][col].boundary_type
                if btype == 'wall':
                    self.fill_box(row * cell_size, row * cell_size + wall_thickness,
                                  col * cell_size, (col + 1) * cell_size + wall_thickness,
                                  floor_level, floor_level + wall_height + floor_thickness)
                if btype == 'door':
                    self.fill_box(row * cell_size, row * cell_size + wall_thickness,
                                  col * cell_size, (col + 1) * cell_size + wall_thickness,
                                  floor_level, floor_level + floor_thickness)
                    self.fill_box(row * cell_size, row * cell_size + wall_thickness,
                                  col * cell_size, (col + 1) * cell_size + wall_thickness,
                                  floor_level + wall_height + floor_thickness - 1, floor_level + wall_height + floor_thickness)
        for row in range(theMaze.num_rows):
            for col in range(theMaze.num_cols + 1):
                btype = theMaze.vertical_boundaries[row][col].boundary_type
                if btype == 'wall':
                    self.fill_box(row * cell_size, (row + 1) * cell_size + wall_thickness,
                                  col * cell_size, col * cell_size + wall_thickness,
                                  floor_level, floor_level + wall_height + floor_thickness)
                if btype == 'door':
                    self.fill_box(row * cell_size, (row + 1) * cell_size + wall_thickness,
                                  col * cell_size, col * cell_size + wall_thickness,
                                  floor_level, floor_level + floor_thickness)
                    self.fill_box(row * cell_size, (row + 1) * cell_size + wall_thickness,
                                  col * cell_size, col * cell_size + wall_thickness,
                                  floor_level + wall_height + floor_thickness - 1, floor_level + wall_height + floor_thickness)
        # stairs: group cells of each flight, then build the steps
        flights = defaultdict(list)
        for row in range(theMaze.num_rows):
            for col in range(theMaze.num_cols):
                room_type = theMaze.rooms[row][col]
                if 19 < room_type < 100:
                    flights[room_type].append((row, col))
        for type, cells in flights.items():
            rows, cols = zip(*cells)
            max_height = floor_level + floor_thickness + wall_height
            match type // 20:
                case 1:  # stairs leading up north
                    start_row = max(rows)
                    col = cols[0]
                    num_rooms = abs(start_row - min(rows)) + 1
                    num_steps = (num_rooms * room_size + (num_rooms - 1) * wall_thickness) // 3
                    x = start_row * cell_size
                    ymin = col * cell_size + wall_thickness
                    ymax = ymin + room_size
                    for step in range(num_steps + 1):
                        self.fill_box(x, x + 3, ymin, ymax, floor_level, min(floor_level + 2 * (step + 1), max_height))
                        x -= 3
                case 2:  # stairs leading up east
                    start_col = min(cols)
                    row = rows[0]
                    num_rooms = abs(start_col - max(cols)) + 1
                    num_steps = (num_rooms * room_size + (num_rooms - 1) * wall_thickness) // 3
                    y = start_col * cell_size
                    xmin = row * cell_size + wall_thickness
                    xmax = xmin + room_size
                    for step in range(num_steps + 1):
                        self.fill_box(xmin, xmax, y, y + 3, floor_level, min(floor_level + 2 * (step + 1), max_height))
                        y += 3
                case 3:  # stairs leading up south
                    start_row = min(rows)
                    col = cols[0]
                    num_rooms = abs(start_row - max(rows)) + 1
                    num_steps = (num_rooms * room_size + (num_rooms - 1) * wall_thickness) // 3
                    x = start_row * cell_size
                    ymin = col * cell_size + wall_thickness
                    ymax = ymin + room_size
                    for step in range(num_steps + 1):
                        self.fill_box(x, x + 3, ymin, ymax, floor_level, min(floor_level + 2 * (step + 1), max_height))
                        x += 3
                case 4:  # stairs leading up west
                    start_col = max(cols)
                    row = rows[0]
                    num_rooms = abs(start_col - min(cols)) + 1
                    num_steps = (num_rooms * room_size + (num_rooms - 1) * wall_thickness) // 3
                    y = start_col * cell_size
                    xmin = row * cell_size + wall_thickness
                    xmax = xmin + room_size
                    for step in range(num_steps + 1):
                        self.fill_box(xmin, xmax, y, y + 3, floor_level, min(floor_level + 2 * (step + 1), max_height))
                        y -= 3
        # lustral basins: clear a stepped 2x2 depression per basin
        basins = defaultdict(list)
        for row in range(theMaze.num_rows):
            for col in range(theMaze.num_cols):
                room_type = theMaze.rooms[row][col]
                if 99 < room_type < 180:
                    basins[room_type].append((row, col))
        for room_type, cells in basins.items():
            basin_depth = 1
            type = (room_type - 100) // 10
            rows, cols = zip(*cells)
            ft = floor_level + floor_thickness
            match type:
                case 0:  # n, ccw
                    row, col = min(rows), max(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 3 - basin_depth, ft + 1)
                    row = max(rows)
                    self.clear_box(row * cell_size, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 2, ft + 1)
                    col = min(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size + wall_thickness,
                                   ft - 1, ft + 1)
                case 1:  # e, ccw
                    row, col = max(rows), max(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 3 - basin_depth, ft + 1)
                    col = min(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size + wall_thickness,
                                   ft - 2, ft + 1)
                    row = min(rows)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size + wall_thickness,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 1, ft + 1)
                case 2:  # s, ccw
                    row, col = max(rows), min(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 3 - basin_depth, ft + 1)
                    row = min(rows)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size + wall_thickness,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 2, ft + 1)
                    col = max(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size, (col + 1) * cell_size,
                                   ft - 1, ft + 1)
                case 3:  # w, ccw
                    row, col = min(rows), min(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 3 - basin_depth, ft + 1)
                    col = max(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size, (col + 1) * cell_size,
                                   ft - 2, ft + 1)
                    row = max(rows)
                    self.clear_box(row * cell_size, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 1, ft + 1)
                case 4:  # n, cw
                    row, col = min(rows), min(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 3 - basin_depth, ft + 1)
                    row = max(rows)
                    self.clear_box(row * cell_size, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 2, ft + 1)
                    col = max(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size, (col + 1) * cell_size,
                                   ft - 1, ft + 1)
                case 5:  # e, cw
                    row, col = min(rows), max(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 3 - basin_depth, ft + 1)
                    col = min(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size + wall_thickness,
                                   ft - 2, ft + 1)
                    row = max(rows)
                    self.clear_box(row * cell_size, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 1, ft + 1)
                case 6:  # s, cw
                    row, col = max(rows), max(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 3 - basin_depth, ft + 1)
                    row = min(rows)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size + wall_thickness,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 2, ft + 1)
                    col = min(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size + wall_thickness,
                                   ft - 1, ft + 1)
                case 7:  # w, cw
                    row, col = max(rows), min(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 3 - basin_depth, ft + 1)
                    col = max(cols)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                                   col * cell_size, (col + 1) * cell_size,
                                   ft - 2, ft + 1)
                    row = min(rows)
                    self.clear_box(row * cell_size + wall_thickness, (row + 1) * cell_size + wall_thickness,
                                   col * cell_size + wall_thickness, (col + 1) * cell_size,
                                   ft - 1, ft + 1)
        # entrance stairs (assumes one entrance per direction)
        entrances = defaultdict(list)
        for row in range(theMaze.num_rows):
            for col in range(theMaze.num_cols):
                room_type = theMaze.rooms[row][col]
                if 179 < room_type < 184:
                    entrances[room_type].append((row, col))
        for type, cells in entrances.items():
            rows, cols = zip(*cells)
            min_row, max_row = min(rows) * cell_size, max(rows) * cell_size
            min_col, max_col = min(cols) * cell_size, max(cols) * cell_size
            step_size = 4
            direction = ['n', 'e', 's', 'w'][type - 180]
            min_row_step = {'n': 0, 'e': 1, 's': 1, 'w': 1}
            max_row_step = {'n': 1, 'e': 1, 's': 0, 'w': 1}
            min_col_step = {'n': 1, 'e': 1, 's': 1, 'w': 0}
            max_col_step = {'n': 1, 'e': 0, 's': 1, 'w': 1}
            self.fill_box(min_row + wall_thickness + (min_row_step[direction] - 1) * wall_thickness,
                          max_row + cell_size - (max_row_step[direction] - 1) * wall_thickness,
                          min_col + wall_thickness + (min_col_step[direction] - 1) * wall_thickness,
                          max_col + cell_size - (max_col_step[direction] - 1) * wall_thickness,
                          floor_level, floor_level + floor_thickness)
            for i in range(1, 4):
                self.clear_box(min_row + wall_thickness + min_row_step[direction] * step_size * i + (min_row_step[direction] - 1) * wall_thickness,
                               max_row + cell_size - max_row_step[direction] * step_size * i - (max_row_step[direction] - 1) * wall_thickness,
                               min_col + wall_thickness + min_col_step[direction] * step_size * i + (min_col_step[direction] - 1) * wall_thickness,
                               max_col + cell_size - max_col_step[direction] * step_size * i - (max_col_step[direction] - 1) * wall_thickness,
                               floor_level + floor_thickness - i, floor_level + floor_thickness + 1)

    def _count_neighbors(self, position):
        """26-neighbour count, weighting voxels directly above (a roof bonus)."""
        px, py, pz = position
        neighbors = bottom = 0
        for x in range(-1, 2):
            for y in range(-1, 2):
                for z in range(-1, 2):
                    if (px + x, py + y, pz + z) in self.all_occupied_positions:
                        neighbors += 1
                        if z == 1 and x == 0 and y == 0:
                            neighbors += 6
                        if z == 1 and x != 0 and y != 0:
                            neighbors += 1
                        if z == -1:
                            bottom += 1
        return neighbors, bottom

    def decay(self, max_neighbors=26):
        """Simple erosion: drop voxels with too few neighbours."""
        discard = set()
        for position in self.all_occupied_positions:
            neighbors, _bottom = self._count_neighbors(position)
            if random.randint(0, max_neighbors) > neighbors:
                discard.add(position)
        self.all_occupied_positions -= discard

    def decay_texture(self, reps, rng, noise_fn, *, noise_influence=6.5,
                      noise_offset=-0.4, neighbor_baseline=-9):
        """Logistic, noise-modulated erosion for ``reps`` rounds (vectorised).

        Each round, a voxel survives with probability ``sigmoid(baseline +
        neighbours + noise*influence + floor_bonus)``; cut voxels and any mass
        left disconnected from the floor are then either deleted or dropped to a
        lower position as rubble.

        ``rng`` is a NumPy ``Generator`` (``np.random.default_rng(seed)``) and
        ``noise_fn(x, y) -> float`` is the (deterministic) spatial noise; both
        keep the result reproducible per seed.
        """
        if reps <= 0 or not self.all_occupied_positions:
            return

        bbox = self.bounding_box()
        nx, ny, nz = bbox[1] + 2, bbox[3] + 2, bbox[5] + 2
        occ = np.zeros((nx, ny, nz), dtype=bool)
        for (x, y, z) in self.all_occupied_positions:
            occ[x, y, z] = True

        # Pieces of the logistic that don't change between rounds: the 2-D noise
        # field (broadcast over z) and the stable-floor bonus.
        noise2d = np.array([[noise_fn(x, y) for y in range(ny)] for x in range(nx)])
        noise2d = (noise2d + noise_offset) * noise_influence
        stable = np.where(np.arange(nz) <= self.stable_z, 30.0, 0.0)
        base = neighbor_baseline + noise2d[:, :, None] + stable[None, None, :]
        z_above_floor_base = np.arange(nz) > 0
        scalar = lambda: float(rng.random())   # scalar draw for drop()

        for _ in range(reps):
            occf = occ.astype(np.float64)
            neighbors = ndimage.correlate(occf, _NEIGHBOR_KERNEL, mode="constant", cval=0.0)
            below_full = ndimage.correlate(occf, _BELOW_KERNEL, mode="constant", cval=0.0) > 8.5
            surv = 1.0 / (1.0 + np.exp(-(base + neighbors + 6.0 * below_full)))
            removed = occ & (surv < rng.random(occ.shape))
            occ2 = occ & ~removed

            # Disconnected mass + the just-cut voxels become rubble candidates.
            kept = _grounded_mask(occ2, self.stable_z)
            floating = occ2 & ~kept
            cand = (removed | floating) & z_above_floor_base[None, None, :]

            grid = kept.astype(np.int8)
            cells = np.argwhere(cand)
            for x, y, z in cells[np.argsort(cells[:, 2])]:   # settle bottom-up
                if scalar() < 0.7 and z > self.floor_z:
                    drop(int(x), int(y), int(z), grid, self.floor_z, scalar)
            occ = grid > 0

        self.all_occupied_positions = {
            (int(x), int(y), int(z)) for x, y, z in np.argwhere(occ)}
