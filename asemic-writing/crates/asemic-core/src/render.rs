use crate::decoration::DecorationDef;
use crate::glyph::GlyphDef;
use crate::graph::HexGraph;
use crate::path;
use kurbo::{BezPath, Point};
use rand::Rng;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// How to convert vertex sequences into curves.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub enum CurveMode {
    /// Catmull-Rom interpolating spline (curve passes through each vertex).
    #[default]
    CatmullRom,
    /// Clamped cubic B-spline (curve approximates interior vertices, "loose" look).
    BSpline,
}

/// Parameters controlling how glyphs are rendered as BezPaths.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RenderingParams {
    /// Which spline type to use.
    #[serde(default)]
    pub curve_mode: CurveMode,
    /// How closely the BezPath follows the hex graph vertices (0.0 = smooth, 1.0 = polygonal).
    /// Only used in CatmullRom mode.
    pub tightness: f64,
    /// Maximum random offset per vertex, in units of hex edge length.
    pub vertex_jitter: f64,
    /// Additional random offset applied to BezPath control points.
    pub control_point_jitter: f64,
}

impl Default for RenderingParams {
    fn default() -> Self {
        Self {
            curve_mode: CurveMode::default(),
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
    // Entry and exit vertices are pinned (no jitter) for clean word composition.
    let mut jitter_map = compute_vertex_jitter_map(
        &all_vertex_indices,
        params.vertex_jitter,
        graph.params.hex_size,
        rng,
    );
    jitter_map.insert(graph.entry_vertex, (0.0, 0.0));
    jitter_map.insert(graph.exit_vertex, (0.0, 0.0));

    let main_path = {
        let jittered = apply_jitter_from_map(graph, &main_vertices, &jitter_map);
        points_to_bezpath(&jittered, params, rng)
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
    let mut jitter_map = compute_vertex_jitter_map(
        &vertices,
        params.vertex_jitter,
        graph.params.hex_size,
        rng,
    );
    jitter_map.insert(graph.entry_vertex, (0.0, 0.0));
    jitter_map.insert(graph.exit_vertex, (0.0, 0.0));
    let jittered = apply_jitter_from_map(graph, &vertices, &jitter_map);
    points_to_bezpath(&jittered, params, rng)
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

    points_to_bezpath(&positions, params, rng)
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

/// Dispatch to the appropriate spline converter based on curve mode.
fn points_to_bezpath(
    points: &[(f64, f64)],
    params: &RenderingParams,
    rng: &mut impl Rng,
) -> BezPath {
    match params.curve_mode {
        CurveMode::CatmullRom => {
            catmull_rom_to_bezpath(points, params.tightness, params.control_point_jitter, rng)
        }
        CurveMode::BSpline => bspline_to_bezpath(points, params.control_point_jitter, rng),
    }
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

/// Convert a sequence of points to a BezPath using a clamped uniform cubic B-spline.
///
/// The curve passes through the first and last points exactly, but only
/// approximates the interior points — producing a "loose" appearance.
/// C2 (curvature) continuity is guaranteed at all interior joins.
///
/// Conversion to Bézier segments uses Boehm's knot insertion algorithm
/// to raise every interior knot to multiplicity 3.
fn bspline_to_bezpath(
    points: &[(f64, f64)],
    cp_jitter: f64,
    rng: &mut impl Rng,
) -> BezPath {
    let mut path = BezPath::new();
    let n = points.len();

    if n == 0 {
        return path;
    }
    if n == 1 {
        path.move_to(Point::new(points[0].0, points[0].1));
        return path;
    }
    if n == 2 {
        path.move_to(Point::new(points[0].0, points[0].1));
        path.line_to(Point::new(points[1].0, points[1].1));
        return path;
    }
    if n == 3 {
        // Promote to cubic: treat the 3 points as a quadratic Bézier,
        // then degree-elevate to cubic so the curve passes through endpoints.
        let (p0, p1, p2) = (points[0], points[1], points[2]);
        path.move_to(Point::new(p0.0, p0.1));
        let cp1 = (
            p0.0 + 2.0 / 3.0 * (p1.0 - p0.0) + jitter(cp_jitter, rng),
            p0.1 + 2.0 / 3.0 * (p1.1 - p0.1) + jitter(cp_jitter, rng),
        );
        let cp2 = (
            p2.0 + 2.0 / 3.0 * (p1.0 - p2.0) + jitter(cp_jitter, rng),
            p2.1 + 2.0 / 3.0 * (p1.1 - p2.1) + jitter(cp_jitter, rng),
        );
        path.curve_to(
            Point::new(cp1.0, cp1.1),
            Point::new(cp2.0, cp2.1),
            Point::new(p2.0, p2.1),
        );
        return path;
    }

    // n >= 4: clamped uniform cubic B-spline.
    // Build knot vector: [0,0,0,0, 1, 2, ..., n-4, n-3, n-3, n-3, n-3]
    let max_t = (n as f64) - 3.0;
    let mut knots: Vec<f64> = Vec::new();
    for _ in 0..4 {
        knots.push(0.0);
    }
    for i in 1..=(n - 4) {
        knots.push(i as f64);
    }
    for _ in 0..4 {
        knots.push(max_t);
    }

    let mut cps: Vec<(f64, f64)> = points.to_vec();

    // Insert each interior knot twice to raise its multiplicity from 1 to 3.
    for knot_val in 1..=(n - 4) {
        let t = knot_val as f64;
        boehm_insert_knot(&mut cps, &mut knots, t);
        boehm_insert_knot(&mut cps, &mut knots, t);
    }

    // After full insertion, every interior knot has multiplicity 3.
    // The control points form Bézier segments: groups of 4 sharing endpoints.
    let num_segments = (cps.len() - 1) / 3;
    path.move_to(Point::new(cps[0].0, cps[0].1));

    for seg in 0..num_segments {
        let base = seg * 3;
        let b1 = cps[base + 1];
        let b2 = cps[base + 2];
        let b3 = cps[base + 3];
        path.curve_to(
            Point::new(b1.0 + jitter(cp_jitter, rng), b1.1 + jitter(cp_jitter, rng)),
            Point::new(b2.0 + jitter(cp_jitter, rng), b2.1 + jitter(cp_jitter, rng)),
            Point::new(b3.0, b3.1),
        );
    }

    path
}

/// Boehm's knot insertion: insert `t_new` into the B-spline once.
fn boehm_insert_knot(cps: &mut Vec<(f64, f64)>, knots: &mut Vec<f64>, t_new: f64) {
    let degree = 3usize;

    // Find span k: knots[k] <= t_new < knots[k+1].
    let k = {
        let mut k = 0;
        for i in 0..knots.len() - 1 {
            if knots[i] <= t_new && knots[i + 1] > t_new {
                k = i;
                break;
            }
        }
        k
    };

    let old_n = cps.len();
    let mut new_cps = Vec::with_capacity(old_n + 1);

    for i in 0..=old_n {
        if i <= k.saturating_sub(degree) {
            // Before affected range: copy directly.
            new_cps.push(cps[i]);
        } else if i > k {
            // After affected range: shift by one.
            new_cps.push(cps[i - 1]);
        } else {
            // In the affected range: linear interpolation.
            let denom = knots[i + degree] - knots[i];
            let alpha = if denom.abs() < 1e-12 {
                0.0
            } else {
                (t_new - knots[i]) / denom
            };
            let prev = cps[i - 1];
            let curr = cps[i];
            new_cps.push((
                (1.0 - alpha) * prev.0 + alpha * curr.0,
                (1.0 - alpha) * prev.1 + alpha * curr.1,
            ));
        }
    }

    // Insert knot value into the knot vector.
    knots.insert(k + 1, t_new);
    *cps = new_cps;
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
            ..PathConstraints::default()
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
            ..PathConstraints::default()
        };
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let edge_path = crate::path::generate_path(&g, &c, &mut rng).expect("path");

        let params = RenderingParams {
            tightness: 1.0,
            vertex_jitter: 0.0,
            control_point_jitter: 0.0,
            ..RenderingParams::default()
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
    fn test_bspline_4_points_is_single_bezier() {
        // A clamped cubic B-spline with exactly 4 control points is a single cubic Bézier.
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let points = vec![(0.0, 0.0), (1.0, 2.0), (3.0, 3.0), (4.0, 0.0)];
        let path = bspline_to_bezpath(&points, 0.0, &mut rng);

        let elems = path.elements();
        // Should be: MoveTo + 1 CurveTo = 2 elements.
        assert_eq!(elems.len(), 2, "4-point B-spline should be 1 Bézier segment");
        assert!(matches!(elems[0], kurbo::PathEl::MoveTo(_)));
        assert!(matches!(elems[1], kurbo::PathEl::CurveTo(_, _, _)));

        // The Bézier control points should match the B-spline control points exactly.
        if let kurbo::PathEl::MoveTo(p0) = elems[0] {
            assert!((p0.x - 0.0).abs() < 1e-10 && (p0.y - 0.0).abs() < 1e-10);
        }
        if let kurbo::PathEl::CurveTo(b1, b2, b3) = elems[1] {
            assert!((b1.x - 1.0).abs() < 1e-10 && (b1.y - 2.0).abs() < 1e-10);
            assert!((b2.x - 3.0).abs() < 1e-10 && (b2.y - 3.0).abs() < 1e-10);
            assert!((b3.x - 4.0).abs() < 1e-10 && (b3.y - 0.0).abs() < 1e-10);
        }
    }

    #[test]
    fn test_bspline_passes_through_endpoints() {
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let points = vec![
            (0.0, 0.0),
            (1.0, 3.0),
            (2.0, 1.0),
            (3.0, 4.0),
            (4.0, 2.0),
            (5.0, 0.0),
        ];
        let path = bspline_to_bezpath(&points, 0.0, &mut rng);
        let elems = path.elements();

        // First element is MoveTo at the first point.
        if let kurbo::PathEl::MoveTo(p) = elems[0] {
            assert!((p.x - 0.0).abs() < 1e-10, "start x");
            assert!((p.y - 0.0).abs() < 1e-10, "start y");
        } else {
            panic!("expected MoveTo");
        }

        // Last CurveTo ends at the last point.
        if let kurbo::PathEl::CurveTo(_, _, p) = elems[elems.len() - 1] {
            assert!((p.x - 5.0).abs() < 1e-10, "end x");
            assert!((p.y - 0.0).abs() < 1e-10, "end y");
        } else {
            panic!("expected CurveTo");
        }
    }

    #[test]
    fn test_bspline_deterministic() {
        let points = vec![
            (0.0, 0.0),
            (1.0, 2.0),
            (2.0, 1.0),
            (3.0, 3.0),
            (4.0, 0.0),
        ];
        let path1 = {
            let mut rng = ChaCha8Rng::seed_from_u64(99);
            bspline_to_bezpath(&points, 0.0, &mut rng)
        };
        let path2 = {
            let mut rng = ChaCha8Rng::seed_from_u64(99);
            bspline_to_bezpath(&points, 0.0, &mut rng)
        };
        let e1: Vec<_> = path1.elements().to_vec();
        let e2: Vec<_> = path2.elements().to_vec();
        assert_eq!(e1.len(), e2.len());
    }

    #[test]
    fn test_bspline_render_glyph() {
        // Full pipeline test with B-spline mode.
        let (g, glyph) = make_test_glyph();
        let params = RenderingParams {
            curve_mode: CurveMode::BSpline,
            ..RenderingParams::default()
        };
        let mut rng = ChaCha8Rng::seed_from_u64(99);

        let rendered = render_glyph(&g, &glyph, &params, &mut rng);
        assert!(!rendered.main_path.elements().is_empty());

        // No NaN values.
        for el in rendered.main_path.elements() {
            match el {
                kurbo::PathEl::MoveTo(p) => {
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
