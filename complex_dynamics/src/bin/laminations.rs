use complex_dynamics::*;
use whiskers::prelude::*;
use vsvg::Color;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::f64::consts::PI;

// ── Serialisable parameter snapshot ──────────────────────────────────────────

#[derive(Serialize, Deserialize, Clone, Default)]
struct SavedParams {
    misiurewicz_mode: Option<bool>,
    p: Option<usize>,
    q: Option<usize>,
    angle_num: Option<i64>,
    angle_den: Option<i64>,
    depth: Option<usize>,
    mating_mode: Option<bool>,
    p2: Option<usize>,
    q2: Option<usize>,
    scale: Option<f64>,
    generation_color: Option<bool>,
}

// ── Cache key ─────────────────────────────────────────────────────────────────

#[derive(Default, PartialEq, Clone)]
struct LamParams {
    misiurewicz_mode: bool,
    p: usize,
    q: usize,
    angle_num: i64,
    angle_den: i64,
    depth: usize,
    mating_mode: bool,
    p2: usize,
    q2: usize,
}

// ── App struct ────────────────────────────────────────────────────────────────

#[sketch_app]
struct LaminationsSketch {
    /// Toggle between satellite (p/q) and Misiurewicz mode
    misiurewicz_mode: bool,

    // ── Satellite parameters (used when !misiurewicz_mode) ──
    #[param(slider, min = 1, max = 20, step = 1)]
    p: usize,

    #[param(slider, min = 2, max = 20, step = 1)]
    q: usize,

    // ── Misiurewicz parameters (used when misiurewicz_mode) ──
    #[param(slider, min = 1, max = 60, step = 1)]
    angle_num: i64,

    #[param(slider, min = 2, max = 60, step = 1)]
    angle_den: i64,

    // ── Common ──
    #[param(slider, min = 1, max = 15, step = 1)]
    depth: usize,

    // ── Mating ──
    mating_mode: bool,

    /// Draw the second mating lamination outside the unit disk via z → 1/z
    mating_exterior: bool,

    #[param(slider, min = 1, max = 20, step = 1)]
    p2: usize,

    #[param(slider, min = 2, max = 20, step = 1)]
    q2: usize,

    // ── Visual ──
    #[param(slider, min = 10.0, max = 200.0)]
    scale: f64,

    /// Colour leaves by generation (false = monochrome for plotting)
    generation_color: bool,

    /// Draw leaves as circular arcs perpendicular to the unit circle (hyperbolic geodesics)
    hyperbolic_arcs: bool,

    // ── Preset management ──
    save_preset_name: String,
    save_preset: bool,
    load_preset_name: String,
    load_preset: bool,
    refresh_presets: bool,

    // ── Cache (hidden from UI) ──
    #[skip]
    #[serde(skip)]
    cache_valid: bool,
    #[skip]
    #[serde(skip)]
    cached_params: LamParams,
    /// Pre-converted leaf segments grouped by generation: cached_leaves[g] = Vec of (p1, p2)
    #[skip]
    #[serde(skip)]
    cached_leaves: Vec<Vec<((f64, f64), (f64, f64))>>,
    /// Same for the mating's second lamination (reflected θ → 1−θ)
    #[skip]
    #[serde(skip)]
    cached_leaves2: Vec<Vec<((f64, f64), (f64, f64))>>,
    #[skip]
    #[serde(skip)]
    cached_error: String,
}

impl Default for LaminationsSketch {
    fn default() -> Self {
        Self {
            misiurewicz_mode: false,
            p: 1,
            q: 3,
            angle_num: 1,
            angle_den: 6,
            depth: 8,
            mating_mode: false,
            mating_exterior: false,
            p2: 1,
            q2: 2,
            scale: 50.0,
            generation_color: false,
            hyperbolic_arcs: false,
            save_preset_name: String::new(),
            save_preset: false,
            load_preset_name: String::new(),
            load_preset: false,
            refresh_presets: false,
            cache_valid: false,
            cached_params: LamParams::default(),
            cached_leaves: Vec::new(),
            cached_leaves2: Vec::new(),
            cached_error: String::new(),
        }
    }
}

// ── Coordinate helpers ────────────────────────────────────────────────────────

/// θ=0 → right (3 o'clock); y increases downward (page coordinates).
/// Coordinates are on the unit circle (radius = 1); use `sketch.scale()` to size the drawing.
fn angle_to_pt(theta: f64) -> (f64, f64) {
    let t = 2.0 * PI * theta;
    (t.cos(), t.sin())
}

fn leaf_to_pts(leaf: &(Rational64, Rational64)) -> ((f64, f64), (f64, f64)) {
    let a = *leaf.0.numer() as f64 / *leaf.0.denom() as f64;
    let b = *leaf.1.numer() as f64 / *leaf.1.denom() as f64;
    (angle_to_pt(a), angle_to_pt(b))
}

