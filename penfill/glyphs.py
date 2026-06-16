"""Glyph generators.

A glyph is described in its own local frame, centred on the origin, and returned
as a list of ``(points, closed)`` polylines.  ``size`` is the glyph's nominal
half-extent; ``angle`` (degrees) rotates it.  Placement and clipping happen
later — glyphs know nothing about the polygon they land in.

Ported and unified from the inline glyph code in modulo_multiplication_03.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from .geometry import Pt

GLYPH_TYPES = ["dash", "plus", "circle", "chevron", "sine", "sawtooth", "triangle_wave"]


def glyph(gtype: str, size: float, angle: float = 0.0, *,
          chevron_half: float = 60.0, wave_periods: float = 1.0,
          wave_amplitude: float | None = None,
          circle_segments: int = 24) -> List[Tuple[List[Pt], bool]]:
    """Return the local polylines for one glyph.

    ``chevron_half`` is the half opening angle in degrees; ``wave_*`` shape the
    sine/sawtooth/triangle glyphs; ``wave_amplitude`` defaults to ``size/2``.
    """
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)

    def R(x, y):
        return (x * ca - y * sa, x * sa + y * ca)

    s = size

    if gtype == "circle":
        # Rotation-invariant; angle ignored.
        return [([(s * math.cos(2 * math.pi * k / circle_segments),
                   s * math.sin(2 * math.pi * k / circle_segments))
                  for k in range(circle_segments)], True)]

    if gtype == "dash":
        return [([R(-s, 0.0), R(s, 0.0)], False)]

    if gtype == "plus":
        return [([R(-s, 0.0), R(s, 0.0)], False),
                ([R(0.0, -s), R(0.0, s)], False)]

    if gtype == "chevron":
        h = math.radians(chevron_half)
        arm = (-s * math.cos(h), s * math.sin(h))
        return [([R(0.0, 0.0), R(arm[0], arm[1])], False),
                ([R(0.0, 0.0), R(arm[0], -arm[1])], False)]

    if gtype in ("sine", "sawtooth", "triangle_wave"):
        amp = s * 0.5 if wave_amplitude is None else wave_amplitude
        length = wave_periods * s
        n = max(int(wave_periods * 16) + 1, 3)
        pts: List[Pt] = []
        for k in range(n):
            t = (k / (n - 1) - 0.5) * length
            phase = (t + length * 0.5) / s
            if gtype == "sine":
                tr = amp * math.sin(2 * math.pi * phase)
            elif gtype == "sawtooth":
                tr = amp * (2 * (phase % 1) - 1)
            else:  # triangle_wave
                p = phase % 1
                tr = amp * (1 - 4 * abs(p - 0.5))
            pts.append(R(t, tr))
        return [(pts, False)]

    raise ValueError(f"unknown glyph type: {gtype!r}")
