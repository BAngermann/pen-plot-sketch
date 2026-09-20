import heapq
import math
import pathlib
import sys

import vsketch

# Make the repo-root `penfill` package importable when run via `vsk run`.
_REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
from penfill import (FillSpec, draw_geometry, fill_polygon, install_swatches,
                     load_pens, rect_polygon)

# Pen colours converted from DrawingBot presets (see tools/drawingbot_to_vpype.py).
PENS = load_pens(_REPO / "pens")            # {pen name: "#rrggbb"}
PEN_NAMES = list(PENS)
COLOR_CHOICES = ["none"] + PEN_NAMES

# Solid-only sketch: either a solid fill or no fill at all (outline / gap).
FILL_CHOICES = ["none", "solid"]

# CSS pixels per centimetre (96 px/in / 2.54 cm/in) -- used to read the page
# size (in px, via vsk.width/vsk.height) back into the sketch's cm scale.
PX_PER_CM = 96 / 2.54

# Show colour swatches next to pen names in the GUI dropdowns (GUI-only no-op).
install_swatches(PENS)


class CrackSketch(vsketch.SketchClass):
    """A cracked mosaic.

    Recursively guillotine-splits a rectangle into shards, fills each with a
    random palette colour (solid or unfilled), then carves a single jagged
    crack that runs from the top edge to the bottom edge by deleting a
    connected chain of boxes.  Randomness (splitting, crack route, colours) is
    governed by vsketch's own seed — set it in the GUI seed control.
    """

    box_width = vsketch.Param(180, min_value=2)
    box_height = vsketch.Param(270, min_value=2)
    area_threshold = vsketch.Param(10, min_value=1)
    split_lambda = vsketch.Param(1.0, min_value=0.5)
    # Anything vsk.size() accepts as a single string: a known page name (a4,
    # letter, ...) or an explicit "WxH" spec with units, e.g. "10cmx10cm".
    page_size = vsketch.Param("a4")
    # Symmetric page margins in CENTIMETRES.  NOTE: no unit="cm" here — a unit=
    # Param returns pixels (cm×37.8), which would corrupt the cm scale maths.
    margin_x = vsketch.Param(1.0, min_value=0, decimals=2)   # left/right, cm
    margin_y = vsketch.Param(1.0, min_value=0, decimals=2)   # top/bottom, cm
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2, unit="mm")

    # ── Fill ──────────────────────────────────────────────────────────────────
    # "solid" is vsketch's native fill; "none" leaves the shard unfilled.
    fill_pattern = vsketch.Param("solid", choices=FILL_CHOICES)
    # Colours: two independent palettes of up to 3 pens — one for shards on the
    # left of the crack, one for the right.  Within each palette the first "none"
    # ends it (so left_color_2 = "none" uses a single left colour).  Each shard is
    # assigned a random colour from its side's palette.
    left_color_1 = vsketch.Param("Iris Purple 49", choices=COLOR_CHOICES)
    left_color_2 = vsketch.Param("Light Pink 51", choices=COLOR_CHOICES)
    left_color_3 = vsketch.Param("Saxe Blue 79", choices=COLOR_CHOICES)
    right_color_1 = vsketch.Param("Iris Purple 49", choices=COLOR_CHOICES)
    right_color_2 = vsketch.Param("Light Pink 51", choices=COLOR_CHOICES)
    right_color_3 = vsketch.Param("Saxe Blue 79", choices=COLOR_CHOICES)
    draw_outline = vsketch.Param(True)
    outline_color = vsketch.Param("none", choices=COLOR_CHOICES)  # "none" -> black

    def _split_boxes(self, vsk):
        """Recursive guillotine split into leaf ``(x, y, w, h)`` boxes."""

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

        counter = 0

        def push(heap, x, y, w, h):
            nonlocal counter
            heapq.heappush(heap, (-w * h, counter, x, y, w, h))
            counter += 1

        heap = []
        push(heap, 0, 0, self.box_width, self.box_height)
        final_boxes = []

        while heap:
            _, _, x, y, w, h = heapq.heappop(heap)
            area = w * h
            if area < self.area_threshold:
                final_boxes.append((x, y, w, h))
                for e in heap:
                    final_boxes.append((e[2], e[3], e[4], e[5]))
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

    def _crack_path(self, vsk, boxes):
        """Carve a top-to-bottom crack, returning the deleted box indices.

        Start at the top-row box straddling the horizontal midline, then step
        down to a random box sharing the current box's bottom edge, deleting
        each, until the bottom edge of the page is reached.

        A long crack (more than 5 rows) is then widened: for each crack box a
        uniform draw in [0, 0.25] drops the box to its left, one in [0.75, 1]
        drops the box to its right, and anything in between does nothing.  A
        neighbour already deleted (e.g. from a row above) is left as-is.
        """
        eps = 1e-6

        def overlap(a, b):
            return min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])

        def yoverlap(a, b):
            return min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])

        top = [i for i, b in enumerate(boxes) if b[1] < eps]
        if not top:
            return set()

        center = self.box_width / 2
        start = next((i for i in top
                      if boxes[i][0] - eps <= center <= boxes[i][0] + boxes[i][2] + eps),
                     None)
        if start is None:
            start = min(top, key=lambda i: abs(boxes[i][0] + boxes[i][2] / 2 - center))

        deleted = set()
        chain = []
        cur = start
        while True:
            deleted.add(cur)
            chain.append(cur)
            b = boxes[cur]
            bottom = b[1] + b[3]
            if bottom >= self.box_height - eps:
                break
            below = [i for i, c in enumerate(boxes)
                     if abs(c[1] - bottom) < eps and overlap(b, c) > eps]
            if not below:
                break
            cur = below[int(vsk.random(len(below)))]

        if len(chain) > 5:
            for ci in chain:
                b = boxes[ci]
                x = vsk.random(1)
                if x < 0.25:          # left neighbour: its right edge meets ours
                    on_edge = lambda c: abs(c[0] + c[2] - b[0]) < eps
                elif x >= 0.75:       # right neighbour: its left edge meets ours
                    on_edge = lambda c: abs(c[0] - (b[0] + b[2])) < eps
                else:
                    continue
                cand = [i for i, c in enumerate(boxes)
                        if on_edge(c) and yoverlap(b, c) > eps]
                if not cand:
                    continue
                # "the" neighbour = the one bordering our edge the most
                pick = max(cand, key=lambda i: yoverlap(b, boxes[i]))
                if pick not in deleted:   # already gone from a row above -> nothing
                    deleted.add(pick)
        return deleted

    def _palette(self, colors):
        """Selected fill colours (hex), truncated at the first 'none' slot."""
        palette = []
        for c in colors:
            if c == "none":
                break
            palette.append(PENS.get(c, "black"))
        return palette

    @staticmethod
    def _is_left(crack_boxes, cx, cy):
        """Whether point ``(cx, cy)`` lies left of the crack.

        The crack boxes tile ``[0, box_height]`` in y, so the one whose vertical
        span contains ``cy`` fixes the crack's position at that height; the point
        is "left" if it sits left of that box's centreline.  Defaults to left
        when there is no crack.
        """
        eps = 1e-6
        for bx, by, bw, bh in crack_boxes:
            if by - eps <= cy <= by + bh + eps:
                return cx < bx + bw / 2
        return True

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size(self.page_size, landscape=False)
        vsk.penWidth(self.pen_width)  # Param unit="mm" -> value already in px

        # Fit the figure to the page minus margins; the tighter axis binds, so
        # the requested margins are a lower bound (the other axis gets more).
        page_w, page_h = vsk.width / PX_PER_CM, vsk.height / PX_PER_CM  # cm
        scale = min((page_w - 2 * self.margin_x) / self.box_width,
                    (page_h - 2 * self.margin_y) / self.box_height)
        vsk.scale("cm")
        vsk.scale(scale)

        final_boxes = self._split_boxes(vsk)
        deleted = self._crack_path(vsk, final_boxes)
        crack_boxes = [final_boxes[i] for i in deleted]

        # Center on the page (portrait), expressed in box units.
        ox = (page_w / scale - self.box_width) / 2
        oy = (page_h / scale - self.box_height) / 2

        # Per-side colour "mixes" — the random pick draws from these, so a colour
        # listed twice (e.g. [purple, purple, blue]) is chosen 2:1.  Empty side ->
        # black.
        left_mix = self._palette((self.left_color_1, self.left_color_2,
                                  self.left_color_3)) or ["black"]
        right_mix = self._palette((self.right_color_1, self.right_color_2,
                                   self.right_color_3)) or ["black"]

        # Plotter optimisation: map each *distinct* colour to one layer so all
        # same-coloured shards plot in a single pen pass (duplicates in a mix
        # collapse onto the same layer).  Outline gets the next layer up.
        color_layer = {}
        for hexc in left_mix + right_mix:
            color_layer.setdefault(hexc, len(color_layer) + 1)
        outline_layer = len(color_layer) + 1

        for i, (bx, by, bw, bh) in enumerate(final_boxes):
            if i in deleted:
                continue
            mix = left_mix if self._is_left(crack_boxes, bx + bw / 2, by + bh / 2) \
                else right_mix
            layer = color_layer[mix[int(vsk.random(len(mix)))]]
            poly = rect_polygon(ox + bx, oy + by, bw, bh)
            draw_geometry(vsk, fill_polygon(poly, FillSpec(self.fill_pattern, layer, {})))
            if self.draw_outline:
                vsk.stroke(outline_layer)
                vsk.rect(ox + bx, oy + by, bw, bh)

        parts = [f"color --layer {layer} {hexc}"
                 for hexc, layer in color_layer.items()]
        if self.draw_outline:
            outline_hex = "black" if self.outline_color == "none" \
                else PENS.get(self.outline_color, "black")
            parts.append(f"color --layer {outline_layer} {outline_hex}")
        if parts:
            vsk.vpype(" ".join(parts))

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    CrackSketch.display()
