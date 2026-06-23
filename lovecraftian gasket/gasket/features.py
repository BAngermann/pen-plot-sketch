"""Renderer: map each packed circle to a Lovecraftian feature and emit strokes.

The defining trick (what makes an eye read as "manga"): the specular highlights
are **negative space** - we shade the pupil/iris *around* the highlight discs
rather than drawing them.  Implemented by subtracting the highlight discs from
the shaded region (Shapely) before hatching/stippling/contouring.

All feature functions take ``(vsk, circle, style)`` and draw at millimetre
coordinates (the sketch sets ``vsk.scale("mm")``).
"""

from __future__ import annotations

import math
import pathlib
import sys

import shapely.geometry as sg
from shapely.ops import unary_union

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from penfill import FillSpec, draw_geometry, fill_polygon  # noqa: E402

from geometry import Circle  # noqa: E402
from style import Style  # noqa: E402


def _disk(z: complex, r: float, segs: int = 64) -> sg.Polygon:
    return sg.Point(z.real, z.imag).buffer(r, quad_segs=segs)


def _size_mult(vsk, style: Style) -> float:
    """A per-feature size multiplier ~ 1 + N(0, size_jitter_sd), clamped sane."""
    sd = max(0.0, style.size_jitter_sd)
    if sd <= 0.0:
        return 1.0
    return min(1.6, max(0.4, 1.0 + sd * vsk.randomGaussian()))


def _offset(vsk, style: Style, z: complex, r: float, room: float) -> complex:
    """Offset for the iris+pupil group of the eye centred at ``z``, clamped so the
    iris (which leaves ``room`` mm before it touches the sclera) stays inside.

    ``offset_mode`` selects random per-eye jitter or a shared gaze toward a point.
    """
    if style.offset_mode == "gaze":
        g = complex(style.gaze_point[0], style.gaze_point[1])
        off = style.gaze_strength * (g - z)         # toward the point; far -> more
    else:
        sd = max(0.0, style.offset_sd)
        if sd <= 0.0:
            return 0j
        off = r * sd * complex(vsk.randomGaussian(), vsk.randomGaussian())
    cap = max(0.0, room) * 0.9
    if cap and abs(off) > cap:
        off *= cap / abs(off)
    return off


def _draw_shapely(vsk, geom, layer: int) -> None:
    """Draw a Shapely geometry's lines/boundaries on ``layer``."""
    if geom.is_empty:
        return
    vsk.stroke(layer)
    vsk.geometry(geom)


# --------------------------------------------------------------------------- #
# Shading: fill a (possibly holed) region while leaving the holes as blanks.
# --------------------------------------------------------------------------- #
def _shade_region(vsk, region: sg.Polygon, *, center: complex, radius: float,
                  style: Style) -> None:
    if region.is_empty:
        return
    mode = style.shading_mode
    layer = style.fill_layer

    # "ringed" is an eye-specific style; for generic regions (tissue / orifice
    # throats) it falls back to plain hatch so the series stays coherent.
    if mode in ("hatch", "ringed"):
        draw_geometry(vsk, fill_polygon(region, FillSpec(
            "hatch", layer,
            dict(spacing=style.hatch_spacing, angle=style.hatch_angle))))

    elif mode == "contour":
        rings = []
        rr = style.contour_spacing
        while rr < radius:
            ring = _disk(center, rr).exterior
            clipped = ring.intersection(region)
            if not clipped.is_empty:
                rings.append(clipped)
            rr += style.contour_spacing
        if rings:
            _draw_shapely(vsk, unary_union(rings), layer)

    elif mode == "stipple":
        n = max(1, int(style.stipple_density * math.pi * radius * radius))
        minx, miny, maxx, maxy = region.bounds
        vsk.stroke(layer)
        placed = 0
        attempts = 0
        while placed < n and attempts < n * 12:
            attempts += 1
            x = vsk.random(minx, maxx)
            y = vsk.random(miny, maxy)
            if region.contains(sg.Point(x, y)):
                vsk.circle(x, y, radius=0.18)
                placed += 1


def _speculars(center: complex, pr: float, style: Style) -> list[sg.Polygon]:
    """Negative-space highlight discs, offset toward the upper-left."""
    off = style.specular_off * pr
    discs = []
    main_c = center + complex(-off, -off)        # up-left (screen y is down)
    discs.append(_disk(main_c, style.specular_main * pr))
    if style.specular_count >= 2:
        sec_c = center + complex(off * 0.55, off * 0.55)  # small, lower-right
        discs.append(_disk(sec_c, style.specular_main * pr * 0.42))
    return discs


