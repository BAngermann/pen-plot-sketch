use crate::graph::HexGraph;
use rand::Rng;

/// Constraints for path generation.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct PathConstraints {
    pub min_path_length: usize,
    pub max_path_length: usize,
    /// How many times a single edge may be traversed (1 = no revisiting).
    pub max_edge_visits: usize,
    /// How many times a single vertex may be traversed.
    pub max_vertex_visits: usize,
    /// Probability [0.0, 1.0] that the walk may immediately reverse along the
    /// edge it just came from. 0.0 = never backtrack, 1.0 = always allow.
    #[serde(default)]
    pub backtrack_probability: f64,
}

impl Default for PathConstraints {
    fn default() -> Self {
        Self {
            min_path_length: 5,
            max_path_length: 20,
            max_edge_visits: 1,
            max_vertex_visits: 2,
            backtrack_probability: 0.0,
        }
    }
}

/// Generate a single path via constrained random walk.
/// Returns `Some(path)` where path is a sequence of edge indices, or `None` if no valid path found.
pub fn generate_path(
    graph: &HexGraph,
    constraints: &PathConstraints,
    rng: &mut impl Rng,
) -> Option<Vec<usize>> {
    let max_attempts = 1000;

    for _ in 0..max_attempts {
        if let Some(path) = try_generate_path(graph, constraints, rng) {
            return Some(path);
        }
    }
    None
}

/// Generate a batch of N unique paths (no duplicate vertex sequences).
/// Returns as many valid, distinct paths as could be generated.
pub fn generate_batch(
    graph: &HexGraph,
    constraints: &PathConstraints,
    count: usize,
    rng: &mut impl Rng,
) -> Vec<Vec<usize>> {
    let mut paths = Vec::with_capacity(count);
    let mut seen_vertex_seqs: std::collections::HashSet<Vec<usize>> =
        std::collections::HashSet::new();
    let max_total_attempts = count * 500;
    let mut attempts = 0;

    while paths.len() < count && attempts < max_total_attempts {
        attempts += 1;
        if let Some(path) = try_generate_path(graph, constraints, rng) {
            let verts = path_to_vertices(graph, &path);
            if seen_vertex_seqs.insert(verts) {
                paths.push(path);
            }
        }
    }
    paths
}

/// Single attempt at generating a constrained random walk from entry to exit.
fn try_generate_path(
    graph: &HexGraph,
    constraints: &PathConstraints,
    rng: &mut impl Rng,
) -> Option<Vec<usize>> {
    let mut path: Vec<usize> = Vec::new();
    let mut edge_visits = vec![0usize; graph.edges.len()];
    let mut vertex_visits = vec![0usize; graph.vertices.len()];

    let current = graph.entry_vertex;
    vertex_visits[current] = 1;
    let last_edge: Option<usize> = None;

    walk(
        graph,
        constraints,
        rng,
        &mut path,
        &mut edge_visits,
        &mut vertex_visits,
        current,
        last_edge,
    )
}

/// Recursive/iterative random walk step.
fn walk(
    graph: &HexGraph,
    constraints: &PathConstraints,
    rng: &mut impl Rng,
    path: &mut Vec<usize>,
    edge_visits: &mut [usize],
    vertex_visits: &mut [usize],
    current: usize,
    last_edge: Option<usize>,
) -> Option<Vec<usize>> {
    // Check if we've reached the exit with valid length.
    if current == graph.exit_vertex && path.len() >= constraints.min_path_length {
        return Some(path.clone());
    }

    // Check if path is too long already.
    if path.len() >= constraints.max_path_length {
        return None;
    }

    // Decide whether backtracking is allowed for this step.
    let allow_backtrack = constraints.backtrack_probability > 0.0
        && rng.r#gen::<f64>() < constraints.backtrack_probability;

    // Collect valid next edges.
    let valid_edges: Vec<usize> = graph.vertex_edges[current]
        .iter()
        .copied()
        .filter(|&ei| {
            // No immediate backtracking (unless stochastically allowed).
            if Some(ei) == last_edge && !allow_backtrack {
                return false;
            }
            // Edge visit limit.
            if edge_visits[ei] >= constraints.max_edge_visits {
                return false;
            }
            // Vertex visit limit for the other endpoint.
            let other = graph.other_vertex(ei, current);
            if vertex_visits[other] >= constraints.max_vertex_visits {
                // Exception: allow reaching exit even if at limit,
                // as long as we haven't exceeded it.
                if other != graph.exit_vertex {
                    return false;
                }
                // For exit, still respect the limit.
                if vertex_visits[other] >= constraints.max_vertex_visits {
                    return false;
                }
            }
            true
        })
        .collect();

    if valid_edges.is_empty() {
        return None;
    }

    // Shuffle the valid edges and try each one.
    let mut shuffled = valid_edges;
    shuffle(&mut shuffled, rng);

    for &ei in &shuffled {
        let next = graph.other_vertex(ei, current);

        // Take the step.
        path.push(ei);
        edge_visits[ei] += 1;
        vertex_visits[next] += 1;

        if let Some(result) = walk(
            graph,
            constraints,
            rng,
            path,
            edge_visits,
            vertex_visits,
            next,
            Some(ei),
        ) {
            return Some(result);
        }

        // Undo the step (backtrack).
        path.pop();
        edge_visits[ei] -= 1;
        vertex_visits[next] -= 1;
    }

    None
}

