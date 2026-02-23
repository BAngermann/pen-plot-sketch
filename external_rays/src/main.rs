use whiskers::prelude::*;
use std::f64::consts::PI;
use vsvg::Color;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use num_complex::Complex;
use rayon::prelude::*;

#[derive(Clone, Debug)]
struct RayPoint {
    r: f64,
    z: Complex<f64>,
}

#[derive(Clone, Debug, Default)]
struct CachedRay {
    angle: f64,
    points: Vec<RayPoint>,
    is_base: bool,
}

#[derive(Clone, Debug)]
struct AttractingCycle {
    points: Vec<Complex<f64>>,
    period: usize,
    multiplier: Complex<f64>,
    is_super_attracting: bool,
    alpha: Complex<f64>,
}

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

#[sketch_app]
struct ExternalRaySketch {
    #[param(slider, min = 1, max = 2048)]
    denominator: usize,

    #[param(slider, min = -1.8, max = 1.5,step=0.00000001)]
    c_real: f64,

    #[param(slider, min = -1.8, max = 1.5,step=0.00000001)]
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

impl ExternalRaySketch {
    fn params_dir() -> PathBuf {
        PathBuf::from("parameters")
    }
    
    fn ensure_params_dir() -> anyhow::Result<()> {
        let dir = Self::params_dir();
        if !dir.exists() {
            fs::create_dir_all(&dir)?;
        }
        Ok(())
    }
    
    fn load_preset_list() -> Vec<String> {
        let dir = Self::params_dir();
        if !dir.exists() {
            return Vec::new();
        }
        
        let mut presets = Vec::new();
        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                if let Some(ext) = entry.path().extension() {
                    if ext == "json" {
                        if let Some(stem) = entry.path().file_stem() {
                            presets.push(stem.to_string_lossy().to_string());
                        }
                    }
                }
            }
        }
        presets.sort();
        presets
    }
    
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
    
    fn save_preset(&self, name: &str) -> anyhow::Result<()> {
        Self::ensure_params_dir()?;
        let path = Self::params_dir().join(format!("{}.json", name));
        let params = self.to_saved_params();
        let json = serde_json::to_string_pretty(&params)?;
        fs::write(path, json)?;
        Ok(())
    }
    
    fn load_preset(&mut self, name: &str) -> anyhow::Result<()> {
        let path = Self::params_dir().join(format!("{}.json", name));
        let json = fs::read_to_string(path)?;
        let params: SavedParams = serde_json::from_str(&json)?;
        self.from_saved_params(params);
        Ok(())
    }
}

