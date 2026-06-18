import vsketch
import vpype as vp
import math

class ModuloMultiplication01Sketch(vsketch.SketchClass):
    r = vsketch.Param(1.0)
    page_margin_x = vsketch.Param(1.5, min_value=0,decimals = 2)
    page_margin_y = vsketch.Param(1.5, min_value=0,decimals = 2)
    plot_margin_x = vsketch.Param(.7, min_value=0,decimals = 2)
    plot_margin_y = vsketch.Param(.7, min_value=0,decimals = 2)
    n_min = vsketch.Param(2, min_value=2)
    n_max = vsketch.Param(8, min_value=2)
    multiplier_min = vsketch.Param(0, min_value=0)
    multiplier_max = vsketch.Param(-1)   # -1 = use n for each row
    # Shift the multiplier window as n grows: added per increment of n (0 = off).
    multiplier_min_step = vsketch.Param(0)
    multiplier_max_step = vsketch.Param(0)
    # Apply the step on all rows, or only on rows with even / odd n.
    multiplier_step_parity = vsketch.Param("all", choices=["all", "even", "odd"])
    # Shift each row right so columns align by multiplier value (staircase gap on
    # the left) instead of every row starting at the page edge.
    align_by_multiplier = vsketch.Param(False)
    show_text = vsketch.Param(True)
    text_scale = vsketch.Param(0.2, min_value=0.01)
    page_size = vsketch.Param("a4")
    landscape = vsketch.Param(False)
    show_guides = vsketch.Param(False)
    hex_grid = vsketch.Param(False)
    hex_shift_right = vsketch.Param(True)
    # Fill the curvilinear-triangle gaps between three tangent circles (hex grid,
    # zero plot margins) with concentric arcs around each of the three centers.
    fill_hex_gaps = vsketch.Param(False)
    gap_arc_step = vsketch.Param(0.03, min_value=0.001, decimals=3)  # radius increment
    # Also arc the exposed (boundary) sides of edge circles, to match the outline
    # weight of the filled interior.
    fill_boundary = vsketch.Param(True)

    def _step_offset(self, n):
        """How many steps to apply at row n, honouring the parity restriction."""
        if self.multiplier_step_parity == "all":
            return n - self.n_min
        parity = 0 if self.multiplier_step_parity == "even" else 1
        return sum(1 for m in range(self.n_min + 1, n + 1) if m % 2 == parity)

    def _mul_range(self, n):
        offset = self._step_offset(n)
        m_min = self.multiplier_min + self.multiplier_min_step * offset
        if self.multiplier_max >= 0:
            stop = self.multiplier_max + self.multiplier_max_step * offset + 1
        else:
            stop = n + 1   # auto: use n
        return range(m_min, stop)

    # ── Hex-gap fill ───────────────────────────────────────────────────────────

    def _neighbors(self, centers):
        """Indices of circles at the tangency distance 2r (within fp tolerance)."""
        r = self.r
        n = len(centers)
        thr2 = (2 * r * 1.001) ** 2
        min2 = (r * 0.5) ** 2
        neigh = [[] for _ in range(n)]
        for i in range(n):
            xi, yi = centers[i]
            for k in range(i + 1, n):
                xk, yk = centers[k]
                d2 = (xi - xk) ** 2 + (yi - yk) ** 2
                if min2 < d2 <= thr2:
                    neigh[i].append(k)
                    neigh[k].append(i)
        return neigh

    def _fill_hex_gaps(self, vsk, centers):
        """Fill each curvilinear-triangle gap (3 mutually tangent circles) with
        concentric arcs around the three circle centres."""
        if len(centers) < 3 or self.gap_arc_step <= 0:
            return
        neigh = self._neighbors(centers)
        vsk.stroke(2)            # same layer as the circles
        for i in range(len(centers)):
            ni = set(neigh[i])
            for j in neigh[i]:
                if j <= i:
                    continue
                for k in neigh[j]:
                    if k > j and k in ni:           # i < j < k, mutually tangent
                        self._gap_arcs(vsk, centers[i], centers[j], centers[k])

    def _fill_boundary_arcs(self, vsk, centers):
        """Strengthen the grid outline: around each circle, fill the exposed
        (non-triangle) angular sectors with concentric arcs whose span shrinks as
        the radius grows — the outward analogue of the gap fill.

        A sector wider than 60° between two consecutive neighbours is open (no
        third circle, hence no gap triangle), so it is filled.  At radius R each
        bounding neighbour (radius r, distance 2r) hides a half-angle
        ``arccos((R² + 3r²) / 4Rr)`` of the arc, which grows with R — so the arc
        shrinks step by step, mirroring the interior fill.
        """
        r, step = self.r, self.gap_arc_step
        if len(centers) < 2 or step <= 0:
            return
        neigh = self._neighbors(centers)
        r_max = 2 * r / math.sqrt(3)
        sixty = math.pi / 3
        vsk.stroke(2)
        for i, (cx, cy) in enumerate(centers):
            if not neigh[i]:
                continue
            dirs = sorted(math.atan2(centers[k][1] - cy, centers[k][0] - cx)
                          for k in neigh[i])
            m = len(dirs)
            for a in range(m):
                phi1 = dirs[a]
                phi2 = dirs[(a + 1) % m] + (2 * math.pi if a + 1 == m else 0.0)
                if phi2 - phi1 <= sixty + 1e-6:
                    continue                        # triangle sector, already filled
                radius = r + step
                while radius <= r_max + 1e-9:
                    cval = (radius * radius + 3 * r * r) / (4 * radius * r)
                    theta = math.acos(max(-1.0, min(1.0, cval)))
                    a0, a1 = phi1 + theta, phi2 - theta
                    if a1 - a0 > 1e-3:
                        self._draw_arc(vsk, cx, cy, radius, a0, a1)
                    radius += step

    def _gap_arcs(self, vsk, a, b, c):
        r, step = self.r, self.gap_arc_step
        gx = (a[0] + b[0] + c[0]) / 3.0
        gy = (a[1] + b[1] + c[1]) / 3.0
        verts = (a, b, c)
        r_max = max(math.hypot(v[0] - gx, v[1] - gy) for v in verts)
        for vx, vy in verts:
            dir_g = math.atan2(gy - vy, gx - vx)
            others = []
            for ox, oy in verts:
                if ox == vx and oy == vy:
                    continue
                dir_o = math.atan2(oy - vy, ox - vx)
                d_o = math.hypot(ox - vx, oy - vy)
                phi = math.atan2(math.sin(dir_o - dir_g), math.cos(dir_o - dir_g))
                others.append((phi, d_o))
            others.sort()
            (phi_lo, d_lo), (phi_hi, d_hi) = others
            radius = r + step
            while radius <= r_max + step:
                # Half-angle from the centre line to where the equal radius-R
                # circles around two centres intersect: arccos(d / 2R).
                c_lo, c_hi = d_lo / (2 * radius), d_hi / (2 * radius)
                if c_lo <= 1.0 and c_hi <= 1.0:
                    off_lo = phi_lo + math.acos(c_lo)
                    off_hi = phi_hi - math.acos(c_hi)
                    if off_hi - off_lo <= 1e-3:
                        break                       # arc has collapsed to the centroid
                    self._draw_arc(vsk, vx, vy, radius, dir_g + off_lo, dir_g + off_hi)
                radius += step

    def _draw_arc(self, vsk, cx, cy, radius, a0, a1):
        span = a1 - a0
        steps = max(2, int(abs(span) * radius / 0.03))   # ~0.3 mm segments
        xs, ys = [], []
        for t in range(steps + 1):
            ang = a0 + span * t / steps
            xs.append(cx + radius * math.cos(ang))
            ys.append(cy + radius * math.sin(ang))
        vsk.polygon(xs, ys, close=False)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size(self.page_size, landscape=self.landscape, center=False)
        vsk.scale("cm")

        if self.show_guides:
            px_per_cm = vp.convert_length("1cm")
            pw = vsk.width / px_per_cm
            ph = vsk.height / px_per_cm
            if pw > ph:
                vsk.line(pw / 2, 0, pw / 2, ph)
            elif ph > pw:
                vsk.line(0, ph / 2, pw, ph / 2)
            else:
                vsk.line(pw / 2, 0, pw / 2, ph)
                vsk.line(0, ph / 2, pw, ph / 2)

        twopi = 6.28318530718
        text_gap = 3 * self.text_scale if self.show_text else 0
        vsk.translate(self.page_margin_x, self.page_margin_y)

        col_step = self.plot_margin_x + 2 * self.r
        if self.hex_grid:
            row_step = self.plot_margin_y + math.sqrt(3) * self.r
        else:
            row_step = self.plot_margin_y + 2 * self.r
        hex_half = col_step / 2 if self.hex_shift_right else -col_step / 2

        if self.show_text:
            vsk.pushMatrix()
            vsk.translate(0, text_gap)
            for n in range(self.n_min, self.n_max + 1):
                vsk.text(text=f'n={n}', x=-self.r, y=self.r, size=self.text_scale, mode="transform", font="futural")
                vsk.translate(0, row_step)
            vsk.popMatrix()

            # Column labels assume one multiplier per column, which no longer holds
            # once the multiplier window shifts per row.
            shifting = self.multiplier_min_step != 0 or self.multiplier_max_step != 0
            if not self.hex_grid and not shifting:
                col_stop = self.multiplier_max + 1 if self.multiplier_max >= 0 else self.n_max + 1
                vsk.pushMatrix()
                vsk.translate(text_gap, 0)
                for m in range(self.multiplier_min, col_stop):
                    vsk.text(text=f'{m}', x=self.r, y=self.r, size=self.text_scale, mode="transform", font="futural", align="center")
                    vsk.translate(col_step, 0)
                vsk.popMatrix()

        vsk.translate(text_gap, text_gap)
        vsk.translate(self.r, self.r)

        centers = []
        vsk.pushMatrix()
        for row_idx, n in enumerate(range(self.n_min, self.n_max + 1)):
            mul_range = self._mul_range(n)

            mul_tabs = []
            for multiplier in mul_range:
                mul_tabs.append(frozenset([frozenset([i, (i * multiplier) % n]) for i in range(0, n)]))

            equal_pairs = []
            for i in range(len(mul_tabs)):
                for j in range(i + 1, len(mul_tabs)):
                    if mul_tabs[i] == mul_tabs[j]:
                        equal_pairs.append(set([i, j]))
            print(f'n={n}: {len(mul_range)} multipliers, {len(equal_pairs)} redundant pairs')

            x_offset = hex_half if (self.hex_grid and row_idx % 2 == 1) else 0
            if self.align_by_multiplier:
                # Place the first circle at its multiplier's column (m_min - base).
                x_offset += self.multiplier_min_step * self._step_offset(n) * col_step
            cy = row_idx * row_step

            vsk.pushMatrix()
            vsk.translate(x_offset, 0)
            for j, multiplier in enumerate(mul_range):
                centers.append((x_offset + j * col_step, cy))
                vsk.stroke(1)
                tpn = twopi / n
                for i in range(0, n):
                    vsk.line(
                        -self.r * math.cos(i * tpn),
                         self.r * math.sin(i * tpn),
                        -self.r * math.cos(((i * multiplier) % n) * tpn),
                         self.r * math.sin(((i * multiplier) % n) * tpn),
                    )
                vsk.stroke(2)
                vsk.circle(0, 0, 2 * self.r)
                vsk.translate(col_step, 0)
            vsk.popMatrix()
            vsk.translate(0, row_step)
        vsk.popMatrix()

        if self.fill_hex_gaps and self.hex_grid:
            self._fill_hex_gaps(vsk, centers)
            if self.fill_boundary:
                self._fill_boundary_arcs(vsk, centers)

        vsk.vpype("color --layer 2 black")

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    ModuloMultiplication01Sketch.display()
