mod compose;

use asemic_core::decoration;
use asemic_core::glyph::{self, GlyphDef};
use asemic_core::graph::{GraphParams, HexGraph};
use asemic_core::library::{GlyphLibrary, SamplingConstraints};
use asemic_core::path;
use asemic_core::render::{self, CurveMode, RenderingParams};
use compose::{generate_transition_matrix, generate_words, TransitionMatrix};
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use whiskers::prelude::*;

pub use whiskers::Result;

#[sketch_app]
struct WordComposerSketch {
    // --- Graph parameters ---
    #[param(slider, min = 2.0, max = 30.0)]
    hex_size: f64,

    // --- Alphabet source ---
    library_file: String,
    load_library: bool,
    #[param(slider, min = 8, max = 40)]
    alphabet_size: usize,
    generate_alphabet: bool,

    // --- Rendering ---
    use_bspline: bool,
    #[param(slider, min = 0.0, max = 1.0)]
    tightness: f64,
    #[param(slider, min = 0.0, max = 0.5)]
    vertex_jitter: f64,
    #[param(slider, min = 0.0, max = 0.3)]
    control_point_jitter: f64,

    // --- Word length (negative binomial) ---
    #[param(slider, min = 1.0, max = 10.0)]
    nb_r: f64,
    #[param(slider, min = 0.1, max = 0.9)]
    nb_p: f64,

    // --- Transition matrix ---
    #[param(slider, min = 0, max = 999)]
    matrix_seed: usize,
    #[param(slider, min = 0.15, max = 0.50)]
    vowel_fraction: f64,

    // --- Layout ---
    #[param(slider, min = 3, max = 500)]
    word_count: usize,
    #[param(slider, min = 1, max = 8)]
    columns: usize,
    #[param(slider, min = -1.0, max = 3.0)]
    letter_spacing: f64,
    #[param(slider, min = 0.3, max = 4.0)]
    word_spacing: f64,

    // --- Actions ---
    regenerate: bool,

    // --- Internal state ---
    #[skip]
    alphabet: Vec<GlyphDef>,
    #[skip]
    transition: Option<TransitionMatrix>,
    #[skip]
    words: Vec<Vec<usize>>,
    #[skip]
    needs_initial_generation: bool,
}

impl Default for WordComposerSketch {
    fn default() -> Self {
        Self {
            hex_size: 10.0,
            library_file: "glyph_library.json".to_string(),
            load_library: false,
            alphabet_size: 20,
            generate_alphabet: false,
            use_bspline: false,
            tightness: 0.5,
            vertex_jitter: 0.1,
            control_point_jitter: 0.05,
            nb_r: 2.0,
            nb_p: 0.4,
            matrix_seed: 42,
            vowel_fraction: 0.35,
            word_count: 24,
            columns: 2,
            letter_spacing: 0.0,
            word_spacing: 1.5,
            regenerate: false,
            alphabet: Vec::new(),
            transition: None,
            words: Vec::new(),
            needs_initial_generation: true,
        }
    }
}

