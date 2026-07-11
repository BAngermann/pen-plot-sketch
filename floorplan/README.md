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
- **[sketch_floorplan.py](sketch_floorplan.py)** — the ruin in isometric, via
  `isometric.render_voxels`. The `draw_terrain` toggle switches it to draw the
  ruin sitting in/on a noise-driven ground heightfield instead, with surface
  relief and ground shadows, via `isometric.render_scene`.

Per-face fill pattern + colour are exposed in the sketch; pattern `"none"`
disables a face's fill (outline only).

## Running

```
cd floorplan
vsk run sketch_floorplan.py
```

## Tests (headless, no GUI)

See [tests/](tests/): `test_shapes.py`, `test_connectivity.py`,
`test_shafts_basins.py`, `test_multifloor_voxels.py`, `test_building.py`,
`test_roof.py`, `test_contain_maze.py`, `test_expand_room.py` exercise
`maze.py`/`maze.Building`; `test_voxels.py` covers voxelisation, the
vectorised erosion, flood-fill and `drop`. Run the whole suite with
`python -m unittest discover` (needs the vsketch environment's Python, for
`numpy`/`scipy`).
