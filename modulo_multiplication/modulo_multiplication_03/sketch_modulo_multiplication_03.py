import vsketch
import vpype as vp
import math
import random
from collections import Counter
import numpy as np
from scipy.spatial import Voronoi

try:
    from numba import njit
except ImportError:
    def njit(f): return f

try:
    import mpmath as _mpmath
except ImportError:
    _mpmath = None
    print("WARNING: mpmath not found — intersection precision is reduced; "
          "symmetric diagrams may appear asymmetric. Install with: pipx runpip vsketch install mpmath")

_GLYPH_TYPES = ["dash", "circle", "chevron", "plus", "sine", "sawtooth", "triangle_wave"]

# Module-level caches — survive instance recreation between draw() calls.
_VOR_CACHE: dict = {}
_FILL_CACHE: dict = {}


# ── JIT-compiled hot-path helpers ─────────────────────────────────────────────

@njit
def _pip(px, py, poly_x, poly_y):
    """Ray-casting point-in-polygon (numpy float64 arrays)."""
    n = len(poly_x)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly_x[i], poly_y[i]
        xj, yj = poly_x[j], poly_y[j]
        if ((yi > py) != (yj > py)) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@njit
def _cyrus_beck(x1, y1, x2, y2, poly_x, poly_y, cx, cy):
    """Cyrus-Beck segment clipping against convex polygon.

    Returns (t0, t1) with 0 <= t0 <= t1 <= 1, or (-1, -1) if rejected.
    The inward normal for each edge is oriented toward (cx, cy).
    """
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    n = len(poly_x)
    for i in range(n):
        ax, ay = poly_x[i], poly_y[i]
        bx = poly_x[(i + 1) % n]
        by = poly_y[(i + 1) % n]
        enx = by - ay
        eny = ax - bx
        if enx * (cx - ax) + eny * (cy - ay) < 0.0:
            enx = -enx
            eny = -eny
        numer = enx * (x1 - ax) + eny * (y1 - ay)
        denom = enx * dx + eny * dy
        if abs(denom) < 1e-15:
            if numer < 0.0:
                return -1.0, -1.0
        elif denom > 0.0:
            t = -numer / denom
            if t > t0:
                t0 = t
        else:
            t = -numer / denom
            if t < t1:
                t1 = t
        if t0 > t1:
            return -1.0, -1.0
    if t0 > 1.0 or t1 < 0.0:
        return -1.0, -1.0
    return max(0.0, t0), min(1.0, t1)


# ── Geometry helpers ───────────────────────────────────────────────────────────



def _pad_polygon(poly_x, poly_y, d):
    """Expand polygon by pushing each vertex away from its centroid by d."""
    cx, cy = poly_x.mean(), poly_y.mean()
    dx, dy = poly_x - cx, poly_y - cy
    dist = np.sqrt(dx*dx + dy*dy)
    dist = np.where(dist < 1e-15, 1.0, dist)
    scale = (dist + d) / dist
    return cx + dx * scale, cy + dy * scale


def _sh_intersect(p1, p2, ax, ay, enx, eny):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    d = enx * dx + eny * dy
    if abs(d) < 1e-15:
        return p1
    t = -(enx * (p1[0] - ax) + eny * (p1[1] - ay)) / d
    return (p1[0] + t * dx, p1[1] + t * dy)


# ── Sketch ────────────────────────────────────────────────────────────────────

