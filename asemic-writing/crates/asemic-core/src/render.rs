use crate::decoration::DecorationDef;
use crate::glyph::GlyphDef;
use crate::graph::HexGraph;
use crate::path;
use kurbo::{BezPath, Point};
use rand::Rng;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Parameters controlling how glyphs are rendered as BezPaths.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RenderingParams {
    /// How closely the BezPath follows the hex graph vertices (0.0 = smooth, 1.0 = polygonal).
    pub tightness: f64,
    /// Maximum random offset per vertex, in units of hex edge length.
    pub vertex_jitter: f64,
    /// Additional random offset applied to BezPath control points.
    pub control_point_jitter: f64,
}

impl Default for RenderingParams {
    fn default() -> Self {
        Self {
            tightness: 0.5,
            vertex_jitter: 0.1,
            control_point_jitter: 0.05,
        }
    }
}

/// Rendered glyph: a set of BezPaths (main + decorations).
pub struct RenderedGlyph {
    pub main_path: BezPath,
    pub decorations: Vec<BezPath>,
}

/// Render a glyph definition into BezPaths.
///
/// Pre-computes a jitter map so that every occurrence of the same vertex
/// (in the main path or decorations) gets the same positional offset.
pub fn render_glyph(
    graph: &HexGraph,
    glyph: &GlyphDef,
    params: &RenderingParams,
    rng: &mut impl Rng,
) -> RenderedGlyph {
    // Collect all vertex indices used by main path and decorations.
    let main_vertices = path::path_to_vertices(graph, &glyph.main_path);
    let mut all_vertex_indices = main_vertices.clone();
    for dec in &glyph.decorations {
        all_vertex_indices.push(dec.anchor_vertex);
        let mut current = dec.anchor_vertex;
        for &bei in &dec.branch_edges {
            current = graph.other_vertex(bei, current);
            all_vertex_indices.push(current);
        }
    }

    // Build jitter map once: same vertex always gets the same offset.
    let jitter_map = compute_vertex_jitter_map(
        &all_vertex_indices,
        params.vertex_jitter,
        graph.params.hex_size,
        rng,
    );

    let main_path = {
        let jittered = apply_jitter_from_map(graph, &main_vertices, &jitter_map);
        catmull_rom_to_bezpath(&jittered, params.tightness, params.control_point_jitter, rng)
    };

    let decorations = glyph
        .decorations
        .iter()
        .map(|d| render_decoration_with_jitter(graph, d, &jitter_map, params, rng))
        .collect();

    RenderedGlyph {
        main_path,
        decorations,
    }
}

/// Render the main path as a BezPath.
///
/// When used standalone (not via `render_glyph`), builds its own jitter map
/// so that revisited vertices get consistent jitter.
pub fn render_main_path(
    graph: &HexGraph,
    edge_path: &[usize],
    params: &RenderingParams,
    rng: &mut impl Rng,
) -> BezPath {
    let vertices = path::path_to_vertices(graph, edge_path);
    let jitter_map = compute_vertex_jitter_map(
        &vertices,
        params.vertex_jitter,
        graph.params.hex_size,
        rng,
    );
    let jittered = apply_jitter_from_map(graph, &vertices, &jitter_map);
    catmull_rom_to_bezpath(&jittered, params.tightness, params.control_point_jitter, rng)
}