impl App for ExternalRaySketch {
    fn update(&mut self, sketch: &mut Sketch, ctx: &mut Context) -> anyhow::Result<()> {
        if self.save_preset {
            self.save_preset = false;
            if !self.save_preset_name.is_empty() {
                if let Err(e) = self.save_preset(&self.save_preset_name) {
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
                if let Err(e) = self.load_preset(&name) {
                    eprintln!("Failed to load preset: {}", e);
                } else {
                    println!("Loaded preset: {}", name);
                }
            }
        }
        
        if self.refresh_presets {
            self.refresh_presets = false;
            let presets = Self::load_preset_list();
            ctx.inspect("Available presets", format!("{:?}", presets));
        }
        
        sketch.color(Color::DARK_RED).stroke_width(0.01 * Unit::Mm);
        
        let c = Complex::new(self.c_real, self.c_imaginary);
        



/// Compute √z choosing the branch consistent with a reference point `w`.
///
/// There are two square roots of any nonzero complex number; this picks whichever
/// one has a non-negative real inner product with `w`. When `w` varies continuously
/// along a path, this guarantees the result also varies continuously — i.e. it
/// analytically continues the square root along that path without jumping sheets.
fn continuous_sqrt(z: Complex<f64>, w: Complex<f64>) -> Complex<f64> {
    let mut t = z.sqrt();
    if (t.re * w.re + t.im * w.im) < 0.0 {
        t = -t;
    }
    t
}


// Simplify a polyline by removing redundant interior points. The first and last
// points are always kept. An interior point is removed if either:
//  - it is closer than `min_distance` to both its predecessor (last kept point)
//    and its successor (next original point), or
//  - the turning angle between the incoming and outgoing segments is less than
//    `angle_threshold` (in radians), meaning the three points are nearly collinear.
// Uses a single greedy forward pass; predecessor for angle/distance checks is the
// last point that was kept, not the original previous point.
fn simplify_polyline(points: &[(f64, f64)], angle_threshold: f64, min_distance: f64) -> Vec<(f64, f64)> {
    if points.len() <= 2 {
        return points.to_vec();
    }

    let mut result = Vec::with_capacity(points.len());
    result.push(points[0]);

    for i in 1..points.len() - 1 {
        let prev = *result.last().unwrap();
        let curr = points[i];
        let next = points[i + 1];

        let dist_prev = ((curr.0 - prev.0).powi(2) + (curr.1 - prev.1).powi(2)).sqrt();
        let dist_next = ((curr.0 - next.0).powi(2) + (curr.1 - next.1).powi(2)).sqrt();
        if dist_prev < min_distance && dist_next < min_distance {
            continue;
        }

        let v1 = (curr.0 - prev.0, curr.1 - prev.1);
        let v2 = (next.0 - curr.0, next.1 - curr.1);
        let cross = v1.0 * v2.1 - v1.1 * v2.0;
        let dot = v1.0 * v2.0 + v1.1 * v2.1;
        let angle = cross.atan2(dot).abs();
        if angle < angle_threshold {
            continue;
        }

        result.push(curr);
    }

    result.push(*points.last().unwrap());
    result
}

// Compute a simplified polyline from ray points (pure computation, no sketch access)
fn compute_ray_polyline(combined: &[RayPoint], visibility_threshold: f64) -> Vec<(f64, f64)> {
    let polyline_points: Vec<(f64, f64)> = combined.iter()
        .filter(|p| p.z.norm() < visibility_threshold)
        .map(|p| (p.z.re * 100.0, p.z.im * 100.0))
        .collect();

    let polyline_points = simplify_polyline(&polyline_points, PI/2880.0,  0.3  *  Unit::Mm.to_px::<f64>());
    polyline_points
}

/// Wrapper for draw_ray_iteration_f64 that takes a rational angle.
///
/// See draw_ray_iteration_f64 for detailed documentation.
fn draw_ray_iteration(level: f64, ang_num: usize, ang_den: usize, c: Complex<f64>, escape_radius: f64, min_potential: f64) -> Vec<RayPoint>
{
    let angle = ang_num as f64 / ang_den as f64;
    draw_ray_iteration_f64(level, angle, c, escape_radius, min_potential)
}

/// Douady-Hubbard Pulling-Back Method for Computing External Rays
///
/// This function implements the classic algorithm for tracing external rays of the Julia set
/// of f(z) = z² + c, based on analytically continuing the Böttcher coordinate (also called
/// the Riemann mapping) from infinity.
///
/// # Mathematical Background
///
/// The **Böttcher coordinate** φ(z) is a conformal map from the basin of infinity to the
/// exterior of the unit disk that conjugates f(z) = z² + c to the doubling map w ↦ w²:
///
///     φ(f(z)) = φ(z)²
///
/// This map is normalized so that φ(z)/z → 1 as z → ∞, and it can be written as:
///
///     φ(z) = lim_{n→∞} (f^n(z))^(1/2^n)
///
/// The **potential** V(z) = log₂|φ(z)| measures how far a point is from the Julia set
/// (the boundary of the filled Julia set K). Points with V(z) = V have |φ(z)| = 2^V.
///
/// An **external ray** at angle θ is the curve {z : arg(φ(z)) = 2πθ} for fixed θ ∈ [0,1).
/// These rays are the level curves of the argument of φ, and they approach the
/// Julia set as V → 0.
///
/// # The Algorithm: Why Forward Iteration + Square Roots Works
///
/// The key insight is that φ satisfies φ(f(z)) = φ(z)², which means:
///
///     φ(z) = √(φ(f(z)) - c)    (choosing the continuous branch)
///
/// Given an approximate position z on the ray at potential V and angle θ:
///
/// 1. **Forward iterate** z under f repeatedly: z → f(z) → f²(z) → ... → f^n(z)
///    Stop when |f^n(z)| exceeds escape_radius.
///    After n iterations, the potential has doubled n times: V(f^n(z)) ≈ V · 2^n
///    and the angle has also doubled n times (mod 1): arg(φ(f^n(z))) ≈ θ · 2^n (mod 1)
///
/// 2. **Replace the endpoint** with the exact point on the equipotential:
///    For large |z|, φ(z) ≈ z, so we set:
///        f^n(z) := 2^(V·2^n) · exp(2πi · θ · 2^n)
///    This is the exact Böttcher coordinate at potential V·2^n and angle θ·2^n.
///
/// 3. **Pull back via square roots**: Apply the inverse of f iteratively:
///        z_{n-1} := √(z_n - c)    (choosing the branch close to the original orbit)
///        z_{n-2} := √(z_{n-1} - c)
///        ...
///        z_0 := √(z_1 - c)
///    Each square root analytically continues φ^(-1), and choosing the branch closest to
///    the original forward orbit ensures we stay on the correct sheet of the Riemann surface.
///
/// The final z_0 is the corrected position on the ray at potential V and angle θ.
///
/// # Why This Is Numerically Stable
///
/// - Far from the Julia set (large |z|), the Böttcher coordinate φ(z) ≈ z is accurate,
///   so the replacement in step 2 is exact.
/// - The backward iteration via square roots is the analytic continuation of φ^(-1),
///   which is well-defined and smooth in the basin of infinity.
/// - By choosing escape_radius sufficiently big, we ensure the replacement happens where
///   φ ≈ z, minimizing the error introduced.
/// - The continuous square root (using the previous orbit point as a hint) ensures we
///   follow the correct branch, avoiding discontinuities.
///
/// This method, originally developed by Douady and Hubbard, is the standard algorithm
/// used in software like Wolf Jung's Mandel and is described in papers by Kawahira,
/// Schleicher, and others.
///
/// # Parameters
///
/// - `potential`: V(z) = log₂|φ(z)|, the log₂-potential. Determines distance from Julia set.
/// - `angle`: The angle θ of the ray (in [0,1), where 0 corresponds to the positive real axis).
/// - `z`: An approximate starting position on the ray (will be corrected).
/// - `c`: The parameter of the Julia set f(z) = z² + c.
/// - `escape_radius`: Forward iteration stops when |z| exceeds this. Larger → higher accuracy.
///
/// # Returns
///
/// The corrected position z on the external ray at potential V and angle θ.
fn riemann_iteration(potential: f64, angle: f64, z: Complex<f64>, c: Complex<f64>, escape_radius: f64) -> Complex<f64> {
    const LENGTH: usize = 16000;

    let mut orbit = [Complex::new(0.0, 0.0); LENGTH];
    let mut backward_orbit = [Complex::new(0.0, 0.0); LENGTH];
    let mut n: usize;

    // Step 1: Forward iterate until escape
    // Store the orbit sequence: orbit[0] → orbit[1] → ... → orbit[n]
    // where orbit[i+1] = f(orbit[i]) = orbit[i]² + c
    orbit[0] = z;
    n = 0;
    let mut potential_curr = potential;  // Tracks potential: V(f^i(z)) = V · 2^i
    let mut ang_curr = angle;           // Tracks angle: θ · 2^i (mod 1)

    for i in 0..(LENGTH-1) {
        if orbit[i].norm() > escape_radius {
            // Stop when orbit escapes to region where Böttcher coordinate φ ≈ z
            break;
        }
        orbit[i+1] = orbit[i] * orbit[i] + c;
        n += 1;
        potential_curr = 2.0 * potential_curr;  // Potential doubles: V(f(z)) = 2·V(z)
        ang_curr = (2.0 * ang_curr) % 1.0;     // Angle doubles: arg(φ(f(z))) = 2·arg(φ(z))
    }

    // Step 2: Replace endpoint with exact Böttcher coordinate
    // For large |z|, we have φ(z) ≈ z, so we can set the endpoint to the exact value:
    //   φ(f^n(z)) = 2^(V·2^n) · exp(2πi · θ · 2^n)
    // where V·2^n = potential_curr and θ·2^n = ang_curr (mod 1).
    backward_orbit[n] = Complex::from_polar(2.0_f64.powf(potential_curr), 2.0 * PI * ang_curr);

    // Step 3: Pull back via continuous square roots
    // Apply the inverse of f iteratively: f^(-1)(w) = √(w - c)
    // This analytically continues φ^(-1) along the ray, using the original orbit
    // as a guide to choose the correct branch of the square root at each step.
    //
    // From φ(f(z)) = φ(z)², we have φ(z) = √(φ(f(z))), so:
    //   backward_orbit[i-1] = √(backward_orbit[i] - c)
    // The continuous square root (continuous_sqrt) picks the branch closest to orbit[i-1],
    // ensuring we stay on the correct sheet of the Riemann surface.
    for i in (1..=n).rev() {
        backward_orbit[i-1] = continuous_sqrt(backward_orbit[i] - c, orbit[i-1]);
    }

    backward_orbit[0]
}

/// Trace an External Ray from Infinity to the Julia Set
///
/// This function traces a complete external ray by repeatedly calling `riemann_iteration`
/// at progressively smaller potential levels, moving from infinity toward the Julia set.
///
/// # The Ray-Tracing Strategy
///
/// External rays spiral in toward the Julia set as the potential V = log₂|φ(z)| decreases
/// from ∞ down to 0 (the Julia set boundary). To trace a ray:
///
/// 1. Start at a large potential where |φ(z)| = 2^V exceeds escape_radius.
///    At this distance, the Böttcher coordinate φ(z) ≈ z is nearly exact.
///
/// 2. Gradually decrease V by multiplying by step_factor = 2^(-1/80) ≈ 0.9914, creating
///    densely-spaced sample points along the ray.
///
/// 3. At each step, use the previous point as an initial guess and call `riemann_iteration`
///    to compute the corrected position on the ray at the new potential level.
///
/// 4. Stop when V drops below min_potential (close to the Julia set, where numerical
///    precision limits further refinement).
///
/// # Why Gradual Stepping with a Previous Guess Works
///
/// The external ray is a smooth curve, and consecutive sample points are close together
/// in the complex plane. By using the previous point as the initial approximation for
/// `riemann_iteration`, we provide a good starting guess that:
///
/// - Reduces the number of forward iterations needed (since we're already close to the ray)
/// - Ensures the backward square-root continuation follows the correct path
/// - Maintains smoothness and avoids jumping to a different branch
///
/// The step_factor controls the density of sample points. Values closer to 1 produce
/// more points but increase computation time. 2^(-1/80) provides a good balance.
///
/// # Parameters
///
/// - `level`: Starting log₂-potential (usually chosen so that 2^level > escape_radius)
/// - `angle`: The angle θ of the ray (in [0,1), where 0 corresponds to the positive real axis)
/// - `c`: The parameter of the Julia set f(z) = z² + c
/// - `escape_radius`: Forward iteration stops when |z| exceeds this (larger → higher accuracy)
/// - `min_potential`: Stop tracing when the log₂-potential drops below this
///
/// # Returns
///
/// A vector of `RayPoint` structs containing the log₂-potential and position z at each step.
fn draw_ray_iteration_f64(level: f64, angle: f64, c: Complex<f64>, escape_radius: f64, min_potential: f64) -> Vec<RayPoint>
{
    // Geometric decay factor: 80 steps per halving of potential
    let step_factor: f64 = 2.0_f64.powf(-1.0/80.0);

    let mut points = Vec::new();

    // Increase potential until |φ(z)| = 2^potential exceeds escape_radius,
    // ensuring the first point is in the region where φ(z) ≈ z
    let mut potential = level;
    while 2.0_f64.powf(potential) < escape_radius {
        potential *= 2.0;
    }

    // Initial point: exact Böttcher coordinate at this potential and angle θ
    // For large |z|, φ(z) ≈ z, so |z| = 2^potential and arg(z) = 2πθ
    let mut z = Complex::from_polar(2.0_f64.powf(potential), 2.0 * PI * angle);
    let mut prev_z;

    points.push(RayPoint { r: potential, z });

    // Step along the ray, decreasing potential geometrically toward the Julia set
    loop {
        potential *= step_factor;
        prev_z = z;
        // Use the previous point as initial guess; riemann_iteration corrects it
        // to lie exactly on the ray at the new potential level
        z = riemann_iteration(potential, angle, prev_z, c, escape_radius);

        points.push(RayPoint { r: potential, z });

        if potential <= min_potential {
            break;
        }
    }

    points
}

/// Find an attracting cycle for f(z) = z² + c by iterating the critical orbit.
/// Returns None if c is outside the Mandelbrot set or on its boundary.
fn find_attracting_cycle(c: Complex<f64>) -> Option<AttractingCycle> {
    // Iterate the critical orbit to let it settle
    let mut z = Complex::new(0.0, 0.0);
    for _ in 0..2000 {
        z = z * z + c;
        if z.norm() > 1e10 {
            return None;
        }
    }

    // Detect period: find smallest p >= 1 such that f^p(z) ≈ z
    let z_start = z;
    let mut z_test = z_start;
    let mut period = 0;
    for p in 1..=256 {
        z_test = z_test * z_test + c;
        if (z_test - z_start).norm() < 1e-8 {
            period = p;
            break;
        }
    }
    if period == 0 {
        return None;
    }

    // Newton-refine the periodic point: solve f^p(z) = z
    let mut z_curr = z_start;
    for _ in 0..50 {
        let mut w = z_curr;
        let mut dw = Complex::new(1.0, 0.0);
        for _ in 0..period {
            dw = 2.0 * w * dw;
            w = w * w + c;
        }
        let denom = dw - Complex::new(1.0, 0.0);
        if denom.norm() < 1e-30 {
            break;
        }
        let correction = (w - z_curr) / denom;
        z_curr = z_curr - correction;
        if correction.norm() < 1e-15 {
            break;
        }
    }

    // Collect cycle points
    let mut points = Vec::with_capacity(period);
    let mut z_pt = z_curr;
    for _ in 0..period {
        points.push(z_pt);
        z_pt = z_pt * z_pt + c;
    }

    // Compute multiplier: λ = ∏ f'(z_i) = ∏ 2·z_i
    let mut multiplier = Complex::new(1.0, 0.0);
    for pt in &points {
        multiplier = multiplier * (2.0 * pt);
    }

    if multiplier.norm() >= 1.0 {
        return None;
    }

    let is_super_attracting = multiplier.norm() < 1e-10;

    // For super-attracting case, compute α where g(z) ≈ α·z² near z=0
    let alpha = if is_super_attracting {
        let eps = Complex::new(1e-6, 0.0);
        let mut w = eps;
        for _ in 0..period {
            w = w * w + c;
        }
        w / (eps * eps)
    } else {
        Complex::new(0.0, 0.0)
    };

    Some(AttractingCycle {
        points,
        period,
        multiplier,
        is_super_attracting,
        alpha,
    })
}

/// Determine which cycle point's basin z falls into.
fn identify_basin(z: Complex<f64>, c: Complex<f64>, cycle: &AttractingCycle) -> Option<usize> {
    let mut w = z;
    for _ in 0..1000 {
        w = w * w + c;
        if w.norm() > 1e10 {
            return None;
        }
    }
    let mut best_idx = 0;
    let mut best_dist = f64::MAX;
    for (i, pt) in cycle.points.iter().enumerate() {
        let d = (w - pt).norm();
        if d < best_dist {
            best_dist = d;
            best_idx = i;
        }
    }
    if best_dist < 0.01 {
        Some(best_idx)
    } else {
        None
    }
}

/// Compute the Königs coordinate ψ(z) for a point z in a basin.
///
/// Königs case: ψ(z) = lim (g^N(z) - z_attract) / λ^N
/// Super-attracting case: start with u_N = α·g^N(z), pull back via continuous_sqrt.
fn compute_koenigs(
    z: Complex<f64>,
    cycle: &AttractingCycle,
    cycle_point_idx: usize,
    c: Complex<f64>,
) -> Option<Complex<f64>> {
    let z_attract = cycle.points[cycle_point_idx];
    let period = cycle.period;

    if cycle.is_super_attracting {
        // Adaptive iteration: stop when orbit is small enough, not a fixed count.
        // A fixed count causes underflow for z near the boundary (e.g. c=0,
        // z^{2^40} underflows to 0, losing all angle information).
        let mut g_orbit = Vec::new();
        let mut w = z;
        g_orbit.push(w);
        for _ in 0..200 {
            for _ in 0..period {
                w = w * w + c;
            }
            g_orbit.push(w);
            if w.norm() > 1e10 {
                return None;
            }
            if w.norm() < 1e-6 {
                break;
            }
        }
        let n_cycles = g_orbit.len() - 1;
        if n_cycles == 0 || g_orbit[n_cycles].norm() >= 1e-6 {
            return None;
        }
        // Start from far end: u_N = α · g^N(z)
        let mut u = cycle.alpha * g_orbit[n_cycles];
        // Pull back via continuous_sqrt using g-orbit as hints
        for k in (1..=n_cycles).rev() {
            let hint = cycle.alpha * g_orbit[k - 1];
            u = continuous_sqrt(u, hint);
        }
        Some(u)
    } else {
        // Adaptive iteration: stop when orbit is close to z_attract
        let mut w = z;
        let mut lambda_n = Complex::new(1.0, 0.0);
        for _ in 0..200 {
            for _ in 0..period {
                w = w * w + c;
            }
            lambda_n = lambda_n * cycle.multiplier;
            if w.norm() > 1e10 {
                return None;
            }
            if (w - z_attract).norm() < 1e-10 {
                break;
            }
        }
        if lambda_n.norm() < 1e-300 {
            return None;
        }
        Some((w - z_attract) / lambda_n)
    }
}

/// Internal analog of riemann_iteration: compute ψ⁻¹(w).
///
/// Forward iterates z under f until convergence to z_attract,
/// replaces the endpoint with the exact Königs/Böttcher coordinate,
/// then pulls back via continuous_sqrt.
fn koenigs_iteration(
    rho: f64,
    theta: f64,
    z: Complex<f64>,
    c: Complex<f64>,
    cycle: &AttractingCycle,
    cycle_point_idx: usize,
    small: f64,
) -> Complex<f64> {
    const LENGTH: usize = 16000;

    let z_attract = cycle.points[cycle_point_idx];
    let period = cycle.period;
    let w_target = Complex::from_polar(rho, 2.0 * PI * theta);

    let mut orbit = [Complex::new(0.0, 0.0); LENGTH];
    let mut backward_orbit = [Complex::new(0.0, 0.0); LENGTH];

    // Forward iterate under f until close to z_attract
    orbit[0] = z;
    let mut n: usize = 0;
    let mut n_cycles: usize = 0;

    for i in 0..(LENGTH - 1) {
        orbit[i + 1] = orbit[i] * orbit[i] + c;
        n = i + 1;

        if n % period == 0 && (orbit[n] - z_attract).norm() < small {
            n_cycles = n / period;
            break;
        }
    }

    if n_cycles == 0 {
        return z;
    }

    // Replace endpoint with exact internal coordinate
    if cycle.is_super_attracting {
        // w^{2^n_cycles} / α
        let mut w_pow = w_target;
        for _ in 0..n_cycles {
            w_pow = w_pow * w_pow;
        }
        backward_orbit[n] = w_pow / cycle.alpha;
    } else {
        // z_attract + λ^n_cycles · w
        let mut lambda_n = Complex::new(1.0, 0.0);
        for _ in 0..n_cycles {
            lambda_n = lambda_n * cycle.multiplier;
        }
        backward_orbit[n] = z_attract + lambda_n * w_target;
    }

    // Pull back via continuous_sqrt (identical to external case)
    for i in (1..=n).rev() {
        backward_orbit[i - 1] = continuous_sqrt(backward_orbit[i] - c, orbit[i - 1]);
    }

    backward_orbit[0]
}

/// Trace an internal ray from near a cycle point outward toward the Julia set.
fn draw_internal_ray(
    theta: f64,
    c: Complex<f64>,
    cycle: &AttractingCycle,
    cycle_point_idx: usize,
) -> Vec<RayPoint> {
    let z_attract = cycle.points[cycle_point_idx];
    let step_factor: f64 = 2.0_f64.powf(1.0 / 80.0);
    let small = 1e-6;

    let mut points = Vec::new();

    let mut rho = 1e-8;

    // Initial position near z_attract along the ray direction
    let mut z = if cycle.is_super_attracting {
        Complex::from_polar(rho, 2.0 * PI * theta) / cycle.alpha
    } else {
        z_attract + Complex::from_polar(rho, 2.0 * PI * theta)
    };

    points.push(RayPoint { r: rho, z });

    loop {
        rho = rho * step_factor;

        if rho > 10.0 {
            break;
        }

        let new_z = koenigs_iteration(rho, theta, z, c, cycle, cycle_point_idx, small);

        // Stop if the point jumped too far or diverged
        if (new_z - z).norm() > 2.0 || new_z.norm() > 10.0 {
            break;
        }

        z = new_z;
        points.push(RayPoint { r: rho, z });
    }

    points
}

/// Given an external ray's points, find the matching internal angle and basin.
fn find_internal_angle(
    ray_points: &[RayPoint],
    cycle: &AttractingCycle,
    c: Complex<f64>,
) -> Option<(f64, usize)> {
    if ray_points.len() < 2 {
        return None;
    }

    let n = ray_points.len();
    let z_land = ray_points[n - 1].z;
    let z_prev = ray_points[n - 2].z;

    let dir = z_land - z_prev;
    let dir_norm = dir.norm();
    if dir_norm < 1e-15 {
        return None;
    }
    let dir_unit = dir / dir_norm;

    // Try progressively larger perturbations past the Julia set boundary
    for eps_exp in -6..0_i32 {
        let eps = 10.0_f64.powi(eps_exp);
        let z_inside = z_land + eps * dir_unit;

        if let Some(basin_idx) = identify_basin(z_inside, c, cycle) {
            if let Some(psi) = compute_koenigs(z_inside, cycle, basin_idx, c) {
                let angle = psi.arg() / (2.0 * PI);
                let angle = ((angle % 1.0) + 1.0) % 1.0;
                return Some((angle, basin_idx));
            }
        }
    }

    None
}

        let needs_recompute = !self.cache_valid
            || self.denominator != self.cached_denominator
            || self.c_real != self.cached_c_real
            || self.c_imaginary != self.cached_c_imaginary
            || self.adaptive_refinement != self.cached_adaptive_refinement
            || (!self.adaptive_refinement && self.level_set_refinement != self.cached_level_set_refinement)
            || (self.adaptive_refinement && self.adaptive_threshold != self.cached_adaptive_threshold);

        if needs_recompute {
            let denominator = self.denominator;

            if self.adaptive_refinement {
                // === Adaptive refinement ===
                let threshold = self.adaptive_threshold;
                const MAX_RAYS: usize = 32768;

                // Compute base rays
                let mut rays: Vec<CachedRay> = (0..denominator)
                    .into_par_iter()
                    .map(|k| {
                        let angle = k as f64 / denominator as f64;
                        let points = draw_ray_iteration_f64(22.0, angle, c, 1e4/4.04, 1e-10);
                        CachedRay { angle, points, is_base: true }
                    })
                    .collect();

                // Adaptive refinement loop
                loop {
                    // Collect midpoint angles for gaps that exceed the threshold
                    let mut mid_angles: Vec<f64> = Vec::new();
                    for i in 0..rays.len() {
                        let next_i = (i + 1) % rays.len();
                        let land_curr = rays[i].points.last().map(|p| p.z).unwrap_or_default();
                        let land_next = rays[next_i].points.last().map(|p| p.z).unwrap_or_default();
                        let dist = (land_curr - land_next).norm();
                        let mut angle_diff = rays[i].angle - rays[next_i].angle;
                        angle_diff = (if angle_diff > 0.5 {angle_diff - 1.0} else {angle_diff}).abs();
                       

                        if dist > threshold  && angle_diff > 1e-10{
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

                    // Compute new rays in parallel (mid_angles is sorted since
                    // rays are sorted by angle and midpoints preserve order)
                    let new_rays: Vec<CachedRay> = mid_angles.par_iter()
                        .map(|&angle| {
                            let points = draw_ray_iteration_f64(22.0, angle, c, 1e4/4.04, 1e-10);
                            CachedRay { angle, points, is_base: false }
                        })
                        .collect();
println!("new rays {}", new_rays.len());
//println!("mid_angles: {:?}", mid_angles);

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
                self.cached_polylines = rays.iter()
                    .filter(|r| r.is_base)
                    .map(|r| compute_ray_polyline(&r.points, 10.0))
                    .collect();

                self.cached_rays = rays;

            } else {
                // === Uniform refinement (existing logic) ===
                let refinement = self.level_set_refinement;
                let total_rays = denominator * refinement;

                let ray_data: Vec<(Vec<RayPoint>, Vec<(f64, f64)>)> = (0..total_rays)
                    .into_par_iter()
                    .map(|k| {
                        let ray_points = draw_ray_iteration(22.0, k, total_rays, c, 1e12, 1e-10);
                        let polyline = compute_ray_polyline(&ray_points, 10.0);
                        (ray_points, polyline)
                    })
                    .collect();

                self.cached_rays = ray_data.iter()
                    .enumerate()
                    .map(|(idx, (pts, _))| CachedRay {
                        angle: idx as f64 / total_rays as f64,
                        points: pts.clone(),
                        is_base: idx % refinement == 0,
                    })
                    .collect();

                self.cached_polylines = ray_data.into_iter()
                    .enumerate()
                    .filter_map(|(idx, (_, poly))| {
                        if idx % refinement == 0 {
                            Some(poly)
                        } else {
                            None
                        }
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

        // Compute internal rays if enabled
        let needs_internal_recompute = needs_recompute
            || (self.draw_internal_rays && !self.cached_draw_internal_rays);

        if self.draw_internal_rays && needs_internal_recompute {
            let cycle = find_attracting_cycle(c);

            if let Some(ref cycle) = cycle {
                let base_rays: Vec<&CachedRay> = self.cached_rays.iter()
                    .filter(|r| r.is_base)
                    .collect();

                let internal_data: Vec<Vec<(f64, f64)>> = base_rays.par_iter()
                    .filter_map(|ext_cached_ray| {
                        if let Some((angle, basin_idx)) = find_internal_angle(&ext_cached_ray.points, cycle, c) {
                            let int_ray = draw_internal_ray(angle, c, cycle, basin_idx);
                            let polyline = compute_ray_polyline(&int_ray, 10.0);
                            if !polyline.is_empty() {
                                Some(polyline)
                            } else {
                                None
                            }
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

        sketch.scale(self.scale / 100.0);

        // Draw external rays
        sketch.color(Color::DARK_GREEN).stroke_width(0.3 * Unit::Mm);
        for polyline_points in &self.cached_polylines {
            if !polyline_points.is_empty() {
                sketch.polyline(polyline_points.clone(), false);
            }
        }

        // Draw internal rays
        if self.draw_internal_rays && !self.cached_internal_polylines.is_empty() {
            sketch.color(Color::DARK_RED).stroke_width(0.3 * Unit::Mm);
            for polyline_points in &self.cached_internal_polylines {
                if !polyline_points.is_empty() {
                    sketch.polyline(polyline_points.clone(), false);
                }
            }
        }

        // Draw level sets (equipotential curves) if enabled
        if self.draw_level_sets && !self.cached_rays.is_empty() {
            sketch.color(Color::DARK_BLUE).stroke_width(0.2 * Unit::Mm);

            // Find the minimum number of points across all rays
            let min_points = self.cached_rays.iter()
                .map(|ray| ray.points.len())
                .min()
                .unwrap_or(0);

            // Determine which level sets to draw
            let indices_to_draw: Vec<usize> = if self.only_closest_level_set {
                // Only draw the last level set (closest to Julia set)
                if min_points > 0 {
                    vec![min_points - 1]
                } else {
                    vec![]
                }
            } else {
                // Draw all level sets according to spacing
                (0..min_points).step_by(self.level_set_spacing).collect()
            };

            // Draw level sets by connecting points at the same index across all rays
            for point_idx in indices_to_draw {
                let mut level_set: Vec<(f64, f64)> = Vec::new();

                // Collect points at this potential level from all rays
                for ray in &self.cached_rays {
                    if point_idx < ray.points.len() {
                        let pt = &ray.points[point_idx];
                        // Filter by visibility (same threshold as rays)
                        if pt.z.norm() < 10.0 {
                            level_set.push((pt.z.re * 100.0, pt.z.im * 100.0));
                        }
                    }
                }

                // Close the curve by connecting back to the first point
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
