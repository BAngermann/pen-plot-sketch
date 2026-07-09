"""Integral Apollonian packing crop browser.

A finder for visually appealing arrangements: pick an *integral* packing (root
quadruple), then zoom/pan the enclosing circle relative to the page to frame a
crop.  The enclosing circle is normally larger than the page, so the page is a
window onto the gasket - move it around and change ``enclosing_r`` to explore.
Flip ``as_eyes`` to preview the crop rendered as gasket eyes.

    vsk run integral/sketch_integral.py   (from the project root)
"""

import pathlib
import sys

import vsketch

_HERE = pathlib.Path(__file__).resolve().parent
_GASKET = _HERE.parent / "gasket"          # shared library
sys.path.insert(0, str(_GASKET))

from eyestyle import COLOR_CHOICES, build_style, layer_colors  # noqa: E402
from features import render_circle                         # noqa: E402
from geometry import Circle                                # noqa: E402
from integral import label, place_quadruple, root_quadruples  # noqa: E402
from packing import a4_clip, pack                          # noqa: E402
from style import (DROP_CURVES, OFFSET_MODES,              # noqa: E402
                   SHADING_MODES, TEETH_MODES)

QUADS = root_quadruples()


def _touches_clip(c: Circle, clip) -> bool:
    """Does the disk overlap the clip rect at all (even if not fully inside)?"""
    nx = min(max(c.z.real, clip.x0), clip.x1)
    ny = min(max(c.z.imag, clip.y0), clip.y1)
    return abs(complex(nx, ny) - c.z) <= c.r


