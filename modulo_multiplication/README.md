# Modulo Multiplication

Each sketch in this folder visualises the same underlying structure: connect point `i` on a circle to point `(i × multiplier) mod n`. Varying `n` and `multiplier` produces cardioids, roses, and other envelope patterns familiar from times-table drawings.

The two sketches approach that structure from different directions:

- **`modulo_multiplication_01`** — a single multiplication table at high resolution. Fix `n` and `multiplier`, then explore the geometry deeply: straight chords, hyperbolic geodesics, circle inversion, clipping. Good for producing a finished piece from one particular table.
- **`modulo_multiplication_01_b`** — a generative multiples grid. Sweep ranges of `n` and `multiplier` simultaneously to see many tables at once and spot patterns across them (symmetries, duplicates, families of shapes).

---

## `modulo_multiplication_01` — single table, detailed view

### Geometry
| Parameter | Default | Description |
|-----------|---------|-------------|
| `r` | 4.0 | Radius of the boundary circle (cm) |
| `n` | 500 | Number of points equally spaced on the circle |
| `multiplier` | 8 | The multiplication factor; each point `i` connects to `(i × multiplier) mod n` |

### Drawing modes
| Parameter | Default | Description |
|-----------|---------|-------------|
| `hyperbolic` | False | Draw lines as hyperbolic geodesics (circular arcs orthogonal to the boundary circle) instead of straight chords |
| `draw_interior` | True | Draw the interior lines/arcs (inside the boundary circle) |
| `interior_i_start` | 0 | First index `i` to include in interior drawing (inclusive) |
| `interior_i_stop` | 0 | Last index `i` to include in interior drawing (exclusive); 0 = draw all up to `n` |
| `draw_inverted` | False | Draw the image of each line/arc under inversion in the boundary circle. For chords this produces arcs through the origin; for hyperbolic arcs it produces the complementary arc on the same circle, which lies outside the boundary |
| `exterior_i_start` | 0 | First index `i` to include in inverted/exterior drawing (inclusive) |
| `exterior_i_stop` | 0 | Last index `i` to include in inverted/exterior drawing (exclusive); 0 = draw all up to `n` |

### Clipping (applies to inverted arcs and exterior geometry)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `cutoff_r` | 4.5 | Half-height of the clip region (cm); also the radius for circular clipping |
| `square_clip` | False | Clip to a rectangle instead of a circle/ellipse |
| `clip_aspect_ratio` | 1.0 | Width-to-height ratio of the clip region; half-width = `cutoff_r × clip_aspect_ratio` |
| `clip_box_offset_x` | 0.0 | Shift the clip region centre horizontally (cm) |
| `clip_box_offset_y` | 0.0 | Shift the clip region centre vertically (cm) |
| `show_clip_boundary` | False | Draw the clip boundary (circle, ellipse, or rectangle) as a visible line |

### Page & layout
| Parameter | Default | Description |
|-----------|---------|-------------|
| `page_size` | "10cmx10cm" | Page size; accepts vpype format strings (`"a4"`, `"15cmx10cm"`, etc.) |
| `landscape` | False | Rotate page to landscape orientation |
| `offset_x` | 0.0 | Shift the entire drawing horizontally from the page centre (cm) |
| `offset_y` | 0.0 | Shift the entire drawing vertically from the page centre (cm) |
| `multipass` | True | Run vpype `multipass` in `finalize` to double every stroke (useful for pen plotters); disable to export single-pass lines |

### Labels
| Parameter | Default | Description |
|-----------|---------|-------------|
| `show_circle` | True | Draw the boundary circle |
| `show_text` | True | Draw `n` and `multiplier` labels at the bottom corners of the clip region |
| `text_size` | 0.5 | Font size of the labels (cm) |
| `text_offset_x` | 0.0 | Nudge both labels inward from the clip corners (positive = toward centre) |
| `text_offset_y` | 0.0 | Shift both labels vertically from the clip bottom edge (cm) |

---

## `modulo_multiplication_01_b` — comparison grid

Draws a grid of circles: rows correspond to values of `n`, columns to values of `multiplier`. Each cell shows the full multiplication table for that `(n, multiplier)` pair, making symmetries and duplicates immediately visible across the grid.

