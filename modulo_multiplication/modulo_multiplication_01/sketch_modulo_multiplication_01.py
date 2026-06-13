import vsketch
import vpype as vp
import math

class ModuloMultiplication01Sketch(vsketch.SketchClass):
    r = vsketch.Param(4.0)
    multiplier = vsketch.Param(8)
    n = vsketch.Param(500)
    show_text = vsketch.Param(True)
    show_circle = vsketch.Param(True)
    hyperbolic = vsketch.Param(False)
    draw_interior = vsketch.Param(True)
    draw_inverted = vsketch.Param(False)
    cutoff_r = vsketch.Param(4.5)
    square_clip = vsketch.Param(False)
    clip_aspect_ratio = vsketch.Param(1.0)
    clip_box_offset_x = vsketch.Param(0.0)
    clip_box_offset_y = vsketch.Param(0.0)
    show_clip_boundary = vsketch.Param(False)
    offset_x = vsketch.Param(0.0)
    offset_y = vsketch.Param(0.0)
    text_size = vsketch.Param(0.5)
    text_offset_x = vsketch.Param(0.0)
    text_offset_y = vsketch.Param(0.0)
    page_size = vsketch.Param("10cmx10cm")
    landscape = vsketch.Param(False)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size(self.page_size, landscape = self.landscape ,center=False)
        vsk.scale("cm")
        # vsk.width/height are in CSS pixels; convert to cm (the current user unit)
        # using the same conversion vpype uses internally.
        px_per_cm = vp.convert_length("1cm")
        vsk.translate(
            vsk.width / px_per_cm / 2 + self.offset_x,
            vsk.height / px_per_cm / 2 + self.offset_y,
        )
        twopi = 6.28318530718
        if self.show_circle:
            vsk.circle(0, 0, 2 * self.r)

        tpn = twopi / self.n
        for i in range(0, self.n):
            x1 = -self.r * math.cos(i * tpn)
            y1 =  self.r * math.sin(i * tpn)
            j = (i * self.multiplier) % self.n
            x2 = -self.r * math.cos(j * tpn)
            y2 =  self.r * math.sin(j * tpn)
            if self.hyperbolic:
                self._hyperbolic_line(vsk, x1, y1, x2, y2)
            else:
                if self.draw_interior:
                    vsk.line(x1, y1, x2, y2)
                if self.draw_inverted:
                    self._inverted_chord(vsk, x1, y1, x2, y2)

        if self.show_clip_boundary:
            C = self.cutoff_r
            if self.square_clip:
                ar = self.clip_aspect_ratio
                ox, oy = self.clip_box_offset_x, self.clip_box_offset_y
                vsk.rect(ox - C * ar, oy - C, 2 * C * ar, 2 * C)
            else:
                vsk.circle(0, 0, 2 * C)

        if self.show_text:
            C = self.cutoff_r
            hw = C * self.clip_aspect_ratio  # horizontal extent matches box half-width
            box_x = self.clip_box_offset_x
            ty = self.clip_box_offset_y + C + self.text_offset_y
            sz = str(self.text_size)
            vsk.text(text=f'n={self.n}', x=-hw + box_x + self.text_offset_x, y=ty, size=sz, mode="transform", font="futural")
            vsk.text(text=f'x={self.multiplier}', x=hw + box_x - self.text_offset_x, y=ty, size=sz, mode="transform", font="futural", align="right")

    def _hyperbolic_line(self, vsk, x1, y1, x2, y2):
        R = self.r
        cross = x1 * y2 - x2 * y1

        if abs(cross) < 1e-9 * R * R:
            # Antipodal: geodesic is a diameter.
            if self.draw_interior:
                vsk.line(x1, y1, x2, y2)
            if self.draw_inverted:
                # Inversion of a diameter = two outward radial rays from each boundary point.
                # Extend each ray well past C so the clip function finds the real boundary
                # (circle of radius C inscribes inside square [-C,C]², so a point exactly
                # at radius C would be inside the square and never reach its boundary).
                C = self.cutoff_r
                clip = self._clip_to_box if self.square_clip else self._clip_to_disk
                far = self._far_extent(C, R)
                for px, py in [(x1, y1), (x2, y2)]:
                    seg = clip(px, py, px * far / R, py * far / R, C)
                    if seg:
                        vsk.line(*seg)
            return

        R2 = R * R
        cx = R2 * (y2 - y1) / cross
        cy = R2 * (x1 - x2) / cross
        arc_r = math.sqrt((cx - x1) ** 2 + (cy - y1) ** 2)

        a1 = math.atan2(y1 - cy, x1 - cx)
        a2 = math.atan2(y2 - cy, x2 - cx)

        # Direction from arc centre toward disk origin marks the inner-arc midpoint.
        mid_inner = math.atan2(-cy, -cx)
        a2_rel  = (a2 - a1)        % (2 * math.pi)
        mid_rel = (mid_inner - a1) % (2 * math.pi)

        if mid_rel < a2_rel:
            start_a, sweep = a1, a2_rel
        else:
            start_a, sweep = a2, 2 * math.pi - a2_rel

        if self.draw_interior:
            self._draw_arc(vsk, cx, cy, arc_r, start_a, sweep)

        if self.draw_inverted:
            # The arc circle is orthogonal to the boundary circle, so inversion in
            # the boundary circle maps the arc circle to itself. The inverted arc is
            # therefore the complementary arc on the same circle.
            self._draw_arc_clipped(vsk, cx, cy, arc_r, start_a + sweep, 2 * math.pi - sweep)

    def _inverted_chord(self, vsk, x1, y1, x2, y2):
        """Draw the image of chord P1P2 under inversion in the boundary circle.

        A chord not through the origin inverts to an arc of the circumscribed circle
        of {O=(0,0), P1, P2}: the arc from P1 to P2 that does not pass through O.
        Center satisfies x_i·cx + y_i·cy = R²/2 for each endpoint (same Cramer
        system as the hyperbolic arc but with R²/2 instead of R² on the RHS).
        A diameter inverts to two outward radial rays.
        """
        R = self.r
        cross = x1 * y2 - x2 * y1

        if abs(cross) < 1e-9 * R * R:
            C = self.cutoff_r
            clip = self._clip_to_box if self.square_clip else self._clip_to_disk
            far = C * 2
            for px, py in [(x1, y1), (x2, y2)]:
                seg = clip(px, py, px * far / R, py * far / R, C)
                if seg:
                    vsk.line(*seg)
            return

        R2 = R * R
        cx = (R2 / 2) * (y2 - y1) / cross
        cy = (R2 / 2) * (x1 - x2) / cross
        arc_r = math.sqrt(cx * cx + cy * cy)  # distance from center to O

        a_O = math.atan2(-cy, -cx)
        a1  = math.atan2(y1 - cy, x1 - cx)
        a2  = math.atan2(y2 - cy, x2 - cx)

        a2_rel = (a2 - a1) % (2 * math.pi)
        aO_rel = (a_O - a1) % (2 * math.pi)

        if aO_rel < a2_rel:
            # CCW a1→a2 passes through O → take the complementary arc
            start_a, sweep = a2, 2 * math.pi - a2_rel
        else:
            start_a, sweep = a1, a2_rel

        self._draw_arc_clipped(vsk, cx, cy, arc_r, start_a, sweep)

    def _draw_arc(self, vsk, cx, cy, arc_r, start_a, sweep, segments=360):
        for i in range(segments):
            ta = start_a + sweep * i / segments
            tb = start_a + sweep * (i + 1) / segments
            vsk.line(cx + arc_r * math.cos(ta), cy + arc_r * math.sin(ta),
                     cx + arc_r * math.cos(tb), cy + arc_r * math.sin(tb))

    def _draw_arc_clipped(self, vsk, cx, cy, arc_r, start_a, sweep, segments=360):
        clip = self._clip_to_box if self.square_clip else self._clip_to_disk
        C = self.cutoff_r
        for i in range(segments):
            ta = start_a + sweep * i / segments
            tb = start_a + sweep * (i + 1) / segments
            seg = clip(cx + arc_r * math.cos(ta), cy + arc_r * math.sin(ta),
                       cx + arc_r * math.cos(tb), cy + arc_r * math.sin(tb), C)
            if seg:
                vsk.line(*seg)

    def _clip_to_disk(self, x1, y1, x2, y2, C):
        """Clip segment to disk |z| ≤ C, finding the exact boundary crossing."""
        C2 = C * C
        in1 = x1 * x1 + y1 * y1 <= C2
        in2 = x2 * x2 + y2 * y2 <= C2

        if not in1 and not in2:
            return None
        if in1 and in2:
            return x1, y1, x2, y2

        dx, dy = x2 - x1, y2 - y1
        a = dx * dx + dy * dy
        if a < 1e-15:
            return None
        b = 2.0 * (x1 * dx + y1 * dy)
        c = x1 * x1 + y1 * y1 - C2
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        sq = math.sqrt(disc)

        if in1:          # p1 inside → clip p2 to exit point (larger root)
            t = min(1.0, max(0.0, (-b + sq) / (2 * a)))
            return x1, y1, x1 + t * dx, y1 + t * dy
        else:            # p2 inside → clip p1 to entry point (smaller root)
            t = min(1.0, max(0.0, (-b - sq) / (2 * a)))
            return x1 + t * dx, y1 + t * dy, x2, y2

    def _far_extent(self, C, R):
        """Compute a ray endpoint guaranteed to lie outside the active clip region."""
        if self.square_clip:
            ar = self.clip_aspect_ratio
            ox, oy = abs(self.clip_box_offset_x), abs(self.clip_box_offset_y)
            return (C * ar + ox + C + oy + R) * 2
        return C * 2

    def _clip_to_box(self, x1, y1, x2, y2, C):
        """Clip segment to rectangle [ox-C·ar, ox+C·ar] × [oy-C, oy+C] using Liang-Barsky."""
        ar = self.clip_aspect_ratio
        ox, oy = self.clip_box_offset_x, self.clip_box_offset_y
        dx, dy = x2 - x1, y2 - y1
        p = [-dx,          dx,          -dy,     dy     ]
        q = [x1 - (ox - C*ar), (ox + C*ar) - x1,
             y1 - (oy - C),    (oy + C) - y1   ]
        t0, t1 = 0.0, 1.0
        for pi, qi in zip(p, q):
            if abs(pi) < 1e-15:
                if qi < 0:
                    return None
            elif pi < 0:
                t0 = max(t0, qi / pi)
            else:
                t1 = min(t1, qi / pi)
        if t0 > t1:
            return None
        return x1 + t0 * dx, y1 + t0 * dy, x1 + t1 * dx, y1 + t1 * dy

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    ModuloMultiplication01Sketch.display()
