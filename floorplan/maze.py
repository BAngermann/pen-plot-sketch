import math
import random
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
        self.rooms = [[1 for _ in range(num_cols)] for _ in range(num_rows)]
        self.vertical_boundaries = [[Boundary('air') for _ in range(num_cols + 1)] for _ in range(num_rows)]
        self.horizontal_boundaries = [[Boundary('air') for _ in range(num_cols)] for _ in range(num_rows + 1)]    
    
    
    def auto_entrance(self):
        ''' Create an entrance to the maze at the center of the longest outer wall (a wall that devides a room from empty space)'''
        # get the enclosing walls and iterate over the result to find the longest uninterrupted wall segment 
        horizontal_runs = {}
        vertical_runs = {}
        for boundary_type, row, col in self.get_enclosing_walls():
            if boundary_type == 'horizontal':
                if row not in horizontal_runs:
                    horizontal_runs[row] = []
                horizontal_runs[row].append(col)
            elif boundary_type == 'vertical':
                if col not in vertical_runs:
                    vertical_runs[col] = []
                vertical_runs[col].append(row)
        # iterate over the horizontal runs to find the longest with consecutive columns
        longest_horizontal = (0, 0, 0) # length, row, start_col
        for row, cols in horizontal_runs.items():
            cols.sort()
            start_col = cols[0]
            current_length = 1
            for i in range(1, len(cols)):
                if cols[i] == cols[i - 1] + 1:
                    current_length += 1
                else:
                    if current_length > longest_horizontal[0]:
                        longest_horizontal = (current_length, row, start_col)
                    start_col = cols[i]
                    current_length = 1
            if current_length > longest_horizontal[0]:
                longest_horizontal = (current_length, row, start_col)
        # iterate over the vertical runs to find the longest with consecutive rows
        longest_vertical = (0, 0, 0) # length, col, start_row
        for col, rows in vertical_runs.items():
            rows.sort()
            start_row = rows[0]
            current_length = 1
            for i in range(1, len(rows)):
                if rows[i] == rows[i - 1] + 1:
                    current_length += 1
                else:
                    if current_length > longest_vertical[0]:
                        longest_vertical = (current_length, col, start_row)
                    start_row = rows[i]
                    current_length = 1
            if current_length > longest_vertical[0]:
                longest_vertical = (current_length, col, start_row)
        # An enclosing wall always separates a room cell from empty space (or the
        # maze edge); the entrance is placed on the room side facing the gap. This
        # handles both maze-edge walls and interior walls (e.g. around cut-outs).
        def entrance_for_horizontal(row, col):
            below = self.rooms[row][col] if row < self.num_rows else 0
            if row == 0 or (row < self.num_rows and below != 0):
                return (row, col, 'n')          # empty/edge to the north
            return (row - 1, col, 's')          # empty/edge to the south

        def entrance_for_vertical(col, row):
            east = self.rooms[row][col] if col < self.num_cols else 0
            if col == 0 or (col < self.num_cols and east != 0):
                return (row, col, 'w')          # empty/edge to the west
            return (row, col - 1, 'e')          # empty/edge to the east

        # Create the entrance at the centre of the longest run (>= 3 cells).
        if longest_horizontal[0] >= longest_vertical[0] and longest_horizontal[0] >= 3:
            length, row, start_col = longest_horizontal
            entrance = entrance_for_horizontal(row, start_col + length // 2)
        elif longest_vertical[0] >= 3:
            length, col, start_row = longest_vertical
            entrance = entrance_for_vertical(col, start_row + length // 2)
        else:
            return None
        self.make_entrance(*entrance)
        return entrance
        
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
        


    def make_foundation(self):
        # start with a full maze and randomly cut out either
        # up to two corners of empty space 
        # or a central rectangular area of empty space 
        # or an area of empty space on the center of one side to create a U shape
        
        # create a ranom number between 0 and 2 to decide which pattern to use
        pattern = random.randint(0, 2)
        match pattern:
            case 0:
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
                center_row, center_col, facing = self.auto_entrance()
            case 1:
                # cut out a central rectangular area of empty space
                row_min = random.randint(2,self.num_rows//4)
                row_max = random.randint(3*self.num_rows//4,self.num_rows-2)
                col_min = random.randint(2,self.num_cols//4)
                col_max = random.randint(3*self.num_cols//4,self.num_cols-2)
                self.set_room_state(row_min,row_max,col_min,col_max,0,False)
                facing = 's'
                center_row = self.num_rows-1
                center_col = self.num_cols//2
                self.make_entrance(self.num_rows-1,self.num_cols//2,facing)
            case 2:
                # cut out an area of empty space on the center of one side to create a U shape
                facing = random.choice(['n','e','s','w'])
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
                self.make_entrance(center_row,center_col,facing)
        return (center_row, center_col,facing)
    
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


    def place_light_shaft(self):
        """Place light shafts in the maze.

        This will try to place light shafts with states 9,10,11,12. Any placed
        light-shaft cell must have at least 3 other room tiles between it and
        the outside of the maze (an out-of-bounds neighbour or a cell with
        value 0). In other words, the shortest path from the shaft cell to
        outside must be at least 4 steps. Also any two light shafts must have
        at least 3 other room tiles between them (shortest path between shafts
        >= 4).

        The placement is greedy: candidate cells that are deepest (largest
        distance to outside) are considered first; once a shaft is placed the
        next shaft must respect spacing to already-placed shafts.
        """

        # Helper: BFS to find distance from (r,c) to the nearest outside (out-of-bounds
        # or a cell with value 0). We treat stepping into an out-of-bounds or a 0 cell
        # as reaching outside; return number of steps to reach that cell.
        from collections import deque

        def _dist_to_outside(sr, sc):
            q = deque()
            q.append((sr, sc, 0))
            seen = {(sr, sc)}
            while q:
                r, c, d = q.popleft()
                # explore 4-connected neighbours
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    # stepping out of bounds reaches outside at distance d+1
                    if not (0 <= nr < self.num_rows and 0 <= nc < self.num_cols):
                        return d + 1
                    if self.rooms[nr][nc] == 0:
                        return d + 1
                    if (nr, nc) in seen:
                        continue
                    seen.add((nr, nc))
                    q.append((nr, nc, d + 1))
            # If we never reach a zero or edge, return a large number
            return float('inf')

        # Helper: BFS to find shortest distance from (sr,sc) to any cell in shafts_set
        def _dist_to_nearest_shaft(sr, sc, shafts_set):
            if not shafts_set:
                return float('inf')
            q = deque()
            q.append((sr, sc, 0))
            seen = {(sr, sc)}
            while q:
                r, c, d = q.popleft()
                if (r, c) in shafts_set:
                    return d
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < self.num_rows and 0 <= nc < self.num_cols):
                        continue
                    if self.rooms[nr][nc] == 0:
                        continue
                    if (nr, nc) in seen:
                        continue
                    seen.add((nr, nc))
                    q.append((nr, nc, d + 1))
            return float('inf')

        # Collect existing shafts (values 9..12) so we don't overwrite and so new shafts respect spacing
        existing_shafts = set()
        max_existing = 8
        for r in range(self.num_rows):
            for c in range(self.num_cols):
                v = self.rooms[r][c]
                if 9 <= v <= 12:
                    existing_shafts.add((r, c))
                    max_existing = max(max_existing, v)

        next_value = 9
        # If there are existing shafts, set next_value to one higher than the max present (but no more than 12)
        if existing_shafts:
            highest = max(self.rooms[r][c] for (r, c) in existing_shafts)
            next_value = min(12, highest + 1)

        # Build list of candidate cells (cells with value 1)
        candidates = []
        for r in range(self.num_rows):
            for c in range(self.num_cols):
                if self.rooms[r][c] == 1:
                    d_out = _dist_to_outside(r, c)
                    candidates.append((d_out, r, c))

        # sort candidates by descending distance to outside (deeper first)
        candidates.sort(reverse=True)

        placed_shafts = set(existing_shafts)

        # Try to place up to 4 shafts (9..12)
        for val in range(next_value, 13):
            placed = False
            for d_out, r, c in candidates:
                # cell must still be available (not overwritten by earlier placement)
                if self.rooms[r][c] != 1:
                    continue
                # Must be at least 4 steps from outside
                if d_out < 4:
                    continue
                # Must be at least 4 steps from any already placed shaft
                d_shaft = _dist_to_nearest_shaft(r, c, placed_shafts)
                if d_shaft < 4:
                    continue
                # place shaft
                self.rooms[r][c] = val
                placed_shafts.add((r, c))
                placed = True
                break
            if not placed:
                # no suitable spot for this value, stop trying further values
                break


    # Fill the maze with larger rooms. These can be both regular rooms and special room types
    # such as stairs, lustral basins or light shafts
    def gen_rooms(self):
        center_row, center_col, facing = self.make_foundation()
        self.contain_maze()
        # Place a single room adjacent to the entrance. Iterating this into a full
        # generative room layout (using find_possible_new_doorways) is future work.
        next_id = 2
        room_row, room_col = Maze.step(center_row, center_col, opposite[facing])
        self.expand_room(room_row, room_col, 5, opposite[facing], 5, next_id)

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

    def get_enclosing_walls(self):
        """Yield (boundary_type, row, col, orientation) for boundaries to set as 'wall' to enclose the maze."""
        for row in range(self.num_rows):
            for col in range(self.num_cols):
                if self.rooms[row][col] == 1:
                    # Check left boundary
                    if row == 0 or self.rooms[row-1][col] == 0:
                        yield ('horizontal', row, col)
                    # Check right boundary
                    if row == self.num_rows - 1 or self.rooms[row+1][col] == 0:
                        yield ('horizontal', row+1, col)
                    # Check top boundary
                    if col == 0 or self.rooms[row][col-1] == 0:
                        yield ('vertical', row, col)
                    # Check bottom boundary
                    if col == self.num_cols - 1 or self.rooms[row][col+1] == 0:
                        yield ('vertical', row, col+1)

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
                            
    def sidewinder(self,draw_state,seed=42):
        """ Generate a maze using the sidewinder algorithm. Only consider rooms that have a state given by draw_state as accessible"""
        # initialize all boundaries between rooms that are eqaul draws_state as walls
        self.fill_with_walls(draw_state)

        if seed is not None:
            random.seed(seed)
        for row in range(self.num_rows):
            run = []
            for col in range(self.num_cols):
                if self.rooms[row][col] == draw_state:
                    at_eastern_boundary = (col == self.num_cols - 1) or (self.rooms[row][col+1] != draw_state) 
                    at_northern_boundary = (row == 0) or (self.rooms[row-1][col] != draw_state)
                    if not at_northern_boundary:
                        run.append((row, col))
                    carve_east = (not at_eastern_boundary)  and (random.choice([True, False])  or at_northern_boundary)
                    if carve_east:
                        # Carve east: open vertical boundary to the right
                        self.vertical_boundaries[row][col+1].boundary_type = 'air'
                    else:
                        # Carve north: pick a random cell from the run and open horizontal boundary above
                        if not at_northern_boundary:
                            carve_row, carve_col = random.choice(run)
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
                        
    def make_stairs(self,start_row,start_col,direction="e",shape = "straight", length=2):
        """ create a flight of stairs starting at the given point and leading up in the given direction,
        stairs are bordered by walls."""
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
            # TODO add walls, ensure if a set of stairs in the same direction already exists the room value of the stair is incremented
            
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
            
