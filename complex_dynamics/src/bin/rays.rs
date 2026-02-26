use complex_dynamics::*;
use whiskers::prelude::*;
use vsvg::Color;
use serde::{Deserialize, Serialize};
use num_complex::Complex;
use rayon::prelude::*;

// ── Serialisable parameter snapshot ──────────────────────────────────────────

#[derive(Serialize, Deserialize, Clone)]
struct SavedParams {
    denominator: Option<usize>,
    c_real: Option<f64>,
    c_imaginary: Option<f64>,
    draw_level_sets: Option<bool>,
    only_closest_level_set: Option<bool>,
    level_set_spacing: Option<usize>,
    level_set_refinement: Option<usize>,
    draw_internal_rays: Option<bool>,
    adaptive_refinement: Option<bool>,
    adaptive_threshold: Option<f64>,
}

// ── App struct ────────────────────────────────────────────────────────────────

#[sketch_app]
struct ExternalRaySketch {
    #[param(slider, min = 1, max = 2048)]
    denominator: usize,

    #[param(slider, min = -1.8, max = 1.5, step = 0.00000001)]
    c_real: f64,

    #[param(slider, min = -1.8, max = 1.5, step = 0.00000001)]
    c_imaginary: f64,

    #[param(slider, min = 0.5, max = 500.0)]
    scale: f64,

    draw_level_sets: bool,

    only_closest_level_set: bool,

    draw_internal_rays: bool,

    #[param(slider, min = 1, max = 100)]
    level_set_spacing: usize,

    #[param(slider, min = 1, max = 256)]
    level_set_refinement: usize,

    adaptive_refinement: bool,

    #[param(slider, min = 0.001, max = 0.5)]
    adaptive_threshold: f64,

    save_preset_name: String,
    save_preset: bool,
    load_preset_name: String,
    load_preset: bool,
    refresh_presets: bool,

    #[skip]
    #[serde(skip)]
    cache_valid: bool,
    #[skip]
    #[serde(skip)]
    cached_denominator: usize,
    #[skip]
    #[serde(skip)]
    cached_c_real: f64,
    #[skip]
    #[serde(skip)]
    cached_c_imaginary: f64,
    #[skip]
    #[serde(skip)]
    cached_polylines: Vec<Vec<(f64, f64)>>,
    #[skip]
    #[serde(skip)]
    cached_rays: Vec<CachedRay>,
    #[skip]
    #[serde(skip)]
    cached_adaptive_refinement: bool,
    #[skip]
    #[serde(skip)]
    cached_level_set_refinement: usize,
    #[skip]
    #[serde(skip)]
    cached_adaptive_threshold: f64,
    #[skip]
    #[serde(skip)]
    cached_draw_internal_rays: bool,
    #[skip]
    #[serde(skip)]
    cached_internal_polylines: Vec<Vec<(f64, f64)>>,
}

impl Default for ExternalRaySketch {
    fn default() -> Self {
        Self {
            denominator: 15,
            c_real: 0.0,
            c_imaginary: 1.0,
            scale: 10.0,
            draw_level_sets: false,
            only_closest_level_set: false,
            draw_internal_rays: false,
            level_set_spacing: 10,
            level_set_refinement: 4,
            adaptive_refinement: false,
            adaptive_threshold: 0.05,
            save_preset_name: String::new(),
            save_preset: false,
            load_preset_name: String::new(),
            load_preset: false,
            refresh_presets: false,
            cache_valid: false,
            cached_denominator: 0,
            cached_c_real: 0.0,
            cached_c_imaginary: 0.0,
            cached_polylines: Vec::new(),
            cached_rays: Vec::new(),
            cached_adaptive_refinement: false,
            cached_level_set_refinement: 0,
            cached_adaptive_threshold: 0.0,
            cached_draw_internal_rays: false,
            cached_internal_polylines: Vec::new(),
        }
    }
}

// ── Preset helpers (delegate to complex_dynamics preset utilities) ─────────────

impl ExternalRaySketch {
    fn to_saved_params(&self) -> SavedParams {
        SavedParams {
            denominator: Some(self.denominator),
            c_real: Some(self.c_real),
            c_imaginary: Some(self.c_imaginary),
            draw_level_sets: Some(self.draw_level_sets),
            only_closest_level_set: Some(self.only_closest_level_set),
            level_set_spacing: Some(self.level_set_spacing),
            level_set_refinement: Some(self.level_set_refinement),
            draw_internal_rays: Some(self.draw_internal_rays),
            adaptive_refinement: Some(self.adaptive_refinement),
            adaptive_threshold: Some(self.adaptive_threshold),
        }
    }

