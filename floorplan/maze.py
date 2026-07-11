import math
import random
from collections import defaultdict
# a class representing a maze consisting of rooms walls and doors.
# the rooms are represented as a 2d grid of integer cells. 
# An integer vaule of 0 reprents an empty cell, meaning no room is present, to allow for non rectangular mazes.
# Rooms with state 1-9 are reqular rooms.
#
# Rooms with state 9-12 are light shafts these prevent the generation of any other room type in the floors above.
#
# Rooms with state 20-39,40-59,60-79,80-99 are stairs leading up in northern,eastern,southern or western direction,respectively.
#
# Rooms with state 100-109,110-119,120-129,130-139 are 2x2 Lustral basins (including the path leading to them) 
# with the exit door facing in northern,eastern,southern or western direction,respectively.
# The path to the basin will be counterclockwise. States 140-179 are for the corresponding
# lustral basins with clockwise access.
#
# Rooms with state 180-183 are entrance stairs.
#
# Boundaries between rooms are represented as two grids one for horizontal boundaries and one for vertical boundaries.
# A boundary can be air, a wall, or a door.
opposite = {'n':'s','e':'w','s':'n','w':'e'}
left = {'n':'w','e':'n','s':'e','w':'s'}
right = {'n':'e','e':'s','s':'w','w':'n'}

class Boundary:
    def __init__(self, boundary_type):
        self.boundary_type = boundary_type  # 'air', 'wall', or 'door'