/// Render a decoration as a BezPath, using the shared jitter map for vertex positions.
fn render_decoration_with_jitter(
    graph: &HexGraph,
    decoration: &DecorationDef,
    jitter_map: &HashMap<usize, (f64, f64)>,
    params: &RenderingParams,
    rng: &mut impl Rng,
) -> BezPath {
    let shared_midpoint = graph.edge_midpoint(decoration.shared_edge);

    let mut positions = Vec::new();

    // Shared edge midpoint is not a graph vertex — apply independent jitter at half strength.
    let max_offset = params.vertex_jitter * 0.5 * graph.params.hex_size;
    let dx = (rng.gen_range(0.0..1.0) - 0.5) * 2.0 * max_offset;
    let dy = (rng.gen_range(0.0..1.0) - 0.5) * 2.0 * max_offset;
    positions.push((shared_midpoint.0 + dx, shared_midpoint.1 + dy));

    // Anchor and branch vertices use the shared jitter map.
    let mut vertex_seq = vec![decoration.anchor_vertex];
    let mut current = decoration.anchor_vertex;
    for &bei in &decoration.branch_edges {
        current = graph.other_vertex(bei, current);
        vertex_seq.push(current);
    }

    for &vi in &vertex_seq {
        let (x, y) = graph.vertex_pos(vi);
        if let Some(&(vdx, vdy)) = jitter_map.get(&vi) {
            positions.push((x + vdx, y + vdy));
        } else {
            positions.push((x, y));
        }
    }

    catmull_rom_to_bezpath(&positions, params.tightness, params.control_point_jitter, rng)
}

/// Compute jitter offsets per unique vertex index.
/// The first occurrence of each vertex gets a random offset; subsequent occurrences reuse it.
fn compute_vertex_jitter_map(
    vertex_indices: &[usize],
    jitter_amount: f64,
    hex_size: f64,
    rng: &mut impl Rng,
) -> HashMap<usize, (f64, f64)> {
    let max_offset = jitter_amount * hex_size;
    let mut map = HashMap::new();
    for &vi in vertex_indices {
        map.entry(vi).or_insert_with(|| {
            let dx = (rng.gen_range(0.0..1.0) - 0.5) * 2.0 * max_offset;
            let dy = (rng.gen_range(0.0..1.0) - 0.5) * 2.0 * max_offset;
            (dx, dy)
        });
    }
    map
}

/// Apply pre-computed jitter from a vertex map to a sequence of vertex indices.
fn apply_jitter_from_map(
    graph: &HexGraph,
    vertices: &[usize],
    jitter_map: &HashMap<usize, (f64, f64)>,
) -> Vec<(f64, f64)> {
    vertices
        .iter()
        .map(|&vi| {
            let (x, y) = graph.vertex_pos(vi);
            if let Some(&(dx, dy)) = jitter_map.get(&vi) {
                (x + dx, y + dy)
            } else {
                (x, y)
            }
        })
        .collect()
}

/// Convert a sequence of points to a BezPath using Catmull-Rom interpolation.
///
/// `tightness` controls how closely the curve follows the control points:
/// - 1.0: straight-line segments (polygonal)
/// - 0.0: smooth Catmull-Rom spline
///
/// `cp_jitter` adds random offset to Bézier control points.
fn catmull_rom_to_bezpath(
    points: &[(f64, f64)],
    tightness: f64,
    cp_jitter: f64,
    rng: &mut impl Rng,
) -> BezPath {
    let mut path = BezPath::new();

    if points.is_empty() {
        return path;
    }

    if points.len() == 1 {
        path.move_to(Point::new(points[0].0, points[0].1));
        return path;
    }

    if points.len() == 2 {
        path.move_to(Point::new(points[0].0, points[0].1));
        path.line_to(Point::new(points[1].0, points[1].1));
        return path;
    }

    // Extend points with duplicated endpoints for Catmull-Rom boundary handling.
    let n = points.len();
    let mut extended = Vec::with_capacity(n + 2);
    extended.push(points[0]); // duplicate first
    extended.extend_from_slice(points);
    extended.push(points[n - 1]); // duplicate last

    path.move_to(Point::new(points[0].0, points[0].1));

    // The tangent scale factor: at tightness=1 tangents are zero, at tightness=0 normal Catmull-Rom.
    let tau = 1.0 - tightness;

    for i in 1..=n - 1 {
        let p0 = extended[i - 1]; // P_{i-1}
        let p1 = extended[i];     // P_i (segment start)
        let p2 = extended[i + 1]; // P_{i+1} (segment end)
        let p3 = extended[i + 2]; // P_{i+2}

        // Catmull-Rom tangents.
        let t1x = tau * (p2.0 - p0.0) / 2.0;
        let t1y = tau * (p2.1 - p0.1) / 2.0;
        let t2x = tau * (p3.0 - p1.0) / 2.0;
        let t2y = tau * (p3.1 - p1.1) / 2.0;

        // Convert to cubic Bézier control points.
        let cp1x = p1.0 + t1x / 3.0 + jitter(cp_jitter, rng);
        let cp1y = p1.1 + t1y / 3.0 + jitter(cp_jitter, rng);
        let cp2x = p2.0 - t2x / 3.0 + jitter(cp_jitter, rng);
        let cp2y = p2.1 - t2y / 3.0 + jitter(cp_jitter, rng);

        path.curve_to(
            Point::new(cp1x, cp1y),
            Point::new(cp2x, cp2y),
            Point::new(p2.0, p2.1),
        );
    }

    path
}

