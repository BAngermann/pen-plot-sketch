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
    random_fill = vsketch.Param(True)            # random/freeze mode vs one fixed spec
    fill_seed = vsketch.Param(0)
    fill_spacing = vsketch.Param(1.5, min_value=0.1, decimals=2)  # box units
    draw_outline = vsketch.Param(True)
    # Random/freeze mode: after the first `freeze_after_splits` cuts, each new box
    # is frozen (prob `freeze_prob`) to a random fill TYPE — solid, hatch, or one
    # glyph — that all its descendants inherit.  Unfrozen boxes get an independent
    # random type.  Other params (spacing, direction, grid, glyph angle…) still
    # vary box to box.
    freeze_after_splits = vsketch.Param(3, min_value=0)
    freeze_prob = vsketch.Param(0.3, min_value=0, decimals=2)
    spacing_var = vsketch.Param(0.5, min_value=0, decimals=2)  # ± fraction of fill_spacing
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

    def _fill_types(self):
        """The freezable fill types: solid, hatch, and one entry per glyph."""
        return ["solid", "hatch"] + [f"glyph:{g}" for g in GLYPH_TYPES]

    def _split_boxes(self, vsk):
        """Recursive guillotine split.

        Returns ``(x, y, w, h, frozen_type)`` per leaf box.  In random_fill mode,
        once the split count exceeds ``freeze_after_splits`` each newly created
        box may be frozen (prob ``freeze_prob``) to a random fill type that
        propagates to its whole subtree; ``frozen_type`` is ``None`` otherwise.
        """
        freeze = self.random_fill
        fill_types = self._fill_types()
        prob = min(1.0, max(0.0, self.freeze_prob))

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

        def child_type(parent_type, split_count):
            # Inherit a frozen type; otherwise maybe freeze once past the warm-up.
            if not freeze or parent_type is not None:
                return parent_type
            if split_count > self.freeze_after_splits and vsk.random(1) < prob:
                return fill_types[int(vsk.random(len(fill_types)))]
            return None

        counter = 0

        def push(heap, x, y, w, h, ftype):
            nonlocal counter
            heapq.heappush(heap, (-w * h, counter, x, y, w, h, ftype))
            counter += 1

        heap = []
        push(heap, 0, 0, self.box_width, self.box_height, None)
        final_boxes = []
        split_count = 0

        while heap:
            _, _, x, y, w, h, ftype = heapq.heappop(heap)
            area = w * h
            if area < self.area_threshold:
                final_boxes.append((x, y, w, h, ftype))
                for e in heap:
                    final_boxes.append((e[2], e[3], e[4], e[5], e[6]))
                break

            can_cut_v, can_cut_h = w > 1, h > 1
            if not can_cut_v and not can_cut_h:
                final_boxes.append((x, y, w, h, ftype))
                continue
            if can_cut_v and can_cut_h:
                cut_v = vsk.random(w + h) < w
            else:
                cut_v = can_cut_v

            split_count += 1
            t1 = child_type(ftype, split_count)
            t2 = child_type(ftype, split_count)

            if cut_v:
                cut = biased_cut(w)
                push(heap, x, y, cut, h, t1)
                push(heap, x + cut, y, w - cut, h, t2)
            else:
                cut = biased_cut(h)
                push(heap, x, y, w, cut, t1)
                push(heap, x, y + cut, w, h - cut, t2)
        return final_boxes

    def _spec_for_type(self, vsk, fill_type, layer):
        """Build a fill of a given type with the remaining params sampled."""
        lo, hi = max(0.1, 1 - self.spacing_var), 1 + self.spacing_var
        spacing = self.fill_spacing * vsk.random(lo, hi)
        if fill_type == "solid":
            return FillSpec("solid", layer, {})
        if fill_type == "hatch":
            return sample_fill("hatch", VskRandom(vsk), layer=layer, spacing=spacing)
        glyph = fill_type.split(":", 1)[1]
        return sample_fill("glyph_grid", VskRandom(vsk), layer=layer,
                           spacing=spacing, glyph=glyph,
                           halton_bases=(self.halton_base_x, self.halton_base_y))

    def _deterministic_spec(self, layer):
        bases = (self.halton_base_x, self.halton_base_y)
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

        fill_types = self._fill_types()

        # Reseed so fill sampling is reproducible from fill_seed (0 = vary each run).
        if self.fill_seed:
            vsk.randomSeed(self.fill_seed)

        for bx, by, bw, bh, ftype in final_boxes:
            if vsk.random(1) <= self.drop_probability:
                continue
            layer = int(vsk.random(2, 5))
            poly = rect_polygon(ox + bx, oy + by, bw, bh)
            if self.random_fill:
                # Unfrozen boxes get an independent random type.
                if ftype is None:
                    ftype = fill_types[int(vsk.random(len(fill_types)))]
                spec = self._spec_for_type(vsk, ftype, layer)
            else:
                spec = self._deterministic_spec(layer)
            draw_geometry(vsk, fill_polygon(poly, spec))
            if self.draw_outline:
                vsk.stroke(6)
                vsk.rect(ox + bx, oy + by, bw, bh)

        vsk.vpype("color --layer 6 black color --layer 2 #1c0f1f "
                  "color --layer 3 #341c3d color --layer 4 #be98c0")

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    BoxesSketch.display()