fn shuffle(v: &mut [usize], rng: &mut impl Rng) {
    for i in (1..v.len()).rev() {
        let j = rng.gen_range(0..=i);
        v.swap(i, j);
    }
}

/// Validate a path against constraints.
pub fn validate_path(
    graph: &HexGraph,
    path: &[usize],
    constraints: &PathConstraints,
) -> Result<(), String> {
    if path.is_empty() {
        return Err("Path is empty".to_string());
    }

    // Check length bounds.
    if path.len() < constraints.min_path_length {
        return Err(format!(
            "Path length {} < min {}",
            path.len(),
            constraints.min_path_length
        ));
    }
    if path.len() > constraints.max_path_length {
        return Err(format!(
            "Path length {} > max {}",
            path.len(),
            constraints.max_path_length
        ));
    }

    // Check all edge indices are valid.
    for &ei in path {
        if ei >= graph.edges.len() {
            return Err(format!("Invalid edge index {}", ei));
        }
    }

    // Reconstruct the vertex sequence and check connectivity.
    let first_edge = &graph.edges[path[0]];
    let start = if first_edge.v0 == graph.entry_vertex || first_edge.v1 == graph.entry_vertex {
        graph.entry_vertex
    } else {
        return Err("Path does not start at entry vertex".to_string());
    };

    let mut current = start;
    let mut edge_counts = vec![0usize; graph.edges.len()];
    let mut vertex_counts = vec![0usize; graph.vertices.len()];
    vertex_counts[current] += 1;

    for (i, &ei) in path.iter().enumerate() {
        let e = &graph.edges[ei];
        if e.v0 != current && e.v1 != current {
            return Err(format!(
                "Edge {} at step {} is not incident to current vertex {}",
                ei, i, current
            ));
        }

        // No immediate backtracking.
        if i > 0 && path[i] == path[i - 1] {
            return Err(format!("Immediate backtracking at step {}", i));
        }

        edge_counts[ei] += 1;
        if edge_counts[ei] > constraints.max_edge_visits {
            return Err(format!(
                "Edge {} visited {} times (max {})",
                ei, edge_counts[ei], constraints.max_edge_visits
            ));
        }

        let next = if e.v0 == current { e.v1 } else { e.v0 };
        vertex_counts[next] += 1;
        if vertex_counts[next] > constraints.max_vertex_visits {
            return Err(format!(
                "Vertex {} visited {} times (max {})",
                next, vertex_counts[next], constraints.max_vertex_visits
            ));
        }

        current = next;
    }

    // Check path ends at exit.
    if current != graph.exit_vertex {
        return Err(format!(
            "Path ends at vertex {} instead of exit vertex {}",
            current, graph.exit_vertex
        ));
    }

    Ok(())
}

