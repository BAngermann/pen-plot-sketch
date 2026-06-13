# Modulo Multiplication

Connects point `i` on a circle to point `(i × multiplier) mod n`, producing times-table / cardioid patterns.

## Parameters

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
| `draw_inverted` | False | Draw the image of each line/arc under inversion in the boundary circle. For chords this produces arcs through the origin; for hyperbolic arcs it produces the complementary arc on the same circle, which lies outside the boundary |

### Clipping (applies to inverted arcs)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `cutoff_r` | 4.5 | Half-height of the clip region (cm). Also the radius for circular clipping |
| `square_clip` | False | Clip to a rectangle instead of a circle |
| `clip_aspect_ratio` | 1.0 | Width-to-height ratio of the clip rectangle (`square_clip` only); half-width = `cutoff_r × clip_aspect_ratio` |
| `clip_box_offset_x` | 0.0 | Shift the clip rectangle centre horizontally (cm) |
| `clip_box_offset_y` | 0.0 | Shift the clip rectangle centre vertically (cm) |
| `show_clip_boundary` | False | Draw the clip circle or rectangle as a visible line |

### Page & layout
| Parameter | Default | Description |
|-----------|---------|-------------|
| `page_size` | "10cmx10cm" | Page size; accepts vpype format strings (`"a4"`, `"15cmx10cm"`, etc.) |
| `landscape` | False | Rotate page to landscape orientation |
| `offset_x` | 0.0 | Shift the entire drawing horizontally from the page centre (cm) |
| `offset_y` | 0.0 | Shift the entire drawing vertically from the page centre (cm) |

### Labels
| Parameter | Default | Description |
|-----------|---------|-------------|
| `show_circle` | True | Draw the boundary circle |
| `show_text` | True | Draw `n` and `multiplier` labels at the bottom corners of the clip region |
| `text_size` | 0.5 | Font size of the labels (cm) |
| `text_offset_x` | 0.0 | Nudge both labels inward from the clip corners (positive = toward centre) |
| `text_offset_y` | 0.0 | Shift both labels vertically from the clip bottom edge (cm) |

## Ideas to explore
- For multiple plots in one sketch, collect all multipliers that produce the same figure and plot them only once.
- For circles/Voronoi: scale each circle so it touches at least one other. Explore colouring Voronoi cells by number of intersecting lines or number of neighbours.
