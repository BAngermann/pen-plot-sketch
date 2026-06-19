"""True 30° isometric projection and its integer triangular lattice.

A 3D point ``(x, y, z)`` projects to the screen with::

    sx = (x - y) * C
    sy = (x + y) * S - z          # screen y grows downward; larger z -> higher up

where ``C = cos 30°`` and ``S = sin 30°``.  The three screen edge directions are
``u_x = (C, S)``, ``u_y = (-C, S)``, ``u_z = (0, -1)`` and satisfy
``u_z = -(u_x + u_y)``.  Substituting, a point lands at::

    screen = (x - z) * u_x + (y - z) * u_y

so every integer voxel corner has *integer* lattice coordinates
``(a, b) = (x - z, y - z)`` — the view direction ``(1, 1, 1)`` (the projection
kernel) collapses away.  All faces therefore tile one shared triangular lattice,
which is what makes hidden-surface removal an exact integer z-buffer (see
``boxes.py``).
"""
from __future__ import annotations

import math
from typing import Tuple

Pt = Tuple[float, float]

C = math.cos(math.radians(30.0))   # ≈ 0.8660254
S = math.sin(math.radians(30.0))   # = 0.5


def project(x: float, y: float, z: float, scale: float = 1.0) -> Pt:
    """Project a 3D point to the 2D screen (y grows downward)."""
    return ((x - y) * C * scale, ((x + y) * S - z) * scale)


def lattice_to_screen(a: int, b: int, scale: float = 1.0) -> Pt:
    """Screen position of triangular-lattice vertex ``(a, b)``.

    ``a*u_x + b*u_y = (C*(a - b), S*(a + b))``; independent of ``z`` because the
    lattice coordinate already absorbed it.
    """
    return (scale * C * (a - b), scale * S * (a + b))
