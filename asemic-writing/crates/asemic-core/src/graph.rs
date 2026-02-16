use serde::{Deserialize, Serialize};
use std::f64::consts::PI;

/// Layout of the hex grid.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum HexLayout {
    /// 2-3-2 flat-top hex layout (3 columns: 2, 3, 2 hexes).
    Layout232,
}

/// Parameters needed to reconstruct the hex graph.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GraphParams {
    pub hex_size: f64,
    pub layout: HexLayout,
}

impl Default for GraphParams {
    fn default() -> Self {
        Self {
            hex_size: 10.0,
            layout: HexLayout::Layout232,
        }
    }
}

/// A vertex in the hex graph.
#[derive(Debug, Clone)]
pub struct Vertex {
    pub index: usize,
    pub pos: (f64, f64),
}

/// An edge in the hex graph, connecting two vertices.
#[derive(Debug, Clone)]
pub struct Edge {
    pub index: usize,
    pub v0: usize,
    pub v1: usize,
}

/// The complete hex graph: vertices, edges, entry/exit points, and adjacency.
#[derive(Debug, Clone)]
pub struct HexGraph {
    pub params: GraphParams,
    pub vertices: Vec<Vertex>,
    pub edges: Vec<Edge>,
    pub entry_vertex: usize,
    pub exit_vertex: usize,
    /// For each vertex, the list of incident edge indices.
    pub vertex_edges: Vec<Vec<usize>>,
    /// For each vertex, the list of adjacent vertex indices.
    pub vertex_neighbors: Vec<Vec<usize>>,
}

impl HexGraph {
    /// Build the hex graph from parameters.
    pub fn new(params: &GraphParams) -> Self {
        match params.layout {
            HexLayout::Layout232 => Self::build_232(params),
        }
    }

    /// Returns the other endpoint of an edge given one endpoint.
    pub fn other_vertex(&self, edge_idx: usize, vertex_idx: usize) -> usize {
        let e = &self.edges[edge_idx];
        if e.v0 == vertex_idx {
            e.v1
        } else {
            e.v0
        }
    }

    /// Returns the position of a vertex.
    pub fn vertex_pos(&self, idx: usize) -> (f64, f64) {
        self.vertices[idx].pos
    }

    /// Returns the midpoint of an edge.
    pub fn edge_midpoint(&self, edge_idx: usize) -> (f64, f64) {
        let e = &self.edges[edge_idx];
        let p0 = self.vertices[e.v0].pos;
        let p1 = self.vertices[e.v1].pos;
        ((p0.0 + p1.0) / 2.0, (p0.1 + p1.1) / 2.0)
    }

    /// Find the edge index connecting two vertices, if any.
    pub fn find_edge(&self, v0: usize, v1: usize) -> Option<usize> {
        self.vertex_edges[v0]
            .iter()
            .copied()
            .find(|&ei| {
                let e = &self.edges[ei];
                (e.v0 == v0 && e.v1 == v1) || (e.v0 == v1 && e.v1 == v0)
            })
    }

