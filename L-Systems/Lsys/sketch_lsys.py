import vsketch
import numpy as np

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
    Align_instances = vsketch.Param(False)
    Fix_reference = vsketch.Param(False)
    iterations = vsketch.Param(1)
    Scale = vsketch.Param(0.2, decimals = 3)
    TransformScale = vsketch.Param(0.5, decimals = 3)
    GlobalRotation = vsketch.Param(0.0, decimals = 2)
    GlobalTranslateX = vsketch.Param(0.0, decimals = 2)
    GlobalTranslateY = vsketch.Param(0.0, decimals = 2)

    # A4 portrait page dimensions in cm, used to centre the drawing.
    PAGE_W_CM = 21.0
    PAGE_H_CM = 29.7

    def draw(self, vsk: vsketch.Vsketch) -> None:
        # center=False disables vsketch's automatic centring; we place the
        # drawing ourselves (centre on the page, then apply the global offset).
        vsk.size("a4", landscape=False, center=False)
        vsk.scale("cm")
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

        if self.Align_instances and len(instances) > 1:
            # Align each instance onto the first by the rigid transform
            # (rotation + translation) that minimises the mean squared distance
            # between corresponding endpoints, rather than pinning them all to a
            # shared starting point.
            reference = self._endpoints(instances[0])
            for i in range(1, len(instances)):
                R, t = self._kabsch(self._endpoints(instances[i]), reference)
                instances[i] = self._transform(instances[i], R, t)

        # Place the whole drawing: centre its bounding box on the page, rotate
        # about that centre, then apply the global translation (cm).
        all_pts = np.vstack([self._endpoints(s) for s in instances if s])
        if len(all_pts):
            center = (all_pts.min(axis=0) + all_pts.max(axis=0)) / 2
            offset = np.array([self.PAGE_W_CM / 2 + self.GlobalTranslateX,
                               self.PAGE_H_CM / 2 + self.GlobalTranslateY])
            R = self._rotate(self.GlobalRotation)[:2, :2]
            t = offset - R @ center
            instances = [self._transform(s, R, t) for s in instances]

        # Draw each instance on its own layer, then linemerge only within that
        # layer (--no-flip preserves segment direction). Keeping instances on
        # separate layers/passes lets the ink dry instead of piling overlapping
        # strokes in the same spot.
        for i, segments in enumerate(instances):
            layer = i + 1
            vsk.stroke(layer)
            for (x0, y0), (x1, y1) in segments:
                vsk.line(x0, y0, x1, y1)
            vsk.vpype(f"linemerge --no-flip --layer {layer}")
            # Black at 30% opacity (alpha 0x4D) so overlapping passes read faint.
            vsk.vpype(f'color --layer {layer} "#0000004d"')

    def _generate_segments(self, vsk: vsketch.Vsketch, state, jitter=True):
        """Walk the turtle over `state`, returning a list of ((x0,y0),(x1,y1))
        line segments in cm (Scale folded into the root matrix). When `jitter`
        is False the turtle uses exact nominal lengths/angles."""
        def gauss():
            return vsk.randomGaussian() if jitter else 0.0
        matrix = self._scale(self.Scale)
        stack = []
        segments = []
        for t in state:
            if t in self.Draw:
                dist = 1 + gauss() * self.Length_std_deviation
                p0 = matrix @ np.array([0.0, 0.0, 1.0])
                p1 = matrix @ np.array([0.0, dist, 1.0])
                segments.append(((p0[0], p0[1]), (p1[0], p1[1])))
                matrix = matrix @ self._translate(0, dist)
            elif t == "+":
                matrix = matrix @ self._rotate(self.TurnAngle + gauss() * self.Angle__std_deviation)
            elif t == "-":
                matrix = matrix @ self._rotate(-self.TurnAngle + gauss() * self.Angle__std_deviation)
            elif t == self.Move:
                matrix = matrix @ self._translate(0, 1 + gauss() * self.Length_std_deviation)
            elif t == "[":
                stack.append(matrix.copy())
            elif t == "]":
                matrix = stack.pop()
            elif t == "*":
                matrix = matrix @ self._scale(self.TransformScale)
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

    @staticmethod
    def _endpoints(segments):
        """Flatten a segment list into an (N, 2) array of endpoints, in order."""
        pts = []
        for a, b in segments:
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
        for a, b in segments:
            a2 = R @ np.array(a) + t
            b2 = R @ np.array(b) + t
            out.append(((a2[0], a2[1]), (b2[0], b2[1])))
        return out

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        pass


if __name__ == "__main__":
    LsysSketch.display()
