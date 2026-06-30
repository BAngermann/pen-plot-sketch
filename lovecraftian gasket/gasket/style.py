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
TEETH_MODES = ["ring", "spiral"]          # orifice tooth layout
DROP_CURVES = ["linear", "sqrt", "square"]  # tooth-loss probability falloff


@dataclass
class Style:
    # --- feature mapping (mm radius).  Two eye renderers split by size:
    #   r >= eye_big           -> elaborate eye   (eye(): iris rings, speculars...)
    #   eye_min <= r < eye_big -> simple eye      (simple_eye(): plain fill + dot)
    #   r < eye_min            -> vein            (interstitial; not yet drawn)
    # The recursion floors at eye_min, so a gasket has no sub-eye_min circles -
    # that space is reserved for veins.
    eye_big: float = 9.0
    eye_min: float = 3.5
    # Per-circle uniform jitter (mm, full width) on each threshold, so circles
    # near a cutoff don't all fall the same way - breaks up the over-regular
    # "every circle of this size is the same feature" banding.  0 = hard cutoff.
    eye_big_jitter: float = 0.0
    eye_min_jitter: float = 0.0
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
    # --- teeth layout: "ring" (a single rim row, uses tooth_count) or "spiral"
    # (sunflower phyllotaxis - teeth on a golden-angle lattice whose count is a
    # random Fibonacci number per orifice, giving recognizable spiral arms).
    teeth_mode: str = "ring"
    spiral_inner: float = 0.18    # spiral: no teeth inside this fraction of r
    drop_inner: float = 0.92      # spiral: tooth-loss probability at spiral_inner (~1)
    drop_outer: float = 0.05      # spiral: tooth-loss probability at the rim (~0)
    drop_curve: str = "linear"    # spiral: drop-prob falloff inner->outer

    # --- layers / weights
    stroke_layer: int = 1        # line work (sclera, iris, teeth, rings)
    fill_layer: int = 2          # dark shading (pupil, orifice interior, simple eye)

    # --- frame
    frame_style: str = "circle"  # none | circle | rect | circle+rect

    def feature_for(self, radius: float, tag: str = "",
                    big_jit: float = 0.0, min_jit: float = 0.0) -> str:
        """Map a circle to a feature.  A seed ``tag`` of "orifice" wins; otherwise
        size decides: ``>= eye_big`` elaborate ``eye``, ``>= eye_min`` ``simple_eye``,
        else a ``vein`` (interstitial filler, not yet implemented so not drawn).

        ``big_jit``/``min_jit`` are signed per-circle offsets added to the two
        thresholds (drawn from ``eye_*_jitter`` by the caller) so the cutoff is
        soft rather than a hard radius line."""
        if tag == "orifice":
            return "orifice"
        if radius < self.eye_min + min_jit:
            return "vein"
        return "eye" if radius >= self.eye_big + big_jit else "simple_eye"
