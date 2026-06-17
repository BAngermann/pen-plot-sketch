#!/usr/bin/env python3
"""Convert a DrawingBot 3.0 pen preset (JSON) into a vpype custom pen config (TOML).

DrawingBot stores each pen under ``jsonMap[].data`` with a signed 32-bit ``argb``
integer (alpha in the high byte). For opaque pens (alpha = 0xFF) the RGB value is
recovered by adding ``256**3`` — equivalently, masking the low 24 bits:

    rgb = argb + 256**3            # 0xFFRRGGBB (signed) -> 0xRRGGBB

The output is a vpype pen-config file (see the vpype cookbook, "Creating a custom
pen configuration"), usable both by this repo's sketches (``penfill.load_pens``)
and directly by vpype:

    vpype read in.svg pens <config_name> write out.svg

Usage:
    python tools/drawingbot_to_vpype.py Emott.json
    python tools/drawingbot_to_vpype.py Emott.json -o pens/Emott.toml --name Emott
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re


def argb_to_hex(argb: int) -> str:
    """DrawingBot signed ``argb`` -> ``'#rrggbb'`` (assumes opaque alpha = 0xFF)."""
    return f"#{(argb + 256 ** 3) & 0xFFFFFF:06x}"


def _toml_str(s: str) -> str:
    """Quote a string as a TOML basic string."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_key(s: str) -> str:
    """A TOML bare key if possible, else a quoted key."""
    return s if re.fullmatch(r"[A-Za-z0-9_-]+", s) else _toml_str(s)


def convert(data: dict) -> list[dict]:
    """Extract enabled drawing pens as ordered layer dicts."""
    pens = []
    layer_id = 1
    for entry in data.get("jsonMap", []):
        if entry.get("presetType") != "drawing_pen":
            continue
        d = entry.get("data", {})
        if d.get("isEnabled") is False or entry.get("enabled") is False:
            continue
        name = d.get("name") or entry.get("presetName") or f"pen{layer_id}"
        stroke = d.get("strokeSize", 0.3)
        pens.append({
            "layer_id": layer_id,
            "name": str(name),
            "color": argb_to_hex(int(d["argb"])),
            "pen_width": f"{stroke}mm",
        })
        layer_id += 1
    return pens


def to_toml(config_name: str, pens: list[dict]) -> str:
    lines = [f"[pen_config.{_toml_key(config_name)}]", "layers = ["]
    for p in pens:
        lines.append(
            f'    {{ layer_id = {p["layer_id"]}, name = {_toml_str(p["name"])}, '
            f'color = {_toml_str(p["color"])}, pen_width = {_toml_str(p["pen_width"])} }},'
        )
    lines.append("]")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=pathlib.Path, help="DrawingBot 3.0 preset JSON")
    ap.add_argument("-o", "--output", type=pathlib.Path,
                    help="output TOML (default: pens/<input stem>.toml)")
    ap.add_argument("--name", help="pen_config name (default: input stem)")
    args = ap.parse_args()

    data = json.loads(args.input.read_text())
    config_name = args.name or args.input.stem
    pens = convert(data)
    if not pens:
        raise SystemExit("no enabled drawing_pen presets found")

    out = args.output or (pathlib.Path("pens") / f"{args.input.stem}.toml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_toml(config_name, pens))
    print(f"wrote {len(pens)} pens to {out} (pen_config.{config_name})")


if __name__ == "__main__":
    main()
