"""isometric — true 30° isometric rendering of integer-grid boxes for pen plots.

Renders collections of boxes (or unit voxels) with exact, plotter-correct hidden
surface removal and per-face penfill fills, returning the penfill Geometry IR::

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from penfill import FillSpec, draw_geometry
    from isometric import Box, render_boxes, face_type_resolver

    boxes = [Box(0, 0, 0, 1, 1, 3), Box(1, 0, 0, 1, 1, 1)]
    resolver = face_type_resolver({
        "top":   FillSpec("solid", 1),
        "left":  FillSpec("hatch", 2, dict(spacing=0.15, angle=45)),
        "right": FillSpec("hatch", 3, dict(spacing=0.15, angle=-45)),
    })
    draw_geometry(vsk, render_boxes(boxes, resolver, scale=1.0, outline_layer=4))

See :mod:`.projection` for why occlusion is an exact integer z-buffer.
"""
from __future__ import annotations

from .boxes import (Box, Cell, FaceKind, FillResolver, face_type_resolver,
                    render_boxes, render_voxels)
from .heightfield import Heightfield
from .projection import lattice_to_screen, project
from .scene import render_scene

__all__ = [
    "Box", "Cell", "FaceKind", "FillResolver",
    "face_type_resolver", "render_boxes", "render_voxels",
    "Heightfield", "render_scene",
    "project", "lattice_to_screen",
]
