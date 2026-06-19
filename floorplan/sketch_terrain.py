import pathlib
import random
import sys

import numpy as np
import vsketch

_REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
from penfill import (FillSpec, PATTERN_NAMES, draw_geometry, install_swatches,
                     load_pens)
from isometric import Heightfield, face_type_resolver, render_scene

from maze import Maze
from voxels import PositionGrid

PENS = load_pens(_REPO / "pens")
PEN_NAMES = list(PENS)
COLOR_CHOICES = ["none"] + PEN_NAMES
PATTERN_CHOICES = ["none"] + PATTERN_NAMES   # "none" disables the fill (outline only)
install_swatches(PENS)

# Layers: structure top/right/left, ground top/wall, shadow, outline, relief.
L_TOP, L_RIGHT, L_LEFT = 1, 2, 3
L_GTOP, L_GWALL = 4, 5
L_SHADOW, L_OUTLINE, L_RELIEF = 6, 7, 8


def _default_color(i):
    return PEN_NAMES[i - 1] if i - 1 < len(PEN_NAMES) else "none"


class TerrainSketch(vsketch.SketchClass):
    # ── Maze + voxelisation ─────────────────────────────────────────────────────
    num_rows = vsketch.Param(8, min_value=8)
    num_cols = vsketch.Param(8, min_value=8)
    maze_seed = vsketch.Param(3)
    room_size = vsketch.Param(5, min_value=2)
    wall_thickness = vsketch.Param(2, min_value=1)
    wall_height = vsketch.Param(7, min_value=1)
    floor_thickness = vsketch.Param(3, min_value=1)
    decay_reps = vsketch.Param(3, min_value=0)
    decay_seed = vsketch.Param(0)

    # ── Terrain ─────────────────────────────────────────────────────────────────
    subdiv = vsketch.Param(2, min_value=1)
    terrain_margin = vsketch.Param(6, min_value=0)       # coarse cells around footprint
    terrain_amplitude = vsketch.Param(5.0, min_value=0)  # fine-z units
    terrain_noise_scale = vsketch.Param(0.04, min_value=0.001, decimals=3)
    terrain_seed = vsketch.Param(0)
    relief = vsketch.Param(True)
    sloped_ground = vsketch.Param(True)   # True: smooth sloped mesh; False: terraced

    # ── Light / shadow ──────────────────────────────────────────────────────────
    light_x = vsketch.Param(-3.0)
    light_y = vsketch.Param(-2.0)
    light_z = vsketch.Param(3.0)
    cast_shadows = vsketch.Param(True)

    # ── Drawing ─────────────────────────────────────────────────────────────────
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2, unit="mm")
    margin_cm = vsketch.Param(1.5, min_value=0, decimals=1)
    # Per-direction fill pattern; "none" disables that face's fill (outline only).
    top_pattern = vsketch.Param("solid", choices=PATTERN_CHOICES)
    right_pattern = vsketch.Param("solid", choices=PATTERN_CHOICES)
    left_pattern = vsketch.Param("solid", choices=PATTERN_CHOICES)
    ground_pattern = vsketch.Param("hatch", choices=PATTERN_CHOICES)
    fill_spacing = vsketch.Param(0.4, min_value=0.01, decimals=3)

    color_top = vsketch.Param(_default_color(1), choices=COLOR_CHOICES)
    color_right = vsketch.Param(_default_color(2), choices=COLOR_CHOICES)
    color_left = vsketch.Param(_default_color(3), choices=COLOR_CHOICES)
    color_ground = vsketch.Param(_default_color(4), choices=COLOR_CHOICES)
    color_shadow = vsketch.Param(_default_color(3), choices=COLOR_CHOICES)

    def _spec(self, pattern, layer, angle=0.0):
        if pattern == "none":
            return None
        if pattern == "solid":
            return FillSpec("solid", layer, {})
        if pattern == "hatch":
            return FillSpec("hatch", layer, dict(spacing=self.fill_spacing, angle=angle))
        return FillSpec("glyph_grid", layer,
                        dict(grid="hex", spacing=self.fill_spacing,
                             size=self.fill_spacing * 0.4, glyph="dash", angle=angle))

    def _build_structure(self, vsk):
        random.seed(self.maze_seed)
        m = Maze(self.num_rows, self.num_cols)
        m.gen_rooms()
        g = PositionGrid(self.num_rows, self.num_cols, self.wall_height)
        g.fromMaze(m, room_size=self.room_size, wall_thickness=self.wall_thickness,
                   wall_height=self.wall_height, floor_thickness=self.floor_thickness)
        if self.decay_reps:
            vsk.noiseSeed(self.decay_seed)
            g.decay_texture(self.decay_reps, np.random.default_rng(self.decay_seed),
                            lambda x, y: vsk.noise(x * 0.02, y * 0.02),
                            noise_influence=3.5, noise_offset=-0.8,
                            neighbor_baseline=-9)
        return g.all_occupied_positions

    def _build_terrain(self, vsk, occ):
        m = self.subdiv
        xs = [x for x, _y, _z in occ]
        ys = [y for _x, y, _z in occ]
        pad = self.terrain_margin
        W = (max(xs) + 1 + 2 * pad) * m
        H = (max(ys) + 1 + 2 * pad) * m
        ox = oy = -pad * m
        vsk.noiseSeed(self.terrain_seed)
        ns = self.terrain_noise_scale
        return Heightfield.from_noise(
            W, H, lambda x, y: vsk.noise(x * ns, y * ns),
            amplitude=self.terrain_amplitude, base=0.0, ox=ox, oy=oy)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=True)
        vsk.penWidth(self.pen_width)

        occ = self._build_structure(vsk)
        hf = self._build_terrain(vsk, occ)

        resolver = face_type_resolver({
            "top": self._spec(self.top_pattern, L_TOP),
            "right": self._spec(self.right_pattern, L_RIGHT, 30.0),
            "left": self._spec(self.left_pattern, L_LEFT, -30.0),
        })
        light = (self.light_x, self.light_y, self.light_z) if self.cast_shadows else None
        geom = render_scene(
            occ, hf, subdiv=self.subdiv, fill_for=resolver,
            ground_top_fill=self._spec(self.ground_pattern, L_GTOP, 90.0),
            ground_wall_fill=FillSpec("solid", L_GWALL),
            scale=1.0, outline_layer=L_OUTLINE,
            relief_layer=L_RELIEF if self.relief else None,
            sloped_ground=self.sloped_ground,
            light=light,
            shadow_fill=FillSpec("hatch", L_SHADOW, dict(spacing=self.fill_spacing * 0.6, angle=60.0)))

        xs = [p[0] for prim in geom for p in prim[2]]
        ys = [p[1] for prim in geom for p in prim[2]]
        if not xs:
            return
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        w, h = maxx - minx, maxy - miny
        pw, ph = 29.7, 21.0
        fit = min((pw - 2 * self.margin_cm) / w, (ph - 2 * self.margin_cm) / h) if w and h else 1.0
        vsk.scale("cm")
        vsk.translate(pw / 2, ph / 2)
        vsk.scale(fit)
        vsk.translate(-(minx + maxx) / 2, -(miny + maxy) / 2)
        draw_geometry(vsk, geom)

        colors = {L_TOP: self.color_top, L_RIGHT: self.color_right, L_LEFT: self.color_left,
                  L_GTOP: self.color_ground, L_GWALL: self.color_ground,
                  L_SHADOW: self.color_shadow}
        parts = [f"color --layer {lyr} {self._hex(c)}" for lyr, c in colors.items()]
        parts.append(f"color --layer {L_OUTLINE} black")
        parts.append(f"color --layer {L_RELIEF} {self._hex(self.color_ground)}")
        vsk.vpype(" ".join(parts))

    def _hex(self, name):
        return "black" if name == "none" else PENS.get(name, "black")

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    TerrainSketch.display()
