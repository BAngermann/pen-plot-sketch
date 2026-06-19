import pathlib
import random
import sys

import numpy as np
import vsketch

# Repo-root packages (penfill, isometric)...
_REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
from penfill import (FillSpec, GLYPH_TYPES, GRID_TYPES, PATTERN_NAMES,
                     draw_geometry, install_swatches, load_pens)
from isometric import face_type_resolver, render_voxels

# ...and the local maze/voxel modules (sketch dir is on sys.path under `vsk run`).
from maze import Maze
from voxels import PositionGrid

PENS = load_pens(_REPO / "pens")
PEN_NAMES = list(PENS)
COLOR_CHOICES = ["none"] + PEN_NAMES
PATTERN_CHOICES = ["none"] + PATTERN_NAMES   # "none" disables the fill (outline only)
install_swatches(PENS)

LAYER = {"top": 1, "right": 2, "left": 3}
OUTLINE_LAYER = 4


def _default_color(i: int) -> str:
    return PEN_NAMES[i - 1] if i - 1 < len(PEN_NAMES) else "none"


class FloorplanSketch(vsketch.SketchClass):
    # ── Maze ────────────────────────────────────────────────────────────────────
    num_rows = vsketch.Param(9, min_value=8)      # make_foundation needs >= 8
    num_cols = vsketch.Param(9, min_value=8)
    maze_seed = vsketch.Param(7)

    # ── Voxelisation (cell = room_size + wall_thickness) ────────────────────────
    room_size = vsketch.Param(6, min_value=2)
    wall_thickness = vsketch.Param(2, min_value=1)
    wall_height = vsketch.Param(8, min_value=1)
    floor_thickness = vsketch.Param(3, min_value=1)

    # ── Erosion (ruins) ─────────────────────────────────────────────────────────
    decay_reps = vsketch.Param(4, min_value=0)
    decay_seed = vsketch.Param(0)
    noise_scale = vsketch.Param(0.02, min_value=0.001, decimals=3)
    # NB: vsk.noise is ~[0,1] (Blender's mathutils.fractal was ~[-1,1]); these
    # defaults are a starting point and will likely need re-tuning.
    noise_influence = vsketch.Param(3.5, decimals=2)
    noise_offset = vsketch.Param(-0.8, decimals=2)
    neighbor_baseline = vsketch.Param(-9.0, decimals=1)

    # ── Drawing ───────────────────────────────────────────────────────────────
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2, unit="mm")
    margin = vsketch.Param(2.0, min_value=0, decimals=1)            # cm

    # ── Fill: one pattern + colour per face kind ("none" disables that face) ─────
    top_pattern = vsketch.Param("solid", choices=PATTERN_CHOICES)
    right_pattern = vsketch.Param("hatch", choices=PATTERN_CHOICES)
    left_pattern = vsketch.Param("hatch", choices=PATTERN_CHOICES)
    fill_spacing = vsketch.Param(0.3, min_value=0.01, decimals=3)   # voxel units
    size_ratio = vsketch.Param(0.4, min_value=0.05, decimals=2)
    grid_type = vsketch.Param("hex", choices=GRID_TYPES)
    glyph_type = vsketch.Param("dash", choices=GLYPH_TYPES)
    top_angle = vsketch.Param(0.0)
    right_angle = vsketch.Param(30.0)
    left_angle = vsketch.Param(-30.0)

    top_color = vsketch.Param(_default_color(1), choices=COLOR_CHOICES)
    right_color = vsketch.Param(_default_color(2), choices=COLOR_CHOICES)
    left_color = vsketch.Param(_default_color(3), choices=COLOR_CHOICES)
    draw_outline = vsketch.Param(True)
    outline_color = vsketch.Param("none", choices=COLOR_CHOICES)    # "none" -> black

    def _spec(self, pattern: str, layer: int, angle: float):
        if pattern == "none":
            return None
        if pattern == "solid":
            return FillSpec("solid", layer, {})
        if pattern == "hatch":
            return FillSpec("hatch", layer,
                            dict(spacing=self.fill_spacing, angle=angle))
        return FillSpec("glyph_grid", layer,
                        dict(grid=self.grid_type, spacing=self.fill_spacing,
                             size=self.fill_spacing * self.size_ratio,
                             glyph=self.glyph_type, angle=angle))

    def _build_voxels(self, vsk: vsketch.Vsketch):
        random.seed(self.maze_seed)                # maze generation uses stdlib random
        m = Maze(self.num_rows, self.num_cols)
        m.gen_rooms()
        g = PositionGrid(self.num_rows, self.num_cols, self.wall_height)
        g.fromMaze(m, room_size=self.room_size, wall_thickness=self.wall_thickness,
                   wall_height=self.wall_height, floor_thickness=self.floor_thickness)
        if self.decay_reps:
            vsk.noiseSeed(self.decay_seed)
            noise_fn = lambda x, y: vsk.noise(x * self.noise_scale, y * self.noise_scale)
            g.decay_texture(self.decay_reps, np.random.default_rng(self.decay_seed),
                            noise_fn, noise_influence=self.noise_influence,
                            noise_offset=self.noise_offset,
                            neighbor_baseline=self.neighbor_baseline)
        return g.all_occupied_positions

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=True)
        vsk.penWidth(self.pen_width)

        occupied = self._build_voxels(vsk)
        resolver = face_type_resolver({
            "top": self._spec(self.top_pattern, LAYER["top"], self.top_angle),
            "right": self._spec(self.right_pattern, LAYER["right"], self.right_angle),
            "left": self._spec(self.left_pattern, LAYER["left"], self.left_angle),
        })
        outline_layer = OUTLINE_LAYER if self.draw_outline else None
        # Render in unit (per-voxel) screen space, then fit-to-page below.
        geom = render_voxels(occupied, resolver, scale=1.0, outline_layer=outline_layer)
        if not geom:
            return

        xs = [p[0] for prim in geom for p in prim[2]]
        ys = [p[1] for prim in geom for p in prim[2]]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        w, h = maxx - minx, maxy - miny
        page_w, page_h = 29.7, 21.0          # A4 landscape, cm
        avail_w, avail_h = page_w - 2 * self.margin, page_h - 2 * self.margin
        fit = min(avail_w / w, avail_h / h) if w and h else 1.0

        vsk.scale("cm")
        vsk.translate(page_w / 2, page_h / 2)
        vsk.scale(fit)
        vsk.translate(-(minx + maxx) / 2, -(miny + maxy) / 2)
        draw_geometry(vsk, geom)

        parts = [f"color --layer {LAYER['top']} {self._hex(self.top_color)}",
                 f"color --layer {LAYER['right']} {self._hex(self.right_color)}",
                 f"color --layer {LAYER['left']} {self._hex(self.left_color)}"]
        if self.draw_outline:
            oc = "black" if self.outline_color == "none" else self._hex(self.outline_color)
            parts.append(f"color --layer {OUTLINE_LAYER} {oc}")
        vsk.vpype(" ".join(parts))

    def _hex(self, name: str) -> str:
        return "black" if name == "none" else PENS.get(name, "black")

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    FloorplanSketch.display()
