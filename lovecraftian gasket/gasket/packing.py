"""Apollonian recursion: fill curvilinear triangles down to ``r_min``.

Sign-free reflection recursion (see :mod:`geometry`).  A *gap* is a triple of
mutually tangent circles; its inner Soddy circle is found once, then each of the
three sub-triangles it creates is recursed into.

Boundary handling
-----------------
Two distinct ideas, deliberately separate:

* **Packing boundary** - an enclosing circle with *negative* curvature whose
  interior is the region being filled.  Circle-only Descartes (no ``k=0`` lines)
  keeps the algebra robust.
* **Drawable clip** - an axis-aligned rectangle (A4 minus margins).  Any circle
  whose disk is not fully inside the clip is *discarded* (it is never emitted and
  never recursed through).  This is what lets an *irregular frame* poke past a
  pure rectangle while keeping ink inside the printable area.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from geometry import Circle, descartes_pair, soddy_reflect, tangency_error

# Absolute tangency tolerance (mm) for detecting seed triples.  Snap leaves
# residuals ~1e-4 mm, far below this; the strict relative test in geometry is
# too tight to recognise snapped seeds as tangent.
SEED_TANGENT_TOL = 0.6


@dataclass(frozen=True)
class Rect:
    """Axis-aligned drawable region (mm)."""

    x0: float
    y0: float
    x1: float
    y1: float

    def contains_disk(self, c: Circle, slack: float = 0.0) -> bool:
        z, r = c.z, c.r
        return (z.real - r >= self.x0 - slack and z.real + r <= self.x1 + slack
                and z.imag - r >= self.y0 - slack and z.imag + r <= self.y1 + slack)

    def contains_point(self, z: complex) -> bool:
        return self.x0 <= z.real <= self.x1 and self.y0 <= z.imag <= self.y1


def a4_clip(margin: float = 20.0, landscape: bool = False) -> Rect:
    """A4 (210x297 mm) drawable rectangle inset by ``margin`` mm on every side."""
    w, h = (297.0, 210.0) if landscape else (210.0, 297.0)
    return Rect(margin, margin, w - margin, h - margin)


# The same circle is reached via several reflection paths, each accruing ~um of
# floating-point drift.  Dedup by *distance* (not a fine grid, which splits on
# bucket straddles): two emissions of one circle land within DEDUP_TOL mm, while
# distinct packing circles are >= r_a + r_b (>= 2*r_min) apart - orders of
# magnitude more - so there is no risk of merging genuinely different circles.
DEDUP_TOL = 0.02   # mm
_DEDUP_CELL = 0.5  # mm; bucket size for the spatial hash (>> DEDUP_TOL)
_OVERLAP_CELL = 8.0  # mm; bucket size for the overlap-rejection grid


def pack(seeds: list[Circle], outer: Circle | None, clip: Rect, *,
         r_min: float = 1.5, max_depth: int = 40,
         reject_overlaps: bool = True) -> list[Circle]:
    """Pack the region bounded by ``outer`` and tangencies among ``seeds``.

    ``seeds`` and ``outer`` must already be (approximately) mutually tangent
    where they touch - run :mod:`snap` first on hand-placed circles.  Returns
    all positive-curvature circles inside ``clip`` (the ``outer`` circle itself
    is not emitted).

    ``outer`` may be ``None`` to drop the enclosing circle entirely: only the
    curvilinear gaps *between* mutually tangent seed circles are filled, so the
    outer edge follows the seed arrangement rather than a fixed circle.
    """
    out: list[Circle] = []
    buckets: dict[tuple[int, int], list[Circle]] = {}
    ogrid: dict[tuple[int, int], list[Circle]] = {}

    def _cell(z: complex) -> tuple[int, int]:
        return (int(z.real // _DEDUP_CELL), int(z.imag // _DEDUP_CELL))

    def _register(c: Circle) -> None:
        buckets.setdefault(_cell(c.z), []).append(c)

    def _seen(c: Circle) -> bool:
        cx, cy = _cell(c.z)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for kc in buckets.get((cx + dx, cy + dy), ()):
                    if abs(kc.z - c.z) < DEDUP_TOL:
                        return True
        return False

    # Overlap guard: a valid packing has only tangent (overlap ~ 0) or disjoint
    # circles.  Auto-generated seed graphs (snap satisfies declared edges but is
    # not a globally consistent packing) can produce intersecting circles, which
    # the Descartes recursion then propagates.  Reject any circle overlapping an
    # already-placed one.  Circles are hashed by every cell their bbox covers, so
    # overlaps between far-apart big circles are still found.
    def _ocells(c: Circle):
        z, r = c.z, c.r
        for cx in range(int((z.real - r) // _OVERLAP_CELL),
                        int((z.real + r) // _OVERLAP_CELL) + 1):
            for cy in range(int((z.imag - r) // _OVERLAP_CELL),
                            int((z.imag + r) // _OVERLAP_CELL) + 1):
                yield (cx, cy)

    def _oregister(c: Circle) -> None:
        for cell in _ocells(c):
            ogrid.setdefault(cell, []).append(c)

    def _overlaps(c: Circle) -> bool:
        # Drawn gasket circles all have positive curvature and are mutually
        # *externally* tangent or disjoint - never nested - so a simple
        # interior-distance test suffices: flag when the disks intersect by more
        # than the tangency tolerance.  (A "nested" exclusion would wrongly pass
        # near-duplicate circles, e.g. an other-side Soddy landing on a seed.)
        if not reject_overlaps:
            return False
        checked: set[int] = set()
        for cell in _ocells(c):
            for o in ogrid.get(cell, ()):
                if id(o) in checked:
                    continue
                checked.add(id(o))
                ov = (o.r + c.r) - abs(o.z - c.z)    # >0 means the disks intersect
                tol = 0.3 + 0.03 * min(o.r, c.r)     # tangency reads as ov ~ 0
                if ov > tol:
                    return True
        return False

    # The overlap grid holds only *drawn* circles.  Overlap blocks DRAWING a
    # circle, never EXPLORING its subtree: a child may intersect a neighbour yet
    # still bound curvilinear gaps (toward the other parents) that hold perfectly
    # valid, visible circles.  Pruning the subtree on overlap would drop those.
    def _draw(c: Circle) -> bool:
        if _overlaps(c):
            return False
        _oregister(c)
        out.append(c)
        return True

    # Seeds first (so feature tags survive).  In-clip seeds are drawn unless they
    # intersect one already drawn; out-of-clip seeds aren't drawn but still block
    # overlaps (they occupy space) and still seed the recursion.
    placed_seeds: list[Circle] = []
    for s in seeds:
        if s.k <= 0:
            continue
        if clip.contains_disk(s):
            if _draw(s):
                placed_seeds.append(s)
        elif not _overlaps(s):
            _oregister(s)
            placed_seeds.append(s)

    members = [outer, *placed_seeds] if outer is not None else list(placed_seeds)

    def recurse(c1: Circle, c2: Circle, c3: Circle, known: Circle, depth: int):
        if depth > max_depth:
            return
        child = soddy_reflect(known, c1, c2, c3)
        if child.k <= 0:                   # reflected back to an enclosing circle
            return
        if child.r < r_min:
            return
        # Recurse only while the circle is near/inside the clip; a circle fully
        # outside contributes no visible descendants either.
        inside = clip.contains_disk(child)
        if not inside and not _touches(child, clip):
            return
        child = Circle(k=child.k, w=child.w, depth=depth, parent=-1)
        # Each curvilinear gap inscribes a unique circle, so a child we've already
        # seen means this exact gap was reached by another path - its whole subtree
        # is identical and already explored.  Prune (prevents the 3x redundant
        # recursion that would otherwise blow up at small r_min).
        if _seen(child):
            return
        _register(child)                   # dedup (always, even if not drawn)
        if inside:                         # draw only disks fully inside the clip,
            _draw(child)                   # and only if they don't overlap a drawn one
        recurse(c1, c2, child, c3, depth + 1)
        recurse(c1, c3, child, c2, depth + 1)
        recurse(c2, c3, child, c1, depth + 1)

    def trio_tangent(a, b, c) -> bool:
        return (tangency_error(a, b) <= SEED_TANGENT_TOL
                and tangency_error(b, c) <= SEED_TANGENT_TOL
                and tangency_error(a, c) <= SEED_TANGENT_TOL)

    # Seed the recursion from every mutually tangent triple in the initial set.
    for a, b, c in combinations(members, 3):
        if not trio_tangent(a, b, c):
            continue
        inner, _ = descartes_pair(a, b, c)
        if inner.k <= 0:
            continue
        inner = Circle(k=inner.k, w=inner.w, depth=1)
        if not _seen(inner):
            _register(inner)
            if inner.r >= r_min and clip.contains_disk(inner):
                _draw(inner)               # drawn only if it doesn't overlap
        # Four triangles around the freshly created inner circle.
        recurse(a, b, inner, c, 2)
        recurse(a, c, inner, b, 2)
        recurse(b, c, inner, a, 2)
        recurse(a, b, c, inner, 2)        # the other lens, opposite `inner`

    return out


def _touches(c: Circle, clip: Rect) -> bool:
    """Loose test: does the disk overlap the clip rect at all?"""
    z, r = c.z, c.r
    nx = min(max(z.real, clip.x0), clip.x1)
    ny = min(max(z.imag, clip.y0), clip.y1)
    return abs(complex(nx, ny) - z) <= r


if __name__ == "__main__":
    # Smoke test: classic (-1,2,2,3) gasket, clipped to its bounding box.
    outer = Circle.from_center(0 + 0j, 1.0, inside=True)
    a = Circle.from_center(0.5 + 0j, 0.5)
    b = Circle.from_center(-0.5 + 0j, 0.5)
    clip = Rect(-1, -1, 1, 1)
    assert tangency_error(a, b) < 1e-9, "seed circles should be tangent"
    circles = pack([a, b], outer, clip, r_min=0.02, max_depth=20)
    print(f"packed {len(circles)} circles")
    print("radii range:", min(c.r for c in circles), "..", max(c.r for c in circles))
    assert all(clip.contains_disk(c) for c in circles)
    assert any(abs(c.k - 3.0) < 1e-6 for c in circles), "missing the k=3 circles"
    print("PACKING SMOKE TEST PASSED")