# --------------------------------------------------------------------------- #
# "ringed" eye-style helpers: sector specular + concentric iris arcs.
# Angles are in radians, screen space (y points down).
# --------------------------------------------------------------------------- #
def _annular_sector(center: complex, r_in: float, r_out: float,
                    a0: float, a1: float, segs: int = 40) -> sg.Polygon:
    """A wedge between radii ``r_in..r_out`` and angles ``a0..a1``.

    With ``r_in == 0`` this is a pie slice; ``r_in > 0`` blunts the apex
    (annular sector) so the centre is less pointy.
    """
    cx, cy = center.real, center.imag
    n = max(2, int(segs * (a1 - a0) / math.pi) + 2)
    outer = [(cx + r_out * math.cos(a0 + (a1 - a0) * i / n),
              cy + r_out * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    if r_in <= 1e-9:
        inner = [(cx, cy)]
    else:
        inner = [(cx + r_in * math.cos(a1 - (a1 - a0) * i / n),
                  cy + r_in * math.sin(a1 - (a1 - a0) * i / n))
                 for i in range(n + 1)]
    return sg.Polygon(outer + inner)


def _arc(center: complex, radius: float, a0: float, a1: float,
         segs: int = 48) -> sg.LineString:
    cx, cy = center.real, center.imag
    n = max(2, int(segs * (a1 - a0) / math.pi) + 2)
    return sg.LineString([(cx + radius * math.cos(a0 + (a1 - a0) * i / n),
                           cy + radius * math.sin(a0 + (a1 - a0) * i / n))
                          for i in range(n + 1)])


def _strip(p0: complex, p1: complex, w0: float, w1: float) -> sg.Polygon:
    """A quad along the segment ``p0->p1``, width ``w0`` at p0 and ``w1`` at p1."""
    d = p1 - p0
    L = abs(d) or 1.0
    perp = (d / L) * 1j                     # unit perpendicular
    a = p0 + perp * (w0 / 2)
    b = p0 - perp * (w0 / 2)
    cc = p1 - perp * (w1 / 2)
    dd = p1 + perp * (w1 / 2)
    return sg.Polygon([(a.real, a.imag), (b.real, b.imag),
                       (cc.real, cc.imag), (dd.real, dd.imag)])


def _eye_ringed(vsk, c: Circle, style: Style) -> None:
    """Manga eye: hatched pupil with a negative-space sector specular, and a
    wider sector of concentric arc-rings shading part of the iris."""
    z, r = c.z, c.r
    pr = r * style.pupil_ratio * _size_mult(vsk, style)
    iris_mult = _size_mult(vsk, style)
    iris_outer = r * style.iris_ring_outer_ratio * iris_mult
    ze = z + _offset(vsk, style, z, r, r - iris_outer)   # iris+pupil group offset
    a = math.radians(style.specular_angle)
    half_spec = math.radians(style.specular_sector_deg) / 2
    half_iris = math.radians(style.iris_sector_deg) / 2

    # The specular wedge.  ``specular_reach`` >= 1 lets it extend past the pupil
    # to cover the outline and bite into the iris rings (all as negative space).
    reach = max(0.05, style.specular_reach)
    spec = _annular_sector(ze, style.specular_inner_ratio * pr, pr * reach,
                           a - half_spec, a + half_spec)

    # sclera (centred)
    vsk.stroke(style.stroke_layer)
    vsk.circle(z.real, z.imag, radius=r)

    # iris arc-rings (shading) in a wide sector, same direction as the specular.
    # A fixed *count* (not mm spacing) keeps the arc density consistent across
    # eyes of very different sizes.  ``iris_ring_taper_deg`` shortens each ring
    # inward by that many degrees (outermost ring full length), giving a fan.
    rings = []
    iris_inner = pr * 1.18
    n = max(1, int(style.iris_ring_count))
    taper = math.radians(style.iris_ring_taper_deg)
    if iris_outer > iris_inner:
        step = (iris_outer - iris_inner) / n
        for i in range(n):
            rr = iris_inner + (i + 0.5) * step
            hw = max(math.radians(3.0), half_iris - (n - 1 - i) * taper / 2)
            arc = _arc(ze, rr, a - hw, a + hw)
            if reach > 1.0:                     # specular eats into the iris
                arc = arc.difference(spec)
            if not arc.is_empty:
                rings.append(arc)
    if rings:
        _draw_shapely(vsk, unary_union(rings), style.fill_layer)

    # pupil outline - full circle, unless the specular reaches past it (then the
    # outline is broken where the wedge covers it).
    vsk.stroke(style.stroke_layer)
    if reach > 1.0:
        outline = _disk(ze, pr).exterior.difference(spec)
        _draw_shapely(vsk, outline, style.stroke_layer)
    else:
        vsk.circle(ze.real, ze.imag, radius=pr)

    # hatched pupil minus the sector specular (negative space)
    pupil = _disk(ze, pr).difference(spec)
    if not pupil.is_empty:
        draw_geometry(vsk, fill_polygon(pupil, FillSpec(
            "hatch", style.fill_layer,
            dict(spacing=style.hatch_spacing, angle=style.hatch_angle))))


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
def eye(vsk, c: Circle, style: Style) -> None:
    if style.shading_mode == "ringed":
        _eye_ringed(vsk, c, style)
        return
    z, r = c.z, c.r
    vsk.stroke(style.stroke_layer)
    vsk.circle(z.real, z.imag, radius=r)                       # sclera (centred)
    ir = r * style.iris_ratio * _size_mult(vsk, style)
    pr = r * style.pupil_ratio * _size_mult(vsk, style)

    ze = z + _offset(vsk, style, z, r, r - ir)                 # iris+pupil group
    vsk.circle(ze.real, ze.imag, radius=ir)                    # iris ring
    specs = _speculars(ze, pr, style)
    pupil = _disk(ze, pr).difference(unary_union(specs))
    _shade_region(vsk, pupil, center=ze, radius=pr, style=style)


def tissue(vsk, c: Circle, style: Style) -> None:
    """Bulging tissue: the circle outline + a small specular dot left blank."""
    z, r = c.z, c.r
    vsk.stroke(style.stroke_layer)
    vsk.circle(z.real, z.imag, radius=r)
    # a single negative-space dot keeps it consistent with the eyes
    spec = _disk(z + complex(-0.3 * r, -0.3 * r), 0.22 * r)
    region = _disk(z, r * 0.92).difference(spec)
    _shade_region(vsk, region, center=z, radius=r, style=style)


def orifice(vsk, c: Circle, style: Style) -> None:
    """Tooth-studded orifice: a solid dark disc whose **teeth** and irregular
    **radial streaks** are negative space (paper) carved out of the fill, so the
    pale teeth read in stark contrast to the dark background."""
    z, r = c.z, c.r
    n = max(3, int(style.tooth_count))

    teeth = []

    # Teeth: inward-pointing triangles around the rim, left blank (negative space).
    slot = 2 * math.pi / n
    half = slot * style.tooth_width_frac / 2
    for i in range(n):
        ac = slot * (i + vsk.random(-0.12, 0.12))        # jittered centre angle
        hw = half * vsk.random(0.7, 1.2)
        base_r = r * vsk.random(0.95, 0.995)
        tip_r = r * (1 - style.tooth_depth) * vsk.random(0.72, 1.12)
        b1 = z + base_r * complex(math.cos(ac - hw), math.sin(ac - hw))
        b2 = z + base_r * complex(math.cos(ac + hw), math.sin(ac + hw))
        ta = ac + hw * vsk.random(-0.4, 0.4)
        tip = z + tip_r * complex(math.cos(ta), math.sin(ta))
        teeth.append(sg.Polygon([(b1.real, b1.imag), (tip.real, tip.imag),
                                 (b2.real, b2.imag)]))

    holes = list(teeth)

    # Irregular white streaks: placed at *random* angles around the rim (not one
    # per gap) so the maw reads as uneven folds rather than a regular sunburst.
    # Each runs from near the rim inward to about `orifice_line_reach`*r, with
    # random start/end, varying width, and a tilt.
    maxw = style.orifice_line_width * r
    n_streaks = int(round(n * max(0, style.orifice_lines_per_gap) * 0.55))
    for _ in range(n_streaks):
        a0 = vsk.random(0, 2 * math.pi)
        a1 = a0 + slot * vsk.random(-0.5, 0.5)           # inner end tilts away
        r0 = r * vsk.random(0.84, 0.99)                  # start near the rim
        r1 = r * style.orifice_line_reach * vsk.random(0.55, 1.4)  # ~1/3 r, varied
        if r0 - r1 < 0.12 * r:
            continue
        p0 = z + r0 * complex(math.cos(a0), math.sin(a0))
        p1 = z + r1 * complex(math.cos(a1), math.sin(a1))
        w0 = maxw * vsk.random(0.45, 1.0)
        w1 = maxw * vsk.random(0.0, 0.35)                # taper toward the centre
        holes.append(_strip(p0, p1, w0, w1))

    # Solid dark disc minus the negative-space holes; cross-hatch reads as black.
    region = _disk(z, r).difference(unary_union(holes))
    if not region.is_empty:
        draw_geometry(vsk, fill_polygon(region, FillSpec(
            "hatch", style.fill_layer,
            dict(spacing=style.hatch_spacing, angle=style.hatch_angle,
                 cross=bool(style.orifice_cross_hatch)))))

    # Crisp ink outline around each tooth so the fangs read sharply.
    for t in teeth:
        _draw_shapely(vsk, t.exterior, style.stroke_layer)

    # Crisp rim (ink, not a white ring).
    vsk.stroke(style.stroke_layer)
    vsk.circle(z.real, z.imag, radius=r)


def render_circle(vsk, c: Circle, style: Style) -> None:
    feature = style.feature_for(c.r, c.feature)
    if feature == "orifice":
        orifice(vsk, c, style)
    elif feature == "tissue":
        tissue(vsk, c, style)
    else:
        eye(vsk, c, style)
