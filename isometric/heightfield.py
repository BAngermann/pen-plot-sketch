"""A perlin-style ground heightfield for the isometric renderer.

The surface is drawn as a smooth *sloped* mesh (one quad per fine grid cell at
the real corner heights), but its occlusion is resolved on the integer lattice
via a **terraced-column proxy**: each cell is treated as solid up to
``round(cell height)``.  That keeps structure↔terrain hidden-surface removal on
the same exact integer z-buffer as the voxels (see :mod:`.boxes`), accurate to
≤ ½ fine cell, while the drawn mesh stays smooth.

All coordinates are in *fine* integer units (the shared frame with subdivided
voxels); ``(ox, oy)`` offsets the field's origin within that frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Tuple

from .boxes import Box, FaceTask

Pt3 = Tuple[float, float, float]


@dataclass
class Heightfield:
    h: List[List[float]]          # vertex heights, shape (W+1) x (H+1), fine-z units
    ox: int = 0
    oy: int = 0
    _col: List[List[int]] = field(default=None, repr=False, compare=False)

    @property
    def W(self) -> int:
        return len(self.h) - 1

    @property
    def H(self) -> int:
        return len(self.h[0]) - 1

    def __post_init__(self):
        # Terraced proxy height per cell = round(mean of its 4 corner heights).
        w, h = self.W, self.H
        self._col = [[0] * h for _ in range(w)]
        for i in range(w):
            for j in range(h):
                m = (self.h[i][j] + self.h[i + 1][j]
                     + self.h[i][j + 1] + self.h[i + 1][j + 1]) / 4.0
                self._col[i][j] = max(0, round(m))

    @classmethod
    def from_noise(cls, W: int, H: int, noise_fn: Callable[[float, float], float],
                   amplitude: float, base: float = 0.0, ox: int = 0, oy: int = 0) -> "Heightfield":
        """Sample ``noise_fn(x, y)`` (~[0,1]) on the (W+1)x(H+1) vertex grid."""
        h = [[base + amplitude * noise_fn(i, j) for j in range(H + 1)]
             for i in range(W + 1)]
        return cls(h, ox, oy)

    def terr_int(self, i: int, j: int) -> int:
        """Terraced proxy height of cell (i, j) (solid for z < terr_int)."""
        return self._col[i][j]

    def occupied(self, x: int, y: int, z: int) -> bool:
        """Terraced-proxy solidity at fine world coords — for the shadow march."""
        i, j = x - self.ox, y - self.oy
        if 0 <= i < self.W and 0 <= j < self.H:
            return z < self._col[i][j]
        return False

    def sloped_quad(self, i: int, j: int) -> List[Pt3]:
        """The cell's real (sloped) top corners in ring order, world coords."""
        ox, oy = self.ox, self.oy
        return [(ox + i, oy + j, self.h[i][j]),
                (ox + i + 1, oy + j, self.h[i + 1][j]),
                (ox + i + 1, oy + j + 1, self.h[i + 1][j + 1]),
                (ox + i, oy + j + 1, self.h[i][j + 1])]

    def terraced_faces(self) -> Iterable[FaceTask]:
        """Unit FaceTasks of the terraced proxy for the z-buffer.

        Emits each column's top plus the visible (+x/+y) step walls down to the
        next-lower neighbour (or to the base 0 at the field edge).  gids are
        tagged ``"GT"`` (ground top) / ``"GW"`` (ground wall) so the scene
        reconstruction can tell terrain from structure.
        """
        ox, oy, w, h, col = self.ox, self.oy, self.W, self.H, self._col
        for i in range(w):
            for j in range(h):
                H = col[i][j]
                x0, y0 = ox + i, oy + j
                # top of the column
                box = Box(x0, y0, 0, 1, 1, H, key=(i, j))
                yield ("GT", i, j), box, "top", [
                    (x0, y0, H), (x0 + 1, y0, H),
                    (x0 + 1, y0 + 1, H), (x0, y0 + 1, H)]
                # right (+x) step wall down to the lower neighbour / edge
                h2 = col[i + 1][j] if i + 1 < w else 0
                for z in range(h2, H):
                    yield ("GW", i, j, "right", z), box, "right", [
                        (x0 + 1, y0, z), (x0 + 1, y0 + 1, z),
                        (x0 + 1, y0 + 1, z + 1), (x0 + 1, y0, z + 1)]
                # left (+y) step wall
                h3 = col[i][j + 1] if j + 1 < h else 0
                for z in range(h3, H):
                    yield ("GW", i, j, "left", z), box, "left", [
                        (x0, y0 + 1, z), (x0 + 1, y0 + 1, z),
                        (x0 + 1, y0 + 1, z + 1), (x0, y0 + 1, z + 1)]
