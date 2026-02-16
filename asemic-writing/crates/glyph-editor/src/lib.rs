use asemic_core::decoration;
use asemic_core::glyph::{self, GlyphDef};
use asemic_core::graph::{GraphParams, HexGraph};
use asemic_core::library::{GlyphLibrary, SamplingConstraints};
use asemic_core::path;
use asemic_core::render::{self, RenderingParams};
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use whiskers::prelude::*;

pub use whiskers::Result;

#[sketch_app]
struct GlyphEditorSketch {
    // --- Graph parameters ---
    #[param(slider, min = 5.0, max = 30.0)]
    hex_size: f64,

    // --- Sampling constraints ---
    #[param(slider, min = 1, max = 30)]
    min_path_length: usize,
    #[param(slider, min = 1, max = 30)]
    max_path_length: usize,
    #[param(slider, min = 1, max = 3)]
    max_edge_visits: usize,
    #[param(slider, min = 1, max = 4)]
    max_vertex_visits: usize,
    #[param(slider, min = 0.0, max = 1.0)]
    decoration_probability: f64,
    #[param(slider, min = 1, max = 2)]
    max_decoration_branch_length: usize,
    #[param(slider, min = 0.0, max = 1.0)]
    branch_continuation_probability: f64,
    #[param(slider, min = 0, max = 5)]
    max_decorations_per_glyph: usize,

    // --- Rendering parameters ---
    #[param(slider, min = 0.0, max = 1.0)]
    tightness: f64,
    #[param(slider, min = 0.0, max = 0.5)]
    vertex_jitter: f64,
    #[param(slider, min = 0.0, max = 0.3)]
    control_point_jitter: f64,

    // --- Batch generation ---
    #[param(slider, min = 1, max = 90)]
    batch_size: usize,

    // --- Actions (toggles used as buttons) ---
    generate_batch: bool,
    accept_all_visible: bool,
    #[param(slider, min = 0, max = 29)]
    selected_glyph: usize,
    accept_selected: bool,
    view_library: bool,
    #[param(slider, min = 0, max = 99)]
    remove_index: usize,
    remove_glyph: bool,

    // --- File operations ---
    library_file: String,
    save_library: bool,
    load_library: bool,

    // --- Internal state (not exposed as UI params) ---
    #[skip]
    candidates: Vec<GlyphDef>,
    #[skip]
    library: GlyphLibrary,
    #[skip]
    needs_initial_batch: bool,
}

impl Default for GlyphEditorSketch {
    fn default() -> Self {
        Self {
            hex_size: 10.0,
            min_path_length: 5,
            max_path_length: 15,
            max_edge_visits: 1,
            max_vertex_visits: 2,
            decoration_probability: 0.3,
            max_decoration_branch_length: 2,
            branch_continuation_probability: 0.5,
            max_decorations_per_glyph: 3,
            tightness: 0.5,
            vertex_jitter: 0.1,
            control_point_jitter: 0.05,
            batch_size: 12,
            generate_batch: false,
            accept_all_visible: false,
            selected_glyph: 0,
            accept_selected: false,
            view_library: false,
            remove_index: 0,
            remove_glyph: false,
            library_file: "glyph_library.json".to_string(),
            save_library: false,
            load_library: false,
            candidates: Vec::new(),
            library: GlyphLibrary::default(),
            needs_initial_batch: true,
        }
    }
}