    fn build_232(params: &GraphParams) -> Self {
        let s = params.hex_size;
        let h = s * 3.0_f64.sqrt(); // height between parallel sides

        // Hex centers for the 2-3-2 layout.
        // Column 0 (2 hexes): centered at x=0
        // Column 1 (3 hexes): centered at x=1.5s, offset by h/2
        // Column 2 (2 hexes): centered at x=3s
        let hex_centers = vec![
            // Column 0
            (0.0, h / 2.0),
            (0.0, 3.0 * h / 2.0),
            // Column 1
            (1.5 * s, 0.0),
            (1.5 * s, h),
            (1.5 * s, 2.0 * h),
            // Column 2
            (3.0 * s, h / 2.0),
            (3.0 * s, 3.0 * h / 2.0),
        ];

        // Compute vertices for each hex, then deduplicate.
        let mut all_positions: Vec<(f64, f64)> = Vec::new();
        let mut hex_vertex_indices: Vec<[usize; 6]> = Vec::new();

        for &(cx, cy) in &hex_centers {
            let mut indices = [0usize; 6];
            for k in 0..6 {
                let angle = k as f64 * PI / 3.0;
                let vx = cx + s * angle.cos();
                let vy = cy + s * angle.sin();

                // Find existing vertex or create new one.
                let idx = match find_vertex(&all_positions, vx, vy, s * 1e-6) {
                    Some(i) => i,
                    None => {
                        let i = all_positions.len();
                        all_positions.push((vx, vy));
                        i
                    }
                };
                indices[k] = idx;
            }
            hex_vertex_indices.push(indices);
        }

        let vertices: Vec<Vertex> = all_positions
            .iter()
            .enumerate()
            .map(|(i, &pos)| Vertex { index: i, pos })
            .collect();

        // Compute edges from hex topology, deduplicating shared edges.
        let mut edge_set: Vec<(usize, usize)> = Vec::new();
        for hex_verts in &hex_vertex_indices {
            for k in 0..6 {
                let v0 = hex_verts[k];
                let v1 = hex_verts[(k + 1) % 6];
                let canonical = if v0 < v1 { (v0, v1) } else { (v1, v0) };
                if !edge_set.contains(&canonical) {
                    edge_set.push(canonical);
                }
            }
        }

        let edges: Vec<Edge> = edge_set
            .iter()
            .enumerate()
            .map(|(i, &(v0, v1))| Edge {
                index: i,
                v0,
                v1,
            })
            .collect();

        // Build adjacency: vertex → edges and vertex → neighbors.
        let n_verts = vertices.len();
        let mut vertex_edges: Vec<Vec<usize>> = vec![Vec::new(); n_verts];
        let mut vertex_neighbors: Vec<Vec<usize>> = vec![Vec::new(); n_verts];

        for (ei, e) in edges.iter().enumerate() {
            vertex_edges[e.v0].push(ei);
            vertex_edges[e.v1].push(ei);
            vertex_neighbors[e.v0].push(e.v1);
            vertex_neighbors[e.v1].push(e.v0);
        }

        // Find entry and exit vertices: leftmost and rightmost at the vertical midline.
        // The midline is at y = h (center of the layout's vertical span).
        let midline_y = h;
        let eps = s * 1e-6;

        let mut entry_vertex = 0;
        let mut entry_x = f64::MAX;
        let mut exit_vertex = 0;
        let mut exit_x = f64::MIN;

        for v in &vertices {
            if (v.pos.1 - midline_y).abs() < eps {
                if v.pos.0 < entry_x {
                    entry_x = v.pos.0;
                    entry_vertex = v.index;
                }
                if v.pos.0 > exit_x {
                    exit_x = v.pos.0;
                    exit_vertex = v.index;
                }
            }
        }

        HexGraph {
            params: params.clone(),
            vertices,
            edges,
            entry_vertex,
            exit_vertex,
            vertex_edges,
            vertex_neighbors,
        }
    }

    /// Returns the bounding box of the graph as (min_x, min_y, max_x, max_y).
    pub fn bounding_box(&self) -> (f64, f64, f64, f64) {
        let mut min_x = f64::MAX;
        let mut min_y = f64::MAX;
        let mut max_x = f64::MIN;
        let mut max_y = f64::MIN;
        for v in &self.vertices {
            min_x = min_x.min(v.pos.0);
            min_y = min_y.min(v.pos.1);
            max_x = max_x.max(v.pos.0);
            max_y = max_y.max(v.pos.1);
        }
        (min_x, min_y, max_x, max_y)
    }

    /// Returns vertex indices at the two leftmost and two rightmost x-coordinate columns.
    /// This covers both the absolute boundary (hex tips) and the entry/exit columns.
    pub fn boundary_vertices(&self) -> Vec<usize> {
        let entry_x = self.vertices[self.entry_vertex].pos.0;
        let exit_x = self.vertices[self.exit_vertex].pos.0;
        let bb = self.bounding_box();
        let eps = self.params.hex_size * 1e-6;
        self.vertices
            .iter()
            .filter(|v| {
                (v.pos.0 - bb.0).abs() < eps
                    || (v.pos.0 - bb.2).abs() < eps
                    || (v.pos.0 - entry_x).abs() < eps
                    || (v.pos.0 - exit_x).abs() < eps
            })
            .map(|v| v.index)
            .collect()
    }

    /// Total width of the graph.
    pub fn width(&self) -> f64 {
        let bb = self.bounding_box();
        bb.2 - bb.0
    }

    /// Total height of the graph.
    pub fn height(&self) -> f64 {
        let bb = self.bounding_box();
        bb.3 - bb.1
    }
}

