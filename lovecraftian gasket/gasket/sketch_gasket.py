"""Lovecraftian Apollonian eye-packing - vsketch entry point.

    vsk run gasket/sketch_gasket.py   (from the project root)

Loads a seed config, snaps it to tangency, packs the Apollonian gasket down to
``r_min`` inside the A4 margin clip (circles outside the margins are discarded),
then renders each circle as a manga eye / orifice / tissue.  A coherent series is
produced by sweeping only ``shading_mode``; ``frame_style`` and the seed file are
the other top-level choices.
"""

import pathlib
import sys

import vsketch

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_REPO = _HERE.parents[1]
sys.path.insert(0, str(_REPO))

from config import load                                    # noqa: E402
from eyestyle import COLOR_CHOICES, build_style, layer_colors  # noqa: E402
from features import render_circle                         # noqa: E402
from packing import pack                                   # noqa: E402
from snap import snap                                      # noqa: E402
from style import FRAME_STYLES, OFFSET_MODES, SHADING_MODES  # noqa: E402

SEED_FILES = sorted(p.name for p in (_HERE / "seeds").glob("*.json"))


class GasketSketch(vsketch.SketchClass):
    seed_file = vsketch.Param(SEED_FILES[0] if SEED_FILES else "",
                              choices=SEED_FILES)
    landscape = vsketch.Param(False)
    # NOTE on units: a Param with unit="mm" is auto-converted to *document pixels*
    # (1 mm -> 3.78 px at 96 dpi) when read inside draw().  Our geometry works in
    # millimetres, so length params consumed in mm-space (r_min, eye_*, *_spacing)
    # must NOT use unit="mm" or they arrive ~3.78x too large.  Only pen_width keeps
    # unit="mm" because vsk.penWidth() genuinely wants pixels.
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2, unit="mm")
    snap_seed = vsketch.Param(0)            # vsk.randomSeed for stipple/orifice jitter

    # --- packing
    r_min = vsketch.Param(2.0, min_value=0.5, decimals=2)   # mm
    max_depth = vsketch.Param(40, min_value=1)

    # --- the coherent-series axis + frame
    shading_mode = vsketch.Param("hatch", choices=SHADING_MODES)
    frame_style = vsketch.Param("circle", choices=FRAME_STYLES)

    # --- feature mapping (mm radius)
    eye_big = vsketch.Param(9.0, min_value=1.0, decimals=1)   # mm
    eye_min = vsketch.Param(3.5, min_value=0.5, decimals=1)   # mm

    # --- eye proportions
    iris_ratio = vsketch.Param(0.62, min_value=0.1, max_value=0.95, decimals=2)
    pupil_ratio = vsketch.Param(0.36, min_value=0.05, max_value=0.9, decimals=2)
    size_jitter_sd = vsketch.Param(0.05, min_value=0.0, max_value=0.3, decimals=3)
    # iris+pupil offset: "random" jitter, or "gaze" toward a page point (all eyes
    # appear to stare at the same spot; far eyes shift more).
    offset_mode = vsketch.Param("random", choices=OFFSET_MODES)
    offset_sd = vsketch.Param(0.05, min_value=0.0, max_value=0.4, decimals=3)  # random
    gaze_x = vsketch.Param(0.5, min_value=0.0, max_value=1.0, decimals=2)  # gaze, frac
    gaze_y = vsketch.Param(0.4, min_value=0.0, max_value=1.0, decimals=2)  # of page
    gaze_strength = vsketch.Param(0.08, min_value=0.0, max_value=0.5, decimals=3)
    specular_count = vsketch.Param(2, min_value=0, max_value=2)

    # --- shading detail
    hatch_spacing = vsketch.Param(0.5, min_value=0.1, decimals=2)   # mm
    hatch_angle = vsketch.Param(35.0)
    contour_spacing = vsketch.Param(0.6, min_value=0.1, decimals=2)  # mm
    stipple_density = vsketch.Param(0.9, min_value=0.05, decimals=2)

    # --- "ringed" eye style (sector specular + iris arc-rings); screen degrees
    specular_angle = vsketch.Param(225.0)            # wedge/arc direction
    specular_sector_deg = vsketch.Param(42.0, min_value=2.0)
    specular_inner_ratio = vsketch.Param(0.18, min_value=0.0, max_value=0.9, decimals=2)
    specular_reach = vsketch.Param(1.0, min_value=0.1, max_value=3.0, decimals=2)
    iris_sector_deg = vsketch.Param(150.0, min_value=2.0)
    iris_ring_outer_ratio = vsketch.Param(0.88, min_value=0.4, max_value=0.98, decimals=2)
    iris_ring_count = vsketch.Param(6, min_value=1, max_value=30)
    iris_ring_taper_deg = vsketch.Param(0.0, min_value=0.0)

    # --- orifice (solid dark fill; teeth + streaks are negative space)
    tooth_count = vsketch.Param(14, min_value=3)
    tooth_depth = vsketch.Param(0.34, min_value=0.05, max_value=0.9, decimals=2)
    tooth_width_frac = vsketch.Param(0.45, min_value=0.1, max_value=0.95, decimals=2)
    orifice_line_reach = vsketch.Param(0.33, min_value=0.05, max_value=0.9, decimals=2)
    orifice_line_width = vsketch.Param(0.035, min_value=0.005, max_value=0.2, decimals=3)
    orifice_lines_per_gap = vsketch.Param(2, min_value=0, max_value=8)
    orifice_cross_hatch = vsketch.Param(True)

    # --- colours (layer 1 = line work, layer 2 = dark shading); "none" -> black
    line_color = vsketch.Param("none", choices=COLOR_CHOICES)
    shade_color = vsketch.Param("none", choices=COLOR_CHOICES)

    def _draw_frame(self, vsk, cfg, style) -> None:
        if style.frame_style in ("none",):
            return
        vsk.stroke(style.stroke_layer)
        if style.frame_style in ("circle", "circle+rect"):
            o = cfg.outer_circle()
            if o is not None:                      # no-op when boundary dropped
                vsk.circle(o.z.real, o.z.imag, radius=o.r)
        if style.frame_style in ("rect", "circle+rect"):
            r = cfg.clip
            vsk.rect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        # center=False: absolute mm coordinates (page top-left = 0,0), so seeds
        # render at their true positions (matching the margin clip) rather than
        # vsketch re-centering the bounding box.
        vsk.size("a4", landscape=self.landscape, center=False)
        vsk.penWidth(self.pen_width)
        vsk.scale("mm")
        if self.snap_seed:
            vsk.randomSeed(self.snap_seed)

        cfg = load(_HERE / "seeds" / self.seed_file)
        seeds = snap(cfg)
        outer = cfg.outer_circle()
        circles = pack(seeds, outer, cfg.clip,
                       r_min=self.r_min, max_depth=int(self.max_depth))

        style = build_style(self, frame_style=self.frame_style)
        for c in circles:
            render_circle(vsk, c, style)
        self._draw_frame(vsk, cfg, style)

        vsk.vpype(layer_colors(self))

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    GasketSketch.display()