class Maze:
    def __init__(self, num_rows, num_cols, state=1):
        self.num_rows = num_rows
        self.num_cols = num_cols
        self.rooms = [[state for _ in range(num_cols)] for _ in range(num_rows)]
        self.vertical_boundaries = [[Boundary('air') for _ in range(num_cols + 1)] for _ in range(num_rows)]
        self.horizontal_boundaries = [[Boundary('air') for _ in range(num_cols)] for _ in range(num_rows + 1)]    
    
    
    def auto_entrance(self, sides=('n', 'e', 's', 'w')):
        '''Create an entrance at the centre of the longest outer-wall run whose
        resolved facing direction is in `sides`. An enclosing wall always
        separates a room cell from empty space (or the maze edge); the
        entrance is placed on the room side facing the gap. Returns
        (row, col, facing), or None if no run of length >= 3 exists among the
        allowed sides.'''
        runs = {'n': {}, 's': {}, 'e': {}, 'w': {}}   # facing -> {fixed_coord: [running_coords]}
        for boundary_type, row, col in self.get_enclosing_walls():
            if boundary_type == 'horizontal':
                below = self.rooms[row][col] if row < self.num_rows else 0
                if row == 0 or (row < self.num_rows and below != 0):
                    facing, key, pos = 'n', row, col
                else:
                    facing, key, pos = 's', row - 1, col
            else:
                east = self.rooms[row][col] if col < self.num_cols else 0
                if col == 0 or (col < self.num_cols and east != 0):
                    facing, key, pos = 'w', col, row
                else:
                    facing, key, pos = 'e', col - 1, row
            runs[facing].setdefault(key, []).append(pos)

        best = None   # (length, facing, key, mid_pos)
        for facing in sides:
            for key, positions in runs[facing].items():
                positions.sort()
                start = positions[0]
                length = 1
                for i in range(1, len(positions) + 1):
                    if i < len(positions) and positions[i] == positions[i - 1] + 1:
                        length += 1
                        continue
                    if length >= 3 and (best is None or length > best[0]):
                        best = (length, facing, key, start + length // 2)
                    if i < len(positions):
                        start = positions[i]
                        length = 1

        if best is None:
            return None
        _, facing, key, mid = best
        row, col = (key, mid) if facing in ('n', 's') else (mid, key)
        self.make_entrance(row, col, facing)
        return (row, col, facing)
        
    def expand_room(self,center_row,center_col,width,direction,max_size,id):
        """ Expand a room from the given center in the given direction set the room state to the given id.
        Depending on the direction a room will start as a single column or row of and expand in the perpendicular direction as indicated by the direction parameter.
        The expansion stops when the max_size is reached or when it hits another room with id != 1 or the edge of the maze.
        The width parameter indicates how wide the room should be in the direction perpendicular to the expansion direction.
        """
        # compute half-width on either side of the center line
        if width < 1:
            return 0
        left_off = width // 2
        right_off = width - left_off - 1

        placed = []

        # helper to check and set a block at (r, c_start..c_end) or (r_start..r_end, c)
        def can_place_cells(cells):
            # cells: iterable of (r,c)
            for r, c in cells:
                if r < 0 or r >= self.num_rows or c < 0 or c >= self.num_cols:
                    return False
                if self.rooms[r][c] != 1:
                    return False
            return True

        def place_cells(cells):
            nonlocal placed
            for r, c in cells:
                self.rooms[r][c] = id
                placed.append((r, c))

        # Expansion depends on direction
        if direction == 'n':
            for step in range(max_size):
                r = center_row - step
                # build cells horizontally centered at center_col
                cells = [(r, center_col - left_off + dx) for dx in range(width)]
                if not can_place_cells(cells):
                    break
                place_cells(cells)
        elif direction == 's':
            for step in range(max_size):
                r = center_row + step
                cells = [(r, center_col - left_off + dx) for dx in range(width)]
                if not can_place_cells(cells):
                    break
                place_cells(cells)
        elif direction == 'e':
            for step in range(max_size):
                c = center_col + step
                cells = [(center_row - left_off + dy, c) for dy in range(width)]
                if not can_place_cells(cells):
                    break
                place_cells(cells)
        elif direction == 'w':
            for step in range(max_size):
                c = center_col - step
                cells = [(center_row - left_off + dy, c) for dy in range(width)]
                if not can_place_cells(cells):
                    break
                place_cells(cells)
        else:
            # unknown direction
            return 0
        self.contain_room(id)
        # iterate over places to find the minimum and maximum row and column and return a tuple of min_row, max_row, min_col, max_col
        min_row = self.num_rows
        max_row = 0
        min_col = self.num_cols
        max_col = 0
        for r, c in placed:
            if r < min_row:
                min_row = r
            if r > max_row:
                max_row = r
            if c < min_col:
                min_col = c
            if c > max_col:
                max_col = c
        return (min_row, max_row, min_col, max_col)
        


    _SHAPES = ("rectangular", "courtyard", "l_shape", "c_shape", "h_shape", "corners")

    def make_foundation(self, shape="random", entrance_sides=('s', 'e')):
        """Carve the exterior silhouette (`shape`, one of Maze._SHAPES or
        "random") and place a viewer-visible entrance restricted to
        `entrance_sides` (default south/east — the two sides the isometric
        camera actually shows). Returns (center_row, center_col, facing)."""
        if shape == "random" or shape not in Maze._SHAPES:
            shape = random.choice(Maze._SHAPES)
        return getattr(self, f"_shape_{shape}")(entrance_sides)

    def _cut_rectangular(self):
        pass   # no cutout: the full footprint is the building

    def _shape_rectangular(self, entrance_sides):
        self._cut_rectangular()
        return self.auto_entrance(sides=entrance_sides)

    def _cut_corners(self):
        # cut out up to two corners of empty space
        corners = [(0,0),(0,self.num_cols-1),(self.num_rows-1,0),(self.num_rows-1,self.num_cols-1)]
        num_corners = random.randint(1,2)
        chosen_corners = random.sample(corners,num_corners)
        for corner in chosen_corners:
            row,col = corner
            if row == 0:
                row_max = random.randint(self.num_rows//4,self.num_rows//2 -1)
                row_min = 0
            else:
                row_min = random.randint(self.num_rows//2 +1,self.num_rows-self.num_rows//4)
                row_max = self.num_rows
            if col == 0:
                col_max = random.randint(self.num_rows//4,self.num_cols//2 - 1)
                col_min = 0
            else:
                col_min = random.randint(self.num_cols//2 +1,self.num_cols-self.num_rows//4)
                col_max = self.num_cols
            self.set_room_state(row_min,row_max,col_min,col_max,0,False)

    def _shape_corners(self, entrance_sides):
        self._cut_corners()
        return self.auto_entrance(sides=entrance_sides)

    def _cut_courtyard(self):
        # cut out a central rectangular area of empty space (never touches the edge)
        row_min = random.randint(2,self.num_rows//4)
        row_max = random.randint(3*self.num_rows//4,self.num_rows-2)
        col_min = random.randint(2,self.num_cols//4)
        col_max = random.randint(3*self.num_cols//4,self.num_cols-2)
        self.set_room_state(row_min,row_max,col_min,col_max,0,False)

    def _shape_courtyard(self, entrance_sides):
        self._cut_courtyard()
        if 's' in entrance_sides:
            facing, row, col = 's', self.num_rows - 1, self.num_cols // 2
        elif 'e' in entrance_sides:
            facing, row, col = 'e', self.num_rows // 2, self.num_cols - 1
        else:
            facing = next(iter(entrance_sides))
            row, col = self.num_rows // 2, self.num_cols // 2
        self.make_entrance(row, col, facing)
        return (row, col, facing)

    def _cut_c_shape(self, facing):
        # cut out an area of empty space on the center of one side to create a U/C shape
        if facing == 'n':
            row_min = 0
            row_max = random.randint(2,self.num_rows//4)
            col_min = random.randint(self.num_cols//4, self.num_cols//2)
            col_max = random.randint(3*self.num_cols//4,self.num_cols-1)
            center_row = row_max
            center_col =  (col_min + col_max)//2
        elif facing == 'e':
            col_max = self.num_cols
            col_min = random.randint(3*self.num_cols//4,self.num_cols-2)
            row_min = random.randint(self.num_rows//4, self.num_rows//2)
            row_max = random.randint(3*self.num_rows//4,self.num_rows-1)
            center_row = (row_min + row_max)//2
            center_col =  col_min - 1
        elif facing == 's':
            row_max = self.num_rows
            row_min = random.randint(3*self.num_rows//4,self.num_rows-2)
            col_min = random.randint(self.num_cols//4, self.num_cols//2)
            col_max = random.randint(3*self.num_cols//4,self.num_cols-1)
            center_row = row_min - 1
            center_col =  (col_min + col_max)//2
        elif facing == 'w':
            col_min = 0
            col_max = random.randint(2,self.num_cols//4)
            row_min = random.randint(self.num_rows//4, self.num_rows//2)
            row_max = random.randint(3*self.num_rows//4,self.num_rows-1)
            center_row = (row_min + row_max)//2
            center_col =  col_max
        self.set_room_state(row_min,row_max,col_min,col_max,0,False)
        return center_row, center_col

    def _shape_c_shape(self, entrance_sides):
        candidates = [s for s in ('n','e','s','w') if s in entrance_sides]
        if not candidates:
            facing = random.choice(('n','e','s','w'))
            self._cut_c_shape(facing)
            return self.auto_entrance(sides=entrance_sides)
        facing = random.choice(candidates)
        center_row, center_col = self._cut_c_shape(facing)
        self.make_entrance(center_row, center_col, facing)
        return (center_row, center_col, facing)

    def _cut_l_shape(self):
        # remove one full quadrant, leaving an L-shaped footprint. row_split/
        # col_split each sit in [3/8, 5/8] of the grid, so for grids >=8x8 the
        # remaining south/east edge always has a run of >= 3 cells (verified
        # by hand: the worst case, the 'se' corner, leaves partial south/east
        # runs of length row_split/col_split, whose randint lower bound
        # 3*size//8 is already >= 3 for size >= 8).
        row_split = random.randint(self.num_rows * 3 // 8, self.num_rows * 5 // 8)
        col_split = random.randint(self.num_cols * 3 // 8, self.num_cols * 5 // 8)
        corner = random.choice(('nw', 'ne', 'sw', 'se'))
        row_min, row_max = (0, row_split) if corner[0] == 'n' else (row_split, self.num_rows)
        col_min, col_max = (0, col_split) if corner[1] == 'w' else (col_split, self.num_cols)
        self.set_room_state(row_min, row_max, col_min, col_max, 0, False)

    def _shape_l_shape(self, entrance_sides):
        self._cut_l_shape()
        return self.auto_entrance(sides=entrance_sides)

    def _cut_h_shape(self):
        # two notches on opposite sides, leaving a connecting bridge (an H, or
        # its 90-degree transpose). Verified by hand: for axis 'ns' the east
        # edge is never touched by either notch (both stop at leg_col_max <
        # num_cols), so it's always a full-length run; for axis 'ew' the south
        # edge is never touched (the bottom bar spans full width), so it's
        # always a full-length run. auto_entrance(sides=('s','e')) is always
        # safe regardless of axis.
        axis = random.choice(('ns', 'ew'))
        if axis == 'ns':
            leg_col_min = random.randint(self.num_cols // 4, self.num_cols * 3 // 8)
            leg_col_max = random.randint(self.num_cols * 5 // 8, self.num_cols * 3 // 4)
            bar_row_min = random.randint(self.num_rows * 3 // 8, self.num_rows // 2 - 1)
            bar_row_max = random.randint(self.num_rows // 2 + 1, self.num_rows * 5 // 8)
            self.set_room_state(0, bar_row_min, leg_col_min, leg_col_max, 0, False)
            self.set_room_state(bar_row_max, self.num_rows, leg_col_min, leg_col_max, 0, False)
        else:
            leg_row_min = random.randint(self.num_rows // 4, self.num_rows * 3 // 8)
            leg_row_max = random.randint(self.num_rows * 5 // 8, self.num_rows * 3 // 4)
            bar_col_min = random.randint(self.num_cols * 3 // 8, self.num_cols // 2 - 1)
            bar_col_max = random.randint(self.num_cols // 2 + 1, self.num_cols * 5 // 8)
            self.set_room_state(leg_row_min, leg_row_max, 0, bar_col_min, 0, False)
            self.set_room_state(leg_row_min, leg_row_max, bar_col_max, self.num_cols, 0, False)

    def _shape_h_shape(self, entrance_sides):
        self._cut_h_shape()
        return self.auto_entrance(sides=entrance_sides)
    
    @staticmethod
    def step(row,col,direction):
        if direction == 'n':
            return (row-1,col)
        elif direction == 's':
            return (row+1,col)
        elif direction == 'e':
            return (row,col+1)
        elif direction == 'w':
            return (row,col-1)
        else:
            return (row,col)


    def find_possible_new_doorways(self,min_row,max_row,min_col,max_col):
        # max_row and max_col are the larges index that contain the room.
        # If the room touches the boundary of the maze, that side cannot have a doorway.
        # Doors may be be at any side of the room if they do not violate any other conditions.
        # if the room has an odd length on that side, the door must be at the center cell
        # if the room has an even length, place two doors. The doors may not be at corners.
        # If the size is six or more, leave space between doors. 
        # A door must not lead into empty space (value 0 in the rooms array).
        possible_doors = []
        # North side
        if min_row > 0:
            length = max_col - min_col + 1
            if length % 2 == 1:
                door_col = (min_col + max_col) // 2
                if self.rooms[min_row-1][door_col] != 0:
                    possible_doors.append( (min_row, door_col, 'n') )
            elif length > 2:
                door_col1 = (min_col + max_col) // 2
                door_col2 = door_col1 + 1
                if length >= 6:
                    door_col1 -= 1
                    door_col2 += 1
                if self.rooms[min_row-1][door_col1] != 0:
                    possible_doors.append( (min_row, door_col1, 'n') )
                if self.rooms[min_row-1][door_col2] != 0:
                    possible_doors.append( (min_row, door_col2, 'n') )
        # South side
        if max_row < self.num_rows - 1:
            length = max_col - min_col + 1
            if length % 2 == 1:
                door_col = (min_col + max_col) // 2
                if self.rooms[max_row+1][door_col] != 0:
                    possible_doors.append( (max_row+1, door_col, 's') )
            elif length > 2:
                door_col1 = (min_col + max_col) // 2
                door_col2 = door_col1 + 1
                if length >= 6:
                    door_col1 -= 1
                    door_col2 += 1
                if self.rooms[max_row+1][door_col1] != 0:
                    possible_doors.append( (max_row+1, door_col1, 's') )
                if self.rooms[max_row+1][door_col2] != 0:
                    possible_doors.append( (max_row+1, door_col2, 's') )
        # West side
        if min_col > 0:
            length = max_row - min_row + 1
            if length % 2 == 1:
                door_row = (min_row + max_row) // 2
                if self.rooms[door_row][min_col-1] != 0:
                    possible_doors.append( (door_row, min_col, 'w') )
            elif length > 2:
                door_row1 = (min_row + max_row) // 2
                door_row2 = door_row1 + 1
                if length >= 6:
                    door_row1 -= 1
                    door_row2 += 1
                if self.rooms[door_row1][min_col-1] != 0:
                    possible_doors.append( (door_row1, min_col, 'w') )
                if self.rooms[door_row2][min_col-1] != 0:
                    possible_doors.append( (door_row2, min_col, 'w') )
        # East side
        if max_col < self.num_cols - 1:
            length = max_row - min_row + 1
            if length % 2 == 1:
                door_row = (min_row + max_row) // 2
                if self.rooms[door_row][max_col+1] != 0:
                    possible_doors.append( (door_row, max_col+1, 'e') )
            elif length > 2:
                door_row1 = (min_row + max_row) // 2
                door_row2 = door_row1 + 1
                if length >= 6:
                    door_row1 -= 1
                    door_row2 += 1
                if self.rooms[door_row1][max_col+1] != 0:
                    possible_doors.append( (door_row1, max_col+1, 'e') )
                if self.rooms[door_row2][max_col+1] != 0:
                    possible_doors.append( (door_row2, max_col+1, 'e') )
        return possible_doors

    def get_8_neighbours(self,row,colum):
        """Return a generator over the (up to) eight neighbours of a cell.

        This yields the coordinates (r, c) for each 8-connected neighbour of the
        cell located at (row, colum). Neighbours that fall outside the maze
        bounds [0..num_rows-1] x [0..num_cols-1] are not returned.

        Parameters:
            row (int): Row index of the source cell.
            colum (int): Column index of the source cell.

        Yields:
            tuple[int, int]: A pair (r, c) representing the row and column of a
                             neighbouring cell. Up to eight neighbours are yielded
                             in no particular order.

        Example:
            list(self.get_8_neighbours(1, 1)) -> [(0,0),(0,1),(0,2),(1,0),(1,2),(2,0),(2,1),(2,2)]
        """
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r = row + dr
                c = colum + dc
                if 0 <= r < self.num_rows and 0 <= c < self.num_cols:
                    yield (r, c)


    def place_light_shafts(self, max_shafts=4, size_range=(1, 2),
                           min_dist_outside=4, min_dist_between=4, rng=None,
                           protected_cells=frozenset()):
        """Place up to `max_shafts` rectangular light-shaft regions (states
        9-12), each a random w x h block (w, h independently drawn from
        size_range). A shaft's distance to the outside / to another shaft is
        the shortest 4-connected path in cells from ANY cell of its footprint
        (multi-source BFS), generalizing the original single-cell spacing
        rule. Constraints: dist-to-outside >= min_dist_outside, dist-to-other-
        shafts >= min_dist_between. Placement is greedy: the deepest-from-
        outside valid candidate is taken first (ties broken randomly); once a
        shaft is placed, the next must respect spacing to it. Each placed
        shaft is walled in via contain_room (its cells are then excluded from
        the walkable-corridor graph and from every floor above it, see
        gen_rooms/fromMaze). `protected_cells` (e.g. a forced stair landing)
        are never claimed by a shaft -- a shaft turns a cell non-walkable, so
        claiming a forced cell would silently break whatever guarantee forced
        it in the first place."""
        from collections import deque
        rng = rng or random

        def _bfs_dists(seeds, blocked):
            """Multi-source BFS from `seeds` over state==1 cells; returns the
            shortest distance to (a) the outside (edge or state-0 cell) and
            (b) any cell in `blocked` (another shaft)."""
            q = deque((r, c, 0) for (r, c) in seeds)
            seen = set(seeds)
            dist_out = dist_blocked = float('inf')
            while q:
                r, c, d = q.popleft()
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < self.num_rows and 0 <= nc < self.num_cols) \
                       or self.rooms[nr][nc] == 0:
                        dist_out = min(dist_out, d + 1)
                        continue
                    if (nr, nc) in blocked:
                        dist_blocked = min(dist_blocked, d + 1)
                        continue
                    if (nr, nc) in seen or self.rooms[nr][nc] != 1:
                        continue
                    seen.add((nr, nc))
                    q.append((nr, nc, d + 1))
            return dist_out, dist_blocked

        # Existing shafts (e.g. from a prior call) block new placements too.
        placed_cells = {(r, c) for r in range(self.num_rows) for c in range(self.num_cols)
                        if 9 <= self.rooms[r][c] <= 12}
        existing_values = {self.rooms[r][c] for (r, c) in placed_cells}
        next_value = min(existing_values, default=8) + 1 if existing_values else 9

        for val in range(next_value, min(13, next_value + max_shafts)):
            candidates = []
            for r in range(self.num_rows):
                for c in range(self.num_cols):
                    for w in range(size_range[0], size_range[1] + 1):
                        for h in range(size_range[0], size_range[1] + 1):
                            if r + h > self.num_rows or c + w > self.num_cols:
                                continue
                            block = [(rr, cc) for rr in range(r, r + h) for cc in range(c, c + w)]
                            if any(self.rooms[rr][cc] != 1 or (rr, cc) in protected_cells for rr, cc in block):
                                continue
                            dist_out, dist_blocked = _bfs_dists(block, placed_cells)
                            if dist_out < min_dist_outside or dist_blocked < min_dist_between:
                                continue
                            candidates.append((dist_out, r, c, w, h))
            if not candidates:
                break
            best_dist = max(t[0] for t in candidates)
            best = [t for t in candidates if t[0] == best_dist]
            _, r, c, w, h = rng.choice(best)
            self.set_room_state(r, r + h, c, c + w, val, False)
            self.contain_room(val)
            placed_cells |= {(rr, cc) for rr in range(r, r + h) for cc in range(c, c + w)}

    def _find_basin_site(self, rng=None):
        """Return (entrance_row, entrance_col, direction, orientation) for a
        random valid 2x2 pocket of state==1 cells not touching the maze edge,
        or None if no such pocket is found within a bounded number of tries."""
        rng = rng or random
        for _ in range(20):
            r = rng.randint(1, self.num_rows - 2)
            c = rng.randint(1, self.num_cols - 2)
            if self.rooms[r][c] != 1:
                continue
            direction = rng.choice(('n', 'e', 's', 'w'))
            orientation = rng.choice(('cw', 'ccw'))
            offsets = {'cw':  {'n': [1, -1], 'e': [-1, -1], 's': [-1, 1], 'w': [1, 1]},
                       'ccw': {'n': [1, 1],  'e': [1, -1],  's': [-1, -1], 'w': [-1, 1]}}
            dr, dc = offsets[orientation][direction]
            rows = [r, r + dr]
            cols = [c, c + dc]
            if not (0 <= min(rows) and max(rows) < self.num_rows - 1
                    and 0 <= min(cols) and max(cols) < self.num_cols - 1):
                continue
            if all(self.rooms[rr][cc] == 1 for rr in range(min(rows), max(rows) + 1)
                   for cc in range(min(cols), max(cols) + 1)):
                return (r, c, direction, orientation)
        return None

    def place_lustral_basins(self, max_basins=1, probability=0.3, rng=None):
        """Randomly site and carve up to `max_basins` lustral basins (see
        make_lustral_basin), each independently at `probability` chance."""
        rng = rng or random
        placed = 0
        for _ in range(max_basins):
            if rng.random() >= probability:
                continue
            site = self._find_basin_site(rng)
            if site is None:
                break
            self.make_lustral_basin(*site)
            placed += 1
        return placed


    def _place_explicit_rooms(self, max_rooms=None, width_range=(2,4), max_size_range=(3,6), rng=None):
        """Place up to `max_rooms` rectangular rooms (ids 2..8) via expand_room,
        seeded at random still-unassigned (state==1) cells. Whatever
        expand_room produces (including a trivially small room) is kept as-is:
        expand_room's own contain_room(id) call already sets wall boundaries
        when it places cells, so undoing a placement after the fact would also
        need to revert those boundaries -- simplest and correct is to just
        accept the result."""
        rng = rng or random
        id_start, id_end = 2, 8
        if max_rooms is None:
            free = sum(row.count(1) for row in self.rooms)
            max_rooms = max(1, min(id_end - id_start + 1, free // 16))
        placed_ids = []
        next_id = id_start
        attempts_per_room = 6
        while next_id <= min(id_end, id_start + max_rooms - 1):
            for _ in range(attempts_per_room):
                free_cells = [(r, c) for r in range(self.num_rows) for c in range(self.num_cols)
                              if self.rooms[r][c] == 1]
                if not free_cells:
                    return placed_ids
                row, col = rng.choice(free_cells)
                direction = rng.choice('nesw')
                width = rng.randint(*width_range)
                max_size = rng.randint(*max_size_range)
                bbox = self.expand_room(row, col, width, direction, max_size, next_id)
                if bbox != 0:
                    placed_ids.append(next_id)
                    break
            next_id += 1
        return placed_ids

    _WALKABLE_ROOM_MAX = 8

    def _is_walkable_state(self, v):
        """Plain corridor/unassigned cells, rooms, and stairs are walkable
        corridors for connectivity purposes; light shafts, basins, and
        entrance-stair cells are self-contained / not meant to be walked
        through as ordinary corridors."""
        return v == 1 or 2 <= v <= self._WALKABLE_ROOM_MAX or 20 <= v <= 99

    def _walkable_components(self):
        """Flood-fill over walkable cells using currently-open ('air'/'door')
        boundaries as edges. Returns a list of sets of (row,col)."""
        visited = set()
        components = []
        for row in range(self.num_rows):
            for col in range(self.num_cols):
                if (row, col) in visited or not self._is_walkable_state(self.rooms[row][col]):
                    continue
                comp = set()
                stack = [(row, col)]
                while stack:
                    r, c = stack.pop()
                    if (r, c) in comp:
                        continue
                    comp.add((r, c))
                    visited.add((r, c))
                    for d in 'nesw':
                        if self.get_wall(r, c, d) in ('air', 'door'):
                            nr, nc = Maze.step(r, c, d)
                            if 0 <= nr < self.num_rows and 0 <= nc < self.num_cols \
                               and self._is_walkable_state(self.rooms[nr][nc]) and (nr, nc) not in comp:
                                stack.append((nr, nc))
                components.append(comp)
        return components

    def _connect_via_light_shafts(self, components, rng=None):
        """Fallback for a light shaft that happens to sit on the sole
        1-cell-wide connector between two areas: since shaft cells are
        excluded from the walkable graph, the normal merge pass can't reach
        across one. For every light-shaft room (cells sharing one state value
        9-12) wall-adjacent to >=2 different remaining components, open one
        door from the shaft into each -- turning the shaft into a connector
        hub, reusing its own walls (already placed by contain_room)."""
        comp_of = {cell: i for i, comp in enumerate(components) for cell in comp}
        shafts = defaultdict(list)
        for r in range(self.num_rows):
            for c in range(self.num_cols):
                if 9 <= self.rooms[r][c] <= 12:
                    shafts[self.rooms[r][c]].append((r, c))
        for cells in shafts.values():
            touched = {}   # component index -> (row, col, direction) to open
            for (row, col) in cells:
                for d in 'nesw':
                    nr, nc = Maze.step(row, col, d)
                    if (nr, nc) in comp_of and self.get_wall(row, col, d) == 'wall':
                        touched.setdefault(comp_of[(nr, nc)], (row, col, d))
            if len(touched) >= 2:
                for (row, col, d) in touched.values():
                    self.set_wall(row, col, d, 'door')

    def ensure_connectivity(self, rng=None, is_ground_floor=True):
        """Guarantee every walkable cell is reachable from every other: union-
        find the walkable components together by opening ('wall'->'door') one
        boundary per merge, from a candidate list of every wall-adjacent
        walkable pair collected up front (so union-find doesn't need "fresh"
        edges after each merge -- one pass suffices as long as the walkable
        adjacency graph, ignoring current boundary type, is itself connected,
        which it always is for a single carved footprint). On the ground floor
        only, falls back to `_connect_via_light_shafts` for any pocket a light
        shaft was the sole (now excluded) connector for."""
        rng = rng or random
        components = self._walkable_components()
        if len(components) <= 1:
            return

        comp_of = {}
        for i, comp in enumerate(components):
            for cell in comp:
                comp_of[cell] = i
        parent = list(range(len(components)))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        candidates = []
        for row in range(self.num_rows):
            for col in range(self.num_cols):
                if not self._is_walkable_state(self.rooms[row][col]):
                    continue
                i = comp_of[(row, col)]
                for d in ('e', 's'):
                    nr, nc = Maze.step(row, col, d)
                    if 0 <= nr < self.num_rows and 0 <= nc < self.num_cols \
                       and self._is_walkable_state(self.rooms[nr][nc]) \
                       and self.get_wall(row, col, d) == 'wall':
                        j = comp_of[(nr, nc)]
                        if i != j:
                            candidates.append((row, col, d, i, j))
        rng.shuffle(candidates)

        roots = {find(i) for i in range(len(components))}
        for (row, col, d, i, j) in candidates:
            if len(roots) <= 1:
                break
            ri, rj = find(i), find(j)
            if ri == rj:
                continue
            self.set_wall(row, col, d, 'door')
            parent[ri] = rj
            roots.discard(ri)

        if len(roots) > 1 and is_ground_floor:
            self._connect_via_light_shafts(self._walkable_components(), rng)

    def _add_extra_doors(self, rng=None, probability=0.2):
        """After connectivity is guaranteed, probabilistically open additional
        'wall' boundaries between two walkable cells into 'door' -- liberal
        doorways beyond the bare reachability minimum, for visual variety
        (their eroded lintels look good after decay_texture)."""
        rng = rng or random
        if probability <= 0:
            return
        for row in range(self.num_rows):
            for col in range(self.num_cols):
                if not self._is_walkable_state(self.rooms[row][col]):
                    continue
                for d in ('e', 's'):
                    nr, nc = Maze.step(row, col, d)
                    if not (0 <= nr < self.num_rows and 0 <= nc < self.num_cols):
                        continue
                    if not self._is_walkable_state(self.rooms[nr][nc]):
                        continue
                    if self.get_wall(row, col, d) == 'wall' and rng.random() < probability:
                        self.set_wall(row, col, d, 'door')

    def footprint_area(self):
        return sum(1 for row in self.rooms for v in row if v != 0)

    def footprint_cells(self):
        return {(r, c) for r in range(self.num_rows) for c in range(self.num_cols)
                if self.rooms[r][c] != 0}

    def _restrict_footprint(self, allowed_cells):
        """Zero out every cell not in allowed_cells (used to seed an upper
        floor's footprint as a subset of the floor below)."""
        for r in range(self.num_rows):
            for c in range(self.num_cols):
                if (r, c) not in allowed_cells:
                    self.rooms[r][c] = 0

    def terrace_cells(self, upper_maze):
        """This floor's footprint cells not covered by `upper_maze` (or the
        whole footprint if upper_maze is None) -- the part of this floor's
        roof left exposed as an accessible terrace."""
        ground = self.footprint_cells()
        if upper_maze is None:
            return ground
        return ground - upper_maze.footprint_cells()

    def parapet_boundaries(self, upper_maze, terrace_cells):
        """Yield (row, col, direction) for every terrace_cells edge that faces
        true exterior (out of bounds or this floor's own state==0), excluding
        edges that face upper_maze's own footprint (that boundary is already
        served by the upper floor's own exterior wall -- no double parapet)."""
        for (row, col) in terrace_cells:
            for d, (dr, dc) in (('n', (-1, 0)), ('s', (1, 0)), ('w', (0, -1)), ('e', (0, 1))):
                nr, nc = row + dr, col + dc
                if 0 <= nr < self.num_rows and 0 <= nc < self.num_cols:
                    if (nr, nc) in terrace_cells:
                        continue
                    if upper_maze is not None and upper_maze.rooms[nr][nc] != 0:
                        continue
                yield (row, col, d)

    # Fill the maze with larger rooms. These can be both regular rooms and special room types
    # such as stairs, lustral basins or light shafts
    def gen_rooms(self, *, shape="random", entrance_sides=('s', 'e'), entrance_cell=None,
                  allowed_cells=None, forced_cells=None,
                  max_explicit_rooms=None, room_width_range=(2, 4), room_max_size_range=(3, 6),
                  use_sidewinder=True, door_probability=0.2,
                  place_shafts=True, max_shafts=2, shaft_size_range=(1, 2),
                  shaft_min_dist_outside=4, shaft_min_dist_between=4,
                  place_basins=True, basin_probability=0.3, max_basins=1,
                  rng=None):
        """Fill the maze with rooms, corridors, doors, light shafts and
        lustral basins, guaranteeing every walkable cell is reachable. Two
        modes:
          - ground-floor mode (entrance_cell=None): carves the exterior shape
            and an entrance via make_foundation(shape, entrance_sides).
          - upper-floor mode (entrance_cell given): the caller has already
            constrained the footprint (allowed_cells/forced_cells); no
            exterior entrance is carved, entrance_cell roots reachability."""
        rng = rng or random
        is_ground_floor = entrance_cell is None
        if is_ground_floor:
            center_row, center_col, facing = self.make_foundation(shape=shape, entrance_sides=entrance_sides)
            self.contain_maze()
            entrance_interior = Maze.step(center_row, center_col, opposite[facing])
        else:
            if allowed_cells is not None:
                self._restrict_footprint(allowed_cells)
            if forced_cells:
                for (r, c) in forced_cells:
                    self.rooms[r][c] = 1
            self.contain_maze()
            entrance_interior = entrance_cell

        if place_shafts:
            self.place_light_shafts(max_shafts=max_shafts, size_range=shaft_size_range,
                                    min_dist_outside=shaft_min_dist_outside,
                                    min_dist_between=shaft_min_dist_between, rng=rng,
                                    protected_cells=forced_cells or frozenset())
        if place_basins:
            self.place_lustral_basins(max_basins=max_basins, probability=basin_probability, rng=rng)

        self._place_explicit_rooms(max_rooms=max_explicit_rooms, width_range=room_width_range,
                                   max_size_range=room_max_size_range, rng=rng)
        if use_sidewinder:
            self.sidewinder(1, rng=rng)

        self.ensure_connectivity(rng=rng, is_ground_floor=is_ground_floor)
        self._add_extra_doors(rng=rng, probability=door_probability)

        if forced_cells:
            for (r, c) in forced_cells:
                assert self._is_walkable_state(self.rooms[r][c]), \
                    f"forced cell {(r, c)} ended up non-walkable (state={self.rooms[r][c]})"

    def set_room_state(self,row_min,row_max,col_min,col_max,state=0,walls = False,doors = "d.d."):
        for row in range(row_min,row_max):
            for col in range(col_min,col_max):
                self.rooms[row][col] = state
        if walls:
            # North
            col_middle = (col_min+col_max-1)/2
            row_middle = (row_min+row_max-1)/2
            for col in range(col_min,col_max):
                if doors[0] != 'd' or (col != math.floor(col_middle) and col != math.ceil(col_middle) ) :
                    self.horizontal_boundaries[row_min][col].boundary_type = 'wall'
                else:
                    self.horizontal_boundaries[row_min][col].boundary_type = 'door'
            # South
            for col in range(col_min,col_max):
                if doors[2] != 'd' or (col != math.floor(col_middle) and col != math.ceil(col_middle) ) :
                    self.horizontal_boundaries[row_max][col].boundary_type = 'wall'
                else:
                    self.horizontal_boundaries[row_max][col].boundary_type = 'door'
            # West
            for row in range(row_min,row_max):
                if doors[3] != 'd' or (row != math.floor(row_middle) and row != math.ceil(row_middle) ) :
                    self.vertical_boundaries[row][col_min].boundary_type = 'wall'
                else:
                    self.vertical_boundaries[row][col_min].boundary_type = 'door'
             # East
            for row in range(row_min,row_max):
                if doors[1] != 'd' or (row != math.floor(row_middle) and row != math.ceil(row_middle) ) :
                    self.vertical_boundaries[row][col_max].boundary_type = 'wall'
                else:
                    self.vertical_boundaries[row][col_max].boundary_type = 'door'

    def _enclosing_boundaries(self, cell_set):
        """Yield (orientation, row, col) boundary coords enclosing `cell_set`
        (a set of (row,col)) against everything not in it, including the maze
        edge."""
        for (row, col) in cell_set:
            if row == 0 or (row - 1, col) not in cell_set:
                yield ('horizontal', row, col)
            if row == self.num_rows - 1 or (row + 1, col) not in cell_set:
                yield ('horizontal', row + 1, col)
            if col == 0 or (row, col - 1) not in cell_set:
                yield ('vertical', row, col)
            if col == self.num_cols - 1 or (row, col + 1) not in cell_set:
                yield ('vertical', row, col + 1)

    def get_enclosing_walls(self):
        """Yield (boundary_type, row, col) for boundaries enclosing the still-
        unassigned (state==1) footprint."""
        cells = {(r, c) for r in range(self.num_rows) for c in range(self.num_cols)
                 if self.rooms[r][c] == 1}
        yield from self._enclosing_boundaries(cells)

    def contain_maze(self):
        """Surround the non zero cells with walls, such that cells with value 1 have a wall at the boundary facing a cell with value 0 or the edge of the domain."""
        for boundary_type, row, col in self.get_enclosing_walls():
            if boundary_type == 'horizontal':
                self.horizontal_boundaries[row][col].boundary_type = 'wall'
            elif boundary_type == 'vertical':
                self.vertical_boundaries[row][col].boundary_type = 'wall'
    
    def contain_room(self,draw_state):
        """Surround the cells with the given draw_state by replacing air with walls (leaving doors unchanged), such that cells with value draw_state have a wall at the boundary facing a cell with value != draw_state."""
    # iterate over all cells
        for row in range(self.num_rows):
            for col in range(self.num_cols):
                if self.rooms[row][col] == draw_state:
                    # check north
                    if row == 0 or self.rooms[row-1][col] != draw_state:
                        if self.get_wall(row,col,'n') == 'air':
                            self.set_wall(row,col,'n','wall')
                    # check south
                    if row == self.num_rows - 1 or self.rooms[row+1][col] != draw_state:
                        if self.get_wall(row,col,'s') == 'air':
                            self.set_wall(row,col,'s','wall')
                    # check west
                    if col == 0 or self.rooms[row][col-1] != draw_state:
                        if self.get_wall(row,col,'w') == 'air':
                            self.set_wall(row,col,'w','wall')
                    # check east
                    if col == self.num_cols - 1 or self.rooms[row][col+1] != draw_state:
                        if self.get_wall(row,col,'e') == 'air':
                            self.set_wall(row,col,'e','wall')

    def fill_with_walls(self,draw_state):
        for row in range(self.num_rows):
            for col in range(self.num_cols):
                if self.rooms[row][col] == draw_state:
                    if row!=0 and self.rooms[row-1][col] == draw_state:
                        self.horizontal_boundaries[row][col].boundary_type = 'wall'
                    if col!=0 and self.rooms[row][col-1] == draw_state:
                        self.vertical_boundaries[row][col].boundary_type = 'wall'
                            
    def sidewinder(self,draw_state,rng=None):
        """ Generate a maze using the sidewinder algorithm. Only consider rooms that have a state given by draw_state as accessible.
        `rng` exposes .choice(seq) (default: the shared `random` module) -- no
        internal reseeding, so callers control reproducibility themselves
        (e.g. one random.seed(...) up front, or pass a random.Random instance)."""
        rng = rng or random
        # initialize all boundaries between rooms that are eqaul draws_state as walls
        self.fill_with_walls(draw_state)

        for row in range(self.num_rows):
            run = []
            for col in range(self.num_cols):
                if self.rooms[row][col] == draw_state:
                    at_eastern_boundary = (col == self.num_cols - 1) or (self.rooms[row][col+1] != draw_state)
                    at_northern_boundary = (row == 0) or (self.rooms[row-1][col] != draw_state)
                    if not at_northern_boundary:
                        run.append((row, col))
                    carve_east = (not at_eastern_boundary)  and (rng.choice([True, False])  or at_northern_boundary)
                    if carve_east:
                        # Carve east: open vertical boundary to the right
                        self.vertical_boundaries[row][col+1].boundary_type = 'air'
                    else:
                        # Carve north: pick a random cell from the run and open horizontal boundary above
                        if not at_northern_boundary:
                            carve_row, carve_col = rng.choice(run)
                            self.horizontal_boundaries[carve_row][carve_col].boundary_type = 'air'
                        run = []
                        
    def make_entrance(self,center_row,center_col,direction = "e"):
        match direction:
            case 'n':
                d_row = 0
                d_col = 1
                val = 180
            case 'e':
                d_row = 1
                d_col = 0
                val = 181
            case 's':
                d_row = 0
                d_col = -1
                val = 182
            case 'w':
                d_row = -1
                d_col = 0
                val = 183
        row = center_row - d_row
        col = center_col - d_col
        self.set_wall(row,col,left[direction],type='wall')
        self.set_wall(row,col,right[direction],type='air')
        for i in range(3):
            self.rooms[row][col] = val
            self.set_wall(row,col,direction,type='air')
            self.set_wall(row,col,opposite[direction],type='wall')
            row = row + d_row
            col = col + d_col
        row = center_row + d_row
        col = center_col + d_col
        self.set_wall(row,col,right[direction],type='wall')
        self.set_wall(row,col,left[direction],type='air')
        self.set_wall(center_row,center_col,opposite[direction],type='door')
                        
    _STAIR_BASE = {'n': 20, 'e': 40, 's': 60, 'w': 80}

    def unused_stair_state(self, direction):
        """Smallest free room-state value in `direction`'s 20-wide bracket
        (base..base+19) not already used by an existing flight on this floor
        -- lets multiple distinct flights share a direction without
        fromMaze's group-by-exact-value flight logic merging them."""
        base = self._STAIR_BASE[direction]
        used = {self.rooms[r][c] for r in range(self.num_rows) for c in range(self.num_cols)
                if base <= self.rooms[r][c] < base + 20}
        for offset in range(20):
            if base + offset not in used:
                return base + offset
        raise RuntimeError(f"no free stair state in the '{direction}' bracket")

    def make_stairs(self,start_row,start_col,direction="e",shape = "straight", length=2, state_value=None):
        """ create a flight of stairs starting at the given point and leading up in the given direction,
        stairs are bordered by walls. `state_value`, if given, overrides the
        flight's room-state value (must stay within `direction`'s 20-wide
        bracket, e.g. via unused_stair_state, so fromMaze's direction dispatch
        still resolves correctly)."""
        row = start_row
        col = start_col
        match direction:
            case 'n':
                d_row = -1
                d_col = 0
                val = 20
            case 'e':
                d_row = 0
                d_col = 1
                val = 40
            case 's':
                d_row = 1
                d_col = 0
                val = 60
            case 'w':
                d_row = 0
                d_col = -1
                val = 80
        if state_value is not None:
            val = state_value
        for i in range(length):
            if d_col == 0:
                self.horizontal_boundaries[row][col].boundary_type = 'air'
                self.set_wall(row,col,direction='w',type='wall')
                self.set_wall(row,col,direction='e',type='wall')
            if d_row == 0:
                self.vertical_boundaries[row][col].boundary_type = 'air'
                self.set_wall(row,col,direction='n',type='wall')
                self.set_wall(row,col,direction='s',type='wall')    
            self.rooms[row][col] = val
            row += d_row
            col += d_col
            # A second flight in the same direction needs its own state_value
            # (see unused_stair_state) so fromMaze's group-by-exact-value
            # flight logic doesn't merge the two footprints.

    def find_stair_site(self, length, rng=None, room_ids=None):
        """Find a straight run of `length` consecutive cells sharing one
        explicit room id (from room_ids, default: every id 2..8 present),
        oriented along one of n/e/s/w, such that every cell in the run is
        that same room id and the cell immediately behind the run's start is
        also that room id (a real point of entry from the rest of the room,
        not part of the run itself). Returns (start_row, start_col,
        direction) or None if no such site exists."""
        rng = rng or random
        if room_ids is None:
            room_ids = sorted({v for row in self.rooms for v in row if 2 <= v <= 8})
        candidates = []
        for room_id in room_ids:
            cells = {(r, c) for r in range(self.num_rows) for c in range(self.num_cols)
                    if self.rooms[r][c] == room_id}
            for (row, col) in cells:
                for direction in ('n', 'e', 's', 'w'):
                    run = [(row, col)]
                    r, c = row, col
                    ok = True
                    for _ in range(length - 1):
                        r, c = Maze.step(r, c, direction)
                        if (r, c) not in cells:
                            ok = False
                            break
                        run.append((r, c))
                    if not ok:
                        continue
                    br, bc = Maze.step(row, col, opposite[direction])
                    if (br, bc) in cells and (br, bc) not in run:
                        candidates.append((row, col, direction))
        if not candidates:
            return None
        return rng.choice(candidates)

    def make_lustral_basin(self,entrance_row,entrance_col,direction = 'e', orientation = 'ccw'):
        offsets = {'cw'  : { 'n':[ 1,-1], 'e':[-1,-1], 's':[-1, 1], 'w':[ 1, 1] },
                   'ccw' : { 'n':[ 1, 1], 'e':[ 1,-1], 's':[-1,-1], 'w':[-1, 1] } }

        inner_wall_offsets = {'cw'  : { 'n':0, 'e':0, 's':1, 'w':1 },
                   'ccw' : { 'n':1, 'e':1, 's':0, 'w':0 } }
        room_states = {'n': 100,'e': 110,'s': 120,'w': 130}
        
        state = room_states[direction]
        if orientation == 'cw':
            state += 40
            
        rows = [entrance_row,entrance_row + offsets[orientation][direction][0]]
        cols = [entrance_col,entrance_col + offsets[orientation][direction][1]]
        self.set_room_state(min(rows),max(rows)+1,min(cols),max(cols)+1,state,walls = True,doors = "....")
        # add the entrance and the wall separating the entrance from the basin itself.
        match direction:
            case 'n':
                self.horizontal_boundaries[min(rows)][entrance_col].boundary_type = 'air'
                self.vertical_boundaries[entrance_row][entrance_col+inner_wall_offsets[orientation][direction]].boundary_type = 'wall'
            case 'e':
                self.vertical_boundaries[entrance_row][max(cols)+1].boundary_type = 'air'
                self.horizontal_boundaries[entrance_row + inner_wall_offsets[orientation][direction]][entrance_col].boundary_type = 'wall'
            case 's':
                self.horizontal_boundaries[max(rows)+1][entrance_col].boundary_type = 'air'
                self.vertical_boundaries[entrance_row][entrance_col+inner_wall_offsets[orientation][direction]].boundary_type = 'wall'
            case 'w':
                self.vertical_boundaries[entrance_row][min(cols)].boundary_type = 'air'
                self.horizontal_boundaries[entrance_row + inner_wall_offsets[orientation][direction]][entrance_col].boundary_type = 'wall'
        
    def set_wall(self,row,col,direction='n',type='wall'):
        """ Set the wall of the room at row,col in the given direction to the given type """
        match direction:
            case 'n':
                self.horizontal_boundaries[row][col].boundary_type = type
            case 'e':
                self.vertical_boundaries[row][col+1].boundary_type = type
            case 's':
                self.horizontal_boundaries[row+1][col].boundary_type = type
            case 'w':
                self.vertical_boundaries[row][col].boundary_type = type 

    def get_wall(self,row,col,direction='n'):
        """ Get the wall of the room at row,col in the given direction """
        match direction:
            case 'n':
                return self.horizontal_boundaries[row][col].boundary_type
            case 'e':
                return self.vertical_boundaries[row][col+1].boundary_type
            case 's':
                return self.horizontal_boundaries[row+1][col].boundary_type
            case 'w':
                return self.vertical_boundaries[row][col].boundary_type                               
    
    def display(self):
        """ Display the maze using ASCII characters. Rooms are represented by "▢", 
        spaces that are not part of a room by "X", horizontal walls by "-", vertical walls by "|", and doors by ".". """
        for row in range(self.num_rows):
            #print(" ", end="")
            for col in range(self.num_cols):
                if self.horizontal_boundaries[row][col].boundary_type == 'wall':
                    print(' _', end="")
                elif self.horizontal_boundaries[row][col].boundary_type == 'door':
                    print(" .", end="")
                else:
                    print("  ", end="")
            print()
            for col in range(self.num_cols):
                if self.vertical_boundaries[row][col].boundary_type == 'wall':
                    print("|", end="")
                elif self.vertical_boundaries[row][col].boundary_type == 'door':
                    print(".", end="")
                else:
                    print(" ", end="")
                if self.rooms[row][col] != 0:
                    print("▢", end="")
                else:
                    print("X", end="")
                if col == self.num_cols - 1 and self.vertical_boundaries[row][col + 1].boundary_type == 'wall':
                    print("|", end="")
            print()
        #print(" ", end="")
        # Print the bottom boundary
        for col in range(self.num_cols):
            if self.horizontal_boundaries[self.num_rows][col].boundary_type == 'wall':
                print(' _', end="")
            elif self.horizontal_boundaries[self.num_rows][col].boundary_type == 'door':
                print(" .", end="")
            else:
                print("  ", end="")    
        print()

    def print_rooms(self):
        for row in range(self.num_rows):
            for col in range(self.num_cols):
                print(self.rooms[row][col], end="")
            print()


    def print_boundaries(self):
        """ Print the boundaries of the maze for debugging purposes. """
        print("Vertical Boundaries:")
        for row in self.vertical_boundaries:
            print(" ".join([boundary.boundary_type[0] for boundary in row]))
        print("Horizontal Boundaries:")
        for row in self.horizontal_boundaries:
            print(" ".join([boundary.boundary_type[0] for boundary in row]))


def _random_subfootprint(allowed_cells, must_include, rng, coverage=0.6):
    """BFS-grow a random connected subset of allowed_cells starting from
    must_include, to roughly `coverage` fraction of allowed_cells (jittered).
    Connected to must_include by construction -- unlike re-applying one of the
    whole-grid-relative _cut_xxx shape functions to a restricted footprint
    (which could trivially re-cut straight through a forced cell and isolate
    it with no walkable neighbour at all), this can never isolate the cells
    in must_include."""
    result = set(must_include)
    frontier = list(must_include)
    target = max(len(result), int(len(allowed_cells) * coverage * rng.uniform(0.5, 1.0)))
    while frontier and len(result) < target:
        rng.shuffle(frontier)
        r, c = frontier.pop()
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if (nr, nc) in allowed_cells and (nr, nc) not in result:
                result.add((nr, nc))
                frontier.append((nr, nc))
    return result


class Building:
    """Orchestrates 1-2 Maze floors + inter-floor stairs + roof access, ready
    for PositionGrid.fromBuilding. Deliberately capped at 2 floors (ground +
    one upper) per the current requirement, but every step here is phrased
    per-floor-transition so adding a 3rd floor later is a matter of looping
    the same "pick a landing, carve the next floor around it" step again."""

    def __init__(self, num_rows, num_cols):
        self.num_rows = num_rows
        self.num_cols = num_cols
        self.floors = []            # [ground_maze] or [ground_maze, upper_maze]
        self.stair_links = []       # [{from_floor, to_floor, landing, state_base}]
        self.roof_floor_index = 0
        self.roof_open_cells = set()
        self.roof_stair_state = None

    def generate(self, *, shape="random", entrance_sides=('s', 'e'),
                 floor2_area_threshold=50, stair_length=3,
                 roof_access="auto", rng_seed=None, **gen_rooms_kwargs):
        rng = random.Random(rng_seed) if rng_seed is not None else random

        ground = Maze(self.num_rows, self.num_cols)
        ground.gen_rooms(shape=shape, entrance_sides=entrance_sides, rng=rng, **gen_rooms_kwargs)
        self.floors.append(ground)

        if ground.footprint_area() >= floor2_area_threshold:
            site = ground.find_stair_site(stair_length, rng=rng)
            if site is not None:
                row, col, direction = site
                state_base = ground.unused_stair_state(direction)
                ground.make_stairs(row, col, direction, length=stair_length, state_value=state_base)
                landing = (row, col)
                for _ in range(stair_length - 1):
                    landing = Maze.step(*landing, direction)

                upper = Maze(self.num_rows, self.num_cols)
                allowed = _random_subfootprint(ground.footprint_cells(), {landing}, rng)
                # Lustral basins are a ground-floor-only feature (sunken pits
                # accessed via one fixed door); only light shafts punch
                # through to upper floors.
                upper_kwargs = {**gen_rooms_kwargs, 'place_basins': False}
                upper.gen_rooms(shape=shape, entrance_sides=entrance_sides,
                                entrance_cell=landing, allowed_cells=allowed,
                                forced_cells={landing}, rng=rng, **upper_kwargs)
                self.floors.append(upper)
                self.stair_links.append({'from_floor': 0, 'to_floor': 1,
                                          'landing': landing, 'state_base': state_base})

        self.roof_floor_index = len(self.floors) - 1
        self._place_roof_access(roof_access, rng)
        return self

    def _place_roof_access(self, mode, rng):
        top = self.floors[self.roof_floor_index]
        if mode == "auto":
            mode = rng.choice(("stairs", "hatch"))
        if mode == "none":
            return
        if mode == "stairs":
            site = top.find_stair_site(2, rng=rng)
            if site is not None:
                row, col, direction = site
                state_value = top.unused_stair_state(direction)
                top.make_stairs(row, col, direction, length=2, state_value=state_value)
                landing = Maze.step(row, col, direction)
                self.roof_open_cells.add(landing)
                self.roof_stair_state = state_value
                return
            mode = "hatch"   # fall back if no straight run available
        if mode == "hatch":
            candidates = [(r, c) for r in range(top.num_rows) for c in range(top.num_cols)
                          if top.rooms[r][c] == 1 or 2 <= top.rooms[r][c] <= 8]
            if candidates:
                self.roof_open_cells.add(rng.choice(candidates))

