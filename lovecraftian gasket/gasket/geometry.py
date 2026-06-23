"""Pure-geometry core for Apollonian circle packing.

No vsketch / matplotlib imports here so this module can run headless inside the
search loop and be unit-tested.

Representation
--------------
Every disk is stored as a ``(k, w)`` pair where

    k = signed curvature (1/r); negative for an enclosing circle
    w = k * z              (complex "curvature-times-centre")

This curvature-centre form is what makes the complex Descartes algebra terse and
- crucially - lets the recursion use the *sign-free reflection identity* instead
of the error-prone ``±sqrt`` branch selection.

Descartes' Circle Theorem (complex form), for four mutually tangent circles::

    k4 + k4' = 2 (k1 + k2 + k3)
    w4 + w4' = 2 (w1 + w2 + w3)

So given three mutually tangent circles and *one* known fourth circle tangent to
all three, the other fourth circle is a pure reflection - no square roots, no
sign ambiguity.  Seeding (when no fourth circle is known yet) uses the explicit
``±sqrt`` form, which for **circles** (k != 0) is well behaved; both solutions are
returned and the caller picks.
"""

from __future__ import annotations

import cmath
from dataclasses import dataclass


@dataclass
class Circle:
    """A disk in curvature-centre coordinates.

    ``k`` is the signed curvature (negative for the enclosing boundary circle);
    ``w = k * z`` where ``z`` is the centre as a complex number.
    """

    k: float            # signed curvature (1/r)
    w: complex          # k * z
    depth: int = 0
    feature: str = ""   # assigned later by the renderer
    parent: int = -1    # index into the packing list, -1 for seeds

    @classmethod
    def from_center(cls, z: complex, r: float, *, inside: bool = False,
                    depth: int = 0, feature: str = "") -> "Circle":
        """Build from centre and (positive) radius.

        ``inside=True`` marks an *enclosing* boundary circle (negative curvature
        so its interior is the packing region).
        """
        k = (-1.0 if inside else 1.0) / r
        return cls(k=k, w=k * z, depth=depth, feature=feature)

    @property
    def z(self) -> complex:
        return self.w / self.k

    @property
    def r(self) -> float:
        return abs(1.0 / self.k)

    def __repr__(self) -> str:
        z = self.z
        return (f"Circle(z=({z.real:.4g},{z.imag:.4g}), r={self.r:.4g}, "
                f"k={self.k:.4g}, depth={self.depth})")


def descartes_pair(c1: Circle, c2: Circle, c3: Circle) -> tuple[Circle, Circle]:
    """Both circles tangent to three mutually tangent circles (seeding form).

    Returns ``(inner, outer)`` ordered by curvature: ``inner`` has the larger
    curvature (the small Soddy circle nestled in the curvilinear triangle);
    ``outer`` the smaller / more negative (the enclosing solution).
    """
    k1, k2, k3 = c1.k, c2.k, c3.k
    w1, w2, w3 = c1.w, c2.w, c3.w

    ksum = k1 + k2 + k3
    kroot = 2.0 * cmath.sqrt(k1 * k2 + k2 * k3 + k3 * k1)
    wsum = w1 + w2 + w3
    wroot = 2.0 * cmath.sqrt(w1 * w2 + w2 * w3 + w3 * w1)

    # The k and w roots must use a *consistent* sign.  Build both candidates and
    # keep the pairing that is actually tangent to all three inputs.
    cand_a = Circle(k=(ksum + kroot).real, w=wsum + wroot)
    cand_b = Circle(k=(ksum - kroot).real, w=wsum - wroot)
    cand_c = Circle(k=(ksum + kroot).real, w=wsum - wroot)
    cand_d = Circle(k=(ksum - kroot).real, w=wsum + wroot)

    def err(c: Circle) -> float:
        if abs(c.k) < 1e-12:
            return float("inf")
        return (tangency_error(c, c1) ** 2 + tangency_error(c, c2) ** 2
                + tangency_error(c, c3) ** 2)

    sols = sorted((cand_a, cand_b, cand_c, cand_d), key=err)
    s1, s2 = sols[0], sols[1]
    inner, outer = (s1, s2) if s1.k >= s2.k else (s2, s1)
    return inner, outer


def soddy_reflect(known: Circle, c1: Circle, c2: Circle, c3: Circle) -> Circle:
    """The *other* Soddy circle in triangle (c1,c2,c3), given one (``known``).

    Sign-free Descartes reflection - the workhorse of the recursion.
    """
    k4 = 2.0 * (c1.k + c2.k + c3.k) - known.k
    w4 = 2.0 * (c1.w + c2.w + c3.w) - known.w
    return Circle(k=k4, w=w4)


def tangency_error(a: Circle, b: Circle) -> float:
    """Signed deviation from tangency between two disks (0 == tangent).

    For two positive circles the tangency distance is ``r_a + r_b`` (external)
    or ``|r_a - r_b|`` (internal); we return the smaller residual so that an
    enclosing circle (negative k) reads as internally tangent to its children.
    """
    d = abs(a.z - b.z)
    ext = abs(d - (a.r + b.r))
    internal = abs(d - abs(a.r - b.r))
    return min(ext, internal)


def are_tangent(a: Circle, b: Circle, tol: float = 1e-6) -> bool:
    return tangency_error(a, b) <= tol * max(1.0, a.r, b.r)


# ---------------------------------------------------------------------------
# Self-check: run ``python geometry.py`` to verify sign conventions on the
# classic integer Apollonian gasket (-1, 2, 2, 3) before trusting anything.
# ---------------------------------------------------------------------------
def _selfcheck() -> None:
    # Outer circle radius 1 at origin (enclosing -> negative curvature), two
    # interior circles radius 1/2 at (+-1/2, 0).
    outer = Circle.from_center(0 + 0j, 1.0, inside=True)
    a = Circle.from_center(0.5 + 0j, 0.5)
    b = Circle.from_center(-0.5 + 0j, 0.5)
    assert are_tangent(a, b), "seed circles should be tangent"
    assert are_tangent(a, outer), "seed tangent to outer"

    inner, _ = descartes_pair(outer, a, b)
    print("descartes_pair inner:", inner, " expected k=3, centre (0, +-2/3)")
    assert abs(inner.k - 3.0) < 1e-9, f"expected k=3, got {inner.k}"
    assert abs(abs(inner.z.imag) - 2.0 / 3.0) < 1e-9, inner.z

    # Reflection: the *other* k=3 circle is the mirror of `inner` through (outer,a,b).
    other = soddy_reflect(inner, outer, a, b)
    print("soddy_reflect other:", other, " expected k=3, mirrored centre")
    assert abs(other.k - 3.0) < 1e-9
    assert abs(other.z.imag + inner.z.imag) < 1e-9, "should mirror across x-axis"

    # One more generation: triangle (inner, a, outer) reflecting b.
    nxt = soddy_reflect(b, inner, a, outer)
    print("next generation circle:", nxt)
    assert nxt.k > 3.0, "deeper circle should be smaller"
    for parent in (inner, a, outer):
        assert are_tangent(nxt, parent), f"new circle must be tangent to {parent}"

    print("\nALL GEOMETRY SELF-CHECKS PASSED")


if __name__ == "__main__":
    _selfcheck()
