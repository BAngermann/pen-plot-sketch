use crate::decoration::{self, DecorationConstraints};
use crate::glyph::GlyphDef;
use crate::graph::{GraphParams, HexGraph};
use crate::path::{self, PathConstraints};
use crate::render::RenderingParams;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;

/// Sampling constraints used to generate glyphs.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SamplingConstraints {
    pub min_path_length: usize,
    pub max_path_length: usize,
    pub max_edge_visits: usize,
    pub max_vertex_visits: usize,
    pub decoration_probability: f64,
    pub max_decoration_branch_length: usize,
    pub branch_continuation_probability: f64,
    pub max_decorations_per_glyph: usize,
    #[serde(default)]
    pub backtrack_probability: f64,
}

impl Default for SamplingConstraints {
    fn default() -> Self {
        Self {
            min_path_length: 5,
            max_path_length: 20,
            max_edge_visits: 1,
            max_vertex_visits: 2,
            decoration_probability: 0.3,
            max_decoration_branch_length: 2,
            branch_continuation_probability: 0.5,
            max_decorations_per_glyph: 3,
            backtrack_probability: 0.0,
        }
    }
}

impl SamplingConstraints {
    pub fn to_path_constraints(&self) -> PathConstraints {
        PathConstraints {
            min_path_length: self.min_path_length,
            max_path_length: self.max_path_length,
            max_edge_visits: self.max_edge_visits,
            max_vertex_visits: self.max_vertex_visits,
            backtrack_probability: self.backtrack_probability,
        }
    }

    pub fn to_decoration_constraints(&self) -> DecorationConstraints {
        DecorationConstraints {
            decoration_probability: self.decoration_probability,
            max_branch_length: self.max_decoration_branch_length,
            branch_continuation_probability: self.branch_continuation_probability,
            max_decorations: self.max_decorations_per_glyph,
        }
    }
}

/// A glyph library: the complete serializable state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlyphLibrary {
    pub version: String,
    pub graph_params: GraphParams,
    pub sampling_constraints: SamplingConstraints,
    pub default_rendering: RenderingParams,
    pub glyphs: Vec<GlyphDef>,
}

impl Default for GlyphLibrary {
    fn default() -> Self {
        Self {
            version: "0.1.0".to_string(),
            graph_params: GraphParams::default(),
            sampling_constraints: SamplingConstraints::default(),
            default_rendering: RenderingParams::default(),
            glyphs: Vec::new(),
        }
    }
}

impl GlyphLibrary {
    /// Create a new empty library with the given parameters.
    pub fn new(
        graph_params: GraphParams,
        sampling_constraints: SamplingConstraints,
        default_rendering: RenderingParams,
    ) -> Self {
        Self {
            version: "0.1.0".to_string(),
            graph_params,
            sampling_constraints,
            default_rendering,
            glyphs: Vec::new(),
        }
    }

    /// Add a glyph to the library, assigning it a unique ID.
    pub fn add_glyph(&mut self, mut glyph: GlyphDef) {
        if glyph.id.is_empty() {
            glyph.id = format!("glyph_{}", self.glyphs.len());
        }
        self.glyphs.push(glyph);
    }

    /// Remove a glyph by index.
    pub fn remove_glyph(&mut self, index: usize) -> Option<GlyphDef> {
        if index < self.glyphs.len() {
            Some(self.glyphs.remove(index))
        } else {
            None
        }
    }

    /// Save the library to a JSON file.
    pub fn save(&self, path: &Path) -> Result<()> {
        let json = serde_json::to_string_pretty(self)
            .context("Failed to serialize library")?;
        std::fs::write(path, json)
            .context("Failed to write library file")?;
        Ok(())
    }

    /// Load a library from a JSON file.
    pub fn load(path: &Path) -> Result<Self> {
        let json = std::fs::read_to_string(path)
            .context("Failed to read library file")?;
        let library: GlyphLibrary = serde_json::from_str(&json)
            .context("Failed to deserialize library")?;
        Ok(library)
    }

