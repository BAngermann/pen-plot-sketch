"""Global style object + per-variant shading dispatch.

"Coherent style, different shading" means: keep one packing, one seed config and
all the size/weight/specular conventions fixed, and vary only ``shading_mode``
between variants.  Everything here is plain data so it can be built from vsketch
``Param``s or from a preset.
"""

from __future__ import annotations

from dataclasses import dataclass

SHADING_MODES = ["hatch", "stipple", "contour", "ringed"]
FRAME_STYLES = ["none", "circle", "rect", "circle+rect"]
OFFSET_MODES = ["random", "gaze"]


@dataclass
class Style:
    # --- feature-mapping thresholds (mm radius); reasonable defaults, tune later
    eye_big: float = 9.0        # r >= this -> full manga eye
    eye_min: float = 3.5        # r in [eye_min, eye_big) -> small eye
    #                              r < eye_min -> bulging tissue
    # --- eye proportions (fractions of the packed circle radius)
    iris_ratio: float = 0.62
    pupil_ratio: float = 0.36
    size_jitter_sd: float = 0.05  # per-eye pupil/iris size: x (1 + N(0, sd))
    # Iris+pupil offset off the sclera centre (auto-clamped so the iris stays in):
    #   "random" -> independent 2-D N(0, offset_sd*r) jitter
    #   "gaze"   -> every pupil slides toward `gaze_point`; magnitude grows with
    #               distance (offset = gaze_strength*(gaze_point - eye_centre)) so
    #               all eyes appear to stare at the same spot.
    offset_mode: str = "random"
    offset_sd: float = 0.05       # "random" mode: fraction of r
    gaze_point: tuple = (105.0, 148.5)  # mm, the spot all eyes look at ("gaze" mode)
    gaze_strength: float = 0.08   # "gaze" mode: shift per unit distance to the point
    specular_count: int = 2     # 1 or 2 negative-space highlights
    specular_main: float = 0.30  # main highlight radius / pupil radius
    specular_off: float = 0.34   # highlight centre offset / pupil radius (up-left)

    # --- shading
    shading_mode: str = "hatch"  # hatch | stipple | contour | ringed
    hatch_spacing: float = 0.5   # mm
    hatch_angle: float = 35.0    # degrees
    stipple_density: float = 0.9  # dots per mm^2
    contour_spacing: float = 0.6  # mm between concentric rings (also iris rings)

    # --- "ringed" eye style (hatched pupil + sector specular + iris arc-rings)
    # Angles are screen-space degrees (y points down; default points upper-left).
    specular_angle: float = 225.0    # direction of specular wedge & iris arcs
    specular_sector_deg: float = 42.0  # angular width of the negative-space wedge
    specular_inner_ratio: float = 0.18  # blunt the wedge apex (annular sector); 0 = pie
    specular_reach: float = 1.0      # wedge outer radius / pupil radius; >1 extends
    #                                  past the pupil over its outline + iris rings
    iris_sector_deg: float = 150.0   # angular width of the iris arc-rings (wider)
    iris_ring_outer_ratio: float = 0.88  # iris arcs reach this fraction of the sclera
    iris_ring_count: int = 6         # number of concentric arcs (count, not spacing,
    #                                  so every eye reads with the same arc density)
    iris_ring_taper_deg: float = 0.0  # shorten each ring inward by this many degrees
    #                                  (outermost full length) -> a tapered fan

    # --- orifice (solid dark fill; teeth + radial streaks are negative space)
    tooth_count: int = 14
    tooth_depth: float = 0.34    # fraction of radius the teeth reach inward
    tooth_width_frac: float = 0.45  # angular fraction of each slot the tooth fills
    orifice_line_reach: float = 0.33  # inner end of the white streaks (fraction of r)
    orifice_line_width: float = 0.035  # max streak width (fraction of r)
    orifice_lines_per_gap: int = 2    # white streaks per inter-tooth gap
    orifice_cross_hatch: bool = True  # cross-hatch the fill so it reads stark/dark

    # --- layers / weights
    stroke_layer: int = 1        # line work (sclera, iris, teeth, rings)
    fill_layer: int = 2          # dark shading (pupil, orifice interior, tissue)

    # --- frame
    frame_style: str = "circle"  # none | circle | rect | circle+rect

    def feature_for(self, radius: float, tag: str = "") -> str:
        """Map a circle to a feature.  An explicit seed ``tag`` wins."""
        if tag in ("orifice", "eye", "tissue"):
            # honour deliberate tags, but a tagged eye too small to read becomes tissue
            if tag == "eye" and radius < self.eye_min:
                return "tissue"
            return tag
        if radius >= self.eye_big:
            return "eye"
        if radius >= self.eye_min:
            return "eye"          # small eye uses the same renderer, scaled
        return "tissue"
