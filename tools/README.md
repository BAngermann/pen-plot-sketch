# tools

Standalone utilities for the plotter repo.

## drawingbot_to_vpype.py

Convert a [DrawingBot 3.0](https://drawingbotv3.com/) pen preset (JSON export)
into a [vpype custom pen configuration](https://vpype.readthedocs.io/en/latest/cookbook.html#creating-a-custom-pen-configuration)
(TOML). The resulting config is consumed by the sketches via
[`penfill.load_pens`](../penfill/) and is also usable directly by vpype's `pens`
command.

```sh
python tools/drawingbot_to_vpype.py Emott.json                 # -> pens/Emott.toml
python tools/drawingbot_to_vpype.py Emott.json -o pens/Emott.toml --name Emott
```

### Colour conversion

DrawingBot stores each pen's colour as a signed 32-bit `argb` integer (alpha in
the high byte). For opaque pens (alpha `0xFF`) the RGB value is recovered by
adding `256**3` — equivalently masking the low 24 bits:

```
rgb = argb + 256**3      # 0xFFRRGGBB (signed) -> 0xRRGGBB
```

`strokeSize` is carried over as the pen width (in mm). Only enabled
`drawing_pen` presets are emitted, in file order, as layers `1..N`.

Requires only the standard library (`json`, `tomllib`-free output is
hand-written). Run with any Python 3.11+.
