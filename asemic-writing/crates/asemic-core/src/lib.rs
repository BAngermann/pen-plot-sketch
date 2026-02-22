pub mod graph;
pub mod path;
pub mod decoration;
pub mod glyph;
pub mod properties;
pub mod render;
pub mod library;
pub mod transition;

#[cfg(test)]
mod integration_tests {
    use crate::decoration::{self, DecorationConstraints};
    use crate::glyph::{self, GlyphDef};
    use crate::graph::{GraphParams, HexGraph};
    use crate::library::{GlyphLibrary, SamplingConstraints};
    use crate::path::{self, PathConstraints};
    use crate::render::{self, RenderingParams};
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    #[test]
    fn test_end_to_end_pipeline() {
        // Full pipeline: graph → paths → decorations → properties → serialize → deserialize → validate.
        let graph_params = GraphParams::default();
        let graph = HexGraph::new(&graph_params);

        let sampling = SamplingConstraints::default();
        let path_constraints = sampling.to_path_constraints();
        let dec_constraints = sampling.to_decoration_constraints();
        let rendering = RenderingParams::default();

        let mut rng = ChaCha8Rng::seed_from_u64(12345);
        let mut library = GlyphLibrary::new(
            graph_params,
            sampling,
            rendering.clone(),
        );

        // Generate several glyphs.
        for i in 0..10 {
            if let Some(main_path) = path::generate_path(&graph, &path_constraints, &mut rng) {
                let decorations =
                    decoration::generate_decorations(&graph, &main_path, &dec_constraints, &mut rng);
                let properties = glyph::compute_properties(&graph, &main_path, &decorations);

                library.add_glyph(GlyphDef {
                    id: format!("glyph_{}", i),
                    main_path,
                    decorations,
                    rendering: None,
                    properties,
                });
            }
        }

        assert!(!library.glyphs.is_empty(), "should have generated some glyphs");

        // Serialize and deserialize.
        let json = serde_json::to_string_pretty(&library).expect("serialize");
        let loaded: GlyphLibrary = serde_json::from_str(&json).expect("deserialize");

        // Validate the loaded library.
        assert!(loaded.validate().is_ok(), "loaded library should be valid");

        // Check properties are preserved.
        for (orig, loaded) in library.glyphs.iter().zip(loaded.glyphs.iter()) {
            assert_eq!(orig.properties, loaded.properties);
            assert_eq!(orig.main_path, loaded.main_path);
            assert_eq!(orig.decorations, loaded.decorations);
        }

        // Render all glyphs.
        let mut render_rng = ChaCha8Rng::seed_from_u64(99);
        for glyph_def in &loaded.glyphs {
            let params = glyph_def.rendering.as_ref().unwrap_or(&rendering);
            let rendered = render::render_glyph(&graph, glyph_def, params, &mut render_rng);
            assert!(!rendered.main_path.elements().is_empty());
            assert_eq!(rendered.decorations.len(), glyph_def.decorations.len());
        }
    }

    #[test]
    fn test_properties_stable_across_roundtrip() {
        let graph_params = GraphParams::default();
        let graph = HexGraph::new(&graph_params);

        let constraints = PathConstraints {
            min_path_length: 5,
            max_path_length: 15,
            max_edge_visits: 2,
            max_vertex_visits: 3,
            ..PathConstraints::default()
        };
        let dec_constraints = DecorationConstraints::default();
        let mut rng = ChaCha8Rng::seed_from_u64(42);

        let main_path = path::generate_path(&graph, &constraints, &mut rng).expect("path");
        let decorations =
            decoration::generate_decorations(&graph, &main_path, &dec_constraints, &mut rng);

        // Compute properties before serialization.
        let props_before = glyph::compute_properties(&graph, &main_path, &decorations);

        // Create glyph, serialize, deserialize.
        let glyph_def = GlyphDef {
            id: "test".to_string(),
            main_path: main_path.clone(),
            decorations: decorations.clone(),
            rendering: None,
            properties: props_before.clone(),
        };

        let json = serde_json::to_string(&glyph_def).expect("serialize");
        let loaded: GlyphDef = serde_json::from_str(&json).expect("deserialize");

        // Recompute properties from the loaded data.
        let props_after = glyph::compute_properties(&graph, &loaded.main_path, &loaded.decorations);

        assert_eq!(props_before, props_after);
        assert_eq!(loaded.properties, props_after);
    }
}