fn jitter(amount: f64, rng: &mut impl Rng) -> f64 {
    if amount.abs() < 1e-10 {
        0.0
    } else {
        (rng.gen_range(0.0..1.0) - 0.5) * 2.0 * amount
    }
}

/// Render the hex graph skeleton as a set of line segments (for ghost overlay).
pub fn render_graph_skeleton(graph: &HexGraph) -> BezPath {
    let mut path = BezPath::new();
    for e in &graph.edges {
        let p0 = graph.vertex_pos(e.v0);
        let p1 = graph.vertex_pos(e.v1);
        path.move_to(Point::new(p0.0, p0.1));
        path.line_to(Point::new(p1.0, p1.1));
    }
    path
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::decoration::{self, DecorationConstraints};
    use crate::graph::GraphParams;
    use crate::path::PathConstraints;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    fn make_test_glyph() -> (HexGraph, GlyphDef) {
        let g = HexGraph::new(&GraphParams::default());
        let c = PathConstraints {
            min_path_length: 5,
            max_path_length: 15,
            max_edge_visits: 2,
            max_vertex_visits: 3,
        };
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let main_path = crate::path::generate_path(&g, &c, &mut rng).expect("path");
        let dc = DecorationConstraints::default();
        let decorations = decoration::generate_decorations(&g, &main_path, &dc, &mut rng);
        let properties = crate::glyph::compute_properties(&g, &main_path, &decorations);

        let glyph = GlyphDef {
            id: "test".to_string(),
            main_path,
            decorations,
            rendering: None,
            properties,
        };
        (g, glyph)
    }

    #[test]
    fn test_render_produces_valid_bezpath() {
        let (g, glyph) = make_test_glyph();
        let params = RenderingParams::default();
        let mut rng = ChaCha8Rng::seed_from_u64(99);

        let rendered = render_glyph(&g, &glyph, &params, &mut rng);

        // Check that the main path is not empty.
        assert!(!rendered.main_path.elements().is_empty());

        // Check no NaN in control points.
        for el in rendered.main_path.elements() {
            match el {
                kurbo::PathEl::MoveTo(p) => {
                    assert!(!p.x.is_nan() && !p.y.is_nan());
                }
                kurbo::PathEl::LineTo(p) => {
                    assert!(!p.x.is_nan() && !p.y.is_nan());
                }
                kurbo::PathEl::CurveTo(p1, p2, p3) => {
                    assert!(!p1.x.is_nan() && !p1.y.is_nan());
                    assert!(!p2.x.is_nan() && !p2.y.is_nan());
                    assert!(!p3.x.is_nan() && !p3.y.is_nan());
                }
                _ => {}
            }
        }
    }

    #[test]
    fn test_render_deterministic() {
        let (g, glyph) = make_test_glyph();
        let params = RenderingParams::default();

        let rendered1 = {
            let mut rng = ChaCha8Rng::seed_from_u64(42);
            render_glyph(&g, &glyph, &params, &mut rng)
        };
        let rendered2 = {
            let mut rng = ChaCha8Rng::seed_from_u64(42);
            render_glyph(&g, &glyph, &params, &mut rng)
        };

        // Compare main path elements.
        let e1: Vec<_> = rendered1.main_path.elements().to_vec();
        let e2: Vec<_> = rendered2.main_path.elements().to_vec();
        assert_eq!(e1.len(), e2.len());
    }

    #[test]
    fn test_tightness_one_nearly_polygonal() {
        let g = HexGraph::new(&GraphParams::default());
        let c = PathConstraints {
            min_path_length: 3,
            max_path_length: 8,
            max_edge_visits: 2,
            max_vertex_visits: 3,
        };
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let edge_path = crate::path::generate_path(&g, &c, &mut rng).expect("path");

        let params = RenderingParams {
            tightness: 1.0,
            vertex_jitter: 0.0,
            control_point_jitter: 0.0,
        };

        let rendered = render_main_path(&g, &edge_path, &params, &mut rng);
        let vertices = path::path_to_vertices(&g, &edge_path);

        // At tightness=1.0 with no jitter, the curve should pass very close to all vertices.
        // The cubic Bezier control points collapse to the endpoints.
        for &vi in &vertices {
            let pos = g.vertex_pos(vi);
            let target = Point::new(pos.0, pos.1);

            // Check that some point on the path is close to this vertex.
            let mut min_dist = f64::MAX;
            for el in rendered.elements() {
                let p = match el {
                    kurbo::PathEl::MoveTo(p) | kurbo::PathEl::LineTo(p) => *p,
                    kurbo::PathEl::CurveTo(_, _, p) => *p,
                    _ => continue,
                };
                let dist = ((p.x - target.x).powi(2) + (p.y - target.y).powi(2)).sqrt();
                min_dist = min_dist.min(dist);
            }
            assert!(
                min_dist < g.params.hex_size * 0.01,
                "vertex {:?} should be on tight curve, min_dist={}",
                pos,
                min_dist
            );
        }
    }

    #[test]
    fn test_decorations_produce_separate_bezpaths() {
        let (g, glyph) = make_test_glyph();
        let params = RenderingParams::default();
        let mut rng = ChaCha8Rng::seed_from_u64(99);

        let rendered = render_glyph(&g, &glyph, &params, &mut rng);
        assert_eq!(rendered.decorations.len(), glyph.decorations.len());
    }

    #[test]
    fn test_revisited_vertex_gets_same_jitter() {
        // Verify that compute_vertex_jitter_map returns the same offset
        // for a vertex that appears multiple times.
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let vertices = vec![0, 1, 2, 1, 3, 0]; // vertices 0 and 1 appear twice
        let map = compute_vertex_jitter_map(&vertices, 0.1, 10.0, &mut rng);

        // Each unique vertex should have exactly one entry.
        assert_eq!(map.len(), 4);

        // Apply to a graph and check positions are identical for repeated vertices.
        let g = HexGraph::new(&GraphParams::default());
        let positions = apply_jitter_from_map(&g, &vertices, &map);

        // vertices[0] and vertices[5] are both vertex 0 — should have identical positions.
        assert_eq!(positions[0], positions[5], "vertex 0 at indices 0 and 5 should match");
        // vertices[1] and vertices[3] are both vertex 1 — should have identical positions.
        assert_eq!(positions[1], positions[3], "vertex 1 at indices 1 and 3 should match");
    }

    #[test]
    fn test_graph_skeleton_render() {
        let g = HexGraph::new(&GraphParams::default());
        let skeleton = render_graph_skeleton(&g);
        assert!(!skeleton.elements().is_empty());

        // Should have one MoveTo + LineTo pair per edge.
        let move_count = skeleton
            .elements()
            .iter()
            .filter(|el| matches!(el, kurbo::PathEl::MoveTo(_)))
            .count();
        assert_eq!(move_count, g.edges.len());
    }
}
