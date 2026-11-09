# Implementation of Lindemayer systems

## Sketches

- `Lsys/` – general L-system sketch with full parameter set and configs.
- `ASFT/` – almost space-filling tree with the rules, angle, jitter and page fixed;
  only iterations, scales and the pen assignment (RGBK/CMYK, drawn with
  replacement) are exposed, so the randomiser makes many variants. Run with
  `vsk run ASFT`; page size is any ISO A size (default A4, landscape).
- `lsys_common/` – shared rewriting + turtle code (used by `ASFT`).
