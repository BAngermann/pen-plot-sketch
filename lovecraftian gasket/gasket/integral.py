"""Integral Apollonian circle packings: root quadruples + placement.

An *integral* packing has all-integer curvatures (bends).  Each is generated from
a root quadruple ``(k0, k1, k2, k3)`` of four mutually tangent circles satisfying
Descartes' theorem

    (k0 + k1 + k2 + k3)**2 == 2 * (k0**2 + k1**2 + k2**2 + k3**2),

with ``k0 < 0`` the enclosing circle.  Recursion (see :mod:`packing`) then fills
the gaps; every resulting circle also has integer curvature.

See https://en.wikipedia.org/wiki/Apollonian_gasket#Integral_Apollonian_circle_packings
"""

from __future__ import annotations

import math

from geometry import Circle, descartes_pair

# Curated primitive root quadruples from the Wikipedia table (those not already
# in the sequential family below).
_WIKIPEDIA = [
    (-3, 5, 8, 8), (-4, 8, 9, 9), (-5, 7, 18, 18), (-6, 10, 15, 19),
    (-6, 11, 14, 15), (-7, 9, 32, 32), (-7, 12, 17, 20), (-8, 12, 25, 25),
    (-8, 13, 21, 24), (-9, 11, 50, 50), (-9, 14, 26, 27), (-9, 18, 19, 22),
    (-10, 18, 23, 27), (-11, 16, 36, 37), (-12, 21, 24, 28), (-13, 18, 47, 50),
    (-14, 19, 70, 71), (-15, 24, 40, 41),
]


def sequential_quadruples(nmax: int):
    """The *sequential* family ``(-n, n+1, n(n+1), n(n+1)+1)``.

    n=1 -> (-1,2,2,3); n=2 -> (-2,3,6,7); n=3 -> (-3,4,12,13); ...  Each nests a
    big circle flanked by a chain of ever-smaller ones - the most "browsable" of
    the integral packings.
    """
    return [(-n, n + 1, n * (n + 1), n * (n + 1) + 1) for n in range(1, nmax + 1)]


def _valid(q) -> bool:
    s = sum(q)
    return s * s == 2 * sum(k * k for k in q)


def root_quadruples(nmax_sequential: int = 14):
    """All catalogued root quadruples: the sequential family first, then the
    curated Wikipedia primitives.  Deduplicated and Descartes-validated."""
    seen, out = set(), []
    for q in sequential_quadruples(nmax_sequential) + _WIKIPEDIA:
        if not _valid(q):
            continue
        key = tuple(sorted(q))
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def place_quadruple(k0: int, k1: int, k2: int, k3: int):
    """Four mutually tangent circles ``(outer, c1, c2, c3)`` for a root quadruple.

    The enclosing circle (``k0 < 0``) is centred at the origin with radius
    ``1/|k0|``; ``c1`` sits on the -x axis, ``c2`` is placed by the law of cosines
    so it is tangent to both, and ``c3`` is the Descartes companion with curvature
    ``k3``.  All four are tangent to floating-point precision.
    """
    r0, r1, r2 = 1.0 / abs(k0), 1.0 / k1, 1.0 / k2
    c0 = Circle.from_center(0 + 0j, r0, inside=True)

    d1 = r0 - r1                               # |centre| for internal tangency
    c1 = Circle.from_center(complex(-d1, 0.0), r1)

    d2 = r0 - r2
    cosd = max(-1.0, min(1.0, (d1 * d1 + d2 * d2 - (r1 + r2) ** 2) / (2 * d1 * d2)))
    ang = math.pi - math.acos(cosd)            # c1 is at angle pi
    c2 = Circle.from_center(complex(d2 * math.cos(ang), d2 * math.sin(ang)), r2)

    s1, s2 = descartes_pair(c0, c1, c2)
    c3 = s1 if abs(s1.k - k3) < abs(s2.k - k3) else s2
    return c0, c1, c2, c3


def label(q) -> str:
    return "(" + ", ".join(str(k) for k in q) + ")"


if __name__ == "__main__":
    from geometry import tangency_error
    quads = root_quadruples()
    print(f"{len(quads)} root quadruples")
    bad = 0
    for q in quads:
        c0, c1, c2, c3 = place_quadruple(*q)
        circs = [c0, c1, c2, c3]
        # mutual tangency
        tol = 1e-6
        tang = all(tangency_error(a, b) < tol
                   for i, a in enumerate(circs) for b in circs[i + 1:])
        # curvatures match the quadruple (c3 within rounding)
        ks = sorted(round(c.k) for c in circs)
        ok = tang and ks == sorted(q)
        if not ok:
            bad += 1
            print(f"  BAD {label(q)}: tangent={tang} got_k={ks}")
    print("ALL QUADRUPLES PLACED + TANGENT" if bad == 0 else f"{bad} FAILED")
