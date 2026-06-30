"""Shared eye-style plumbing for the sketches that render gaskets as eyes.

vsketch needs each ``Param`` declared in the sketch class body (it reads
``cls.__dict__``), so the *parameter declarations* are repeated per sketch.  What
is shared here is only plain logic: the pen palette, mapping a sketch's parameter
*values* to a :class:`style.Style`, and the layer-colour vpype command.  Nothing
here touches vsketch internals.

A sketch that wants the full eye-shading UI declares the parameters listed in
``EYE_PARAM_NAMES`` (see ``sketch_gasket`` / ``sketch_integral``) and then calls
``build_style(self)`` / ``layer_colors(self)``.
"""

from __future__ import annotations

import pathlib
import sys

from style import Style

_REPO = pathlib.Path(__file__).resolve().parents[2]   # repo root (has pens/)
sys.path.insert(0, str(_REPO))
from penfill import install_swatches, load_pens        # noqa: E402

PENS = load_pens(_REPO / "pens")
PEN_NAMES = list(PENS)
COLOR_CHOICES = ["none"] + PEN_NAMES
install_swatches(PENS)

# The parameter names a sketch must declare to use build_style().  Kept here as
# documentation / a checklist (veins will extend this).
EYE_PARAM_NAMES = (
    "shading_mode eye_big eye_min eye_big_jitter eye_min_jitter "
    "iris_ratio pupil_ratio size_jitter_sd "
    "offset_mode offset_sd gaze_x gaze_y gaze_strength specular_count "
    "hatch_spacing hatch_angle contour_spacing stipple_density "
    "specular_angle specular_sector_deg specular_inner_ratio specular_reach "
    "iris_sector_deg iris_ring_outer_ratio iris_ring_count iris_ring_taper_deg "
    "tooth_count tooth_depth tooth_width_frac orifice_line_reach "
    "orifice_line_width orifice_lines_per_gap orifice_cross_hatch "
    "teeth_mode spiral_inner drop_inner drop_outer drop_curve "
    "line_color shade_color"
).split()


def build_style(sk, *, frame_style: str = "none") -> Style:
    """Build a :class:`Style` from a sketch's parameter *values*.

    ``sk`` is the sketch instance; it must expose the names in
    ``EYE_PARAM_NAMES`` plus ``landscape`` (used to resolve the gaze point).
    """
    w, h = (297.0, 210.0) if sk.landscape else (210.0, 297.0)
    return Style(
        eye_big=sk.eye_big, eye_min=sk.eye_min,
        eye_big_jitter=sk.eye_big_jitter, eye_min_jitter=sk.eye_min_jitter,
        iris_ratio=sk.iris_ratio, pupil_ratio=sk.pupil_ratio,
        size_jitter_sd=sk.size_jitter_sd,
        offset_mode=sk.offset_mode, offset_sd=sk.offset_sd,
        gaze_point=(sk.gaze_x * w, sk.gaze_y * h), gaze_strength=sk.gaze_strength,
        specular_count=int(sk.specular_count),
        shading_mode=sk.shading_mode,
        hatch_spacing=sk.hatch_spacing, hatch_angle=sk.hatch_angle,
        contour_spacing=sk.contour_spacing, stipple_density=sk.stipple_density,
        specular_angle=sk.specular_angle, specular_sector_deg=sk.specular_sector_deg,
        specular_inner_ratio=sk.specular_inner_ratio, specular_reach=sk.specular_reach,
        iris_sector_deg=sk.iris_sector_deg,
        iris_ring_outer_ratio=sk.iris_ring_outer_ratio,
        iris_ring_count=int(sk.iris_ring_count),
        iris_ring_taper_deg=sk.iris_ring_taper_deg,
        tooth_count=int(sk.tooth_count), tooth_depth=sk.tooth_depth,
        tooth_width_frac=sk.tooth_width_frac,
        orifice_line_reach=sk.orifice_line_reach,
        orifice_line_width=sk.orifice_line_width,
        orifice_lines_per_gap=int(sk.orifice_lines_per_gap),
        orifice_cross_hatch=bool(sk.orifice_cross_hatch),
        teeth_mode=sk.teeth_mode, spiral_inner=sk.spiral_inner,
        drop_inner=sk.drop_inner, drop_outer=sk.drop_outer,
        drop_curve=sk.drop_curve,
        stroke_layer=1, fill_layer=2, frame_style=frame_style,
    )


def layer_colors(sk) -> str:
    """vpype ``color`` command for layer 1 (line) / 2 (shade); ``none`` -> black."""
    line_hex = "black" if sk.line_color == "none" \
        else PENS.get(sk.line_color, "black")
    shade_hex = line_hex if sk.shade_color == "none" \
        else PENS.get(sk.shade_color, "black")
    return f"color --layer 1 {line_hex} color --layer 2 {shade_hex}"