    /// Validate all glyphs in the library against the stored graph params.
    pub fn validate(&self) -> Result<()> {
        let graph = HexGraph::new(&self.graph_params);
        let path_constraints = self.sampling_constraints.to_path_constraints();

        for (i, glyph) in self.glyphs.iter().enumerate() {
            // Validate edge indices.
            for &ei in &glyph.main_path {
                anyhow::ensure!(
                    ei < graph.edges.len(),
                    "Glyph {} has invalid edge index {} (graph has {} edges)",
                    i,
                    ei,
                    graph.edges.len()
                );
            }

            // Validate path.
            path::validate_path(&graph, &glyph.main_path, &path_constraints)
                .map_err(|e| anyhow::anyhow!("Glyph {} path invalid: {}", i, e))?;

            // Validate decorations.
            for (di, dec) in glyph.decorations.iter().enumerate() {
                decoration::validate_decoration(&graph, &glyph.main_path, dec)
                    .map_err(|e| anyhow::anyhow!("Glyph {} decoration {} invalid: {}", i, di, e))?;
            }
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::glyph;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    fn make_test_library() -> GlyphLibrary {
        let graph_params = GraphParams::default();
        let sampling = SamplingConstraints::default();
        let rendering = RenderingParams::default();
        let mut library = GlyphLibrary::new(graph_params.clone(), sampling.clone(), rendering);

        let graph = HexGraph::new(&graph_params);
        let path_constraints = sampling.to_path_constraints();
        let dec_constraints = sampling.to_decoration_constraints();
        let mut rng = ChaCha8Rng::seed_from_u64(42);

        for i in 0..5 {
            if let Some(main_path) = path::generate_path(&graph, &path_constraints, &mut rng) {
                let decorations =
                    crate::decoration::generate_decorations(&graph, &main_path, &dec_constraints, &mut rng);
                let properties = glyph::compute_properties(&graph, &main_path, &decorations);

                library.add_glyph(GlyphDef {
                    id: format!("test_{}", i),
                    main_path,
                    decorations,
                    rendering: None,
                    properties,
                });
            }
        }

        library
    }

    #[test]
    fn test_serialization_roundtrip() {
        let library = make_test_library();
        let json = serde_json::to_string_pretty(&library).expect("serialize");
        let loaded: GlyphLibrary = serde_json::from_str(&json).expect("deserialize");

        assert_eq!(library.version, loaded.version);
        assert_eq!(library.graph_params, loaded.graph_params);
        assert_eq!(library.sampling_constraints, loaded.sampling_constraints);
        assert_eq!(library.default_rendering, loaded.default_rendering);
        assert_eq!(library.glyphs.len(), loaded.glyphs.len());

        for (orig, loaded) in library.glyphs.iter().zip(loaded.glyphs.iter()) {
            assert_eq!(orig.id, loaded.id);
            assert_eq!(orig.main_path, loaded.main_path);
            assert_eq!(orig.decorations, loaded.decorations);
            assert_eq!(orig.properties, loaded.properties);
        }
    }

    #[test]
    fn test_file_roundtrip() {
        let library = make_test_library();

        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("test_library.json");

        library.save(&path).expect("save");
        let loaded = GlyphLibrary::load(&path).expect("load");

        assert_eq!(library.glyphs.len(), loaded.glyphs.len());
        for (orig, loaded) in library.glyphs.iter().zip(loaded.glyphs.iter()) {
            assert_eq!(orig.id, loaded.id);
            assert_eq!(orig.main_path, loaded.main_path);
        }
    }

    #[test]
    fn test_validate_valid_library() {
        let library = make_test_library();
        assert!(library.validate().is_ok());
    }

    #[test]
    fn test_validate_invalid_edge_index() {
        let mut library = make_test_library();
        if let Some(glyph) = library.glyphs.first_mut() {
            glyph.main_path.push(9999); // Invalid edge index.
        }
        assert!(library.validate().is_err());
    }

    #[test]
    fn test_add_remove_glyph() {
        let mut library = GlyphLibrary::default();
        assert_eq!(library.glyphs.len(), 0);

        let graph = HexGraph::new(&library.graph_params);
        let constraints = library.sampling_constraints.to_path_constraints();
        let mut rng = ChaCha8Rng::seed_from_u64(42);

        if let Some(main_path) = path::generate_path(&graph, &constraints, &mut rng) {
            let properties = glyph::compute_properties(&graph, &main_path, &[]);
            library.add_glyph(GlyphDef {
                id: String::new(),
                main_path,
                decorations: vec![],
                rendering: None,
                properties,
            });
        }

        assert_eq!(library.glyphs.len(), 1);
        assert!(!library.glyphs[0].id.is_empty());

        library.remove_glyph(0);
        assert_eq!(library.glyphs.len(), 0);
    }

    #[test]
    fn test_properties_preserved_after_roundtrip() {
        let library = make_test_library();
        let json = serde_json::to_string(&library).expect("serialize");
        let loaded: GlyphLibrary = serde_json::from_str(&json).expect("deserialize");

        for (orig, loaded) in library.glyphs.iter().zip(loaded.glyphs.iter()) {
            assert_eq!(orig.properties, loaded.properties);
        }
    }
}
