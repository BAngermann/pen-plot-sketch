"""Almost space-filling tree (ASFT): fixed rules, randomised pen assignment.

Everything that was identical across the ASFT* configs of the Lsys sketch is
fixed here. What remains are the parameters that differed between them
(iterations, Scale, TransformScale), all with min/max ranges so vsketch's
randomiser samples them, plus the pen set and the page size.

Pen assignment: the string picks the pen via the ' / " colour-index symbols
(index mod n_pens). The number of slots, the starting colour index and each
slot's pen (drawn with replacement from the RGBK or CMYK set) are sampled from
the vsketch seed, so a new seed gives a new assignment.
"""
import pathlib
import sys

import numpy as np
import vpype as vp
import vsketch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # lsys_common
from lsys_common import expand, rotate, turtle_segments

# Plain pen colours to draw from (name -> hex). Edit freely.
PEN_SETS = {
    "RGBK": {"red": "#ff0000", "green": "#00ff00", "blue": "#0000ff", "black": "#000000"},
    "CMYK": {"cyan": "#00ffff", "magenta": "#ff00ff", "yellow": "#ffff00", "black": "#000000"},
}
N_SLOTS = 10

# --- fixed L-system (identical across all ASFT* configs) ---------------------
AXIOM = "F"
RULES = {"F": '!G[*+"F][*-F]'}
DRAW = "F,G"
TURN_ANGLE = 90.0
GLOBAL_ROTATION = 180.0
PEN_WIDTH_MM = 0.3
REF_PAGE_H_CM = 21.0  # A4 landscape height: the page Scale was tuned on



class ASFTSketch(vsketch.SketchClass):
    paper = vsketch.Param("a4", choices=[f"a{i}" for i in range(7)])
    pen_set = vsketch.Param("RGBK", choices=list(PEN_SETS))

    # Parameters that varied across ASFT1-3 / "Almost space filling tree".
    iterations = vsketch.Param(16, min_value=12, max_value=19)
    Scale = vsketch.Param(9.0, min_value=8.5, max_value=9.2, decimals=2)
    TransformScale = vsketch.Param(0.704, min_value=0.700, max_value=0.707, decimals=3)

    # TEMPORARY: side of the colour-key squares (cm) on A4; scaled with the
    # page height for other sizes (A6 -> half). For quick turnaround.
    swatch_size = vsketch.Param(0.5, min_value=0.2, max_value=3.0, decimals=2)

    def _assignment(self, vsk):
        """Randomly sample the pen assignment from the vsketch seed: the number
        of active slots, the colour-index start, and each slot's pen (drawn
        with replacement from the pen set)."""
        pens = list(PEN_SETS[self.pen_set])
        n = 2 + int(vsk.random(N_SLOTS - 1))  # 2..N_SLOTS
        start = int(vsk.random(N_SLOTS))
        assignment = [pens[int(vsk.random(len(pens)))] for _ in range(n)]
        return assignment, start

    def _key_squares(self, page_w, page_h, s, tree_right, assignment, color_start):
        """Colour key: one filled square per slot, in the order the colour index
        visits them (starting at ColorStart), laid out left to right in the
        lower right. Gaps are 0.618 times the square side; the key ends 1.618
        times the side left of the tree's right edge and the same distance
        above the bottom page edge. Returns {pen: [complex polylines in cm]}; each square is
        hatched at the pen width as one zigzag stroke."""
        n = len(assignment)
        step = s * (1 + 0.618)
        x_end = tree_right - 1.618 * s
        y1 = page_h - 1.618 * s  # bottom edge (y grows downward)
        x0 = x_end - (n * s + (n - 1) * 0.618 * s)
        y0 = y1 - s
        pitch = PEN_WIDTH_MM / 10
        rows = max(int(round(s / pitch)), 1)
        ys = y0 + pitch / 2 + (s - pitch) * np.arange(rows + 1) / rows if rows > 1 else [y0 + s / 2]
        out = {}
        for i in range(n):
            pen = assignment[(color_start + i) % n]
            xa = x0 + i * step
            xs = [xa, xa + s]
            zig = []
            for j, y in enumerate(ys):
                zig += [xs[j % 2] + 1j * y, xs[(j + 1) % 2] + 1j * y]
            outline = [xa + 1j * y0, xa + s + 1j * y0, xa + s + 1j * y1, xa + 1j * y1, xa + 1j * y0]
            out.setdefault(pen, []).extend([np.array(outline), np.array(zig)])
        return out

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size(self.paper, landscape=True, center=False)
        vsk.scale("cm")
        px_per_cm = vp.convert_length("1cm")
        page_w = vsk.width / px_per_cm
        page_h = vsk.height / px_per_cm

        assignment, color_start = self._assignment(vsk)
        n = len(assignment)
        print(f"pens: {assignment}, start {color_start}")
        segments = turtle_segments(
            expand(AXIOM, RULES, int(self.iterations)),
            draw=DRAW,
            turn_angle=TURN_ANGLE,
            length_scale=self.Scale * page_h / REF_PAGE_H_CM,
            transform_scale=self.TransformScale,
            color=color_start,
        )
        if not segments:
            return

        # Rotate about the origin, then place the bounding box.
        R = rotate(GLOBAL_ROTATION)[:2, :2]
        pts = np.array([(a, b) for a, b, _, _ in segments]).reshape(-1, 2, 2)
        pts = pts @ R.T
        flat = pts.reshape(-1, 2)
        # Centre horizontally; vertically the tree sits above the colour key,
        # its lowest point 0.618 * swatch_size above the top of the squares.
        sz = self.swatch_size * page_h / REF_PAGE_H_CM
        lo, hi = flat.min(axis=0), flat.max(axis=0)
        target_bottom = page_h - 2.618 * sz - 0.618 * sz
        pts += np.array([page_w / 2 - (lo[0] + hi[0]) / 2, target_bottom - hi[1]])
        if target_bottom - (hi[1] - lo[1]) < 0:
            print("warning: tree is taller than the space above the colour key")
        pts *= px_per_cm
        colors = np.array([c for _, _, _, c in segments]) % n

        vsk.penWidth(f"{PEN_WIDTH_MM}mm")
        # One layer per distinct pen (its index in the pen set), so repeated
        # slots merge into a single pass for the plotter.
        colors_of = PEN_SETS[self.pen_set]
        pen_names = list(colors_of)
        key = self._key_squares(
            page_w, page_h, sz, page_w / 2 + (hi[0] - lo[0]) / 2, assignment, color_start)
        for pen in dict.fromkeys(assignment):
            mask = np.array([assignment[c] == pen for c in colors])
            if not mask.any():
                continue
            layer = pen_names.index(pen) + 1
            z = pts[mask, :, 0] + 1j * pts[mask, :, 1]
            vsk.stroke(layer)
            lines = list(z) + [l * px_per_cm for l in key.get(pen, [])]
            vsk.document.add(vp.LineCollection(lines), layer)
            vsk.vpype(f"linemerge --no-flip --layer {layer}")
            vsk.vpype(f'color --layer {layer} "{colors_of[pen]}"')

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        pass


if __name__ == "__main__":
    ASFTSketch.display()