/// Extract the ordered vertex sequence from a path (edge sequence).
pub fn path_to_vertices(graph: &HexGraph, path: &[usize]) -> Vec<usize> {
    if path.is_empty() {
        return vec![];
    }

    let mut vertices = Vec::with_capacity(path.len() + 1);
    let first_edge = &graph.edges[path[0]];

    // Determine the starting vertex (must be entry).
    let mut current = if first_edge.v0 == graph.entry_vertex {
        graph.entry_vertex
    } else {
        graph.entry_vertex
    };
    vertices.push(current);

    for &ei in path {
        let next = graph.other_vertex(ei, current);
        vertices.push(next);
        current = next;
    }

    vertices
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graph::GraphParams;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    fn test_graph() -> HexGraph {
        HexGraph::new(&GraphParams::default())
    }

    fn test_rng() -> ChaCha8Rng {
        ChaCha8Rng::seed_from_u64(42)
    }

    #[test]
    fn test_generate_path_starts_at_entry() {
        let g = test_graph();
        let c = PathConstraints::default();
        let mut rng = test_rng();
        let path = generate_path(&g, &c, &mut rng).expect("should generate a path");

        let first_edge = &g.edges[path[0]];
        assert!(
            first_edge.v0 == g.entry_vertex || first_edge.v1 == g.entry_vertex,
            "path should start at entry vertex"
        );
    }

    #[test]
    fn test_generate_path_ends_at_exit() {
        let g = test_graph();
        let c = PathConstraints::default();
        let mut rng = test_rng();
        let path = generate_path(&g, &c, &mut rng).expect("should generate a path");
        let verts = path_to_vertices(&g, &path);
        assert_eq!(
            *verts.last().unwrap(),
            g.exit_vertex,
            "path should end at exit vertex"
        );
    }

    #[test]
    fn test_path_length_within_bounds() {
        let g = test_graph();
        let c = PathConstraints {
            min_path_length: 5,
            max_path_length: 15,
            max_edge_visits: 2,
            max_vertex_visits: 3,
            ..PathConstraints::default()
        };
        let mut rng = test_rng();

        for _ in 0..20 {
            let path = generate_path(&g, &c, &mut rng).expect("should generate a path");
            assert!(
                path.len() >= c.min_path_length,
                "path too short: {}",
                path.len()
            );
            assert!(
                path.len() <= c.max_path_length,
                "path too long: {}",
                path.len()
            );
        }
    }

    #[test]
    fn test_no_immediate_backtracking() {
        let g = test_graph();
        let c = PathConstraints {
            max_edge_visits: 2,
            max_vertex_visits: 3,
            ..PathConstraints::default()
        };
        let mut rng = test_rng();

        for _ in 0..20 {
            let path = generate_path(&g, &c, &mut rng).expect("should generate a path");
            for i in 1..path.len() {
                assert_ne!(
                    path[i], path[i - 1],
                    "immediate backtracking at step {}",
                    i
                );
            }
        }
    }

    #[test]
    fn test_edge_visit_constraint() {
        let g = test_graph();
        let c = PathConstraints {
            max_edge_visits: 1,
            ..PathConstraints::default()
        };
        let mut rng = test_rng();

        for _ in 0..20 {
            if let Some(path) = generate_path(&g, &c, &mut rng) {
                let mut counts = vec![0usize; g.edges.len()];
                for &ei in &path {
                    counts[ei] += 1;
                    assert!(counts[ei] <= c.max_edge_visits);
                }
            }
        }
    }

    #[test]
    fn test_vertex_visit_constraint() {
        let g = test_graph();
        let c = PathConstraints {
            max_vertex_visits: 1,
            min_path_length: 3,
            max_path_length: 10,
            ..PathConstraints::default()
        };
        let mut rng = test_rng();

        for _ in 0..20 {
            if let Some(path) = generate_path(&g, &c, &mut rng) {
                let verts = path_to_vertices(&g, &path);
                let mut counts = vec![0usize; g.vertices.len()];
                for &vi in &verts {
                    counts[vi] += 1;
                    assert!(counts[vi] <= c.max_vertex_visits);
                }
            }
        }
    }

    #[test]
    fn test_determinism() {
        let g = test_graph();
        let c = PathConstraints::default();

        let path1 = {
            let mut rng = ChaCha8Rng::seed_from_u64(123);
            generate_path(&g, &c, &mut rng)
        };
        let path2 = {
            let mut rng = ChaCha8Rng::seed_from_u64(123);
            generate_path(&g, &c, &mut rng)
        };

        assert_eq!(path1, path2, "same seed should produce same path");
    }

    #[test]
    fn test_validate_accepts_valid_paths() {
        let g = test_graph();
        let c = PathConstraints::default();
        let mut rng = test_rng();

        for _ in 0..20 {
            if let Some(path) = generate_path(&g, &c, &mut rng) {
                assert!(
                    validate_path(&g, &path, &c).is_ok(),
                    "generated path should be valid"
                );
            }
        }
    }

    #[test]
    fn test_validate_rejects_empty() {
        let g = test_graph();
        let c = PathConstraints::default();
        assert!(validate_path(&g, &[], &c).is_err());
    }

    #[test]
    fn test_batch_generation() {
        let g = test_graph();
        let c = PathConstraints {
            min_path_length: 3,
            max_path_length: 15,
            max_edge_visits: 2,
            max_vertex_visits: 3,
            ..PathConstraints::default()
        };
        let mut rng = test_rng();

        let batch = generate_batch(&g, &c, 10, &mut rng);
        assert!(
            !batch.is_empty(),
            "batch should produce at least some paths"
        );

        for path in &batch {
            assert!(validate_path(&g, path, &c).is_ok());
        }
    }

    #[test]
    fn test_impossible_constraints() {
        let g = test_graph();
        // Require very long paths with max 1 edge visit — likely impossible.
        let c = PathConstraints {
            min_path_length: 100,
            max_path_length: 200,
            max_edge_visits: 1,
            max_vertex_visits: 1,
            ..PathConstraints::default()
        };
        let mut rng = test_rng();

        let result = generate_path(&g, &c, &mut rng);
        assert!(result.is_none(), "impossible constraints should return None");
    }
}
