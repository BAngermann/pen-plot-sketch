use crate::decoration::DecorationDef;
use crate::graph::HexGraph;
use crate::path;
use crate::properties::{GlyphProperties, HasProperties};
use crate::render::RenderingParams;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

/// A glyph definition stored in the library.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GlyphDef {
    /// Unique identifier within the library.
    pub id: String,
    /// Main connecting path: ordered sequence of edge indices (entry -> exit).
    pub main_path: Vec<usize>,
    /// Decorations: branching strokes attached to the main path.
    pub decorations: Vec<DecorationDef>,
    /// Per-glyph rendering overrides (falls back to library defaults if None).
    pub rendering: Option<RenderingParams>,
    /// Pre-computed properties for the transition engine.
    pub properties: GlyphProperties,
}

impl HasProperties for GlyphDef {
    fn properties(&self) -> &GlyphProperties {
        &self.properties
    }
}

/// Compute glyph properties from a main path and decorations.
pub fn compute_properties(
    graph: &HexGraph,
    main_path: &[usize],
    decorations: &[DecorationDef],
) -> GlyphProperties {
    let vertices = path::path_to_vertices(graph, main_path);
    let unique_vertices: HashSet<usize> = vertices.iter().copied().collect();

    // Compute direction changes and total turning.
    let mut direction_changes = 0usize;
    let mut total_turning = 0.0f64;

    if vertices.len() >= 3 {
        for i in 1..vertices.len() - 1 {
            let p0 = graph.vertex_pos(vertices[i - 1]);
            let p1 = graph.vertex_pos(vertices[i]);
            let p2 = graph.vertex_pos(vertices[i + 1]);

            let dx1 = p1.0 - p0.0;
            let dy1 = p1.1 - p0.1;
            let dx2 = p2.0 - p1.0;
            let dy2 = p2.1 - p1.1;

            // Angle between consecutive edge directions.
            let angle = (dx1 * dy2 - dy1 * dx2).atan2(dx1 * dx2 + dy1 * dy2);
            let abs_angle = angle.abs();

            if abs_angle > 1e-6 {
                direction_changes += 1;
            }
            total_turning += abs_angle;
        }
    }

    // Bounding box of the path.
    let positions: Vec<(f64, f64)> = vertices.iter().map(|&vi| graph.vertex_pos(vi)).collect();
    let (min_x, min_y, max_x, max_y) = bounding_box(&positions);
    let bb_width = max_x - min_x;
    let bb_height = max_y - min_y;

    let aspect_ratio = if bb_height > 1e-10 {
        bb_width / bb_height
    } else {
        1.0
    };

    // Coverage: fraction of the graph bounding box area covered by the path bounding box.
    let graph_bb = graph.bounding_box();
    let graph_area = (graph_bb.2 - graph_bb.0) * (graph_bb.3 - graph_bb.1);
    let path_area = bb_width * bb_height;
    let coverage = if graph_area > 1e-10 {
        path_area / graph_area
    } else {
        0.0
    };

    // Decoration stats.
    let total_decoration_edges: usize = decorations.iter().map(|d| d.branch_edges.len()).sum();

    GlyphProperties {
        path_length: main_path.len(),
        vertex_count: unique_vertices.len(),
        direction_changes,
        total_turning,
        decoration_count: decorations.len(),
        total_decoration_edges,
        aspect_ratio,
        coverage,
    }
}

fn bounding_box(positions: &[(f64, f64)]) -> (f64, f64, f64, f64) {
    let mut min_x = f64::MAX;
    let mut min_y = f64::MAX;
    let mut max_x = f64::MIN;
    let mut max_y = f64::MIN;
    for &(x, y) in positions {
        min_x = min_x.min(x);
        min_y = min_y.min(y);
        max_x = max_x.max(x);
        max_y = max_y.max(y);
    }
    (min_x, min_y, max_x, max_y)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::decoration::{self, DecorationConstraints};
    use crate::graph::GraphParams;
    use crate::path::PathConstraints;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    fn make_glyph() -> (HexGraph, Vec<usize>, Vec<DecorationDef>) {
        let g = HexGraph::new(&GraphParams::default());
        let c = PathConstraints {
            min_path_length: 5,
            max_path_length: 15,
            max_edge_visits: 2,
            max_vertex_visits: 3,
            ..PathConstraints::default()
        };
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let main_path = path::generate_path(&g, &c, &mut rng).expect("should generate path");
        let dc = DecorationConstraints::default();
        let decorations = decoration::generate_decorations(&g, &main_path, &dc, &mut rng);
        (g, main_path, decorations)
    }

    #[test]
    fn test_path_length_matches() {
        let (g, main_path, decorations) = make_glyph();
        let props = compute_properties(&g, &main_path, &decorations);
        assert_eq!(props.path_length, main_path.len());
    }

    #[test]
    fn test_vertex_count_consistent() {
        let (g, main_path, decorations) = make_glyph();
        let props = compute_properties(&g, &main_path, &decorations);
        let verts: HashSet<usize> = path::path_to_vertices(&g, &main_path)
            .into_iter()
            .collect();
        assert_eq!(props.vertex_count, verts.len());
    }

    #[test]
    fn test_decoration_count_matches() {
        let (g, main_path, decorations) = make_glyph();
        let props = compute_properties(&g, &main_path, &decorations);
        assert_eq!(props.decoration_count, decorations.len());
    }

    #[test]
    fn test_total_decoration_edges() {
        let (g, main_path, decorations) = make_glyph();
        let props = compute_properties(&g, &main_path, &decorations);
        let expected: usize = decorations.iter().map(|d| d.branch_edges.len()).sum();
        assert_eq!(props.total_decoration_edges, expected);
    }

    #[test]
    fn test_aspect_ratio_positive() {
        let (g, main_path, decorations) = make_glyph();
        let props = compute_properties(&g, &main_path, &decorations);
        assert!(props.aspect_ratio > 0.0);
    }

    #[test]
    fn test_coverage_in_range() {
        let (g, main_path, decorations) = make_glyph();
        let props = compute_properties(&g, &main_path, &decorations);
        assert!(props.coverage >= 0.0 && props.coverage <= 1.0);
    }

    #[test]
    fn test_turning_non_negative() {
        let (g, main_path, decorations) = make_glyph();
        let props = compute_properties(&g, &main_path, &decorations);
        assert!(props.total_turning >= 0.0);
    }

    #[test]
    fn test_straight_path_no_turning() {
        // A path of length 1 has no turning.
        let g = HexGraph::new(&GraphParams::default());
        // Find any single edge from entry.
        if let Some(&ei) = g.vertex_edges[g.entry_vertex].first() {
            let props = compute_properties(&g, &[ei], &[]);
            assert_eq!(props.direction_changes, 0);
            assert!((props.total_turning - 0.0).abs() < 1e-10);
        }
    }
}