    fn from_saved_params(&mut self, saved: SavedParams) {
        if let Some(v) = saved.denominator { self.denominator = v; }
        if let Some(v) = saved.c_real { self.c_real = v; }
        if let Some(v) = saved.c_imaginary { self.c_imaginary = v; }
        if let Some(v) = saved.draw_level_sets { self.draw_level_sets = v; }
        if let Some(v) = saved.only_closest_level_set { self.only_closest_level_set = v; }
        if let Some(v) = saved.level_set_spacing { self.level_set_spacing = v; }
        if let Some(v) = saved.level_set_refinement { self.level_set_refinement = v; }
        if let Some(v) = saved.draw_internal_rays { self.draw_internal_rays = v; }
        if let Some(v) = saved.adaptive_refinement { self.adaptive_refinement = v; }
        if let Some(v) = saved.adaptive_threshold { self.adaptive_threshold = v; }
    }

    fn write_preset(&self, name: &str) -> anyhow::Result<()> {
        save_preset("rays", name, &self.to_saved_params())
    }

    fn read_preset(&mut self, name: &str) -> anyhow::Result<()> {
        let saved: SavedParams = load_preset("rays", name)?;
        self.from_saved_params(saved);
        Ok(())
    }
}

// ── App implementation ────────────────────────────────────────────────────────

