# floorplan

Procedurally generated Minoan-ruin mazes rendered as isometric pen plots. The
maze/voxel logic was ported from an original Blender script to pure Python +
[vsketch](https://github.com/abey79/vsketch), drawing through the
[isometric](../isometric) renderer and [penfill](../penfill) fills.

## Pipeline

```
maze.py (generate)  ->  voxels.py (voxelise + erode)  ->  isometric.render_* (draw)
```

- **[maze.py](maze.py)** — `Maze`: a 2-D grid of rooms with wall/door boundaries,
  plus stairs, lustral basins, light shafts and entrances. `gen_rooms()` builds a
  plottable maze (full generative room layout is future work). Pure Python.
- **[voxels.py](voxels.py)** — `PositionGrid`:
  - `fromMaze(...)` turns a maze into a set of occupied integer voxels (walls,
    floors, stairs, basins, entrance steps).
  - `decay_texture(reps, rng, noise_fn, ...)` erodes the mass into ruins —
    vectorised with `scipy.ndimage` (weighted-neighbour `correlate` + connected
    component `label`); `rng` is a NumPy `Generator`. Disconnected/cut voxels
    drop as rubble (`drop`).
- **[sketch_floorplan.py](sketch_floorplan.py)** — the ruin alone, in isometric.
- **[sketch_terrain.py](sketch_terrain.py)** — the ruin on a noise-driven ground
  heightfield, with surface relief and ground shadows (`isometric.render_scene`).

Per-face fill pattern + colour are exposed in the sketches; pattern `"none"`
disables a face's fill (outline only).

## Running

```
cd floorplan
vsk run sketch_floorplan.py      # or: sketch_terrain.py
```

## Tests (headless, no GUI)

`test_maze.py`, `test_contain_maze.py`, `test_expand_room.py` exercise `maze.py`;
`test_voxels.py` covers voxelisation, the vectorised erosion, flood-fill and
`drop`. Run them with the vsketch environment's Python (needs `numpy`/`scipy`).