class ModuloMultiplication03Sketch(vsketch.SketchClass):
    r = vsketch.Param(10.0)
    multiplier = vsketch.Param(41)
    n = vsketch.Param(96)
    add_circle = vsketch.Param(True)
    # Page & layout  (changing these costs only a translate + text redraw)
    page_size = vsketch.Param("25cmx25cm")
    landscape = vsketch.Param(False)
    offset_x = vsketch.Param(0.0)
    offset_y = vsketch.Param(0.0)
    # Labels
    show_text = vsketch.Param(True)
    text_size = vsketch.Param(0.25)
    text_offset_x = vsketch.Param(0.0)
    text_offset_y = vsketch.Param(0.0)
    # Chord overlay
    show_chords = vsketch.Param(False)
    chords_on_top = vsketch.Param(True)
    # Fill  (changing these triggers fill-geometry recomputation, not Voronoi)
    fill_cells = vsketch.Param(False)
    fill_by_neighbors = vsketch.Param(False)
    fill_seed = vsketch.Param(42)
    grid_global_origin = vsketch.Param(True)
    grid_spacing = vsketch.Param(0.1)    # cm
    glyph_scale = vsketch.Param(0.03)     # cm ≈ 0.3 mm pen width
    chevron_beta_a = vsketch.Param(1.0)
    chevron_beta_b = vsketch.Param(1.0)
    wave_periods = vsketch.Param(1.0)
    wave_amplitude = vsketch.Param(0.06)  # cm ≈ 2 × pen width

    # ── draw ──────────────────────────────────────────────────────────────────

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size(self.page_size, landscape=self.landscape, center=False)
        vsk.scale("cm")

        # ── Level-1 cache: Voronoi + ridges + histogram ──────────────────────
        vor_key = (self.n, self.r, self.multiplier, self.add_circle)
        if _VOR_CACHE.get('key') != vor_key:
            _VOR_CACHE.clear()
            _VOR_CACHE['key'] = vor_key
            vor, counts, neighbor_counts, ridges, hist_data = self._build_voronoi()
            _VOR_CACHE['vor'] = vor
            _VOR_CACHE['counts'] = counts
            _VOR_CACHE['neighbor_counts'] = neighbor_counts
            _VOR_CACHE['ridges'] = ridges
            _VOR_CACHE['hist'] = hist_data
            _FILL_CACHE.clear()  # voronoi changed → fill is stale

        # Print histogram from cached data
        hist = _VOR_CACHE['hist']
        max_bar = max(hist.values()) if hist else 1
        print(f"\nChord count histogram — {sum(hist.values())} bounded cells:")
        for k in sorted(hist):
            bar = '█' * int(hist[k] / max_bar * 40)
            print(f"  {k:3d} chords: {hist[k]:4d}  {bar}")

        # ── Level-2 cache: clipped glyph geometry ────────────────────────────
        if self.fill_cells:
            fill_key = (vor_key, self.fill_by_neighbors, self.fill_seed,
                        self.grid_global_origin, self.grid_spacing, self.glyph_scale,
                        self.chevron_beta_a, self.chevron_beta_b,
                        self.wave_periods, self.wave_amplitude)
            if _FILL_CACHE.get('key') != fill_key:
                _FILL_CACHE.clear()
                _FILL_CACHE['key'] = fill_key
                fill_counts = _VOR_CACHE['neighbor_counts'] if self.fill_by_neighbors \
                              else _VOR_CACHE['counts']
                _FILL_CACHE['geom'] = self._build_fill_geom(
                    _VOR_CACHE['vor'], fill_counts)

        # ── Replay ───────────────────────────────────────────────────────────
        px_per_cm = vp.convert_length("1cm")
        vsk.translate(
            vsk.width / px_per_cm / 2 + self.offset_x,
            vsk.height / px_per_cm / 2 + self.offset_y,
        )

        # ── Layer numbering ───────────────────────────────────────────────────
        # fill: layers 2..N  (assigned in _build_fill_geom)
        # outline + text: layer N+1
        # chords (when on top): layer N+2
        # chords (when on bottom): layer 1 — outline is pushed to N+1 ≥ 2
        if self.fill_cells and _FILL_CACHE.get('geom'):
            max_fill_layer = max(cmd[1] for cmd in _FILL_CACHE['geom'])
            outline_layer = max_fill_layer + 1
        else:
            outline_layer = 1

        chords_below = self.show_chords and not self.chords_on_top
        if chords_below and outline_layer < 2:
            outline_layer = 2
        chord_layer = 1 if chords_below else outline_layer + 1

        # ── Draw (bottom → top) ───────────────────────────────────────────────
        if chords_below:
            vsk.stroke(chord_layer)
            self._draw_chords(vsk)

        if self.fill_cells:
            cur_layer = -1
            for cmd in _FILL_CACHE['geom']:
                if cmd[1] != cur_layer:
                    cur_layer = cmd[1]
                    vsk.stroke(cur_layer)
                if cmd[0] == 'L':
                    vsk.line(cmd[2], cmd[3], cmd[4], cmd[5])
                else:  # 'P'
                    vsk.polygon(cmd[2], cmd[3], close=cmd[4])

        vsk.stroke(outline_layer)
        for x1, y1, x2, y2 in _VOR_CACHE['ridges']:
            vsk.line(x1, y1, x2, y2)

        if self.show_text:
            sz = str(self.text_size)
            ty = self.r + self.text_offset_y
            vsk.text(text=f'n={self.n}',         x=-self.r + self.text_offset_x, y=ty, size=sz, mode="transform", font="futural")
            vsk.text(text=f'x={self.multiplier}', x= self.r - self.text_offset_x, y=ty, size=sz, mode="transform", font="futural", align="right")

        if self.show_chords and self.chords_on_top:
            vsk.stroke(chord_layer)
            self._draw_chords(vsk)

        color_cmd = f"color --layer {outline_layer} black"
        if self.show_chords:
            color_cmd += f" color --layer {chord_layer} black"
        vsk.vpype(color_cmd)

    # ── Chord overlay ─────────────────────────────────────────────────────────

    def _draw_chords(self, vsk):
        twopi = 6.28318530718
        tpn = twopi / self.n
        vsk.circle(0, 0, 2 * self.r)
        for i in range(self.n):
            x1 = -self.r * math.cos(i * tpn)
            y1 =  self.r * math.sin(i * tpn)
            j = (i * self.multiplier) % self.n
            x2 = -self.r * math.cos(j * tpn)
            y2 =  self.r * math.sin(j * tpn)
            vsk.line(x1, y1, x2, y2)

    # ── Level-1 build ─────────────────────────────────────────────────────────

    def _build_voronoi(self):
        n, m, r = self.n, self.multiplier, self.r
        tpn = 6.28318530718 / n          # 2π/n, used in the add_circle block below
        jj_arr = [(i * m) % n for i in range(n)]

        if _mpmath is not None:
            # High-precision path: evaluate each intersection from its chord indices
            # using 25-digit arithmetic.  For nearly-parallel chords the cross-product
            # denominator suffers catastrophic cancellation in float64 (error ~1e-4 in
            # the resulting coordinate), breaking symmetry.  mpmath keeps the error
            # at ~1e-9 even in the worst case.  Deduplication uses a 10 dp key
            # computed while still in mpmath space, so points identical by symmetry
            # are always merged before any float64 rounding can separate them.
            _mpmath.mp.dps = 25
            _tpn = 2 * _mpmath.pi / n
            _zero, _one = _mpmath.mpf(0), _mpmath.mpf(1)
            _tol = _mpmath.power(10, -20)
            ax_mp = [-r * _mpmath.cos(i * _tpn) for i in range(n)]
            ay_mp = [ r * _mpmath.sin(i * _tpn) for i in range(n)]
            bx_mp = [-r * _mpmath.cos(jj_arr[i] * _tpn) for i in range(n)]
            by_mp = [ r * _mpmath.sin(jj_arr[i] * _tpn) for i in range(n)]
            mp_counter = {}  # (key_x, key_y) -> (mpf_x, mpf_y, pair_count)
            for li in range(n):
                end_li = jj_arr[li]
                for lj in range(li + 1, n):
                    end_lj = jj_arr[lj]
                    if li == end_lj or end_li == lj or end_li == end_lj:
                        continue
                    rx = bx_mp[li] - ax_mp[li];  ry = by_mp[li] - ay_mp[li]
                    sx = bx_mp[lj] - ax_mp[lj];  sy = by_mp[lj] - ay_mp[lj]
                    denom = rx * sy - ry * sx
                    if _mpmath.fabs(denom) < _tol:
                        continue
                    qpx = ax_mp[lj] - ax_mp[li];  qpy = ay_mp[lj] - ay_mp[li]
                    t = (qpx * sy - qpy * sx) / denom
                    u = (qpx * ry - qpy * rx) / denom
                    if _zero <= t <= _one and _zero <= u <= _one:
                        xi = ax_mp[li] + t * rx
                        yi = ay_mp[li] + t * ry
                        key = (round(float(xi), 10), round(float(yi), 10))
                        if key in mp_counter:
                            ox, oy, cnt = mp_counter[key]
                            mp_counter[key] = (ox, oy, cnt + 1)
                        else:
                            mp_counter[key] = (xi, yi, 1)
            pts_xy, counts = [], []
            for xi_mp, yi_mp, pc in mp_counter.values():
                k = int(round((1.0 + math.sqrt(max(0.0, 1.0 + 8.0 * pc))) / 2.0))
                pts_xy.append((float(xi_mp), float(yi_mp)))
                counts.append(k)
        else:
            # numpy vectorised fallback — may show asymmetry for nearly-parallel chords
            idx = np.arange(n)
            ax = -r * np.cos(idx * tpn);  ay = r * np.sin(idx * tpn)
            jj = np.array(jj_arr)
            bx = -r * np.cos(jj * tpn);   by = r * np.sin(jj * tpn)
            li, lj = np.triu_indices(n, k=1)
            x1, y1, x2, y2 = ax[li], ay[li], bx[li], by[li]
            x3, y3, x4, y4 = ax[lj], ay[lj], bx[lj], by[lj]
            rx, ry = x2 - x1, y2 - y1
            sx, sy = x4 - x3, y4 - y3
            denom = rx * sy - ry * sx
            qpx, qpy = x3 - x1, y3 - y1
            safe = np.abs(denom) > 1e-12
            d_safe = np.where(safe, denom, 1.0)
            t = np.where(safe, (qpx * sy - qpy * sx) / d_safe, -1.0)
            u = np.where(safe, (qpx * ry - qpy * rx) / d_safe, -1.0)
            end_li = (li * m) % n;  end_lj = (lj * m) % n
            shared = (li == end_lj) | (end_li == lj) | (end_li == end_lj)
            valid = safe & ~shared & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
            px = (x1 + t * rx)[valid];  py = (y1 + t * ry)[valid]
            pair_counter = Counter(zip(np.round(px, 5).tolist(), np.round(py, 5).tolist()))
            pts_xy, counts = [], []
            for (xi, yi), pc in pair_counter.items():
                k = int(round((1.0 + math.sqrt(max(0.0, 1.0 + 8.0 * pc))) / 2.0))
                pts_xy.append((xi, yi))
                counts.append(k)

        if self.add_circle:
            for i in range(n):
                pts_xy.append((-self.r * math.cos(i * tpn), self.r * math.sin(i * tpn)))
                counts.append(0)

        pts_np = np.array(pts_xy) if pts_xy else np.zeros((0, 2))
        vor = Voronoi(pts_np)

        ridges = []
        for rv in vor.ridge_vertices:
            if rv[0] != -1 and rv[1] != -1:
                v1 = vor.vertices[rv[0]]
                v2 = vor.vertices[rv[1]]
                if np.linalg.vector_norm(v1) < 2 * self.r and np.linalg.vector_norm(v2) < 2 * self.r:
                    ridges.append((v1[0], v1[1], v2[0], v2[1]))

        bounded_counts = [
            counts[i] for i in range(len(counts))
            if -1 not in vor.regions[vor.point_region[i]]
            and len(vor.regions[vor.point_region[i]]) >= 3
        ]
        hist = Counter(bounded_counts)

        neighbor_counts = [0] * len(pts_xy)
        for p1, p2 in vor.ridge_points:
            neighbor_counts[p1] += 1
            neighbor_counts[p2] += 1

        return vor, counts, neighbor_counts, ridges, hist

    # ── Level-2 build ─────────────────────────────────────────────────────────

    def _build_fill_geom(self, vor, counts):
        rng = random.Random(self.fill_seed)
        unique_counts = sorted(set(counts))
        style_map = {c: {
            'layer':         i + 2,
            'grid_type':     rng.choice(['square', 'hex']),
            'glyph_type':    rng.choice(_GLYPH_TYPES),
            'grid_angle':    rng.uniform(0, 90),
            'glyph_angle':   rng.uniform(0, 360),
            'chevron_half':  math.radians(45 + rng.betavariate(self.chevron_beta_a, self.chevron_beta_b) * 30),
        } for i, c in enumerate(unique_counts)}

        geom = []
        for idx, count in enumerate(counts):
            region = vor.regions[vor.point_region[idx]]
            if -1 in region or len(region) < 3:
                continue
            poly_x = np.array([vor.vertices[v][0] for v in region], dtype=np.float64)
            poly_y = np.array([vor.vertices[v][1] for v in region], dtype=np.float64)
            cx, cy = float(poly_x.mean()), float(poly_y.mean())
            style = style_map[count]
            layer = style['layer']
            pad_x, pad_y = _pad_polygon(poly_x, poly_y, self.glyph_scale)
            ox, oy = (0.0, 0.0) if self.grid_global_origin else (cx, cy)
            for px, py in self._grid_points_in_polygon(pad_x, pad_y, style['grid_type'], style['grid_angle'], ox, oy):
                self._glyph_to_geom(geom, layer, px, py,
                                     style['glyph_type'], style['glyph_angle'],
                                     style['chevron_half'], poly_x, poly_y, cx, cy)
        return geom

    # ── grid ──────────────────────────────────────────────────────────────────

    def _grid_basis(self, grid_type, grid_angle_deg):
        s = self.grid_spacing
        a = math.radians(grid_angle_deg)
        ca, sa = math.cos(a), math.sin(a)
        if grid_type == "hex":
            e1x, e1y = 1.0, 0.0
            e2x, e2y = 0.5, math.sqrt(3) / 2
        else:
            e1x, e1y = 1.0, 0.0
            e2x, e2y = 0.0, 1.0
        ax = s * (ca * e1x - sa * e1y);  ay = s * (sa * e1x + ca * e1y)
        bx = s * (ca * e2x - sa * e2y);  by = s * (sa * e2x + ca * e2y)
        return (ax, ay), (bx, by)

    def _grid_points_in_polygon(self, poly_x, poly_y, grid_type, grid_angle_deg, ox=0.0, oy=0.0):
        (ax, ay), (bx, by) = self._grid_basis(grid_type, grid_angle_deg)
        # Shift bbox corners into grid-origin-relative space for lattice index bounds.
        xmin, xmax = float(poly_x.min()) - ox, float(poly_x.max()) - ox
        ymin, ymax = float(poly_y.min()) - oy, float(poly_y.max()) - oy
        corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
        det = ax * by - ay * bx

        if abs(det) < 1e-12:
            ux, uy = (ax, ay) if ax*ax + ay*ay >= bx*bx + by*by else (bx, by)
            u2 = ux*ux + uy*uy
            if u2 < 1e-20:
                return []
            projs = [(px*ux + py*uy) / u2 for px, py in corners]
            return [(ox + i*ux, oy + i*uy) for i in range(int(min(projs))-1, int(max(projs))+2)
                    if _pip(ox + i*ux, oy + i*uy, poly_x, poly_y)]

        inv = 1.0 / det
        is_ = [(px*by - py*bx) * inv for px, py in corners]
        js_ = [(py*ax - px*ay) * inv for px, py in corners]
        imin, imax = int(min(is_)) - 1, int(max(is_)) + 1
        jmin, jmax = int(min(js_)) - 1, int(max(js_)) + 1
        if (imax - imin + 1) * (jmax - jmin + 1) > 100_000:
            return []
        return [
            (ox + i*ax + j*bx, oy + i*ay + j*by)
            for i in range(imin, imax + 1)
            for j in range(jmin, jmax + 1)
            if _pip(ox + i*ax + j*bx, oy + i*ay + j*by, poly_x, poly_y)
        ]

    # ── glyph geometry (no vsk calls) ─────────────────────────────────────────

    def _glyph_to_geom(self, geom, layer, px, py, glyph_type, glyph_angle_deg,
                        chevron_half, poly_x, poly_y, cx, cy):
        s = self.glyph_scale
        a = math.radians(glyph_angle_deg)
        ca, sa = math.cos(a), math.sin(a)

        def clip_line(x1, y1, x2, y2):
            t0, t1 = _cyrus_beck(x1, y1, x2, y2, poly_x, poly_y, cx, cy)
            if t0 < 0.0:
                return
            dx, dy = x2 - x1, y2 - y1
            geom.append(('L', layer, x1 + t0*dx, y1 + t0*dy, x1 + t1*dx, y1 + t1*dy))

        if glyph_type == "circle":
            N = 48
            circle_pts = [(px + s * math.cos(2*math.pi*k/N),
                           py + s * math.sin(2*math.pi*k/N)) for k in range(N)]
            clipped = self._sutherland_hodgman(circle_pts, poly_x, poly_y, cx, cy)
            if len(clipped) >= 2:
                geom.append(('P', layer, [p[0] for p in clipped], [p[1] for p in clipped], True))

        elif glyph_type == "dash":
            clip_line(px - s*ca, py - s*sa, px + s*ca, py + s*sa)

        elif glyph_type == "plus":
            clip_line(px - s*ca, py - s*sa, px + s*ca, py + s*sa)
            clip_line(px + s*sa, py - s*ca, px - s*sa, py + s*ca)

        elif glyph_type == "chevron":
            bwd = a + math.pi
            clip_line(px, py, px + s*math.cos(bwd + chevron_half), py + s*math.sin(bwd + chevron_half))
            clip_line(px, py, px + s*math.cos(bwd - chevron_half), py + s*math.sin(bwd - chevron_half))

        elif glyph_type in ("sine", "sawtooth", "triangle_wave"):
            period = s
            total = self.wave_periods * period
            amp = self.wave_amplitude
            n_pts = max(int(self.wave_periods * 20) + 1, 3)
            pts_x, pts_y = [], []
            for k in range(n_pts):
                t = (k / (n_pts - 1) - 0.5) * total
                phase = (t + total * 0.5) / period
                if glyph_type == "sine":
                    tr = amp * math.sin(2 * math.pi * phase)
                elif glyph_type == "sawtooth":
                    tr = amp * (2 * (phase % 1) - 1)
                else:
                    p = phase % 1
                    tr = amp * (1 - 4 * abs(p - 0.5))
                pts_x.append(px + t*ca - tr*sa)
                pts_y.append(py + t*sa + tr*ca)

            run_x, run_y = [], []
            for k in range(len(pts_x) - 1):
                t0, t1 = _cyrus_beck(pts_x[k], pts_y[k], pts_x[k+1], pts_y[k+1], poly_x, poly_y, cx, cy)
                if t0 < 0.0:
                    if len(run_x) >= 2:
                        geom.append(('P', layer, run_x, run_y, False))
                    run_x, run_y = [], []
                else:
                    dx, dy = pts_x[k+1] - pts_x[k], pts_y[k+1] - pts_y[k]
                    x1c, y1c = pts_x[k] + t0*dx, pts_y[k] + t0*dy
                    x2c, y2c = pts_x[k] + t1*dx, pts_y[k] + t1*dy
                    if run_x and (abs(x1c - run_x[-1]) > 1e-9 or abs(y1c - run_y[-1]) > 1e-9):
                        if len(run_x) >= 2:
                            geom.append(('P', layer, run_x, run_y, False))
                        run_x, run_y = [x1c], [y1c]
                    elif not run_x:
                        run_x, run_y = [x1c], [y1c]
                    run_x.append(x2c)
                    run_y.append(y2c)
            if len(run_x) >= 2:
                geom.append(('P', layer, run_x, run_y, False))

    def _sutherland_hodgman(self, subject, poly_x, poly_y, cx, cy):
        output = list(subject)
        n = len(poly_x)
        for i in range(n):
            if not output:
                return []
            ax, ay = float(poly_x[i]), float(poly_y[i])
            bx, by = float(poly_x[(i + 1) % n]), float(poly_y[(i + 1) % n])
            enx, eny = by - ay, ax - bx
            if enx * (cx - ax) + eny * (cy - ay) < 0:
                enx, eny = -enx, -eny
            inp, output = output, []
            for j in range(len(inp)):
                curr = inp[j]
                prev = inp[j - 1]
                cd = enx * (curr[0] - ax) + eny * (curr[1] - ay)
                pd = enx * (prev[0] - ax) + eny * (prev[1] - ay)
                if cd >= 0:
                    if pd < 0:
                        output.append(_sh_intersect(prev, curr, ax, ay, enx, eny))
                    output.append(curr)
                elif pd >= 0:
                    output.append(_sh_intersect(prev, curr, ax, ay, enx, eny))
        return output

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    ModuloMultiplication03Sketch.display()
