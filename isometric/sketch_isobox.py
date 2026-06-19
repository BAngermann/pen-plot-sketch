import pathlib
import sys

import vsketch

# Make the repo-root `penfill` and `isometric` packages importable under `vsk run`.
_REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
from penfill import (FillSpec, GLYPH_TYPES, GRID_TYPES, PATTERN_NAMES,
                     draw_geometry, install_swatches, load_pens)
from isometric import Box, face_type_resolver, render_voxels

PENS = load_pens(_REPO / "pens")
PEN_NAMES = list(PENS)
COLOR_CHOICES = ["none"] + PEN_NAMES
PATTERN_CHOICES = ["none"] + PATTERN_NAMES   # "none" disables the fill (outline only)
install_swatches(PENS)

# Fixed layer assignment: one per face kind, plus the outline on top.
LAYER = {"top": 1, "right": 2, "left": 3}
OUTLINE_LAYER = 4


def _default_color(i: int) -> str:
    return PEN_NAMES[i - 1] if i - 1 < len(PEN_NAMES) else "none"


class IsoBoxSketch(vsketch.SketchClass):
    # ── Scene: a grid of voxel columns with a noise height field ────────────────
    nx = vsketch.Param(10, min_value=1)
    ny = vsketch.Param(10, min_value=1)
    max_height = vsketch.Param(6, min_value=1)
    noise_scale = vsketch.Param(0.25, min_value=0.01, decimals=2)  # terrain freq
    height_seed = vsketch.Param(0)
    voxel_size = vsketch.Param(0.7, min_value=0.05, decimals=2)    # cm per edge
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2, unit="mm")

    # ── Fill: one pattern + colour per face kind ("none" disables that face) ────
    top_pattern = vsketch.Param("solid", choices=PATTERN_CHOICES)
    right_pattern = vsketch.Param("hatch", choices=PATTERN_CHOICES)
    left_pattern = vsketch.Param("hatch", choices=PATTERN_CHOICES)
    fill_spacing = vsketch.Param(0.12, min_value=0.01, decimals=3)  # drawing units
    size_ratio = vsketch.Param(0.4, min_value=0.05, decimals=2)     # glyph size/spacing
    grid_type = vsketch.Param("hex", choices=GRID_TYPES)
    glyph_type = vsketch.Param("dash", choices=GLYPH_TYPES)
    # Hatch/grid angles chosen to echo the three isometric directions by default.
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

    def _heightfield(self, vsk: vsketch.Vsketch):
        """Set of unit voxels: column (i, j) filled up to a noise-driven height."""
        vsk.noiseSeed(self.height_seed)
        occupied = set()
        for i in range(self.nx):
            for j in range(self.ny):
                n = vsk.noise(i * self.noise_scale, j * self.noise_scale)
                h = 1 + int(n * self.max_height)
                for k in range(h):
                    occupied.add((i, j, k))
        return occupied

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=True)
        vsk.penWidth(self.pen_width)
        vsk.scale("cm")

        occupied = self._heightfield(vsk)
        resolver = face_type_resolver({
            "top": self._spec(self.top_pattern, LAYER["top"], self.top_angle),
            "right": self._spec(self.right_pattern, LAYER["right"], self.right_angle),
            "left": self._spec(self.left_pattern, LAYER["left"], self.left_angle),
        })
        outline_layer = OUTLINE_LAYER if self.draw_outline else None
        geom = render_voxels(occupied, resolver, scale=self.voxel_size,
                             outline_layer=outline_layer)

        # Centre the projected drawing on the page (A4 landscape: 29.7 x 21 cm).
        xs = [p[0] for prim in geom for p in prim[2]]
        ys = [p[1] for prim in geom for p in prim[2]]
        if xs:
            cx = (min(xs) + max(xs)) / 2
            cy = (min(ys) + max(ys)) / 2
            vsk.translate(29.7 / 2 - cx, 21 / 2 - cy)

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
    IsoBoxSketch.display()
