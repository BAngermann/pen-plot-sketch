use crate::graph::HexGraph;
use rand::Rng;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

/// A decoration attached to the main path.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DecorationDef {
    /// Vertex on the main path where the decoration anchors.
    pub anchor_vertex: usize,
    /// The shared edge (part of main path) — the decoration starts along this edge.
    pub shared_edge: usize,
    /// Branch edges (not part of main path).
    pub branch_edges: Vec<usize>,
}

/// Constraints for decoration generation.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DecorationConstraints {
    /// Probability of generating a decoration at each eligible vertex.
    pub decoration_probability: f64,
    /// Max number of branch edges beyond the shared edge.
    pub max_branch_length: usize,
    /// Probability of extending the branch by one more edge at each step
    /// (0.0 = always stop after the first edge, 1.0 = always extend if possible).
    pub branch_continuation_probability: f64,
    /// Max total decorations per glyph.
    pub max_decorations: usize,
}

impl Default for DecorationConstraints {
    fn default() -> Self {
        Self {
            decoration_probability: 0.3,
            max_branch_length: 2,
            branch_continuation_probability: 0.5,
            max_decorations: 3,
        }
    }
}

/// Generate decorations for a given main path.
///
/// Branch edges only reach vertices that are neither on the main path
/// nor already claimed by another decoration.
pub fn generate_decorations(
    graph: &HexGraph,
    main_path: &[usize],
    constraints: &DecorationConstraints,
    rng: &mut impl Rng,
) -> Vec<DecorationDef> {
    if main_path.is_empty() || constraints.max_decorations == 0 {
        return vec![];
    }

    let path_edges: HashSet<usize> = main_path.iter().copied().collect();
    let path_vertices = crate::path::path_to_vertices(graph, main_path);
    let path_vertex_set: HashSet<usize> = path_vertices.iter().copied().collect();

    // Vertices that are off-limits for decoration endpoints:
    // main path + prior decorations + graph boundary (leftmost/rightmost x).
    let mut used_vertices: HashSet<usize> = path_vertex_set.clone();
    used_vertices.extend(graph.boundary_vertices());

    let mut decorations = Vec::new();

    for (step, &vertex) in path_vertices.iter().enumerate() {
        if decorations.len() >= constraints.max_decorations {
            break;
        }

        // Skip entry and exit vertices — decorations only on interior vertices.
        if step == 0 || step == path_vertices.len() - 1 {
            continue;
        }

        // Probability check.
        if rng.gen_range(0.0..1.0) > constraints.decoration_probability {
            continue;
        }

        // Find edges incident to this vertex that are part of the main path
        // (candidates for shared edge).
        let shared_edge_candidates: Vec<usize> = graph.vertex_edges[vertex]
            .iter()
            .copied()
            .filter(|ei| path_edges.contains(ei))
            .collect();

        if shared_edge_candidates.is_empty() {
            continue;
        }

        // Pick a random shared edge.
        let shared_edge = shared_edge_candidates[rng.gen_range(0..shared_edge_candidates.len())];

        // Find branch edges whose target vertex is not used.
        let branch_candidates: Vec<usize> = graph.vertex_edges[vertex]
            .iter()
            .copied()
            .filter(|&ei| {
                !path_edges.contains(&ei) && !used_vertices.contains(&graph.other_vertex(ei, vertex))
            })
            .collect();

        if branch_candidates.is_empty() {
            continue;
        }

        // Pick first branch edge.
        let first_branch = branch_candidates[rng.gen_range(0..branch_candidates.len())];
        let mut branch_edges = vec![first_branch];
        let mut tip = graph.other_vertex(first_branch, vertex);
        let mut prev_edge = first_branch;

        // Extend the branch one edge at a time, up to max_branch_length.
        while branch_edges.len() < constraints.max_branch_length {
            // Roll for early termination.
            if rng.gen_range(0.0..1.0) >= constraints.branch_continuation_probability {
                break;
            }

            let next_candidates: Vec<usize> = graph.vertex_edges[tip]
                .iter()
                .copied()
                .filter(|&ei| {
                    ei != prev_edge
                        && !path_edges.contains(&ei)
                        && !used_vertices.contains(&graph.other_vertex(ei, tip))
                })
                .collect();

            if next_candidates.is_empty() {
                break;
            }

            let next_edge = next_candidates[rng.gen_range(0..next_candidates.len())];
            tip = graph.other_vertex(next_edge, tip);
            prev_edge = next_edge;
            branch_edges.push(next_edge);
        }

        // Mark all decoration target vertices as used.
        let mut v = vertex;
        for &bei in &branch_edges {
            v = graph.other_vertex(bei, v);
            used_vertices.insert(v);
        }

        decorations.push(DecorationDef {
            anchor_vertex: vertex,
            shared_edge,
            branch_edges,
        });
    }

    decorations
}

