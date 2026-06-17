"""Loading vpype custom pen configurations.

Sketches use this to populate colour choices and resolve a chosen pen name to a
hex colour. The TOML files are produced by ``tools/drawingbot_to_vpype.py`` from
DrawingBot presets (see the vpype cookbook, "Creating a custom pen
configuration") and are also directly usable by vpype's ``pens`` command.
"""
from __future__ import annotations

import pathlib
import tomllib
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Pen:
    name: str
    color: str
    width: str | None = None
    config: str = ""


def load_pen_config(path) -> Dict[str, List[Pen]]:
    """Parse one pen-config TOML into ``{config_name: [Pen, ...]}``."""
    data = tomllib.loads(pathlib.Path(path).read_text())
    out: Dict[str, List[Pen]] = {}
    for cfg_name, cfg in (data.get("pen_config") or {}).items():
        out[cfg_name] = [
            Pen(name=str(layer.get("name", layer.get("layer_id", ""))),
                color=str(layer.get("color", "black")),
                width=layer.get("pen_width"),
                config=cfg_name)
            for layer in cfg.get("layers", [])
        ]
    return out


def load_pens(directory) -> Dict[str, str]:
    """All pens across ``*.toml`` in ``directory`` as an ordered ``{name: color}``.

    On a name collision between configs the colliding entry is prefixed with
    ``'<config>: '`` so every key stays unique. Returns ``{}`` if the directory
    is missing.
    """
    directory = pathlib.Path(directory)
    result: Dict[str, str] = {}
    if not directory.is_dir():
        return result
    for toml_path in sorted(directory.glob("*.toml")):
        for pens in load_pen_config(toml_path).values():
            for pen in pens:
                key = pen.name
                if key in result and result[key] != pen.color:
                    key = f"{pen.config}: {pen.name}"
                result[key] = pen.color
    return result
