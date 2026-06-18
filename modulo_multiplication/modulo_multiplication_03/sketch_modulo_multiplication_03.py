import math
import pathlib
import random
import sys
from collections import Counter

import numpy as np
import vsketch
import vpype as vp
from scipy.spatial import Voronoi

# Make the repo-root `penfill` package importable when run via `vsk run`.
_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from penfill import (FillSpec, GLYPH_TYPES, GRID_TYPES, PATTERN_NAMES,
                     draw_geometry, fill_polygon, install_swatches, load_pens,
                     sample_fill, to_polygon)

try:
    import mpmath as _mpmath
except ImportError:
    _mpmath = None
    print("WARNING: mpmath not found — intersection precision is reduced; "
          "symmetric diagrams may appear asymmetric. Install with: pipx runpip vsketch install mpmath")

# Pen colours converted from DrawingBot presets (see tools/drawingbot_to_vpype.py).
PENS = load_pens(_REPO / "pens")            # {pen name: "#rrggbb"}
PEN_NAMES = list(PENS)
COLOR_CHOICES = ["none"] + PEN_NAMES

# Show colour swatches next to pen names in the GUI dropdowns (GUI-only no-op).
install_swatches(PENS)

# Module-level caches — survive instance recreation between draw() calls.
_VOR_CACHE: dict = {}
_FILL_CACHE: dict = {}


def _default_color(i: int) -> str:
    """Default the first few colour slots to the first pens, the rest to none."""
    return PEN_NAMES[i - 1] if i - 1 < len(PEN_NAMES) else "none"


# ── Sketch ────────────────────────────────────────────────────────────────────

