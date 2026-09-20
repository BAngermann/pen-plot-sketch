import heapq
import math
import pathlib
import sys
from collections import deque

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
    # Widening passes; each pass removes one box adjacent to the crack's
    # current outer edge, left or right per widen_left_prob. 0 = no widening.
    widen_iterations = vsketch.Param(1, min_value=0, max_value=4)
    widen_left_prob = vsketch.Param(0.5, min_value=0.0, max_value=1.0, decimals=2)
    # Widening can enclose shards that lose every connection (through
    # surviving neighbours) to the left or right boundary; drop those too.
    remove_islands = vsketch.Param(True)
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

        The crack is then widened over ``widen_iterations`` passes (see
        :meth:`_widen_crack`) and, if ``remove_islands`` is set, any shard left
        disconnected from both page boundaries is dropped too (see
        :meth:`_remove_islands`).
        """
        eps = 1e-6

        def overlap(a, b):
            return min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])

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

        self._widen_crack(vsk, boxes, deleted, chain)
        if self.remove_islands:
            self._remove_islands(boxes, deleted)
        return deleted

    def _widen_crack(self, vsk, boxes, deleted, chain):
        """Widen the crack in place over ``self.widen_iterations`` passes.

        Each pass walks the crack's current outer edge (the chain on the
        first pass, the boxes added by the previous pass thereafter) and, for
        every box on that edge, deletes one adjacent box: the left neighbour
        with probability ``widen_left_prob``, otherwise the right neighbour.
        A neighbour already deleted is left as-is and does not extend the
        edge further. With 0 iterations the crack is left at its original
        (unwidened) width.
        """
        eps = 1e-6

        def yoverlap(a, b):
            return min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])

        edge = list(chain)
        for _ in range(int(self.widen_iterations)):
            next_edge = []
            for ci in edge:
                b = boxes[ci]
                if vsk.random(1) < self.widen_left_prob:
                    on_edge = lambda c: abs(c[0] + c[2] - b[0]) < eps  # left: its right edge meets ours
                else:
                    on_edge = lambda c: abs(c[0] - (b[0] + b[2])) < eps  # right: its left edge meets ours
                cand = [i for i, c in enumerate(boxes)
                        if on_edge(c) and yoverlap(b, c) > eps]
                if not cand:
                    continue
                # "the" neighbour = the one bordering our edge the most
                pick = max(cand, key=lambda i: yoverlap(b, boxes[i]))
                if pick not in deleted:
                    deleted.add(pick)
                    next_edge.append(pick)
            edge = next_edge
            if not edge:
                break

    def _remove_islands(self, boxes, deleted):
        """Drop surviving shards unreachable, through surviving neighbours,
        from the left (x=0) or right (x=box_width) page boundary.

        Widening can nibble away at the boxes around a shard until it is
        fully enclosed by deleted boxes; left alone, that shard would plot as
        a fragment floating inside the crack. Reachability is flood-filled on
        a unit grid rasterised from the surviving boxes -- guillotine splits
        keep every box on an integer grid, so this is exact -- which stays
        fast regardless of the box count since it scales with page area, not
        shard count.
        """
        w, h = int(round(self.box_width)), int(round(self.box_height))
        owner = [-1] * (w * h)
        for i, (bx, by, bw, bh) in enumerate(boxes):
            if i in deleted:
                continue
            x0, x1 = int(round(bx)), int(round(bx + bw))
            y0, y1 = int(round(by)), int(round(by + bh))
            for y in range(y0, y1):
                row = y * w
                owner[row + x0:row + x1] = [i] * (x1 - x0)

        visited = bytearray(w * h)
        queue = deque()

        def seed(x, y):
            idx = y * w + x
            if owner[idx] >= 0 and not visited[idx]:
                visited[idx] = 1
                queue.append(idx)

        for y in range(h):
            seed(0, y)
            seed(w - 1, y)

        while queue:
            idx = queue.popleft()
            x, y = idx % w, idx // w
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    nidx = ny * w + nx
                    if owner[nidx] >= 0 and not visited[nidx]:
                        visited[nidx] = 1
                        queue.append(nidx)

        deleted.update(owner[i] for i in range(w * h)
                       if owner[i] >= 0 and not visited[i])

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