### Grid
| Parameter | Default | Description |
|-----------|---------|-------------|
| `r` | 1.0 | Radius of each circle in the grid (cm) |
| `n_min` | 2 | First value of `n` to draw (inclusive) |
| `n_max` | 8 | Last value of `n` to draw (inclusive) |
| `multiplier_min` | 0 | First multiplier column to draw (inclusive) |
| `multiplier_max` | −1 | Last multiplier column to draw (inclusive); −1 = use `n` for each row, i.e. show all multipliers 0 … n |

### Layout
| Parameter | Default | Description |
|-----------|---------|-------------|
| `page_margin_x` | 1.5 | Horizontal margin from the page edge to the grid (cm) |
| `page_margin_y` | 1.5 | Vertical margin from the page edge to the grid (cm) |
| `plot_margin_x` | 0.7 | Horizontal gap between circles (cm) |
| `plot_margin_y` | 0.7 | Vertical gap between circles (cm) |

### Labels
| Parameter | Default | Description |
|-----------|---------|-------------|
| `show_text` | True | Draw row labels (`n=…`) and column headers (multiplier values) |
| `text_scale` | 0.2 | Font size of the labels (cm) |

### Page
| Parameter | Default | Description |
|-----------|---------|-------------|
| `page_size` | "a4" | Page size; accepts vpype format strings (`"a4"`, `"a3"`, `"15cmx10cm"`, etc.) |
| `landscape` | False | Rotate page to landscape orientation |
| `show_guides` | False | Draw a centre-line guide that bisects the longer page dimension (or both axes for a square page); useful when plotting a large format in two passes on a smaller plotter |

---

---

## `modulo_multiplication_03` — Voronoi diagram of chord intersections

Computes every intersection point of the `n` chords, builds a Voronoi diagram seeded at those points, and draws the bounded cell edges. Each cell is labelled by how many chords pass through its seed point. Optionally fills cells with hatching patterns and overlays the original chords.

Intersection coordinates are computed with 25-digit precision (via `mpmath`) to avoid catastrophic cancellation in nearly-parallel chord pairs, which otherwise breaks symmetry in symmetric diagrams.

### Geometry
| Parameter | Default | Description |
|-----------|---------|-------------|
| `r` | 10.0 | Radius of the boundary circle (cm) |
| `n` | 96 | Number of points on the circle |
| `multiplier` | 41 | Each point `i` connects to `(i × multiplier) mod n` |
| `add_circle` | True | Add the `n` boundary points as extra Voronoi seeds; anchors all cells so they are bounded |

### Display
| Parameter | Default | Description |
|-----------|---------|-------------|
| `show_text` | True | Draw `n` and `multiplier` labels |
| `text_size` | 0.25 | Label font size (cm) |
| `text_offset_x/y` | 0.0 | Nudge label position |
| `show_chords` | False | Overlay the chords and boundary circle |
| `chords_on_top` | True | Draw chord overlay above the Voronoi (False = below) |

### Fill
| Parameter | Default | Description |
|-----------|---------|-------------|
| `fill_cells` | False | Fill Voronoi cells with hatching glyphs |
| `fill_by_neighbors` | False | Assign fill style by number of Voronoi neighbours instead of chord count |
| `fill_seed` | 42 | Random seed for per-cell style selection |
| `grid_global_origin` | True | All cells share one grid origin; False = each cell uses its own centroid |
| `grid_spacing` | 0.1 | Glyph grid spacing (cm) |
| `glyph_scale` | 0.03 | Glyph half-size (cm); also used as cell-boundary padding to include partial edge glyphs |
| `chevron_beta_a/b` | 1.0 | Beta-distribution shape parameters controlling chevron opening angle |
| `wave_periods` | 1.0 | Periods per cell for sine/sawtooth/triangle-wave glyphs |
| `wave_amplitude` | 0.06 | Amplitude of wave glyphs (cm) |

### Page & layout
| Parameter | Default | Description |
|-----------|---------|-------------|
| `page_size` | "25cmx25cm" | Page size |
| `landscape` | False | Landscape orientation |
| `offset_x/y` | 0.0 | Shift the diagram from page centre (cm) |

### Layer structure
The sketch assigns one layer per unique chord-count value. Fill layers are numbered starting from 2 (one per distinct chord count); the Voronoi outline is always the top layer. When `show_chords` is enabled, chord lines occupy an additional layer either below the fills or above the outline.

### Dependencies
`mpmath` is required for full precision. Install with:
```
pipx runpip vsketch install mpmath
```
Without it the sketch falls back to float64 arithmetic and may produce asymmetric results for symmetric `(n, multiplier)` pairs.
