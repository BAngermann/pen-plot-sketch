import math
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
from isometric import Heightfield, face_type_resolver, render_scene, render_voxels

# ...and the local maze/voxel modules (sketch dir is on sys.path under `vsk run`).
from maze import Building
from voxels import PositionGrid

PENS = load_pens(_REPO / "pens")
PEN_NAMES = list(PENS)
COLOR_CHOICES = ["none"] + PEN_NAMES
PATTERN_CHOICES = ["none"] + PATTERN_NAMES   # "none" disables the fill (outline only)
install_swatches(PENS)

# Structure top/right/left, ground top/wall, shadow, outline, relief. The
# ground/shadow/relief layers are simply left empty when draw_terrain is off.
L_TOP, L_RIGHT, L_LEFT = 1, 2, 3
L_GTOP, L_GWALL, L_SHADOW = 4, 5, 6
L_OUTLINE, L_RELIEF = 7, 8


def _default_color(i: int) -> str:
    return PEN_NAMES[i - 1] if i - 1 < len(PEN_NAMES) else "none"


class FloorplanSketch(vsketch.SketchClass):
    # ── Maze ────────────────────────────────────────────────────────────────────
    num_rows = vsketch.Param(9, min_value=8)      # make_foundation needs >= 8
    num_cols = vsketch.Param(9, min_value=8)
    maze_seed = vsketch.Param(7)
    building_shape = vsketch.Param("random", choices=["random", "rectangular", "courtyard",
                                                        "l_shape", "c_shape", "h_shape", "corners"])

    # ── Rooms / corridors / doors / special rooms ────────────────────────────────
    door_probability = vsketch.Param(0.2, min_value=0.0, max_value=1.0, decimals=2)
    max_explicit_rooms = vsketch.Param(4, min_value=1)
    max_shafts = vsketch.Param(2, min_value=0)
    shaft_min_size = vsketch.Param(1, min_value=1)
    shaft_max_size = vsketch.Param(2, min_value=1)
    basin_probability = vsketch.Param(0.3, min_value=0.0, max_value=1.0, decimals=2)

    # ── Multi-floor / roof ────────────────────────────────────────────────────────
    floor2_area_threshold = vsketch.Param(50, min_value=0)
    stair_length = vsketch.Param(3, min_value=2)
    roof_access = vsketch.Param("auto", choices=["auto", "stairs", "hatch", "none"])
    min_hatch_voxels = vsketch.Param(5, min_value=1)   # roof hatch spans multiple cells if room_size is too small
    parapet_height = vsketch.Param(3, min_value=1)

    # ── Debug ─────────────────────────────────────────────────────────────────
    debug_marker = vsketch.Param(False)         # tall voxel spike at (debug_marker_x, debug_marker_y)
    debug_marker_x = vsketch.Param(0, min_value=0)   # raw voxel coords, not maze row/col
    debug_marker_y = vsketch.Param(0, min_value=0)
    debug_hide_floor2 = vsketch.Param(False)    # drop every voxel at/above debug_hide_floor2_z
    debug_hide_floor2_z = vsketch.Param(11, min_value=0)   # default: top of the ground floor's own walls
    debug_hide_non_ground_slabs = vsketch.Param(False)   # hide floor2's slab/roof cap/terrace cap, keep all walls

    # ── Voxelisation (cell = room_size + wall_thickness) ────────────────────────
    room_size = vsketch.Param(7, min_value=2)
    wall_thickness = vsketch.Param(2, min_value=1)
    wall_height = vsketch.Param(8, min_value=1)
    floor_thickness = vsketch.Param(1, min_value=1)          # upper floor(s) + roof/terrace cap
    ground_floor_thickness = vsketch.Param(3, min_value=1)   # ground floor's own slab only

    # ── Erosion (ruins) ─────────────────────────────────────────────────────────
    decay_reps = vsketch.Param(0, min_value=0)
    decay_seed = vsketch.Param(0)
    noise_scale = vsketch.Param(0.02, min_value=0.001, decimals=3)
    # NB: vsk.noise is ~[0,1] (Blender's mathutils.fractal was ~[-1,1]); these
    # defaults are a starting point and will likely need re-tuning.
    noise_influence = vsketch.Param(3.5, decimals=2)
    noise_offset = vsketch.Param(-0.8, decimals=2)
    neighbor_baseline = vsketch.Param(-9.0, decimals=1)

    # ── Ground (optional -- adds a noise heightfield the building sits in/on,
    # via isometric.render_scene instead of the plain render_voxels) ────────────
    draw_terrain = vsketch.Param(False)
    subdiv = vsketch.Param(2, min_value=1)
    terrain_margin = vsketch.Param(6, min_value=0)       # coarse cells around footprint
    terrain_amplitude = vsketch.Param(5.0, min_value=0)  # fine-z units
    terrain_noise_scale = vsketch.Param(0.04, min_value=0.001, decimals=3)
    terrain_seed = vsketch.Param(0)
    relief = vsketch.Param(True)
    sloped_ground = vsketch.Param(True)   # True: smooth sloped mesh; False: terraced
    ground_pattern = vsketch.Param("hatch", choices=PATTERN_CHOICES)
    color_ground = vsketch.Param(_default_color(4), choices=COLOR_CHOICES)

    # ── Ground shadow (only cast when draw_terrain is on) ────────────────────────
    light_x = vsketch.Param(-3.0)
    light_y = vsketch.Param(-2.0)
    light_z = vsketch.Param(3.0)
    cast_shadows = vsketch.Param(True)
    color_shadow = vsketch.Param(_default_color(3), choices=COLOR_CHOICES)

    # ── Drawing ───────────────────────────────────────────────────────────────
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2, unit="mm")
    margin = vsketch.Param(2.0, min_value=0, decimals=1)            # cm

    # ── Fill: one pattern + colour per structure face kind ("none" disables it) ──
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

    def _spec(self, pattern: str, layer: int, angle: float = 0.0):
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

    def _build(self, vsk: vsketch.Vsketch):
        random.seed(self.maze_seed)                # maze generation uses stdlib random
        building = Building(self.num_rows, self.num_cols).generate(
            shape=self.building_shape,
            floor2_area_threshold=self.floor2_area_threshold,
            stair_length=self.stair_length,
            roof_access=self.roof_access,
            roof_hatch_cells=math.ceil(self.min_hatch_voxels / self.room_size),
            door_probability=self.door_probability,
            max_explicit_rooms=self.max_explicit_rooms,
            max_shafts=self.max_shafts,
            shaft_size_range=(self.shaft_min_size, self.shaft_max_size),
            basin_probability=self.basin_probability)
        g = PositionGrid(self.num_rows, self.num_cols, self.wall_height)
        g.fromBuilding(building, room_size=self.room_size, wall_thickness=self.wall_thickness,
                       wall_height=self.wall_height, floor_thickness=self.floor_thickness,
                       ground_floor_thickness=self.ground_floor_thickness,
                       parapet_height=self.parapet_height)

        hf = None
        if self.draw_terrain:
            # Build from the pre-decay footprint (rubble stays within a cell or
            # two of it) so decay can drop rubble straight onto it below.
            hf = self._build_terrain(vsk, g.all_occupied_positions)

        if self.decay_reps:
            vsk.noiseSeed(self.decay_seed)
            noise_fn = lambda x, y: vsk.noise(x * self.noise_scale, y * self.noise_scale)
            terrain_z = None
            if hf is not None:
                sub = self.subdiv
                # sample_terr_int is a fine-grid lookup, so scale coarse (x,y)
                # up and the result down -- rests debris on the terrain height
                # instead of the (otherwise flat) structural floor_z.
                terrain_z = lambda x, y: hf.sample_terr_int(x * sub, y * sub) / sub
            g.decay_texture(self.decay_reps, np.random.default_rng(self.decay_seed),
                            noise_fn, noise_influence=self.noise_influence,
                            noise_offset=self.noise_offset,
                            neighbor_baseline=self.neighbor_baseline,
                            terrain_z=terrain_z)

        occ = g.all_occupied_positions

        if self.debug_hide_floor2:
            # debug_hide_floor2_z defaults to the top of the ground floor's
            # own walls (floor2 -- its slab, walls, and everything above --
            # starts exactly there), but is user-adjustable to cut off at any
            # height.
            occ = {(x, y, z) for (x, y, z) in occ if z < self.debug_hide_floor2_z}

        if self.debug_hide_non_ground_slabs:
            # Hide every horizontal slab/cap surface except the ground
            # floor's own base slab (floor2's own floor slab, the roof cap,
            # the ground floor's terrace cap), but keep walls/parapets fully
            # visible -- a voxel only counts as a bare "slab" (dropped) if its
            # (x, y) column doesn't extend any higher than the slab itself; a
            # column that keeps going up is a wall/parapet passing through
            # the same footprint, and is kept in full.
            thicknesses = [self.ground_floor_thickness] + [self.floor_thickness] * (len(building.floors) - 1)
            floor_levels = []
            z = 0
            for t in thicknesses:
                floor_levels.append(z)
                z += t + self.wall_height
            roof_thickness = self.floor_thickness
            roof_level = (floor_levels[building.roof_floor_index]
                         + thicknesses[building.roof_floor_index] + self.wall_height)
            hide_ranges = [(roof_level, roof_level + roof_thickness)]
            if len(building.floors) > 1:
                hide_ranges.append((floor_levels[1], floor_levels[1] + self.floor_thickness))
                hide_ranges.append((floor_levels[1], floor_levels[1] + roof_thickness))

            col_max = {}
            for (x, y, z) in occ:
                k = (x, y)
                if k not in col_max or z > col_max[k]:
                    col_max[k] = z

            def keep(x, y, z):
                covering = [hi for lo, hi in hide_ranges if lo <= z < hi]
                if not covering:
                    return True
                return col_max[(x, y)] >= max(covering)

            occ = {(x, y, z) for (x, y, z) in occ if keep(x, y, z)}

        if self.debug_marker:
            # Tall spike piercing straight up through the structure, so its
            # (x, y) is unambiguous on screen regardless of which surface/z it
            # would otherwise land on -- drag debug_marker_x/y until it lines
            # up with whatever you're trying to locate.
            top = max((z for _x, _y, z in occ), default=0)
            occ = occ | {(self.debug_marker_x, self.debug_marker_y, z)
                        for z in range(0, top + 15)}
        return occ, hf

    def _build_terrain(self, vsk: vsketch.Vsketch, occ):
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

        occ, hf = self._build(vsk)
        resolver = face_type_resolver({
            "top": self._spec(self.top_pattern, L_TOP, self.top_angle),
            "right": self._spec(self.right_pattern, L_RIGHT, self.right_angle),
            "left": self._spec(self.left_pattern, L_LEFT, self.left_angle),
        })
        outline_layer = L_OUTLINE if self.draw_outline else None

        if hf is not None:
            light = (self.light_x, self.light_y, self.light_z) if self.cast_shadows else None
            geom = render_scene(
                occ, hf, subdiv=self.subdiv, fill_for=resolver,
                ground_top_fill=self._spec(self.ground_pattern, L_GTOP, 90.0),
                ground_wall_fill=FillSpec("solid", L_GWALL),
                scale=1.0, outline_layer=outline_layer,
                relief_layer=L_RELIEF if self.relief else None,
                sloped_ground=self.sloped_ground,
                light=light,
                shadow_fill=FillSpec("hatch", L_SHADOW, dict(spacing=self.fill_spacing * 0.6, angle=60.0)))
        else:
            # Render in unit (per-voxel) screen space, then fit-to-page below.
            geom = render_voxels(occ, resolver, scale=1.0, outline_layer=outline_layer)
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

        parts = [f"color --layer {L_TOP} {self._hex(self.top_color)}",
                 f"color --layer {L_RIGHT} {self._hex(self.right_color)}",
                 f"color --layer {L_LEFT} {self._hex(self.left_color)}"]
        if self.draw_outline:
            oc = "black" if self.outline_color == "none" else self._hex(self.outline_color)
            parts.append(f"color --layer {L_OUTLINE} {oc}")
        if hf is not None:
            parts.append(f"color --layer {L_GTOP} {self._hex(self.color_ground)}")
            parts.append(f"color --layer {L_GWALL} {self._hex(self.color_ground)}")
            parts.append(f"color --layer {L_SHADOW} {self._hex(self.color_shadow)}")
            parts.append(f"color --layer {L_RELIEF} {self._hex(self.color_ground)}")
        vsk.vpype(" ".join(parts))

    def _hex(self, name: str) -> str:
        return "black" if name == "none" else PENS.get(name, "black")

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    FloorplanSketch.display()