/// Convert a `Generations` map into a Vec indexed by generation.
/// All coordinates lie on the unit circle; apply `sketch.scale()` at render time.
fn generations_to_canvas(
    gens: &HashMap<usize, Vec<(Rational64, Rational64)>>,
    reflect: bool,
) -> Vec<Vec<((f64, f64), (f64, f64))>> {
    let max_gen = *gens.keys().max().unwrap_or(&0);
    let mut by_gen: Vec<Vec<((f64, f64), (f64, f64))>> = vec![Vec::new(); max_gen + 1];
    let one = Rational64::new(1, 1);

    for (&g, leaves) in gens {
        for leaf in leaves {
            let leaf_to_use = if reflect {
                // Mating reflection: θ → 1 − θ
                match normalize_leaf(one - leaf.0, one - leaf.1) {
                    Some(rl) => rl,
                    None => continue,
                }
            } else {
                *leaf
            };
            by_gen[g].push(leaf_to_pts(&leaf_to_use));
        }
    }
    by_gen
}

// ── Colour helpers ────────────────────────────────────────────────────────────

/// Pick a colour for generation `g` out of `max_gen`.
/// For `generation_color = false` the lamination is monochrome (black / dark red for mating).
/// For `generation_color = true` opacity fades with depth.
fn leaf_color(g: usize, max_gen: usize, generation_color: bool, is_second: bool) -> Color {
    let base = if is_second { Color::DARK_RED } else { Color::DARK_BLUE };
    if !generation_color {
        return if is_second { Color::DARK_RED } else { Color::BLACK };
    }
    let opacity = (1.0 - 0.75 * (g as f32 / max_gen.max(1) as f32)).max(0.12);
    base.with_opacity(opacity)
}

// ── Leaf drawing ─────────────────────────────────────────────────────────────

/// Draw a single leaf either as a straight chord or as a hyperbolic geodesic arc.
///
/// A circular arc is perpendicular to the unit circle iff its center `c` satisfies
/// `P·c = 1` for both endpoints P₁ and P₂. Solving gives:
///   c = (cos(φ_avg) / cos(φ_half), sin(φ_avg) / cos(φ_half))
///   r = |tan(φ_half)|
/// where φ_avg = (φ₁+φ₂)/2 and φ_half = (φ₂-φ₁)/2.
/// The center lies outside the unit disk on the opposite side of the chord from the origin.
/// Normalising the sweep to (−π, π] selects the arc that stays inside the disk.
fn draw_leaf(sketch: &mut Sketch, p1: (f64, f64), p2: (f64, f64), hyperbolic: bool) {
    if !hyperbolic {
        sketch.polyline(vec![p1, p2], false);
        return;
    }

    let phi1 = p1.1.atan2(p1.0);
    let phi2 = p2.1.atan2(p2.0);
    let phi_half = (phi2 - phi1) / 2.0;
    let cos_ph = phi_half.cos();

    if cos_ph.abs() < 1e-9 {
        // Chord is a diameter — the geodesic is the straight line itself
        sketch.polyline(vec![p1, p2], false);
        return;
    }

    let phi_avg = (phi1 + phi2) / 2.0;
    let cx = phi_avg.cos() / cos_ph;
    let cy = phi_avg.sin() / cos_ph;
    let r = phi_half.tan().abs();

    let alpha1 = (p1.1 - cy).atan2(p1.0 - cx);
    let alpha2 = (p2.1 - cy).atan2(p2.0 - cx);

    // Normalize sweep to (−π, π] — this always picks the arc inside the unit disk
    let mut sweep = alpha2 - alpha1;
    if sweep > PI {
        sweep -= 2.0 * PI;
    } else if sweep <= -PI {
        sweep += 2.0 * PI;
    }

    sketch.arc(cx, cy, r, r, alpha1, sweep, 0.0);
}