class ModuloMultiplication03Sketch(vsketch.SketchClass):
    r = vsketch.Param(10.0)
    multiplier = vsketch.Param(41)
    n = vsketch.Param(96)
    add_circle = vsketch.Param(True)
    # Page & layout  (changing these costs only a translate + text redraw)
    page_size = vsketch.Param("25cmx25cm")
    landscape = vsketch.Param(False)
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2, unit="mm")
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

    # ── Fill ──────────────────────────────────────────────────────────────────
    # Cells are grouped by chord count; each distinct count gets its own fill
    # style and is assigned a palette colour (cycling through the palette).
    fill_cells = vsketch.Param(False)
    fill_by_neighbors = vsketch.Param(False)
    # "solid" is vsketch's native fill; "hatch"/"glyph_grid" are penfill patterns.
    fill_pattern = vsketch.Param("glyph_grid", choices=PATTERN_NAMES)
    random_style = vsketch.Param(True)   # sample a random style per count vs UI knobs
    fill_seed = vsketch.Param(42)
    grid_global_origin = vsketch.Param(True)
    fill_spacing = vsketch.Param(0.1)     # cm
    size_ratio = vsketch.Param(0.3, min_value=0.05, decimals=2)

    # Colours: pick up to 6 pens for the fill palette; the first "none" ends the
    # palette.  Each chord-count group is assigned a palette colour in turn.
    color_1 = vsketch.Param(_default_color(1), choices=COLOR_CHOICES)
    color_2 = vsketch.Param(_default_color(2), choices=COLOR_CHOICES)
    color_3 = vsketch.Param(_default_color(3), choices=COLOR_CHOICES)
    color_4 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_5 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_6 = vsketch.Param("none", choices=COLOR_CHOICES)
    outline_color = vsketch.Param("none", choices=COLOR_CHOICES)  # "none" -> black
    chord_color = vsketch.Param("none", choices=COLOR_CHOICES)    # "none" -> black

    # Deterministic-style knobs (ignored when random_style is on)
    grid_type = vsketch.Param("square", choices=GRID_TYPES)
    glyph_type = vsketch.Param("dash", choices=GLYPH_TYPES)
    grid_angle = vsketch.Param(0.0)
    glyph_angle = vsketch.Param(0.0)
    halton_base_x = vsketch.Param(2, min_value=2)   # used when grid_type == "halton"
    halton_base_y = vsketch.Param(3, min_value=2)
    hatch_angle = vsketch.Param(45.0)
    hatch_cross = vsketch.Param(False)

    # ── palette ─────────────────────────────────────────────────────────────────

    def _palette(self):
        """Selected fill colours (hex), truncated at the first 'none' slot."""
        palette = []
        for c in (self.color_1, self.color_2, self.color_3,
                  self.color_4, self.color_5, self.color_6):
            if c == "none":
                break
            palette.append(PENS.get(c, "black"))
        return palette

    # ── draw ──────────────────────────────────────────────────────────────────

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size(self.page_size, landscape=self.landscape, center=False)
        vsk.penWidth(self.pen_width)  # Param unit="mm" -> value already in px
        vsk.scale("cm")

        palette = self._palette()
        n_colors = max(1, len(palette))
        outline_layer = n_colors + 1
        chord_layer = n_colors + 2

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

        # ── Level-2 cache: penfill geometry ──────────────────────────────────
        if self.fill_cells:
            fill_key = (vor_key, n_colors, self.fill_by_neighbors, self.fill_pattern,
                        self.random_style, self.fill_seed, self.grid_global_origin,
                        self.fill_spacing, self.size_ratio, self.grid_type,
                        self.glyph_type, self.grid_angle, self.glyph_angle,
                        self.halton_base_x, self.halton_base_y,
                        self.hatch_angle, self.hatch_cross)
            if _FILL_CACHE.get('key') != fill_key:
                _FILL_CACHE.clear()
                _FILL_CACHE['key'] = fill_key
                fill_counts = _VOR_CACHE['neighbor_counts'] if self.fill_by_neighbors \
                              else _VOR_CACHE['counts']
                _FILL_CACHE['geom'] = self._build_fill_geom(
                    _VOR_CACHE['vor'], fill_counts, n_colors)

        # ── Replay ───────────────────────────────────────────────────────────
        px_per_cm = vp.convert_length("1cm")
        vsk.translate(
            vsk.width / px_per_cm / 2 + self.offset_x,
            vsk.height / px_per_cm / 2 + self.offset_y,
        )

        used_fill_layers = set()

        # ── Draw (bottom → top) ───────────────────────────────────────────────
        if self.show_chords and not self.chords_on_top:
            vsk.stroke(chord_layer)
            self._draw_chords(vsk)

        if self.fill_cells and _FILL_CACHE.get('geom'):
            geom = _FILL_CACHE['geom']
            used_fill_layers = {prim[1] for prim in geom}
            draw_geometry(vsk, geom)

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

        # ── Colours ───────────────────────────────────────────────────────────
        parts = [f"color --layer {layer} {palette[layer - 1]}"
                 for layer in sorted(used_fill_layers) if layer - 1 < len(palette)]
        outline_hex = "black" if self.outline_color == "none" \
            else PENS.get(self.outline_color, "black")
        parts.append(f"color --layer {outline_layer} {outline_hex}")
        if self.show_chords:
            chord_hex = "black" if self.chord_color == "none" \
                else PENS.get(self.chord_color, "black")
            parts.append(f"color --layer {chord_layer} {chord_hex}")
        vsk.vpype(" ".join(parts))

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

    # ── Level-2 build (penfill) ─────────────────────────────────────────────────

    def _style_map(self, counts, n_colors):
        """One FillSpec template per distinct count.

        Each distinct count is assigned a palette layer (cycling) and a fill
        style.  In random mode the style is sampled per count from a seeded
        stream; otherwise every count shares the UI-configured style.  The
        ``origin`` param is filled in per cell at build time.
        """
        rng = random.Random(self.fill_seed)
        unique_counts = sorted(set(counts))
        bases = (self.halton_base_x, self.halton_base_y)
        style_map = {}
        for i, c in enumerate(unique_counts):
            layer = 1 + (i % n_colors)
            if self.random_style:
                if self.fill_pattern == "solid":
                    spec = FillSpec("solid", layer, {})
                elif self.fill_pattern == "hatch":
                    spec = sample_fill("hatch", rng, layer=layer,
                                       spacing=self.fill_spacing)
                else:  # glyph_grid
                    spec = sample_fill("glyph_grid", rng, layer=layer,
                                       spacing=self.fill_spacing,
                                       halton_bases=bases)
            else:
                if self.fill_pattern == "solid":
                    params = {}
                elif self.fill_pattern == "hatch":
                    params = dict(spacing=self.fill_spacing, angle=self.hatch_angle,
                                  cross=self.hatch_cross)
                else:  # glyph_grid
                    params = dict(grid=self.grid_type, spacing=self.fill_spacing,
                                  size=self.fill_spacing * self.size_ratio,
                                  glyph=self.glyph_type, angle=self.grid_angle,
                                  glyph_angle=self.glyph_angle, seed=self.fill_seed,
                                  halton_bases=bases)
                spec = FillSpec(self.fill_pattern, layer, params)
            style_map[c] = spec
        return style_map

    def _build_fill_geom(self, vor, counts, n_colors):
        style_map = self._style_map(counts, n_colors)
        geom = []
        for idx, count in enumerate(counts):
            region = vor.regions[vor.point_region[idx]]
            if -1 in region or len(region) < 3:
                continue
            shell = [(vor.vertices[v][0], vor.vertices[v][1]) for v in region]
            poly = to_polygon(shell)
            if not poly.is_valid or poly.area <= 0:
                continue
            base = style_map[count]
            origin = (0.0, 0.0) if self.grid_global_origin else \
                     (poly.centroid.x, poly.centroid.y)
            spec = FillSpec(base.pattern, base.layer, {**base.params, "origin": origin})
            geom += fill_polygon(poly, spec)
        return geom

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    ModuloMultiplication03Sketch.display()