impl App for WordComposerSketch {
    fn update(&mut self, sketch: &mut Sketch, ctx: &mut Context) -> anyhow::Result<()> {
        let graph_params = GraphParams {
            hex_size: self.hex_size,
            layout: asemic_core::graph::HexLayout::Layout232,
        };
        let graph = HexGraph::new(&graph_params);
        let rendering_params = RenderingParams {
            curve_mode: if self.use_bspline {
                CurveMode::BSpline
            } else {
                CurveMode::CatmullRom
            },
            tightness: self.tightness,
            vertex_jitter: self.vertex_jitter,
            control_point_jitter: self.control_point_jitter,
        };

        // Handle loading a library file.
        if self.load_library {
            self.load_library = false;
            let path = std::path::Path::new(&self.library_file);
            match GlyphLibrary::load(path) {
                Ok(lib) => {
                    self.alphabet = lib.glyphs;
                    self.alphabet_size = self.alphabet.len();
                    self.transition = None; // Force matrix rebuild.
                    self.words.clear();
                }
                Err(e) => eprintln!("Failed to load library: {}", e),
            }
        }

        // Handle generating a random alphabet.
        if self.generate_alphabet || (self.needs_initial_generation && self.alphabet.is_empty()) {
            self.generate_alphabet = false;
            self.alphabet = generate_random_alphabet(&graph, self.alphabet_size, ctx);
            self.transition = None; // Force matrix rebuild.
            self.words.clear();
        }

        if self.alphabet.is_empty() {
            return Ok(());
        }

        let n = self.alphabet.len();

        // Rebuild transition matrix if needed.
        if self.transition.is_none()
            || self.transition.as_ref().map_or(true, |t| t.matrix.len() != n)
        {
            self.transition = Some(generate_transition_matrix(
                n,
                self.vowel_fraction,
                self.matrix_seed as u64,
            ));
        }

        // Generate words if needed.
        if self.regenerate || self.words.is_empty() || self.needs_initial_generation {
            self.regenerate = false;
            self.needs_initial_generation = false;

            if let Some(ref tm) = self.transition {
                let seed = ctx.rng.get_seed();
                let mut rng = ChaCha8Rng::from_seed(seed);
                self.words = generate_words(tm, self.nb_r, self.nb_p, self.word_count, &mut rng);
            }
        }

        if self.words.is_empty() {
            return Ok(());
        }

        // --- Layout and rendering ---

        let glyph_bb = graph.bounding_box();
        let glyph_w = glyph_bb.2 - glyph_bb.0;
        let glyph_h = glyph_bb.3 - glyph_bb.1;
        let entry_pos = graph.vertex_pos(graph.entry_vertex);
        let exit_pos = graph.vertex_pos(graph.exit_vertex);
        let advance_width = exit_pos.0 - entry_pos.0;
        let spacing_px = self.letter_spacing * self.hex_size;

        // Compute word widths for column layout.
        let word_widths: Vec<f64> = self
            .words
            .iter()
            .map(|word| {
                if word.is_empty() {
                    0.0
                } else if word.len() == 1 {
                    glyph_w
                } else {
                    (word.len() - 1) as f64 * (advance_width + spacing_px) + glyph_w
                }
            })
            .collect();

        let cols = self.columns.max(1);
        let row_height = glyph_h + self.word_spacing * glyph_h;

        // Distribute words into columns (round-robin).
        let mut column_words: Vec<Vec<usize>> = vec![Vec::new(); cols];
        for (i, _) in self.words.iter().enumerate() {
            column_words[i % cols].push(i);
        }

        // Compute column widths (max word width in each column).
        let col_widths: Vec<f64> = column_words
            .iter()
            .map(|indices| {
                indices
                    .iter()
                    .map(|&i| word_widths[i])
                    .fold(0.0f64, f64::max)
            })
            .collect();

        let col_gap = self.hex_size * 3.0;
        let total_width: f64 = col_widths.iter().sum::<f64>() + (cols as f64 - 1.0) * col_gap;
        let max_rows = column_words.iter().map(|c| c.len()).max().unwrap_or(0);
        let total_height = max_rows as f64 * row_height;

        let page_w = sketch.width();
        let page_h = sketch.height();
        let offset_x = (page_w - total_width) / 2.0;
        let offset_y = (page_h - total_height) / 2.0;

        let seed = ctx.rng.get_seed();

        // Render each word.
        let mut col_x = offset_x;
        for (ci, word_indices) in column_words.iter().enumerate() {
            for (ri, &wi) in word_indices.iter().enumerate() {
                let word = &self.words[wi];
                let word_y = offset_y + ri as f64 * row_height;

                for (li, &letter_idx) in word.iter().enumerate() {
                    let glyph_def = &self.alphabet[letter_idx % n];

                    // Position: align entry points.
                    let glyph_x =
                        col_x + li as f64 * (advance_width + spacing_px) - glyph_bb.0;
                    let glyph_y = word_y - glyph_bb.1;

                    sketch.push_matrix();
                    sketch.translate(glyph_x, glyph_y);

                    let params = glyph_def
                        .rendering
                        .as_ref()
                        .unwrap_or(&rendering_params);

                    // Deterministic seed per word+letter.
                    let glyph_seed =
                        u64::from(seed[0]) ^ (wi as u64 * 7919) ^ (li as u64 * 104729);
                    let mut render_rng = ChaCha8Rng::seed_from_u64(glyph_seed);
                    let rendered =
                        render::render_glyph(&graph, glyph_def, params, &mut render_rng);

                    sketch.set_layer(1);
                    sketch.color(Color::BLACK).stroke_width(0.5);
                    sketch.add_path(rendered.main_path);

                    for dec_path in rendered.decorations {
                        sketch.add_path(dec_path);
                    }

                    sketch.pop_matrix();
                }
            }

            col_x += col_widths[ci] + col_gap;
        }

        Ok(())
    }
}

/// Generate a random alphabet of `count` glyphs using the default sampling constraints.
fn generate_random_alphabet(
    graph: &HexGraph,
    count: usize,
    ctx: &mut Context,
) -> Vec<GlyphDef> {
    let sampling = SamplingConstraints::default();
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
                id: format!("letter_{}", i),
                main_path,
                decorations,
                rendering: None,
                properties,
            }
        })
        .collect()
}

pub fn main() -> Result {
    WordComposerSketch::runner()
        .with_page_size_options(PageSize::A4H)
        .with_layout_options(LayoutOptions::Off)
        .with_info_options(
            InfoOptions::default()
                .description("Word composer: explore asemic word shapes with phonotactic transitions"),
        )
        .run()
}