class IntegralSketch(vsketch.SketchClass):
    landscape = vsketch.Param(False)
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2, unit="mm")
    margin = vsketch.Param(20.0, min_value=0)              # mm

    # --- which packing (browse the catalogue)
    packing_index = vsketch.Param(0, min_value=0, max_value=len(QUADS) - 1)

    # --- the enclosing circle placed in page space (mm): pan + zoom
    enclosing_x = vsketch.Param(105.0)                    # mm, centre on the page
    enclosing_y = vsketch.Param(148.5)
    enclosing_r = vsketch.Param(300.0, min_value=10)      # mm radius (> page = crop)

    # --- packing detail
    max_depth = vsketch.Param(60, min_value=1)
    # Recursively re-pack the largest circle: treat it as the enclosing circle of
    # a fresh packing with the SAME quadruple, and repeat into that sub-packing's
    # largest circle.  0 = off.  (Only the single largest is recursed, not the
    # other large circles.)
    recursion_depth = vsketch.Param(0, min_value=0, max_value=8)

    # --- render
    as_eyes = vsketch.Param(False)                        # preview as gasket eyes
    draw_enclosing = vsketch.Param(True)                  # show the enclosing rim

    # --- eye-shading options (only used when as_eyes; declared explicitly because
    # vsketch reads each sketch class's own Params).  Values are mapped to a Style
    # by eyestyle.build_style; keep the set in sync with sketch_gasket.
    shading_mode = vsketch.Param("hatch", choices=SHADING_MODES)
    eye_big = vsketch.Param(9.0, min_value=1.0, decimals=1)   # mm
    eye_min = vsketch.Param(3.5, min_value=0.5, decimals=1)   # mm
    eye_big_jitter = vsketch.Param(0.0, min_value=0.0, decimals=1)  # mm, full width
    eye_min_jitter = vsketch.Param(0.0, min_value=0.0, decimals=1)  # mm, full width
    # Orifice substitution: an eye with r >= min_orifice is replaced by a
    # tooth-studded orifice with probability orifice_prob (rolled per circle).
    min_orifice = vsketch.Param(8.0, min_value=0.5, decimals=1)     # mm
    orifice_prob = vsketch.Param(0.0, min_value=0.0, max_value=1.0, decimals=2)
    iris_ratio = vsketch.Param(0.62, min_value=0.1, max_value=0.95, decimals=2)
    pupil_ratio = vsketch.Param(0.36, min_value=0.05, max_value=0.9, decimals=2)
    size_jitter_sd = vsketch.Param(0.05, min_value=0.0, max_value=0.3, decimals=3)
    offset_mode = vsketch.Param("random", choices=OFFSET_MODES)
    offset_sd = vsketch.Param(0.05, min_value=0.0, max_value=0.4, decimals=3)
    gaze_x = vsketch.Param(0.5, min_value=0.0, max_value=1.0, decimals=2)
    gaze_y = vsketch.Param(0.4, min_value=0.0, max_value=1.0, decimals=2)
    gaze_strength = vsketch.Param(0.08, min_value=0.0, max_value=0.5, decimals=3)
    specular_count = vsketch.Param(2, min_value=0, max_value=2)
    hatch_spacing = vsketch.Param(0.5, min_value=0.1, decimals=2)   # mm
    hatch_angle = vsketch.Param(35.0)
    contour_spacing = vsketch.Param(0.6, min_value=0.1, decimals=2)  # mm
    stipple_density = vsketch.Param(0.9, min_value=0.05, decimals=2)
    specular_angle = vsketch.Param(225.0)
    specular_sector_deg = vsketch.Param(42.0, min_value=2.0)
    specular_inner_ratio = vsketch.Param(0.18, min_value=0.0, max_value=0.9, decimals=2)
    specular_reach = vsketch.Param(1.0, min_value=0.1, max_value=3.0, decimals=2)
    iris_sector_deg = vsketch.Param(150.0, min_value=2.0)
    iris_ring_outer_ratio = vsketch.Param(0.88, min_value=0.4, max_value=0.98, decimals=2)
    iris_ring_count = vsketch.Param(6, min_value=1, max_value=30)
    iris_ring_taper_deg = vsketch.Param(0.0, min_value=0.0)
    tooth_count = vsketch.Param(14, min_value=3)
    tooth_depth = vsketch.Param(0.34, min_value=0.05, max_value=0.9, decimals=2)
    tooth_width_frac = vsketch.Param(0.45, min_value=0.1, max_value=0.95, decimals=2)
    orifice_line_reach = vsketch.Param(0.33, min_value=0.05, max_value=0.9, decimals=2)
    orifice_line_width = vsketch.Param(0.035, min_value=0.005, max_value=0.2, decimals=3)
    orifice_lines_per_gap = vsketch.Param(2, min_value=0, max_value=8)
    orifice_cross_hatch = vsketch.Param(True)
    teeth_mode = vsketch.Param("ring", choices=TEETH_MODES)
    spiral_inner = vsketch.Param(0.18, min_value=0.0, max_value=0.95, decimals=2)
    drop_inner = vsketch.Param(0.92, min_value=0.0, max_value=1.0, decimals=2)
    drop_outer = vsketch.Param(0.05, min_value=0.0, max_value=1.0, decimals=2)
    drop_curve = vsketch.Param("linear", choices=DROP_CURVES)
    line_color = vsketch.Param("none", choices=COLOR_CHOICES)
    shade_color = vsketch.Param("none", choices=COLOR_CHOICES)

    def _quad(self):
        return QUADS[min(int(self.packing_index), len(QUADS) - 1)]

    def _pack_in(self, enc_z: complex, enc_r: float, clip):
        """Place the quadruple so its enclosing circle is ``(enc_z, enc_r)`` and
        pack it (clipped to the page).  Returns ``(outer, seeds, circles)``."""
        k0, k1, k2, k3 = self._quad()
        c0, c1, c2, c3 = place_quadruple(k0, k1, k2, k3)
        scale = enc_r * abs(k0)                    # outer radius == enc_r
        off = enc_z

        def xf(c: Circle) -> Circle:
            return Circle.from_center(off + c.z * scale, c.r * scale,
                                      inside=(c.k < 0))

        outer = xf(c0)
        seeds = [xf(c1), xf(c2), xf(c3)]
        # Pack a half-jitter below eye_min so the vein cutoff has circles on both
        # sides of its jittered line (otherwise the jitter only ever removes eyes).
        r_floor = max(0.1, self.eye_min - 0.5 * self.eye_min_jitter)
        circles = pack(seeds, outer, clip, r_min=r_floor,
                       max_depth=int(self.max_depth))
        return outer, seeds, circles

    def _build(self, clip):
        """Pack the crop, optionally recursing into the largest circle.

        Returns ``(base_outer, items)`` where ``items`` is a list of
        ``(circle, is_encloser)``; an *encloser* is a largest circle that was
        re-packed (drawn as a plain outline rather than an eye, since its interior
        holds the sub-packing)."""
        enc_z = complex(self.enclosing_x, self.enclosing_y)
        enc_r = self.enclosing_r
        depth = int(self.recursion_depth)
        base_outer = None
        items: list[tuple[Circle, bool]] = []

        for level in range(depth + 1):
            outer, seeds, circles = self._pack_in(enc_z, enc_r, clip)
            if level == 0:
                base_outer = outer
            # The largest circle of a packing is always a root seed - which may be
            # cropped by the page.  Recurse into it anyway (filling whatever part
            # falls on the page); the sub-packing is itself clipped to the page.
            largest = max(seeds, key=lambda c: c.r)
            recurse = (level < depth and largest.r >= 2 * self.eye_min
                       and _touches_clip(largest, clip))
            # `c is largest` marks the encloser only when it is actually drawn
            # (i.e. fully on the page); a cropped encloser is filled but not drawn.
            items.extend((c, recurse and c is largest) for c in circles)
            if not recurse:
                break
            enc_z, enc_r = largest.z, largest.r
        return base_outer, items

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=self.landscape, center=False)
        vsk.penWidth(self.pen_width)
        vsk.scale("mm")

        clip = a4_clip(margin=self.margin, landscape=self.landscape)
        outer, items = self._build(clip)

        # layer 4: enclosing rim (if it crosses the page)
        vsk.stroke(4)
        if self.draw_enclosing:
            vsk.circle(outer.z.real, outer.z.imag, radius=outer.r)

        # layer 1 (+2): the crop.  An "encloser" (a largest circle that was
        # re-packed) is drawn as a plain outline - its interior holds the
        # sub-packing - rather than as a full eye, and `draw_enclosing` suppresses
        # that outline just like it does the top-level rim.
        if self.as_eyes:
            style = build_style(self)
            for c, is_enc in items:
                if is_enc:
                    if self.draw_enclosing:
                        vsk.stroke(1)
                        vsk.circle(c.z.real, c.z.imag, radius=c.r)
                else:
                    # Roll a big-enough eye into a tooth-studded orifice; the
                    # "orifice" tag then wins in style.feature_for.
                    if self.orifice_prob > 0.0 and c.r >= self.min_orifice \
                            and vsk.random(0, 1) < self.orifice_prob:
                        c.feature = "orifice"
                    render_circle(vsk, c, style)
        else:
            vsk.stroke(1)
            for c, _ in items:
                vsk.circle(c.z.real, c.z.imag, radius=c.r)

        # console-only status line (no on-canvas text)
        q = self._quad()
        rec = f"  rec={int(self.recursion_depth)}" if self.recursion_depth else ""
        print("integral:", f"#{int(self.packing_index)}/{len(QUADS) - 1}  "
              f"{label(q)}  circles={len(items)}  R={self.enclosing_r:.0f}mm{rec}")

        # eye fills (layers 1/2) get the chosen pen colours; the enclosing rim
        # (layer 4) stays gray.
        eye_colors = layer_colors(self) if self.as_eyes else \
            "color --layer 1 black color --layer 2 #888888"
        vsk.vpype(eye_colors + " color --layer 4 #cccccc")

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    IntegralSketch.display()
