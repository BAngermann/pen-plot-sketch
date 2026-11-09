import pathlib
import sys

import vpype as vp
import vsketch
import numpy as np

# Make the repo-root `penfill` package importable when run via `vsk run`.
_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from lsys_common import expand, rotate, turtle_segments
from penfill import install_swatches, load_pens

# Pen colours converted from DrawingBot presets (see tools/drawingbot_to_vpype.py).
PENS = load_pens(_REPO / "pens")            # {pen name: "#rrggbb"}
COLOR_CHOICES = ["none"] + list(PENS)

# Show colour swatches next to pen names in the GUI dropdowns (GUI-only no-op).
install_swatches(PENS)


class LsysSketch(vsketch.SketchClass):
    Axiom = vsketch.Param("F")
    Pred1 = vsketch.Param("F")
    Suc1 = vsketch.Param("F[+*F][-*F]")
    Pred2 = vsketch.Param("")
    Suc2 = vsketch.Param("")
    Draw = vsketch.Param("F")
    Move = vsketch.Param("f")
    TurnAngle = vsketch.Param(120.0, decimals=3)
    Angle__std_deviation = vsketch.Param(0.0,decimals = 3)
    Length_std_deviation=  vsketch.Param(0.0,decimals = 3)
    instances = vsketch.Param(1)
    AlignStart = vsketch.Param(0)
    AlignEnd = vsketch.Param(0)
    Fix_reference = vsketch.Param(False)
    iterations = vsketch.Param(1)
    Scale = vsketch.Param(0.2, decimals = 3)
    TransformScale = vsketch.Param(0.5, decimals = 3)
    GlobalRotation = vsketch.Param(0.0, decimals = 2)
    GlobalTranslateX = vsketch.Param(0.0, decimals = 2)
    GlobalTranslateY = vsketch.Param(0.0, decimals = 2)

    # Up to 10 pen colours, cycled across the instance layers. The first "none"
    # ends the palette; if none are selected, layers fall back to faint black.
    color_1 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_2 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_3 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_4 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_5 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_6 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_7 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_8 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_9 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_10 = vsketch.Param("none", choices=COLOR_CHOICES)

    # linemerge joins the per-segment lines into continuous strokes for plotting
    # but dominates the run time; switch it off while tuning in the preview.
    linemerge = vsketch.Param(True)

    # For rules without brackets and without the Move symbol the turtle path is
    # one connected line: draw it as a single polyline (no pen lifts, no
    # linemerge needed). Segments the path retraces are drawn again each time.
    single_path = vsketch.Param(False)

    # How pens are assigned: "instance" cycles the palette across the instance
    # layers; "symbol" lets the string pick the pen via the ' / " colour-index
    # symbols (index mod number of selected pens), starting at ColorStart.
    color_mode = vsketch.Param("instance", choices=["instance", "symbol"])
    ColorStart = vsketch.Param(0)

    # Stroke weight = number of parallel pen lines per segment (vsketch
    # strokeWeight); pen_width (mm) is the spacing between them.
    StrokeWeight = vsketch.Param(1, min_value=1)
    pen_width = vsketch.Param(0.3, min_value=0.01, decimals=2)
    # Pull each end of a stroke in by the amount the extra weight adds there, so
    # a heavy stroke keeps its nominal length instead of poking out past its ends.
    shorten_strokes = vsketch.Param(False)
    page_size = vsketch.Param("a4")
    landscape = vsketch.Param(False)

    # Panel layout: a panels_x x panels_y grid of equal panels, each holding its
    # own copy of the L-system (numbered row by row, left to right, from the
    # top). margin_* is the exterior margin, gap_* the space between panels (cm).
    panels_x = vsketch.Param(1, min_value=1)
    panels_y = vsketch.Param(1, min_value=1)
    margin_x = vsketch.Param(0.0, min_value=0.0, decimals=2)
    margin_y = vsketch.Param(0.0, min_value=0.0, decimals=2)
    gap_x = vsketch.Param(0.0, min_value=0.0, decimals=2)
    gap_y = vsketch.Param(0.0, min_value=0.0, decimals=2)
    # Scale each drawing uniformly to fill its panel (Scale is then irrelevant).
    panel_fit = vsketch.Param(False)
    # What is pinned to the panel: "center" centres the drawing's bounding box
    # in the panel; "start" puts the turtle's starting point at the fractional
    # panel position (anchor_x, anchor_y) (0 = left/top, 1 = right/bottom) and
    # rotates/scales about it, so e.g. tree roots line up across panels.
    panel_anchor = vsketch.Param("center", choices=["center", "start"])
    anchor_x = vsketch.Param(0.5, min_value=0.0, max_value=1.0, decimals=3)
    anchor_y = vsketch.Param(0.5, min_value=0.0, max_value=1.0, decimals=3)
    # With more than one panel, panel k reseeds the random jitter with
    # panel_seed + k * panel_seed_step and uses iterations + k *
    # panel_iterations_step rewrite passes. (A single panel never reseeds.)
    panel_seed = vsketch.Param(0)
    panel_seed_step = vsketch.Param(1)
    panel_iterations_step = vsketch.Param(0)
    # Panel k's whole virtual page (drawing and anchor) is rotated about the
    # panel centre by k * panel_rotation_step degrees.
    panel_rotation_step = vsketch.Param(0.0, decimals=2)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        # center=False disables vsketch's automatic centring; we place the
        # drawing ourselves (centre on the page, then apply the global offset).
        vsk.size(self.page_size, landscape=self.landscape, center=False)
        vsk.scale("cm")
        # Page dimensions in cm, used to centre the drawing.
        px_per_cm = vp.convert_length("1cm")
        page_w_cm = vsk.width / px_per_cm
        page_h_cm = vsk.height / px_per_cm
        # Build every panel; instance i of all panels shares layer(s) so that
        # the plot is organised by pen/pass rather than by panel.
        panels = self._panel_rects(page_w_cm, page_h_cm)
        multi = len(panels) > 1
        instances = [[] for _ in range(self.instances)]
        for k, rect in enumerate(panels):
            if multi:
                vsk.randomSeed(self.panel_seed + k * self.panel_seed_step)
            iterations = max(self.iterations + k * self.panel_iterations_step, 0)
            for i, segs in enumerate(self._build_panel(vsk, iterations, rect, k if multi else None)):
                instances[i].extend(segs)

        # Each instance gets its own layer(s), then linemerge runs only within
        # a layer (--no-flip preserves segment direction). Keeping instances on
        # separate layers/passes lets the ink dry instead of piling overlapping
        # strokes in the same spot. In "symbol" colour mode an instance is
        # further split into one layer per pen, chosen by the colour index.
        palette = self._palette()
        by_symbol = self.color_mode == "symbol" and bool(palette)
        n_slots = len(palette) if by_symbol else 1
        vsk.penWidth(f"{self.pen_width}mm")
        pen_cm = self.pen_width / 10
        chain_mode = self.single_path and self._single_path_possible()
        if self.single_path and not chain_mode:
            print("single_path ignored: the rules contain brackets or the Move symbol")
        for i, segments in enumerate(instances):
            for slot in range(n_slots):
                if by_symbol:
                    group = [sg for sg in segments if sg[3] % n_slots == slot]
                    layer = i * n_slots + slot + 1
                    color = palette[slot]
                else:
                    group = segments
                    layer = i + 1
                    # Cycle the selected pens across layers; with no pens
                    # selected, fall back to black at 30% opacity (alpha 0x4D)
                    # so overlaps read faint.
                    color = palette[i % len(palette)] if palette else "#0000004d"
                if not group:
                    continue
                vsk.stroke(layer)
                if chain_mode:
                    # Connected runs of equal weight become one polyline each
                    # (a bracket-free, move-free string gives one per panel and
                    # pen). shorten_strokes does not apply to continuous paths.
                    lines = []

                    def flush_lines():
                        if lines:
                            vsk.document.add(vp.LineCollection(lines), layer)
                            lines.clear()

                    for weight, pts in self._chains(group):
                        if weight == 1:
                            z = (pts[:, 0] + 1j * pts[:, 1]) * px_per_cm
                            lines.append(z)
                        else:
                            flush_lines()
                            vsk.strokeWeight(weight)
                            vsk.polygon(pts[:, 0], pts[:, 1], close=False)
                    flush_lines()
                    vsk.vpype(f'color --layer {layer} "{color}"')
                    continue
                # Weight-1 strokes are plain two-point lines, so consecutive
                # ones are converted to page units (the only transform in
                # effect is vsk.scale("cm")) and added to the document in one
                # batch instead of one vsk.line call each (much faster).
                # Heavier strokes go through vsk.line so vsketch builds their
                # parallel lines. Batches are flushed before any heavier
                # stroke to keep the line order within the layer unchanged.
                batch = []

                def flush():
                    if batch:
                        pts = np.array(batch).reshape(-1, 2, 2) * px_per_cm
                        z = pts[..., 0] + 1j * pts[..., 1]
                        vsk.document.add(vp.LineCollection(list(z)), layer)
                        batch.clear()

                for (x0, y0), (x1, y1), weight, _ in group:
                    if weight == 1:
                        batch.append((x0, y0, x1, y1))
                        continue
                    flush()
                    vsk.strokeWeight(weight)
                    if self.shorten_strokes:
                        # A weight-n stroke extends (n-1)/2 pen widths past each end.
                        dx, dy = x1 - x0, y1 - y0
                        length = np.hypot(dx, dy)
                        if length > 0:
                            cut = min((weight - 1) / 2 * pen_cm, length / 2 - 1e-6)
                            cut = max(cut, 0.0)
                            ux, uy = dx / length, dy / length
                            x0, y0 = x0 + ux * cut, y0 + uy * cut
                            x1, y1 = x1 - ux * cut, y1 - uy * cut
                    vsk.line(x0, y0, x1, y1)
                flush()
                if self.linemerge:
                    vsk.vpype(f"linemerge --no-flip --layer {layer}")
                vsk.vpype(f'color --layer {layer} "{color}"')

    def _single_path_possible(self):
        """True if no rule (or the axiom) contains a bracket or the Move symbol,
        i.e. the turtle never jumps and the path is one connected line."""
        texts = (self.Axiom, self.Suc1, self.Suc2)
        banned = "[]" + (self.Move if self.Move else "")
        return not any(ch in t for t in texts for ch in banned)

    @staticmethod
    def _chains(group, tol=1e-9):
        """Split a segment list into runs of connected segments with the same
        weight: [(weight, (n, 2) array of polyline points), ...]. A segment
        joins the current run if it starts where the previous one ended."""
        chains = []
        cur, w, end = None, None, None
        for a, b, weight, _ in group:
            if (cur is not None and weight == w
                    and abs(a[0] - end[0]) <= tol and abs(a[1] - end[1]) <= tol):
                cur.append(b)
            else:
                if cur is not None:
                    chains.append((w, np.array(cur)))
                cur, w = [a, b], weight
            end = b
        if cur is not None:
            chains.append((w, np.array(cur)))
        return chains

    def _panel_rects(self, page_w, page_h):
        """(x, y, w, h) in cm of every panel, row by row from the top left."""
        cols, rows = int(self.panels_x), int(self.panels_y)
        w = (page_w - 2 * self.margin_x - (cols - 1) * self.gap_x) / cols
        h = (page_h - 2 * self.margin_y - (rows - 1) * self.gap_y) / rows
        if w <= 0 or h <= 0:
            raise ValueError(
                f"margins/gaps leave no room for the panels (panel size {w:.2f} x {h:.2f} cm)"
            )
        return [
            (self.margin_x + c * (w + self.gap_x), self.margin_y + r * (h + self.gap_y), w, h)
            for r in range(rows) for c in range(cols)
        ]

    def _expand(self, iterations):
        """Apply the rewrite rules `iterations` times to the axiom."""
        rules = {}
        # Pred1 wins if both rules share a predecessor. Predecessors are single
        # characters; anything else never matched.
        for pred, suc in ((self.Pred2, self.Suc2), (self.Pred1, self.Suc1)):
            if len(pred) == 1:
                rules[pred] = suc
        return expand(self.Axiom, rules, iterations)

    def _build_panel(self, vsk, iterations, rect, panel_index):
        """Geometry (one segment list per instance, in page cm) of one panel."""
        px, py, pw, ph = rect
        state = self._expand(iterations)

        # Generate the (jittered) geometry for every instance, in cm (Scale is
        # folded into the turtle). Because the jitter only perturbs
        # lengths/angles and never the string, every instance has the same
        # number of segments in the same order, so their endpoints correspond
        # one-to-one across instances. With Fix_reference, instance 0 is drawn at
        # its nominal (un-jittered) values.
        instances = [
            self._generate_segments(vsk, state, jitter=not (self.Fix_reference and i == 0))
            for i in range(self.instances)
        ]

        # Report the vertex count so the user can pick an AlignStart/AlignEnd range.
        n_vertices = len(self._endpoints(instances[0])) if instances else 0
        label = "" if panel_index is None else f"panel {panel_index} "
        print(f"{label}vertices: {n_vertices}")

        if len(instances) > 1:
            # Align each instance onto the first (instance 0) by the rigid
            # transform (rotation + translation) that minimises the mean squared
            # distance between corresponding endpoints, over the vertex-index
            # range [AlignStart:AlignEnd]. The two extremes:
            #   - first vertex only -> pins instances at their shared start point
            #     (default, and what an empty range falls back to)
            #   - all vertices      -> best whole-shape fit of the bundle
            reference = self._endpoints(instances[0])
            start, end = self._align_range(len(reference))
            for i in range(1, len(instances)):
                pts = self._endpoints(instances[i])
                R, t = self._kabsch(pts[start:end], reference[start:end])
                instances[i] = self._transform(instances[i], R, t)

        # Place the drawing in its panel: rotate it, then either centre its
        # bounding box in the panel or pin the turtle start point to the anchor
        # (optionally scaling it to fill the panel), then apply the global
        # translation (cm).
        all_pts = np.vstack([self._endpoints(s) for s in instances if s])
        if len(all_pts):
            offset = np.array([px + pw / 2 + self.GlobalTranslateX,
                               py + ph / 2 + self.GlobalTranslateY])
            R = rotate(self.GlobalRotation)[:2, :2]
            if self.panel_anchor == "start":
                # The turtle starts at (0, 0) and instance 0 is never moved by
                # the alignment, so (0, 0) is the start point; map it onto the
                # anchor.
                anchor = np.array([px + self.anchor_x * pw + self.GlobalTranslateX,
                                   py + self.anchor_y * ph + self.GlobalTranslateY])
                if self.panel_fit:
                    # Largest scale that keeps the drawing inside the panel
                    # around the fixed anchor. A side with no room (anchor on
                    # that edge) cannot constrain the scale, so the drawing may
                    # overhang there.
                    rel = all_pts @ R.T
                    room = (anchor - np.array([px, py]), np.array([px + pw, py + ph]) - anchor)
                    scale = np.inf
                    for a in (0, 1):
                        lo, hi = rel[:, a].min(), rel[:, a].max()
                        if lo < 0 and room[0][a] > 0:
                            scale = min(scale, room[0][a] / -lo)
                        if hi > 0 and room[1][a] > 0:
                            scale = min(scale, room[1][a] / hi)
                    R = (1.0 if np.isinf(scale) else scale) * R
                t = anchor
            elif self.panel_fit:
                rotated = all_pts @ R.T
                lo, hi = rotated.min(axis=0), rotated.max(axis=0)
                size = hi - lo
                ratios = [lim / d for lim, d in ((pw, size[0]), (ph, size[1])) if d > 0]
                scale = min(ratios) if ratios else 1.0
                R = scale * R
                center = scale * (lo + hi) / 2
                t = offset - center
            else:
                center = (all_pts.min(axis=0) + all_pts.max(axis=0)) / 2
                t = offset - R @ center
            instances = [self._transform(s, R, t) for s in instances]
            # Rotate the whole virtual page of the panel (drawing, anchor and
            # all) about the panel centre, so e.g. at 180 degrees a tree rooted
            # near the bottom edge is rooted the same distance below the top
            # edge and grows downward.
            panel_angle = (panel_index or 0) * self.panel_rotation_step
            if panel_angle:
                Rp = rotate(panel_angle)[:2, :2]
                pc = np.array([px + pw / 2, py + ph / 2])
                instances = [self._transform(s, Rp, pc - Rp @ pc) for s in instances]
        return instances

    def _generate_segments(self, vsk: vsketch.Vsketch, state, jitter=True):
        """Walk the turtle over `state`, returning a list of
        ((x0,y0),(x1,y1),weight,color) line segments in cm (Scale folded into the
        root matrix; weight is the integer stroke weight, color the colour index).
        When `jitter` is False the turtle uses exact nominal lengths/angles."""
        return turtle_segments(
            state,
            draw=self.Draw,
            move=self.Move,
            turn_angle=self.TurnAngle,
            length_scale=self.Scale,
            transform_scale=self.TransformScale,
            angle_std=self.Angle__std_deviation,
            length_std=self.Length_std_deviation,
            gauss=vsk.randomGaussian if jitter else (lambda: 0.0),
            weight=self.StrokeWeight,
            color=int(self.ColorStart),
        )

    def _palette(self):
        """Selected pen colours (hex), truncated at the first 'none' slot."""
        palette = []
        for c in (self.color_1, self.color_2, self.color_3, self.color_4,
                  self.color_5, self.color_6, self.color_7, self.color_8,
                  self.color_9, self.color_10):
            if c == "none":
                break
            palette.append(PENS.get(c, "black"))
        return palette

    def _align_range(self, n):
        """Resolve (AlignStart, AlignEnd) into a half-open vertex slice [start,
        end) over `n` endpoints. start is clamped to >= 0; an end past the last
        vertex or negative means "all vertices"; an empty range falls back to
        the first vertex only (align at the shared start point)."""
        start = max(int(self.AlignStart), 0)
        end = int(self.AlignEnd)
        if end < 0 or end > n:
            end = n
        if start >= end:
            start, end = 0, 1
        return start, end

    @staticmethod
    def _endpoints(segments):
        """Flatten a segment list into an (N, 2) array of endpoints, in order."""
        pts = []
        for a, b, _, _ in segments:
            pts.append(a)
            pts.append(b)
        return np.array(pts)

    @staticmethod
    def _kabsch(points, reference):
        """Optimal rigid transform (R, t) mapping `points` onto `reference`,
        minimising sum |R @ p_i + t - r_i|^2 (Kabsch / Procrustes)."""
        pc = points.mean(axis=0)
        rc = reference.mean(axis=0)
        H = (points - pc).T @ (reference - rc)
        U, _, Vt = np.linalg.svd(H)
        # Correct for a possible reflection so R is a proper rotation.
        d = np.sign(np.linalg.det(Vt.T @ U.T))
        R = Vt.T @ np.diag([1.0, d]) @ U.T
        t = rc - R @ pc
        return R, t

    @staticmethod
    def _transform(segments, R, t):
        out = []
        for a, b, w, c in segments:
            a2 = R @ np.array(a) + t
            b2 = R @ np.array(b) + t
            out.append(((a2[0], a2[1]), (b2[0], b2[1]), w, c))
        return out

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        pass


if __name__ == "__main__":
    LsysSketch.display()
