import heapq
import math
import pathlib
import sys

import vsketch

# Make the repo-root `penfill` package importable when run via `vsk run`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from penfill import (FillSpec, GLYPH_TYPES, GRID_TYPES, PATTERN_NAMES,
                     VskRandom, draw_geometry, fill_polygon, rect_polygon,
                     sample_fill)


class BoxesSketch(vsketch.SketchClass):
    box_width = vsketch.Param(18 * 5, min_value=2)
    box_height = vsketch.Param(27 * 5, min_value=2)
    area_threshold = vsketch.Param(15, min_value=1)
    split_lambda = vsketch.Param(3.0, min_value=0.5)
    scale = vsketch.Param(0.2, min_value=0.1)
    drop_probability = vsketch.Param(0.0, min_value=0, decimals=3)
    split_seed = vsketch.Param(0)

    # ── Fill ──────────────────────────────────────────────────────────────────
    # "solid" is vsketch's native fill; "hatch"/"glyph_grid" are penfill patterns.
    fill_pattern = vsketch.Param("solid", choices=PATTERN_NAMES)
    random_fill = vsketch.Param(True)            # sample a fill per box vs one fixed spec
    fill_seed = vsketch.Param(0)
    fill_spacing = vsketch.Param(1.5, min_value=0.1, decimals=2)  # box units
    draw_outline = vsketch.Param(True)
    # Deterministic-mode knobs (ignored when random_fill is on)
    grid_type = vsketch.Param("hex", choices=GRID_TYPES)
    glyph_type = vsketch.Param("dash", choices=GLYPH_TYPES)
    size_ratio = vsketch.Param(0.4, min_value=0.05, decimals=2)
    grid_angle = vsketch.Param(0.0)
    glyph_angle = vsketch.Param(0.0)
    halton_base_x = vsketch.Param(2, min_value=2)   # used when grid_type == "halton"
    halton_base_y = vsketch.Param(3, min_value=2)
    hatch_angle = vsketch.Param(45.0)
    hatch_cross = vsketch.Param(False)

    def _split_boxes(self, vsk):
        """The recursive guillotine split — unchanged from the original sketch."""
        def poisson_sample():
            L = math.exp(-self.split_lambda)
            k, p = 0, 1.0
            while p > L:
                k += 1
                p *= vsk.random(1)
            return k - 1

        def biased_cut(size):
            for _ in range(50):
                k = poisson_sample()
                cut = k + 1 if vsk.random(1) < 0.5 else size - 1 - k
                if 1 <= cut <= size - 1:
                    return cut
            return int(vsk.random(1, size))

        def push(heap, x, y, w, h):
            heapq.heappush(heap, (-w * h, x, y, w, h))

        heap = []
        push(heap, 0, 0, self.box_width, self.box_height)
        final_boxes = []

        while heap:
            neg_area, x, y, w, h = heapq.heappop(heap)
            area = -neg_area
            if area < self.area_threshold:
                final_boxes.append((x, y, w, h))
                for _, rx, ry, rw, rh in heap:
                    final_boxes.append((rx, ry, rw, rh))
                break

            can_cut_v, can_cut_h = w > 1, h > 1
            if not can_cut_v and not can_cut_h:
                final_boxes.append((x, y, w, h))
                continue
            if can_cut_v and can_cut_h:
                cut_v = vsk.random(w + h) < w
            else:
                cut_v = can_cut_v

            if cut_v:
                cut = biased_cut(w)
                push(heap, x, y, cut, h)
                push(heap, x + cut, y, w - cut, h)
            else:
                cut = biased_cut(h)
                push(heap, x, y, w, cut)
                push(heap, x, y + cut, w, h - cut)
        return final_boxes

    def _fill_spec(self, vsk, layer):
        """Pick a fill for one box: sampled per box, or a fixed deterministic spec."""
        bases = (self.halton_base_x, self.halton_base_y)
        if self.random_fill:
            return sample_fill(self.fill_pattern, VskRandom(vsk), layer=layer,
                               spacing=self.fill_spacing, halton_bases=bases)
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
        return FillSpec(self.fill_pattern, layer, params)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")
        vsk.scale(self.scale)
        if self.split_seed:
            vsk.randomSeed(self.split_seed)

        final_boxes = self._split_boxes(vsk)

        # Center on A4 portrait (21 x 29.7 cm), expressed in box units.
        ox = (21 / self.scale - self.box_width) / 2
        oy = (29.7 / self.scale - self.box_height) / 2

        # Reseed so fill sampling is reproducible from fill_seed (0 = vary each run).
        if self.fill_seed:
            vsk.randomSeed(self.fill_seed)

        for bx, by, bw, bh in final_boxes:
            if vsk.random(1) <= self.drop_probability:
                continue
            layer = int(vsk.random(2, 5))
            poly = rect_polygon(ox + bx, oy + by, bw, bh)
            draw_geometry(vsk, fill_polygon(poly, self._fill_spec(vsk, layer)))
            if self.draw_outline:
                vsk.stroke(6)
                vsk.rect(ox + bx, oy + by, bw, bh)

        vsk.vpype("color --layer 6 black color --layer 2 #1c0f1f "
                  "color --layer 3 #341c3d color --layer 4 #be98c0")

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    BoxesSketch.display()