/// Draw the image outside the unit disk of either a straight chord or a hyperbolic
/// geodesic arc, mapped via z̄ → 1/z.
///
/// The stored points `p1`, `p2` are the mating-reflected (θ → 1−θ) endpoints,
/// equal to Q̄_i (complex conjugates of the original f₂ angles Q_i).
/// We sample N+1 points along the source curve (chord or geodesic arc from Q_1
/// to Q_2), apply z̄ → 1/z = z̄/|z|² to each, and draw the result as a polyline.
fn draw_leaf_exterior(sketch: &mut Sketch, p1: (f64, f64), p2: (f64, f64), hyperbolic: bool) {
    // Recover the original f₂ angles by undoing the θ → 1−θ reflection
    let q1 = (p1.0, -p1.1);
    let q2 = (p2.0, -p2.1);

    const N: usize = 64;

    // Returns the point on the source curve at parameter t ∈ [0, 1]
    let source_pt: Box<dyn Fn(f64) -> (f64, f64)> = if hyperbolic {
        let phi1 = q1.1.atan2(q1.0);
        let phi2 = q2.1.atan2(q2.0);
        let phi_half = (phi2 - phi1) / 2.0;
        let cos_ph = phi_half.cos();

        if cos_ph.abs() < 1e-9 {
            // Diameter: geodesic is the diameter itself
            Box::new(move |t: f64| {
                ((1.0 - t) * q1.0 + t * q2.0, (1.0 - t) * q1.1 + t * q2.1)
            })
        } else {
            let phi_avg = (phi1 + phi2) / 2.0;
            let cx = phi_avg.cos() / cos_ph;
            let cy = phi_avg.sin() / cos_ph;
            let r = phi_half.tan().abs();

            let alpha1 = (q1.1 - cy).atan2(q1.0 - cx);
            let alpha2 = (q2.1 - cy).atan2(q2.0 - cx);
            let mut sweep = alpha2 - alpha1;
            if sweep > PI {
                sweep -= 2.0 * PI;
            } else if sweep <= -PI {
                sweep += 2.0 * PI;
            }

            Box::new(move |t: f64| {
                let angle = alpha1 + t * sweep;
                (cx + r * angle.cos(), cy + r * angle.sin())
            })
        }
    } else {
        Box::new(move |t: f64| {
            ((1.0 - t) * q1.0 + t * q2.0, (1.0 - t) * q1.1 + t * q2.1)
        })
    };

    let pts: Vec<(f64, f64)> = (0..=N)
        .map(|i| {
            let (x, y) = source_pt(i as f64 / N as f64);
            let r2 = x * x + y * y;
            (x / r2, y / r2) // z̄ → 1/z̄ = z̄ / |z|²
        })
        .collect();

    sketch.polyline(pts, false);
}

// ── Preset helpers ────────────────────────────────────────────────────────────

impl LaminationsSketch {
    fn to_saved_params(&self) -> SavedParams {
        SavedParams {
            misiurewicz_mode: Some(self.misiurewicz_mode),
            p: Some(self.p),
            q: Some(self.q),
            angle_num: Some(self.angle_num),
            angle_den: Some(self.angle_den),
            depth: Some(self.depth),
            mating_mode: Some(self.mating_mode),
            p2: Some(self.p2),
            q2: Some(self.q2),
            scale: Some(self.scale),
            generation_color: Some(self.generation_color),
        }
    }

    fn from_saved_params(&mut self, saved: SavedParams) {
        if let Some(v) = saved.misiurewicz_mode {
            self.misiurewicz_mode = v;
        }
        if let Some(v) = saved.p {
            self.p = v;
        }
        if let Some(v) = saved.q {
            self.q = v;
        }
        if let Some(v) = saved.angle_num {
            self.angle_num = v;
        }
        if let Some(v) = saved.angle_den {
            self.angle_den = v;
        }
        if let Some(v) = saved.depth {
            self.depth = v;
        }
        if let Some(v) = saved.mating_mode {
            self.mating_mode = v;
        }
        if let Some(v) = saved.p2 {
            self.p2 = v;
        }
        if let Some(v) = saved.q2 {
            self.q2 = v;
        }
        if let Some(v) = saved.scale {
            self.scale = v;
        }
        if let Some(v) = saved.generation_color {
            self.generation_color = v;
        }
    }

    fn write_preset(&self, name: &str) -> anyhow::Result<()> {
        save_preset("laminations", name, &self.to_saved_params())
    }

    fn read_preset(&mut self, name: &str) -> anyhow::Result<()> {
        let saved: SavedParams = load_preset("laminations", name)?;
        self.from_saved_params(saved);
        Ok(())
    }

    /// Compute the primary lamination and return canvas-ready leaf groups.
    fn compute_primary(
        &self,
    ) -> anyhow::Result<Vec<Vec<((f64, f64), (f64, f64))>>> {
        let gens = if self.misiurewicz_mode {
            let theta = Rational64::new(self.angle_num, self.angle_den);
            build_misiurewicz_lamination(theta, self.depth)?
        } else {
            let portrait = find_alpha_portrait(self.p as i64, self.q as u32)?;
            build_lamination(&portrait, self.depth)
        };
        Ok(generations_to_canvas(&gens, false))
    }

    /// Compute the second (mating) lamination with θ → 1−θ reflection.
    fn compute_mating(&self) -> anyhow::Result<Vec<Vec<((f64, f64), (f64, f64))>>> {
        let portrait2 = find_alpha_portrait(self.p2 as i64, self.q2 as u32)?;
        let gens2 = build_lamination(&portrait2, self.depth);
        Ok(generations_to_canvas(&gens2, true))
    }
}

