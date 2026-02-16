use serde::{Deserialize, Serialize};

/// Pre-computed properties of a glyph, used by the transition engine.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlyphProperties {
    /// Number of edges in the main path.
    pub path_length: usize,
    /// Number of unique vertices visited by the main path.
    pub vertex_count: usize,
    /// Number of direction changes (non-zero angles between consecutive edges).
    pub direction_changes: usize,
    /// Total absolute turning angle (sum of angles between consecutive edges).
    pub total_turning: f64,
    /// Number of decorations.
    pub decoration_count: usize,
    /// Total number of branch edges across all decorations.
    pub total_decoration_edges: usize,
    /// Width/height ratio of the path bounding box.
    pub aspect_ratio: f64,
    /// Fraction of the glyph bounding box covered by the path vertices.
    pub coverage: f64,
}

impl PartialEq for GlyphProperties {
    fn eq(&self, other: &Self) -> bool {
        self.path_length == other.path_length
            && self.vertex_count == other.vertex_count
            && self.direction_changes == other.direction_changes
            && (self.total_turning - other.total_turning).abs() < 1e-10
            && self.decoration_count == other.decoration_count
            && self.total_decoration_edges == other.total_decoration_edges
            && (self.aspect_ratio - other.aspect_ratio).abs() < 1e-10
            && (self.coverage - other.coverage).abs() < 1e-10
    }
}

/// Trait for types that expose glyph properties.
pub trait HasProperties {
    fn properties(&self) -> &GlyphProperties;

    fn path_length(&self) -> usize {
        self.properties().path_length
    }

    fn complexity(&self) -> f64 {
        self.properties().total_turning
    }

    fn decoration_count(&self) -> usize {
        self.properties().decoration_count
    }

    fn vertex_count(&self) -> usize {
        self.properties().vertex_count
    }

    fn aspect_ratio(&self) -> f64 {
        self.properties().aspect_ratio
    }

    fn coverage(&self) -> f64 {
        self.properties().coverage
    }
}