impl App for ExternalRaySketch {
    fn update(&mut self, sketch: &mut Sketch, ctx: &mut Context) -> anyhow::Result<()> {
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
                }
            }
        }

        if self.refresh_presets {
            self.refresh_presets = false;
            let presets = load_preset_list("rays");
            ctx.inspect("Available presets", format!("{:?}", presets));
        }

        let c = Complex::new(self.c_real, self.c_imaginary);

        // ── Cache invalidation ────────────────────────────────────────────────
        let needs_recompute = !self.cache_valid
            || self.denominator != self.cached_denominator
            || self.c_real != self.cached_c_real
            || self.c_imaginary != self.cached_c_imaginary
            || self.adaptive_refinement != self.cached_adaptive_refinement
            || (!self.adaptive_refinement
                && self.level_set_refinement != self.cached_level_set_refinement)
            || (self.adaptive_refinement
                && self.adaptive_threshold != self.cached_adaptive_threshold);

        if needs_recompute {
            let denominator = self.denominator;

            if self.adaptive_refinement {
                // ── Adaptive refinement ───────────────────────────────────────
                let threshold = self.adaptive_threshold;
                const MAX_RAYS: usize = 32768;

                // Compute base rays
                let mut rays: Vec<CachedRay> = (0..denominator)
                    .into_par_iter()
                    .map(|k| {
                        let angle = k as f64 / denominator as f64;
                        let points =
                            draw_ray_iteration_f64(22.0, angle, c, 1e4 / 4.04, 1e-10);
                        CachedRay { angle, points, is_base: true }
                    })
                    .collect();

                // Adaptive refinement loop
                loop {
                    let mut mid_angles: Vec<f64> = Vec::new();
                    for i in 0..rays.len() {
                        let next_i = (i + 1) % rays.len();
                        let land_curr =
                            rays[i].points.last().map(|p| p.z).unwrap_or_default();
                        let land_next =
                            rays[next_i].points.last().map(|p| p.z).unwrap_or_default();
                        let dist = (land_curr - land_next).norm();
                        let mut angle_diff = rays[i].angle - rays[next_i].angle;
                        angle_diff = (if angle_diff > 0.5 {
                            angle_diff - 1.0
                        } else {
                            angle_diff
                        })
                        .abs();

                        if dist > threshold && angle_diff > 1e-10 {
                            let a = rays[i].angle;
                            let b = rays[next_i].angle;
                            let mid_angle = if next_i == 0 {
                                // Wrap-around: midpoint crosses the 0/1 boundary
                                ((a + b + 1.0) / 2.0) % 1.0
                            } else {
                                (a + b) / 2.0
                            };
                            mid_angles.push(mid_angle);
                        }
                    }

                    if mid_angles.is_empty() || rays.len() + mid_angles.len() > MAX_RAYS {
                        break;
                    }

                    let new_rays: Vec<CachedRay> = mid_angles
                        .par_iter()
                        .map(|&angle| {
                            let points =
                                draw_ray_iteration_f64(22.0, angle, c, 1e4 / 4.04, 1e-10);
                            CachedRay { angle, points, is_base: false }
                        })
                        .collect();
                    println!("new rays {}", new_rays.len());

                    // Merge two sorted lists by angle
                    let mut merged = Vec::with_capacity(rays.len() + new_rays.len());
                    let mut old_iter = rays.into_iter().peekable();
                    let mut new_iter = new_rays.into_iter().peekable();

                    loop {
                        match (old_iter.peek(), new_iter.peek()) {
                            (Some(old), Some(new)) => {
                                if old.angle <= new.angle {
                                    merged.push(old_iter.next().unwrap());
                                } else {
                                    merged.push(new_iter.next().unwrap());
                                }
                            }
                            (Some(_), None) => {
                                merged.extend(old_iter);
                                break;
                            }
                            (None, Some(_)) => {
                                merged.extend(new_iter);
                                break;
                            }
                            (None, None) => break,
                        }
                    }

                    rays = merged;
                }

                // Compute polylines for base rays
                self.cached_polylines = rays
                    .iter()
                    .filter(|r| r.is_base)
                    .map(|r| compute_ray_polyline(&r.points, 10.0))
                    .collect();

                self.cached_rays = rays;
            } else {
                // ── Uniform refinement ────────────────────────────────────────
                let refinement = self.level_set_refinement;
                let total_rays = denominator * refinement;

                let ray_data: Vec<(Vec<RayPoint>, Vec<(f64, f64)>)> = (0..total_rays)
                    .into_par_iter()
                    .map(|k| {
                        let ray_points =
                            draw_ray_iteration(22.0, k, total_rays, c, 1e12, 1e-10);
                        let polyline = compute_ray_polyline(&ray_points, 10.0);
                        (ray_points, polyline)
                    })
                    .collect();

                self.cached_rays = ray_data
                    .iter()
                    .enumerate()
                    .map(|(idx, (pts, _))| CachedRay {
                        angle: idx as f64 / total_rays as f64,
                        points: pts.clone(),
                        is_base: idx % refinement == 0,
                    })
                    .collect();

                self.cached_polylines = ray_data
                    .into_iter()
                    .enumerate()
                    .filter_map(|(idx, (_, poly))| {
                        if idx % refinement == 0 { Some(poly) } else { None }
                    })
                    .collect();
            }

            self.cached_denominator = self.denominator;
            self.cached_c_real = self.c_real;
            self.cached_c_imaginary = self.c_imaginary;
            self.cached_adaptive_refinement = self.adaptive_refinement;
            self.cached_level_set_refinement = self.level_set_refinement;
            self.cached_adaptive_threshold = self.adaptive_threshold;
            self.cache_valid = true;
        }

        // ── Internal rays ─────────────────────────────────────────────────────
        let needs_internal_recompute =
            needs_recompute || (self.draw_internal_rays && !self.cached_draw_internal_rays);

        if self.draw_internal_rays && needs_internal_recompute {
            let cycle = find_attracting_cycle(c);

            if let Some(ref cycle) = cycle {
                let base_rays: Vec<&CachedRay> =
                    self.cached_rays.iter().filter(|r| r.is_base).collect();

                let internal_data: Vec<Vec<(f64, f64)>> = base_rays
                    .par_iter()
                    .filter_map(|ext_cached_ray| {
                        if let Some((angle, basin_idx)) =
                            find_internal_angle(&ext_cached_ray.points, cycle, c)
                        {
                            let int_ray = draw_internal_ray(angle, c, cycle, basin_idx);
                            let polyline = compute_ray_polyline(&int_ray, 10.0);
                            if !polyline.is_empty() { Some(polyline) } else { None }
                        } else {
                            None
                        }
                    })
                    .collect();

                self.cached_internal_polylines = internal_data;
            } else {
                self.cached_internal_polylines = Vec::new();
            }
        } else if !self.draw_internal_rays {
            self.cached_internal_polylines = Vec::new();
        }
        self.cached_draw_internal_rays = self.draw_internal_rays;

        // ── Drawing ───────────────────────────────────────────────────────────
        sketch.scale(self.scale / 100.0);

        sketch.color(Color::DARK_GREEN).stroke_width(0.3 * Unit::Mm);
        for polyline_points in &self.cached_polylines {
            if !polyline_points.is_empty() {
                sketch.polyline(polyline_points.clone(), false);
            }
        }

        if self.draw_internal_rays && !self.cached_internal_polylines.is_empty() {
            sketch.color(Color::DARK_RED).stroke_width(0.3 * Unit::Mm);
            for polyline_points in &self.cached_internal_polylines {
                if !polyline_points.is_empty() {
                    sketch.polyline(polyline_points.clone(), false);
                }
            }
        }

        if self.draw_level_sets && !self.cached_rays.is_empty() {
            sketch.color(Color::DARK_BLUE).stroke_width(0.2 * Unit::Mm);

            let min_points = self.cached_rays.iter().map(|r| r.points.len()).min().unwrap_or(0);

            let indices_to_draw: Vec<usize> = if self.only_closest_level_set {
                if min_points > 0 { vec![min_points - 1] } else { vec![] }
            } else {
                (0..min_points).step_by(self.level_set_spacing).collect()
            };

            for point_idx in indices_to_draw {
                let mut level_set: Vec<(f64, f64)> = Vec::new();
                for ray in &self.cached_rays {
                    if point_idx < ray.points.len() {
                        let pt = &ray.points[point_idx];
                        if pt.z.norm() < 10.0 {
                            level_set.push((pt.z.re * 100.0, pt.z.im * 100.0));
                        }
                    }
                }
                if !level_set.is_empty() {
                    level_set.push(level_set[0]);
                    sketch.polyline(level_set, false);
                }
            }
        }

        Ok(())
    }
}

fn main() -> Result {
    ExternalRaySketch::runner()
        .with_page_size_options(PageSize::A5H)
        .with_layout_options(LayoutOptions::Off)
        .run()
}