// ── App implementation ────────────────────────────────────────────────────────

impl App for LaminationsSketch {
    fn update(&mut self, sketch: &mut Sketch, ctx: &mut Context) -> anyhow::Result<()> {
        // ── Preset handling ────────────────────────────────────────────────────
        if self.save_preset {
            self.save_preset = false;
            if !self.save_preset_name.is_empty() {
                if let Err(e) = self.write_preset(&self.save_preset_name) {
                    eprintln!("Failed to save preset: {}", e);
                } else {
                    println!("Saved preset: {}", self.save_preset_name);
                }
            }
        }

        if self.load_preset {
            self.load_preset = false;
            if !self.load_preset_name.is_empty() {
                let name = self.load_preset_name.clone();
                if let Err(e) = self.read_preset(&name) {
                    eprintln!("Failed to load preset: {}", e);
                } else {
                    println!("Loaded preset: {}", name);
                    self.cache_valid = false;
                }
            }
        }

        if self.refresh_presets {
            self.refresh_presets = false;
            let presets = load_preset_list("laminations");
            ctx.inspect("available presets", format!("{:?}", presets));
        }

        // ── Cache invalidation ─────────────────────────────────────────────────
        let current_params = LamParams {
            misiurewicz_mode: self.misiurewicz_mode,
            p: self.p,
            q: self.q,
            angle_num: self.angle_num,
            angle_den: self.angle_den,
            depth: self.depth,
            mating_mode: self.mating_mode,
            p2: self.p2,
            q2: self.q2,
        };

        if !self.cache_valid || current_params != self.cached_params {
            self.cached_error = String::new();

            match self.compute_primary() {
                Ok(leaves) => self.cached_leaves = leaves,
                Err(e) => {
                    self.cached_error = e.to_string();
                    self.cached_leaves = Vec::new();
                }
            }

            if self.mating_mode {
                match self.compute_mating() {
                    Ok(leaves) => self.cached_leaves2 = leaves,
                    Err(e) => {
                        if !self.cached_error.is_empty() {
                            self.cached_error.push_str(" | ");
                        }
                        self.cached_error.push_str(&format!("mating: {}", e));
                        self.cached_leaves2 = Vec::new();
                    }
                }
            } else {
                self.cached_leaves2 = Vec::new();
            }

            self.cached_params = current_params;
            self.cache_valid = true;
        }

        // ── Inspector ──────────────────────────────────────────────────────────
        if !self.cached_error.is_empty() {
            ctx.inspect("error", &self.cached_error);
        }
        let total_leaves: usize = self.cached_leaves.iter().map(|g| g.len()).sum();
        ctx.inspect("leaves", total_leaves);
        ctx.inspect("generations", self.cached_leaves.len().saturating_sub(1));

        // ── Drawing ────────────────────────────────────────────────────────────
        sketch.scale(self.scale);

        // Unit circle boundary
        sketch.color(Color::GRAY).stroke_width(0.2 * Unit::Mm);
        sketch.circle(0.0, 0.0, 1.0);

        // Primary lamination (gen 0 thickest, opacity fades)
        let max_gen = self.cached_leaves.len().saturating_sub(1);
        for (g, gen_leaves) in self.cached_leaves.iter().enumerate() {
            if gen_leaves.is_empty() {
                continue;
            }
            let color = leaf_color(g, max_gen, self.generation_color, false);
            let width_mm = if g == 0 {
                0.4
            } else {
                (0.35 - 0.02 * g as f64).max(0.1)
            };
            sketch.color(color).stroke_width(width_mm * Unit::Mm);
            for &(p1, p2) in gen_leaves {
                draw_leaf(sketch, p1, p2, self.hyperbolic_arcs);
            }
        }

        // Mating second lamination
        if self.mating_mode && !self.cached_leaves2.is_empty() {
            let max_gen2 = self.cached_leaves2.len().saturating_sub(1);
            for (g, gen_leaves) in self.cached_leaves2.iter().enumerate() {
                if gen_leaves.is_empty() {
                    continue;
                }
                let color = leaf_color(g, max_gen2, self.generation_color, true);
                let width_mm = if g == 0 {
                    0.4
                } else {
                    (0.35 - 0.02 * g as f64).max(0.1)
                };
                sketch.color(color).stroke_width(width_mm * Unit::Mm);
                for &(p1, p2) in gen_leaves {
                    if self.mating_exterior {
                        draw_leaf_exterior(sketch, p1, p2, self.hyperbolic_arcs);
                    } else {
                        draw_leaf(sketch, p1, p2, self.hyperbolic_arcs);
                    }
                }
            }
        }

        Ok(())
    }
}

fn main() -> Result {
    LaminationsSketch::runner()
        .with_page_size_options(PageSize::A5H)
        .with_layout_options(LayoutOptions::Off)
        .run()
}
