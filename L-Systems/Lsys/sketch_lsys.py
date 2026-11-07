import pathlib
import sys

import vpype as vp
import vsketch
import numpy as np

# Make the repo-root `penfill` package importable when run via `vsk run`.
_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
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
    TurnAngle = vsketch.Param(120)
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

    # Up to 7 pen colours, cycled across the instance layers. The first "none"
    # ends the palette; if none are selected, layers fall back to faint black.
    color_1 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_2 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_3 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_4 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_5 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_6 = vsketch.Param("none", choices=COLOR_CHOICES)
    color_7 = vsketch.Param("none", choices=COLOR_CHOICES)

    # linemerge joins the per-segment lines into continuous strokes for plotting
    # but dominates the run time; switch it off while tuning in the preview.
    linemerge = vsketch.Param(True)

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

    def draw(self, vsk: vsketch.Vsketch) -> None:
        # center=False disables vsketch's automatic centring; we place the
        # drawing ourselves (centre on the page, then apply the global offset).
        vsk.size(self.page_size, landscape=self.landscape, center=False)
        vsk.scale("cm")
        # Page dimensions in cm, used to centre the drawing.
        px_per_cm = vp.convert_length("1cm")
        page_w_cm = vsk.width / px_per_cm
        page_h_cm = vsk.height / px_per_cm
        state = self.Axiom
        for i in range(self.iterations):
            newstate = ""
            for t in state:
                if t == self.Pred1:
                    newstate += self.Suc1
                elif t == self.Pred2:
                    newstate += self.Suc2
                else:
                    newstate += t
            state = newstate
        #print(state)

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
        print(f"vertices: {n_vertices}")

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

        # Place the whole drawing: centre its bounding box on the page, rotate
        # about that centre, then apply the global translation (cm).
        all_pts = np.vstack([self._endpoints(s) for s in instances if s])
        if len(all_pts):
            center = (all_pts.min(axis=0) + all_pts.max(axis=0)) / 2
            offset = np.array([page_w_cm / 2 + self.GlobalTranslateX,
                               page_h_cm / 2 + self.GlobalTranslateY])
            R = self._rotate(self.GlobalRotation)[:2, :2]
            t = offset - R @ center
            instances = [self._transform(s, R, t) for s in instances]

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

    def _generate_segments(self, vsk: vsketch.Vsketch, state, jitter=True):
        """Walk the turtle over `state`, returning a list of
        ((x0,y0),(x1,y1),weight,color) line segments in cm (Scale folded into the
        root matrix; weight is the integer stroke weight, color the colour index). When `jitter`
        is False the turtle uses exact nominal lengths/angles."""
        def gauss():
            return vsk.randomGaussian() if jitter else 0.0
        matrix = self._scale(self.Scale)
        weight = max(int(self.StrokeWeight), 1)
        color = int(self.ColorStart)
        stack = []
        segments = []
        for t in state:
            if t in self.Draw:
                dist = 1 + gauss() * self.Length_std_deviation
                p0 = matrix @ np.array([0.0, 0.0, 1.0])
                p1 = matrix @ np.array([0.0, dist, 1.0])
                segments.append(((p0[0], p0[1]), (p1[0], p1[1]), weight, color))
                matrix = matrix @ self._translate(0, dist)
            elif t == "+":
                matrix = matrix @ self._rotate(self.TurnAngle + gauss() * self.Angle__std_deviation)
            elif t == "-":
                matrix = matrix @ self._rotate(-self.TurnAngle + gauss() * self.Angle__std_deviation)
            elif t == self.Move:
                matrix = matrix @ self._translate(0, 1 + gauss() * self.Length_std_deviation)
            elif t == "[":
                stack.append((matrix.copy(), weight, color))
            elif t == "]":
                matrix, weight, color = stack.pop()
            elif t == "*":
                matrix = matrix @ self._scale(self.TransformScale)
            elif t == "#":
                weight += 1
            elif t == "!":
                weight = max(weight - 1, 1)
            elif t == "'":
                color += 1
            elif t == '"':
                color -= 1
        return segments

    @staticmethod
    def _translate(dx, dy):
        return np.array([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]])

    @staticmethod
    def _scale(s):
        return np.array([[s, 0.0, 0.0], [0.0, s, 0.0], [0.0, 0.0, 1.0]])

    @staticmethod
    def _rotate(degrees):
        theta = np.radians(degrees)
        c, s = np.cos(theta), np.sin(theta)
        return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])

    def _palette(self):
        """Selected pen colours (hex), truncated at the first 'none' slot."""
        palette = []
        for c in (self.color_1, self.color_2, self.color_3, self.color_4,
                  self.color_5, self.color_6, self.color_7):
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
