# isometric

True 30° isometric rendering of **integer-grid boxes / voxels** for pen plotters,
with exact hidden-surface removal and per-face [penfill](../penfill) fills. Every
function returns the penfill Geometry IR, so output flows straight through
`penfill.draw_geometry`.

## Why it's exact and cheap

A pen plotter draws real ink and can't "paint over" to hide geometry, so occluded
faces must be *removed*, not overdrawn. Under true 30° isometric the integer
voxel lattice maps onto a **single shared triangular lattice** (the three screen
edge directions are 120° apart and `u_z = -(u_x + u_y)`), so every visible face
(top = +z, right = +x, left = +y) is a unit rhombus = two equilateral triangles
on that grid. Hidden-surface removal is then an **analytic per-triangle integer
z-buffer** keyed by the view-depth `x+y+z` — no Shapely boolean ops, no
float-robustness issues. Shapely is used only to *merge* coplanar visible
triangles back into fill polygons.

## Modules

- **[projection.py](projection.py)** — `project(x,y,z,scale)` and the lattice
  helper `lattice_to_screen(a,b,scale)`.
- **[boxes.py](boxes.py)** — `Box`, `render_boxes`, `render_voxels`,
  `face_type_resolver`. The integer z-buffer, coplanar-merge reconstruction, and
  per-face fill resolution. Adjacent coplanar same-direction faces merge by
  default (`merge_coplanar=True`) so internal seams aren't drawn.
- **[heightfield.py](heightfield.py)** — `Heightfield`: a perlin-style ground
  drawn as a smooth sloped mesh, with a `round(height)` **terraced-column proxy**
  used for occlusion so terrain stays on the same integer z-buffer.
- **[scene.py](scene.py)** — `render_scene`: a voxel structure + a ground
  heightfield in one unified z-buffer, plus ground shadows via an integer
  light-march (3D DDA). `sloped_ground` toggles smooth vs terraced terrain.

## Usage

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from penfill import FillSpec, draw_geometry
from isometric import Box, render_boxes, face_type_resolver

boxes = [Box(0, 0, 0, 1, 1, 3), Box(1, 0, 0, 1, 1, 1)]
resolver = face_type_resolver({
    "top":   FillSpec("solid", 1),
    "left":  FillSpec("hatch", 2, dict(spacing=0.15, angle=45)),
    "right": FillSpec("hatch", 3, dict(spacing=0.15, angle=-45)),
})
draw_geometry(vsk, render_boxes(boxes, resolver, scale=1.0, outline_layer=4))
```

`fill_for(box, kind) -> FillSpec | None` resolves the fill per face; return
`None` (or pattern `"none"` in the sketch) to leave a face unfilled (outline
only). `render_voxels(occupied, ...)` is a fast path for unit-voxel sets that
culls faces shared with a neighbour.

## Sketch & tests

- **[sketch_isobox.py](sketch_isobox.py)** — vsketch testbed: a noise height
  field of voxel columns with per-face patterns/colours. Run `vsk run` here.
- **[test_render.py](test_render.py)**, **[test_scene.py](test_scene.py)** —
  headless checks (no GUI). Run with the vsketch environment's Python.

## Dependencies

[penfill](../penfill) (repo root), `shapely`, `scipy`, `numpy`. Sketches add the
repo root to `sys.path` so both `penfill` and `isometric` import under `vsk run`.