impl App for GlyphEditorSketch {
    fn update(&mut self, sketch: &mut Sketch, ctx: &mut Context) -> anyhow::Result<()> {
        let graph_params = GraphParams {
            hex_size: self.hex_size,
            layout: asemic_core::graph::HexLayout::Layout232,
        };
        let graph = HexGraph::new(&graph_params);
        let rendering_params = RenderingParams {
            tightness: self.tightness,
            vertex_jitter: self.vertex_jitter,
            control_point_jitter: self.control_point_jitter,
        };
        let sampling = SamplingConstraints {
            min_path_length: self.min_path_length,
            max_path_length: self.max_path_length,
            max_edge_visits: self.max_edge_visits,
            max_vertex_visits: self.max_vertex_visits,
            decoration_probability: self.decoration_probability,
            max_decoration_branch_length: self.max_decoration_branch_length,
            branch_continuation_probability: self.branch_continuation_probability,
            max_decorations_per_glyph: self.max_decorations_per_glyph,
        };

        // Handle actions.
        if self.generate_batch || self.needs_initial_batch {
            self.generate_batch = false;
            self.needs_initial_batch = false;
            self.candidates = generate_candidate_batch(&graph, &sampling, self.batch_size, ctx);
        }

        if self.accept_selected {
            self.accept_selected = false;
            if self.selected_glyph < self.candidates.len() {
                let glyph = self.candidates[self.selected_glyph].clone();
                self.library.add_glyph(glyph);
            }
        }

        if self.accept_all_visible {
            self.accept_all_visible = false;
            for candidate in &self.candidates {
                self.library.add_glyph(candidate.clone());
            }
            self.candidates.clear();
        }

        if self.remove_glyph {
            self.remove_glyph = false;
            if self.remove_index < self.library.glyphs.len() {
                self.library.remove_glyph(self.remove_index);
            }
        }

        if self.save_library {
            self.save_library = false;
            let mut lib = self.library.clone();
            lib.graph_params = graph_params.clone();
            lib.sampling_constraints = sampling.clone();
            lib.default_rendering = rendering_params.clone();
            let path = std::path::Path::new(&self.library_file);
            if let Err(e) = lib.save(path) {
                eprintln!("Failed to save library: {}", e);
            }
        }

        if self.load_library {
            self.load_library = false;
            let path = std::path::Path::new(&self.library_file);
            match GlyphLibrary::load(path) {
                Ok(lib) => self.library = lib,
                Err(e) => eprintln!("Failed to load library: {}", e),
            }
        }

        // Rendering.
        let glyphs_to_draw = if self.view_library {
            &self.library.glyphs
        } else {
            &self.candidates
        };

        if glyphs_to_draw.is_empty() {
            return Ok(());
        }

        // Compute grid layout for displaying glyphs.
        let cols = (glyphs_to_draw.len() as f64).sqrt().ceil() as usize;

        let glyph_bb = graph.bounding_box();
        let glyph_w = glyph_bb.2 - glyph_bb.0;
        let glyph_h = glyph_bb.3 - glyph_bb.1;
        let padding = self.hex_size * 0.8;
        let cell_w = glyph_w + padding * 2.0;
        let cell_h = glyph_h + padding * 2.0;

        // Center the grid on the page.
        let total_w = cols as f64 * cell_w;
        let rows = (glyphs_to_draw.len() + cols - 1) / cols;
        let total_h = rows as f64 * cell_h;
        let page_w = sketch.width();
        let page_h = sketch.height();
        let offset_x = (page_w - total_w) / 2.0;
        let offset_y = (page_h - total_h) / 2.0;

        let seed = ctx.rng.get_seed();

        for (i, glyph_def) in glyphs_to_draw.iter().enumerate() {
            let col = i % cols;
            let row = i / cols;

            let cell_x = offset_x + col as f64 * cell_w;
            let cell_y = offset_y + row as f64 * cell_h;

            sketch.push_matrix();
            sketch.translate(
                cell_x + padding - glyph_bb.0,
                cell_y + padding - glyph_bb.1,
            );

            // Draw ghost hex graph skeleton.
            sketch.set_layer(0);
            sketch
                .color(Color::new(200, 200, 200, 60))
                .stroke_width(0.1);
            let skeleton = render::render_graph_skeleton(&graph);
            sketch.add_path(skeleton);

            // Mark entry/exit vertices.
            let entry_pos = graph.vertex_pos(graph.entry_vertex);
            let exit_pos = graph.vertex_pos(graph.exit_vertex);
            let marker_r = self.hex_size * 0.15;
            sketch.color(Color::new(0, 150, 0, 120));
            sketch.circle(entry_pos.0, entry_pos.1, marker_r);
            sketch.color(Color::new(150, 0, 0, 120));
            sketch.circle(exit_pos.0, exit_pos.1, marker_r);

            // Render the glyph.
            let params = glyph_def
                .rendering
                .as_ref()
                .unwrap_or(&rendering_params);

            // Use a deterministic sub-seed per glyph for rendering jitter.
            let glyph_seed = u64::from(seed[0]) ^ (i as u64 * 7919);
            let mut render_rng = ChaCha8Rng::seed_from_u64(glyph_seed);
            let rendered = render::render_glyph(&graph, glyph_def, params, &mut render_rng);

            // Draw main path.
            sketch.set_layer(1);
            sketch.color(Color::BLACK).stroke_width(0.5);
            sketch.add_path(rendered.main_path);

            // Draw decorations.
            sketch
                .color(Color::BLACK)
                .stroke_width(0.5);
            for dec_path in rendered.decorations {
                sketch.add_path(dec_path);
            }

            sketch.pop_matrix();

            // Draw selection highlight for non-library view.
            if !self.view_library && i == self.selected_glyph {
                sketch.set_layer(2);
                sketch
                    .color(Color::new(0, 100, 255, 80))
                    .stroke_width(0.3);
                sketch.rect(
                    cell_x + cell_w / 2.0,
                    cell_y + cell_h / 2.0,
                    cell_w - 2.0,
                    cell_h - 2.0,
                );
            }
        }

        Ok(())
    }
}

fn generate_candidate_batch(
    graph: &HexGraph,
    sampling: &SamplingConstraints,
    count: usize,
    ctx: &mut Context,
) -> Vec<GlyphDef> {
    let path_constraints = sampling.to_path_constraints();
    let dec_constraints = sampling.to_decoration_constraints();

    let seed = ctx.rng.get_seed();
    let mut rng = ChaCha8Rng::from_seed(seed);

    let paths = path::generate_batch(graph, &path_constraints, count, &mut rng);

    paths
        .into_iter()
        .enumerate()
        .map(|(i, main_path)| {
            let decorations =
                decoration::generate_decorations(graph, &main_path, &dec_constraints, &mut rng);
            let properties = glyph::compute_properties(graph, &main_path, &decorations);

            GlyphDef {
                id: format!("candidate_{}", i),
                main_path,
                decorations,
                rendering: None,
                properties,
            }
        })
        .collect()
}

pub fn main() -> Result {
    GlyphEditorSketch::runner()
        .with_page_size_options(PageSize::A4H)
        .with_layout_options(LayoutOptions::Off)
        .with_info_options(
            InfoOptions::default()
                .description("Asemic glyph editor: generate, curate, and save glyph libraries"),
        )
        .run()
}