/// Find a vertex by position within epsilon tolerance.
fn find_vertex(positions: &[(f64, f64)], x: f64, y: f64, eps: f64) -> Option<usize> {
    positions.iter().position(|&(px, py)| {
        let dx = px - x;
        let dy = py - y;
        dx * dx + dy * dy < eps * eps
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn default_graph() -> HexGraph {
        HexGraph::new(&GraphParams::default())
    }

    #[test]
    fn test_vertex_count() {
        let g = default_graph();
        assert_eq!(g.vertices.len(), 24, "2-3-2 layout should have 24 unique vertices");
    }

    #[test]
    fn test_edge_count() {
        let g = default_graph();
        assert_eq!(g.edges.len(), 30, "2-3-2 layout should have 30 unique edges");
    }

    #[test]
    fn test_entry_exit_vertices_exist() {
        let g = default_graph();
        assert!(g.entry_vertex < g.vertices.len());
        assert!(g.exit_vertex < g.vertices.len());
        assert_ne!(g.entry_vertex, g.exit_vertex);
    }

    #[test]
    fn test_entry_is_leftmost_at_midline() {
        let g = default_graph();
        let s = g.params.hex_size;
        let h = s * 3.0_f64.sqrt();
        let entry_pos = g.vertex_pos(g.entry_vertex);
        let eps = s * 1e-4;

        // Entry should be at (-s/2, h)
        assert!((entry_pos.0 - (-s / 2.0)).abs() < eps, "entry x");
        assert!((entry_pos.1 - h).abs() < eps, "entry y");
    }

    #[test]
    fn test_exit_is_rightmost_at_midline() {
        let g = default_graph();
        let s = g.params.hex_size;
        let h = s * 3.0_f64.sqrt();
        let exit_pos = g.vertex_pos(g.exit_vertex);
        let eps = s * 1e-4;

        // Exit should be at (3.5s, h)
        assert!((exit_pos.0 - 3.5 * s).abs() < eps, "exit x");
        assert!((exit_pos.1 - h).abs() < eps, "exit y");
    }

    #[test]
    fn test_all_edges_connect_valid_vertices() {
        let g = default_graph();
        for e in &g.edges {
            assert!(e.v0 < g.vertices.len(), "edge v0 out of range");
            assert!(e.v1 < g.vertices.len(), "edge v1 out of range");
            assert_ne!(e.v0, e.v1, "self-loop");
        }
    }

    #[test]
    fn test_all_vertex_positions_distinct() {
        let g = default_graph();
        let eps = g.params.hex_size * 1e-6;
        for i in 0..g.vertices.len() {
            for j in (i + 1)..g.vertices.len() {
                let (x1, y1) = g.vertices[i].pos;
                let (x2, y2) = g.vertices[j].pos;
                let dist_sq = (x1 - x2) * (x1 - x2) + (y1 - y2) * (y1 - y2);
                assert!(
                    dist_sq > eps * eps,
                    "vertices {} and {} are too close: ({}, {}) vs ({}, {})",
                    i, j, x1, y1, x2, y2
                );
            }
        }
    }

    #[test]
    fn test_adjacency_consistency() {
        let g = default_graph();

        // Each edge should appear in both endpoints' adjacency lists.
        for (ei, e) in g.edges.iter().enumerate() {
            assert!(
                g.vertex_edges[e.v0].contains(&ei),
                "edge {} not in vertex {} adjacency",
                ei, e.v0
            );
            assert!(
                g.vertex_edges[e.v1].contains(&ei),
                "edge {} not in vertex {} adjacency",
                ei, e.v1
            );
        }

        // Each vertex's neighbor list should match its edge list.
        for vi in 0..g.vertices.len() {
            assert_eq!(
                g.vertex_edges[vi].len(),
                g.vertex_neighbors[vi].len(),
                "vertex {} edge/neighbor count mismatch",
                vi
            );
        }
    }

    #[test]
    fn test_euler_formula() {
        let g = default_graph();
        // V - E + F = 2 for planar graph. F = 7 hex faces + 1 outer = 8.
        let v = g.vertices.len() as i64;
        let e = g.edges.len() as i64;
        let f = 8_i64; // 7 hexagons + outer face
        assert_eq!(v - e + f, 2, "Euler's formula: V={} E={} F={}", v, e, f);
    }

    #[test]
    fn test_different_hex_sizes() {
        for &size in &[1.0, 5.0, 20.0, 100.0] {
            let params = GraphParams {
                hex_size: size,
                layout: HexLayout::Layout232,
            };
            let g = HexGraph::new(&params);
            assert_eq!(g.vertices.len(), 24);
            assert_eq!(g.edges.len(), 30);
        }
    }

    #[test]
    fn test_find_edge() {
        let g = default_graph();
        // Entry and exit vertices should have edges.
        assert!(!g.vertex_edges[g.entry_vertex].is_empty());
        assert!(!g.vertex_edges[g.exit_vertex].is_empty());

        // find_edge should find edges that exist.
        for e in &g.edges {
            assert_eq!(g.find_edge(e.v0, e.v1), Some(e.index));
            assert_eq!(g.find_edge(e.v1, e.v0), Some(e.index));
        }
    }

    #[test]
    fn test_other_vertex() {
        let g = default_graph();
        for e in &g.edges {
            assert_eq!(g.other_vertex(e.index, e.v0), e.v1);
            assert_eq!(g.other_vertex(e.index, e.v1), e.v0);
        }
    }
}