/// Validate a decoration against the graph and main path.
pub fn validate_decoration(
    graph: &HexGraph,
    main_path: &[usize],
    decoration: &DecorationDef,
) -> Result<(), String> {
    let path_edges: HashSet<usize> = main_path.iter().copied().collect();
    let path_vertices: HashSet<usize> =
        crate::path::path_to_vertices(graph, main_path).into_iter().collect();

    // Anchor vertex must be on the main path.
    if !path_vertices.contains(&decoration.anchor_vertex) {
        return Err(format!(
            "Anchor vertex {} is not on the main path",
            decoration.anchor_vertex
        ));
    }

    // Shared edge must be part of the main path.
    if !path_edges.contains(&decoration.shared_edge) {
        return Err(format!(
            "Shared edge {} is not part of the main path",
            decoration.shared_edge
        ));
    }

    // Shared edge must be incident to anchor vertex.
    let se = &graph.edges[decoration.shared_edge];
    if se.v0 != decoration.anchor_vertex && se.v1 != decoration.anchor_vertex {
        return Err(format!(
            "Shared edge {} is not incident to anchor vertex {}",
            decoration.shared_edge, decoration.anchor_vertex
        ));
    }

    // Branch edges must not be part of the main path.
    for &bei in &decoration.branch_edges {
        if path_edges.contains(&bei) {
            return Err(format!("Branch edge {} is part of the main path", bei));
        }
    }

    // Branch edges must be valid edge indices.
    for &bei in &decoration.branch_edges {
        if bei >= graph.edges.len() {
            return Err(format!("Invalid branch edge index {}", bei));
        }
    }

    // First branch edge must be incident to anchor vertex.
    if !decoration.branch_edges.is_empty() {
        let be = &graph.edges[decoration.branch_edges[0]];
        if be.v0 != decoration.anchor_vertex && be.v1 != decoration.anchor_vertex {
            return Err(format!(
                "First branch edge {} is not incident to anchor vertex {}",
                decoration.branch_edges[0], decoration.anchor_vertex
            ));
        }
    }

    // Subsequent branch edges must form a connected chain.
    let mut current = decoration.anchor_vertex;
    for (i, &bei) in decoration.branch_edges.iter().enumerate() {
        let be = &graph.edges[bei];
        if be.v0 != current && be.v1 != current {
            return Err(format!(
                "Branch edge {} at position {} is not connected to previous vertex {}",
                bei, i, current
            ));
        }
        current = graph.other_vertex(bei, current);
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graph::GraphParams;
    use crate::path::{self, PathConstraints};
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    fn setup() -> (HexGraph, Vec<usize>, ChaCha8Rng) {
        let g = HexGraph::new(&GraphParams::default());
        let c = PathConstraints {
            min_path_length: 5,
            max_path_length: 15,
            max_edge_visits: 2,
            max_vertex_visits: 3,
        };
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let main_path = path::generate_path(&g, &c, &mut rng).expect("should generate path");
        (g, main_path, rng)
    }

    #[test]
    fn test_decorations_anchor_to_path_vertices() {
        let (g, main_path, mut rng) = setup();
        let path_vertices: HashSet<usize> =
            path::path_to_vertices(&g, &main_path).into_iter().collect();

        let constraints = DecorationConstraints {
            decoration_probability: 1.0,
            max_branch_length: 2,
            branch_continuation_probability: 1.0,
            max_decorations: 10,
        };

        let decorations = generate_decorations(&g, &main_path, &constraints, &mut rng);
        for d in &decorations {
            assert!(
                path_vertices.contains(&d.anchor_vertex),
                "anchor vertex {} should be on path",
                d.anchor_vertex
            );
        }
    }

    #[test]
    fn test_shared_edge_is_on_path() {
        let (g, main_path, mut rng) = setup();
        let path_edges: HashSet<usize> = main_path.iter().copied().collect();

        let constraints = DecorationConstraints {
            decoration_probability: 1.0,
            max_branch_length: 2,
            branch_continuation_probability: 1.0,
            max_decorations: 10,
        };

        let decorations = generate_decorations(&g, &main_path, &constraints, &mut rng);
        for d in &decorations {
            assert!(
                path_edges.contains(&d.shared_edge),
                "shared edge {} should be on path",
                d.shared_edge
            );
        }
    }

    #[test]
    fn test_branch_edges_not_on_path() {
        let (g, main_path, mut rng) = setup();
        let path_edges: HashSet<usize> = main_path.iter().copied().collect();

        let constraints = DecorationConstraints {
            decoration_probability: 1.0,
            max_branch_length: 2,
            branch_continuation_probability: 1.0,
            max_decorations: 10,
        };

        let decorations = generate_decorations(&g, &main_path, &constraints, &mut rng);
        for d in &decorations {
            for &bei in &d.branch_edges {
                assert!(
                    !path_edges.contains(&bei),
                    "branch edge {} should not be on path",
                    bei
                );
            }
        }
    }

    #[test]
    fn test_max_decorations_respected() {
        let (g, main_path, mut rng) = setup();

        let constraints = DecorationConstraints {
            decoration_probability: 1.0,
            max_branch_length: 2,
            branch_continuation_probability: 1.0,
            max_decorations: 2,
        };

        let decorations = generate_decorations(&g, &main_path, &constraints, &mut rng);
        assert!(
            decorations.len() <= constraints.max_decorations,
            "got {} decorations, max is {}",
            decorations.len(),
            constraints.max_decorations
        );
    }

    #[test]
    fn test_branch_length_respected() {
        let (g, main_path, mut rng) = setup();

        for max_len in [1, 2, 3] {
            let constraints = DecorationConstraints {
                decoration_probability: 1.0,
                max_branch_length: max_len,
                branch_continuation_probability: 1.0,
                max_decorations: 10,
            };

            let decorations = generate_decorations(&g, &main_path, &constraints, &mut rng);
            for d in &decorations {
                assert!(
                    d.branch_edges.len() <= max_len,
                    "branch has {} edges, max is {}",
                    d.branch_edges.len(),
                    max_len
                );
            }
        }
    }

    #[test]
    fn test_validate_generated_decorations() {
        let (g, main_path, mut rng) = setup();

        let constraints = DecorationConstraints {
            decoration_probability: 1.0,
            max_branch_length: 2,
            branch_continuation_probability: 1.0,
            max_decorations: 10,
        };

        let decorations = generate_decorations(&g, &main_path, &constraints, &mut rng);
        for d in &decorations {
            assert!(
                validate_decoration(&g, &main_path, d).is_ok(),
                "generated decoration should be valid: {:?}",
                validate_decoration(&g, &main_path, d)
            );
        }
    }

    #[test]
    fn test_branch_vertices_not_on_path_or_other_decorations() {
        let (g, main_path, mut rng) = setup();
        let path_vertex_set: HashSet<usize> =
            path::path_to_vertices(&g, &main_path).into_iter().collect();

        let constraints = DecorationConstraints {
            decoration_probability: 1.0,
            max_branch_length: 2,
            branch_continuation_probability: 1.0,
            max_decorations: 10,
        };

        let decorations = generate_decorations(&g, &main_path, &constraints, &mut rng);

        let mut seen_branch_vertices: HashSet<usize> = HashSet::new();
        for d in &decorations {
            let mut v = d.anchor_vertex;
            for &bei in &d.branch_edges {
                v = g.other_vertex(bei, v);
                assert!(
                    !path_vertex_set.contains(&v),
                    "branch vertex {} is on the main path",
                    v
                );
                assert!(
                    seen_branch_vertices.insert(v),
                    "branch vertex {} is already used by another decoration",
                    v
                );
            }
        }
    }

    #[test]
    fn test_zero_continuation_gives_length_one() {
        let (g, main_path, mut rng) = setup();

        let constraints = DecorationConstraints {
            decoration_probability: 1.0,
            max_branch_length: 5,
            branch_continuation_probability: 0.0,
            max_decorations: 10,
        };

        let decorations = generate_decorations(&g, &main_path, &constraints, &mut rng);
        for d in &decorations {
            assert_eq!(
                d.branch_edges.len(),
                1,
                "0 continuation probability should always give length-1 branches"
            );
        }
    }

    #[test]
    fn test_zero_probability_no_decorations() {
        let (g, main_path, mut rng) = setup();

        let constraints = DecorationConstraints {
            decoration_probability: 0.0,
            max_branch_length: 2,
            branch_continuation_probability: 1.0,
            max_decorations: 10,
        };

        let decorations = generate_decorations(&g, &main_path, &constraints, &mut rng);
        assert!(decorations.is_empty(), "0 probability should yield no decorations");
    }
}
