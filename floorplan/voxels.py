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


def _floor_at(floor_z, x: int, y: int) -> int:
    """Resolve a resting floor: a plain scalar, or a per-column (nx, ny) array."""
    return int(floor_z[x, y]) if isinstance(floor_z, np.ndarray) else int(floor_z)


def drop(x: int, y: int, z: int, grid: np.ndarray, floor_z, rng, stop_drop=False) -> np.ndarray:
    """Let a floating voxel fall, then maybe tumble once into an adjacent column.

    ``floor_z`` is the lowest z a voxel may occupy at column ``(x, y)`` (the
    first free cell above whatever it rests on) — either a scalar used
    everywhere, or a per-column ``(nx, ny)`` array (e.g. a structural floor
    where present, terrain height elsewhere; see ``PositionGrid.decay_texture``).
    The voxel falls straight down until it rests on a solid cell or on that
    floor, optionally tumbles once sideways off a ledge (re-resolving the floor
    at the new column), and is always placed (marked ``3``) at a valid resting
    cell — never below its column's floor and never discarded.
    """
    fz = _floor_at(floor_z, x, y)
    if z < fz:
        z = fz
    grid[x, y, z] = 0
    # Fall straight down to rest on the first solid cell (or this column's floor).
    while z > fz and grid[x, y, z - 1] == 0:
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

    def _fill_floor_slab(self, theMaze, room_size, wall_thickness, thickness, z0, cells):
        """Fill a `thickness`-tall floor slab at [z0, z0+thickness) for exactly
        `cells` (a set of (row,col)), including the inter-cell seam fill
        between orthogonally adjacent members of `cells` (closes the
        wall_thickness-wide gap between two cells' own tiles).

        Each cell's own tile is inset by wall_thickness on its north/west
        sides (and stops short of its own south/east wall strip too) -- for a
        *normal* floor slab that's invisible, because a real wall already
        fills that same footprint at every z from the floor up to its own
        ceiling. But a slab used as a roof/terrace cap sits *above* where the
        walls stop, so nothing else fills that boundary strip there -- it
        must be filled explicitly wherever a cell has no same-region neighbour
        in a given direction (a true exterior edge of `cells`), or the wall
        below appears to stop short of the cap sitting on top of it.
        """
        cell_size = room_size + wall_thickness
        for (row, col) in cells:
            self.fill_box(row * cell_size + wall_thickness, (row + 1) * cell_size,
                          col * cell_size + wall_thickness, (col + 1) * cell_size,
                          z0, z0 + thickness)
            # Always the generous (corner-covering) fill -- fill_box just adds
            # to a set, so overshooting a wall_thickness strip into a
            # perpendicular neighbour's row/column is harmless even when that
            # neighbour isn't in `cells` (same reasoning as the boundary
            # strips below). A narrower fill keyed on whether the
            # perpendicular neighbour is also present used to leave the
            # shared corner between 4 cells unfilled whenever `cells` has an
            # irregular boundary (e.g. a terrace ring notched by the floor
            # above) -- each of the two seam fills backed off independently,
            # and neither alone covered the corner square.
            if (row, col + 1) in cells:
                self.fill_box(row * cell_size, (row + 1) * cell_size + wall_thickness,
                              (col + 1) * cell_size, (col + 1) * cell_size + wall_thickness,
                              z0, z0 + thickness)
            if (row + 1, col) in cells:
                self.fill_box((row + 1) * cell_size, (row + 1) * cell_size + wall_thickness,
                              col * cell_size, (col + 1) * cell_size + wall_thickness,
                              z0, z0 + thickness)
            # Exterior boundary strips: no same-region neighbour there, so
            # nothing else (seam fill or wall) would cover this cap slab's own
            # footprint edge -- fill it directly, generous past the corners
            # (harmless redundancy in a set) to avoid corner gaps.
            if (row - 1, col) not in cells:
                self.fill_box(row * cell_size, row * cell_size + wall_thickness,
                              col * cell_size, (col + 1) * cell_size + wall_thickness,
                              z0, z0 + thickness)
            if (row, col - 1) not in cells:
                self.fill_box(row * cell_size, (row + 1) * cell_size + wall_thickness,
                              col * cell_size, col * cell_size + wall_thickness,
                              z0, z0 + thickness)
            if (row + 1, col) not in cells:
                self.fill_box((row + 1) * cell_size, (row + 1) * cell_size + wall_thickness,
                              col * cell_size, (col + 1) * cell_size + wall_thickness,
                              z0, z0 + thickness)
            if (row, col + 1) not in cells:
                self.fill_box(row * cell_size, (row + 1) * cell_size + wall_thickness,
                              (col + 1) * cell_size, (col + 1) * cell_size + wall_thickness,
                              z0, z0 + thickness)

    def fromMaze(self, theMaze, room_size=12, wall_thickness=3, wall_height=16, floor_thickness=1,
                 floor_level=0, omit_floor_cells=frozenset(),
                 roof_stair_state=None, roof_break_height=None):
        if floor_level == 0:
            self.stable_z = floor_thickness + 1
            # First free cell above the floor (floor voxels occupy z in [0, floor_thickness)).
            # This is where dropped debris should come to rest.
            self.floor_z = floor_thickness
        cell_size = room_size + wall_thickness

        floor_cells = theMaze.footprint_cells() - set(omit_floor_cells)
        if floor_level > 0:
            # A light shaft never gets a floor slab on any floor above the one
            # it originates on -- it stays an open vertical void up to the roof.
            floor_cells -= {(r, c) for r in range(theMaze.num_rows) for c in range(theMaze.num_cols)
                            if 9 <= theMaze.rooms[r][c] <= 12}
        self._fill_floor_slab(theMaze, room_size, wall_thickness, floor_thickness, floor_level, floor_cells)
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
            if roof_stair_state is not None and type == roof_stair_state:
                max_height = roof_break_height   # punch through the roof cap
            else:
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
                      noise_offset=-0.4, neighbor_baseline=-9, terrain_z=None):
        """Logistic, noise-modulated erosion for ``reps`` rounds (vectorised).

        Each round, a voxel survives with probability ``sigmoid(baseline +
        neighbours + noise*influence + floor_bonus)``; cut voxels and any mass
        left disconnected from the floor are then either deleted or dropped to a
        lower position as rubble.

        ``rng`` is a NumPy ``Generator`` (``np.random.default_rng(seed)``) and
        ``noise_fn(x, y) -> float`` is the (deterministic) spatial noise; both
        keep the result reproducible per seed.

        ``terrain_z(x, y) -> float``, if given, is the ground rest height for
        column ``(x, y)`` (in this grid's own integer coordinates). Rubble in a
        column with no structural floor beneath it (no solid within
        ``[0, floor_z)``) rests on ``terrain_z`` instead of falling all the way
        to the (otherwise flat) ``floor_z`` — e.g. debris tumbling outside the
        building footprint lands on the surrounding terrain rather than floating
        above or sinking below it. Columns that do have a structural floor are
        unaffected and keep resting on it.
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

        # Sample the (static) terrain resting height once, up front.
        terrain_arr = None
        if terrain_z is not None:
            terrain_arr = np.array([[terrain_z(x, y) for y in range(ny)] for x in range(nx)])
            terrain_arr = np.clip(np.round(terrain_arr), 0, nz - 1).astype(int)

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

            # Per-column resting floor: the structural floor where one exists
            # (unchanged behaviour), else the terrain (when provided).
            if terrain_arr is not None:
                has_floor = kept[:, :, : self.floor_z].any(axis=2) if self.floor_z > 0 \
                    else np.zeros((nx, ny), dtype=bool)
                column_floor = np.where(has_floor, self.floor_z, terrain_arr)
            else:
                column_floor = self.floor_z   # scalar: identical to the old behaviour

            grid = kept.astype(np.int8)
            cells = np.argwhere(cand)
            for x, y, z in cells[np.argsort(cells[:, 2])]:   # settle bottom-up
                fz = _floor_at(column_floor, x, y)
                if scalar() < 0.7 and z > fz:
                    drop(int(x), int(y), int(z), grid, column_floor, scalar)
            occ = grid > 0

        self.all_occupied_positions = {
            (int(x), int(y), int(z)) for x, y, z in np.argwhere(occ)}

    def fromBuilding(self, building, room_size=12, wall_thickness=3, wall_height=16,
                     floor_thickness=1, ground_floor_thickness=None,
                     parapet_height=None, roof_thickness=None):
        """Voxelise every floor of a maze.Building into one combined occupancy
        set, stacking each floor directly on top of the previous one's own
        ceiling, and omitting each upper floor's own stair-flight cells from
        its own floor slab -- that omission is the literal hole the stairs
        below rise into, kept open across the whole flight (not just its
        landing) so headroom stays a full room height along the whole climb
        (fromMaze's roof_stair_state/roof_break_height punch the flight
        itself up through what would otherwise be its ceiling).
        Roof capping and the ground-floor roof terrace + parapet are added
        after the floor loop (see PositionGrid._cap_roof).

        `ground_floor_thickness` (default: same as `floor_thickness`) lets the
        ground floor's own slab be a different thickness than every floor
        above it and the roof/terrace cap -- e.g. a thick stone foundation
        slab under a thinner wooden upper floor/roof."""
        roof_thickness = floor_thickness if roof_thickness is None else roof_thickness
        ground_floor_thickness = floor_thickness if ground_floor_thickness is None else ground_floor_thickness

        # Per-floor slab thickness: only the ground floor can differ: every
        # floor above it, and the roof/terrace cap, always use floor_thickness.
        thicknesses = [ground_floor_thickness] + [floor_thickness] * (len(building.floors) - 1)
        floor_levels = []
        z = 0
        for t in thicknesses:
            floor_levels.append(z)
            z += t + wall_height

        for i, maze in enumerate(building.floors):
            floor_level = floor_levels[i]
            this_thickness = thicknesses[i]
            omit = set()
            if i > 0:
                for link in building.stair_links:
                    if link['to_floor'] == i:
                        # The whole flight, not just the landing -- a flat
                        # slab at a fixed height above a rising staircase
                        # gives shrinking headroom over the run and would dip
                        # below a full room's clearance well before the top
                        # step. Open the slab across the entire flight so
                        # clearance stays a full room height throughout.
                        omit.update(link['flight_cells'])
            is_roof_floor = (i == building.roof_floor_index)
            roof_stair_state = building.roof_stair_state if is_roof_floor else None
            # Genuine headroom above the roof cap's own top surface (not just
            # up to the normal ceiling) so the flight actually pokes through
            # the cap instead of merely reaching it.
            roof_top = floor_level + this_thickness + wall_height + roof_thickness
            roof_break_height = (roof_top + wall_height) if roof_stair_state else None
            self.fromMaze(maze, room_size=room_size, wall_thickness=wall_thickness,
                          wall_height=wall_height, floor_thickness=this_thickness,
                          floor_level=floor_level, omit_floor_cells=omit,
                          roof_stair_state=roof_stair_state, roof_break_height=roof_break_height)

        self._cap_roof(building, room_size, wall_thickness, wall_height, floor_thickness,
                       parapet_height, roof_thickness, floor_levels, thicknesses)

    def _cap_roof(self, building, room_size, wall_thickness, wall_height, floor_thickness,
                  parapet_height, roof_thickness, floor_levels, thicknesses):
        """Cap the topmost floor's footprint (minus its own light shafts --
        they stay open to the sky -- and any roof-access opening) with a roof
        slab, and if a 2nd floor exists, also cap whatever part of the ground
        floor's roof it does NOT cover as an accessible terrace, surrounded by
        a parapet. `floor_levels`/`thicknesses` are per-floor (see
        fromBuilding), since the ground floor's own thickness can differ from
        every floor above it."""
        parapet_height = max(1, wall_height // 3) if parapet_height is None else parapet_height

        top = building.floors[building.roof_floor_index]
        roof_level = (floor_levels[building.roof_floor_index]
                     + thicknesses[building.roof_floor_index] + wall_height)
        shaft_top = {(r, c) for r in range(top.num_rows) for c in range(top.num_cols)
                    if 9 <= top.rooms[r][c] <= 12}
        cap_cells = top.footprint_cells() - shaft_top - building.roof_open_cells
        self._fill_floor_slab(top, room_size, wall_thickness, roof_thickness, roof_level, cap_cells)

        if len(building.floors) > 1:
            ground, upper = building.floors[0], building.floors[1]
            # A stair flight's non-landing cells are excluded from floor2's
            # own footprint (see Building.generate), so they fall out as
            # "terrace" too -- ground floor roof it doesn't cover -- and
            # would otherwise get capped right back over, sealing the
            # stairwell the same way an uncapped floor slab alone couldn't.
            stair_voids = {cell for link in building.stair_links if link['to_floor'] == 1
                          for cell in link['flight_cells'] - {link['landing']}}
            terrace = ground.terrace_cells(upper) - stair_voids
            if terrace:
                terrace_level = floor_levels[1]   # top of the ground floor == where floor 1 starts
                self._fill_floor_slab(ground, room_size, wall_thickness, roof_thickness,
                                      terrace_level, terrace)
                # The parapet sits on the *outer boundary strip* of the terrace
                # (where a full room wall would normally rise) -- the roof cap
                # itself never fills that strip (only cell interiors + inter-
                # cell seams), so the parapet must start flush at the top of
                # the ground floor's own wall (terrace_level), not above the
                # cap, or there's a gap between the wall-top and the parapet.
                self._build_parapet(ground, upper, terrace, room_size, wall_thickness,
                                    roof_thickness + parapet_height, terrace_level)

    def _build_parapet(self, ground, upper, terrace_cells, room_size, wall_thickness, parapet_height, z0):
        cell_size = room_size + wall_thickness
        for (row, col, direction) in ground.parapet_boundaries(upper, terrace_cells):
            if direction == 'n':
                self.fill_box(row * cell_size, row * cell_size + wall_thickness,
                              col * cell_size, (col + 1) * cell_size + wall_thickness,
                              z0, z0 + parapet_height)
            elif direction == 's':
                self.fill_box((row + 1) * cell_size, (row + 1) * cell_size + wall_thickness,
                              col * cell_size, (col + 1) * cell_size + wall_thickness,
                              z0, z0 + parapet_height)
            elif direction == 'w':
                self.fill_box(row * cell_size, (row + 1) * cell_size + wall_thickness,
                              col * cell_size, col * cell_size + wall_thickness,
                              z0, z0 + parapet_height)
            elif direction == 'e':
                self.fill_box(row * cell_size, (row + 1) * cell_size + wall_thickness,
                              (col + 1) * cell_size, (col + 1) * cell_size + wall_thickness,
                              z0, z0 + parapet_height)
