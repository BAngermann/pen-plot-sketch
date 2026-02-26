use std::f64::consts::PI;
use std::fs;
use std::path::PathBuf;
use num_complex::Complex;
use serde::{Serialize, de::DeserializeOwned};
use whiskers::prelude::Unit;
pub use num_rational::Rational64;

// ── Shared types ─────────────────────────────────────────────────────────────

#[derive(Clone, Debug)]
pub struct RayPoint {
    pub r: f64,
    pub z: Complex<f64>,
}

#[derive(Clone, Debug, Default)]
pub struct CachedRay {
    pub angle: f64,
    pub points: Vec<RayPoint>,
    pub is_base: bool,
}

#[derive(Clone, Debug)]
pub struct AttractingCycle {
    pub points: Vec<Complex<f64>>,
    pub period: usize,
    pub multiplier: Complex<f64>,
    pub is_super_attracting: bool,
    pub alpha: Complex<f64>,
}

// ── Preset file utilities ─────────────────────────────────────────────────────
//
// Each binary stores its presets under  parameters/<binary_name>/*.json.
// The `binary` argument is typically the binary's own name (e.g. "rays").

pub fn params_dir(binary: &str) -> PathBuf {
    PathBuf::from("parameters").join(binary)
}

pub fn ensure_params_dir(binary: &str) -> anyhow::Result<()> {
    let dir = params_dir(binary);
    if !dir.exists() {
        fs::create_dir_all(&dir)?;
    }
    Ok(())
}

pub fn load_preset_list(binary: &str) -> Vec<String> {
    let dir = params_dir(binary);
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

pub fn save_preset<T: Serialize>(binary: &str, name: &str, params: &T) -> anyhow::Result<()> {
    ensure_params_dir(binary)?;
    let path = params_dir(binary).join(format!("{}.json", name));
    let json = serde_json::to_string_pretty(params)?;
    fs::write(path, json)?;
    Ok(())
}

pub fn load_preset<T: DeserializeOwned>(binary: &str, name: &str) -> anyhow::Result<T> {
    let path = params_dir(binary).join(format!("{}.json", name));
    let json = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&json)?)
}

// ── Drawing utilities ─────────────────────────────────────────────────────────

// Simplify a polyline by removing redundant interior points. The first and last
// points are always kept. An interior point is removed if either:
//  - it is closer than `min_distance` to both its predecessor (last kept point)
//    and its successor (next original point), or
//  - the turning angle between the incoming and outgoing segments is less than
//    `angle_threshold` (in radians), meaning the three points are nearly collinear.
// Uses a single greedy forward pass; predecessor for angle/distance checks is the
// last point that was kept, not the original previous point.
pub fn simplify_polyline(
    points: &[(f64, f64)],
    angle_threshold: f64,
    min_distance: f64,
) -> Vec<(f64, f64)> {
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

/// Compute a simplified polyline from ray points (pure computation, no sketch access).
pub fn compute_ray_polyline(combined: &[RayPoint], visibility_threshold: f64) -> Vec<(f64, f64)> {
    let polyline_points: Vec<(f64, f64)> = combined
        .iter()
        .filter(|p| p.z.norm() < visibility_threshold)
        .map(|p| (p.z.re * 100.0, p.z.im * 100.0))
        .collect();

    simplify_polyline(
        &polyline_points,
        PI / 2880.0,
        0.3 * Unit::Mm.to_px::<f64>(),
    )
}

// ── External ray computation ──────────────────────────────────────────────────

/// Compute √z choosing the branch consistent with a reference point `w`.
///
/// There are two square roots of any nonzero complex number; this picks whichever
/// one has a non-negative real inner product with `w`. When `w` varies continuously
/// along a path, this guarantees the result also varies continuously — i.e. it
/// analytically continues the square root along that path without jumping sheets.
pub fn continuous_sqrt(z: Complex<f64>, w: Complex<f64>) -> Complex<f64> {
    let mut t = z.sqrt();
    if (t.re * w.re + t.im * w.im) < 0.0 {
        t = -t;
    }
    t
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
pub fn riemann_iteration(
    potential: f64,
    angle: f64,
    z: Complex<f64>,
    c: Complex<f64>,
    escape_radius: f64,
) -> Complex<f64> {
    const LENGTH: usize = 16000;

    let mut orbit = [Complex::new(0.0, 0.0); LENGTH];
    let mut backward_orbit = [Complex::new(0.0, 0.0); LENGTH];
    let mut n: usize;

    // Step 1: Forward iterate until escape
    orbit[0] = z;
    n = 0;
    let mut potential_curr = potential;
    let mut ang_curr = angle;

    for i in 0..(LENGTH - 1) {
        if orbit[i].norm() > escape_radius {
            break;
        }
        orbit[i + 1] = orbit[i] * orbit[i] + c;
        n += 1;
        potential_curr = 2.0 * potential_curr;
        ang_curr = (2.0 * ang_curr) % 1.0;
    }

    // Step 2: Replace endpoint with exact Böttcher coordinate
    backward_orbit[n] =
        Complex::from_polar(2.0_f64.powf(potential_curr), 2.0 * PI * ang_curr);

    // Step 3: Pull back via continuous square roots
    // The continuous_sqrt picks the branch closest to orbit[i-1],
    // ensuring we stay on the correct sheet of the Riemann surface.
    for i in (1..=n).rev() {
        backward_orbit[i - 1] = continuous_sqrt(backward_orbit[i] - c, orbit[i - 1]);
    }

    backward_orbit[0]
}

/// Trace an external ray from infinity toward the Julia set.
///
/// Steps along the ray from large potential down to `min_potential`, calling
/// `riemann_iteration` at each step with the previous point as the initial guess.
pub fn draw_ray_iteration_f64(
    level: f64,
    angle: f64,
    c: Complex<f64>,
    escape_radius: f64,
    min_potential: f64,
) -> Vec<RayPoint> {
    // Geometric decay factor: 80 steps per halving of potential
    let step_factor: f64 = 2.0_f64.powf(-1.0 / 80.0);

    let mut points = Vec::new();

    // Increase potential until |φ(z)| = 2^potential exceeds escape_radius
    let mut potential = level;
    while 2.0_f64.powf(potential) < escape_radius {
        potential *= 2.0;
    }

    let mut z = Complex::from_polar(2.0_f64.powf(potential), 2.0 * PI * angle);
    let mut prev_z;

    points.push(RayPoint { r: potential, z });

    loop {
        potential *= step_factor;
        prev_z = z;
        z = riemann_iteration(potential, angle, prev_z, c, escape_radius);

        points.push(RayPoint { r: potential, z });

        if potential <= min_potential {
            break;
        }
    }

    points
}

/// Wrapper for `draw_ray_iteration_f64` that takes a rational angle (num/den).
pub fn draw_ray_iteration(
    level: f64,
    ang_num: usize,
    ang_den: usize,
    c: Complex<f64>,
    escape_radius: f64,
    min_potential: f64,
) -> Vec<RayPoint> {
    let angle = ang_num as f64 / ang_den as f64;
    draw_ray_iteration_f64(level, angle, c, escape_radius, min_potential)
}

// ── Attracting cycle detection ────────────────────────────────────────────────

/// Find an attracting cycle for f(z) = z² + c by iterating the critical orbit.
/// Returns None if c is outside the Mandelbrot set or on its boundary.
pub fn find_attracting_cycle(c: Complex<f64>) -> Option<AttractingCycle> {
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
pub fn identify_basin(
    z: Complex<f64>,
    c: Complex<f64>,
    cycle: &AttractingCycle,
) -> Option<usize> {
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
pub fn compute_koenigs(
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

// ── Internal ray computation ──────────────────────────────────────────────────

/// Internal analog of riemann_iteration: compute ψ⁻¹(w).
///
/// Forward iterates z under f until convergence to z_attract,
/// replaces the endpoint with the exact Königs/Böttcher coordinate,
/// then pulls back via continuous_sqrt.
pub fn koenigs_iteration(
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
pub fn draw_internal_ray(
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
pub fn find_internal_angle(
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

// ── Lamination math ───────────────────────────────────────────────────────────
//
// Exact rational arithmetic throughout (mirroring Python's Fraction).
// All angles are in [0, 1) as reduced Rational64 fractions.

/// Angle doubling map: θ ↦ 2θ mod 1.
pub fn sigma2(theta: Rational64) -> Rational64 {
    let r = theta * Rational64::new(2, 1);
    let floor = *r.numer() / *r.denom(); // integer division = floor for non-negative
    r - Rational64::new(floor, 1)
}

/// Normalize a leaf so that a < b, reducing both to [0,1). Returns None if degenerate.
pub fn normalize_leaf(a: Rational64, b: Rational64) -> Option<(Rational64, Rational64)> {
    let fa = *a.numer() / *a.denom();
    let fb = *b.numer() / *b.denom();
    let a = a - Rational64::new(fa, 1);
    let b = b - Rational64::new(fb, 1);
    if a == b {
        return None;
    }
    if a > b { Some((b, a)) } else { Some((a, b)) }
}

/// Two chords on the circle cross iff exactly one endpoint of the second
/// lies in the open arc cut by the first.
pub fn leaves_cross(l1: &(Rational64, Rational64), l2: &(Rational64, Rational64)) -> bool {
    let (a1, b1) = l1;
    let (a2, b2) = l2;
    if a1 == a2 || a1 == b2 || b1 == a2 || b1 == b2 {
        return false;
    }
    (a1 < a2 && a2 < b1) != (a1 < b2 && b2 < b1)
}

/// All 4 candidate preimage leaves of a leaf under σ₂ (gap-aware pullback).
pub fn all_preimage_candidates(
    leaf: &(Rational64, Rational64),
) -> Vec<(Rational64, Rational64)> {
    let (a, b) = leaf;
    let half = Rational64::new(1, 2);
    let one = Rational64::new(1, 1);
    [
        (a * half, b * half),
        ((a + one) * half, (b + one) * half),
        (a * half, (b + one) * half),
        ((a + one) * half, b * half),
    ]
    .into_iter()
    .filter_map(|(ap, bp)| normalize_leaf(ap, bp))
    .collect()
}

/// Find the q angles of the α-fixed point orbit portrait for the p/q satellite.
/// Angles are in {1,…,2^q−2}/(2^q−1), forming an orbit under σ₂
/// whose cyclic permutation has rotation number p/q.
pub fn find_alpha_portrait(p: i64, q: u32) -> anyhow::Result<Vec<Rational64>> {
    use std::collections::HashSet;

    let denom: i64 = (1i64 << q) - 1;
    if denom <= 1 {
        anyhow::bail!("q={} too small", q);
    }

    let mut used: HashSet<i64> = HashSet::new();

    for k in 1..denom {
        if used.contains(&k) {
            continue;
        }

        // Build the full q-orbit of k under doubling mod denom
        let mut orb: Vec<i64> = Vec::with_capacity(q as usize);
        let mut current = k;
        for _ in 0..q {
            orb.push(current);
            current = (current * 2) % denom;
        }

        // Must return to k and have exactly q distinct elements
        if current != k || orb.iter().collect::<HashSet<_>>().len() != q as usize {
            used.extend(&orb);
            continue;
        }
        used.extend(&orb);

        // Convert to sorted angles and verify rotation number
        orb.sort_unstable();
        let angles: Vec<Rational64> = orb.iter().map(|&n| Rational64::new(n, denom)).collect();
        let angle_to_idx: std::collections::HashMap<Rational64, usize> =
            angles.iter().enumerate().map(|(i, &a)| (a, i)).collect();

        let ok = angles.iter().enumerate().all(|(i, &a)| {
            let img = sigma2(a);
            angle_to_idx
                .get(&img)
                .map(|&j| (j as i64 - i as i64).rem_euclid(q as i64) == p)
                .unwrap_or(false)
        });

        if ok {
            return Ok(angles);
        }
    }

    anyhow::bail!("No orbit portrait found for p/q = {}/{}", p, q)
}

/// Compute the critical gap vertices for a given orbit portrait.
/// For each portrait angle θ, one of its σ₂-preimages is in the portrait;
/// the other is a critical gap vertex.
pub fn compute_critical_gap(portrait: &[Rational64]) -> Vec<Rational64> {
    use std::collections::HashSet;
    let portrait_set: HashSet<Rational64> = portrait.iter().copied().collect();
    let half = Rational64::new(1, 2);
    let one = Rational64::new(1, 1);

    let mut gap_vertices: Vec<Rational64> = portrait
        .iter()
        .map(|&theta| {
            let pre1 = theta * half;
            let pre2 = (theta + one) * half;
            let p1_in = portrait_set.contains(&pre1);
            let p2_in = portrait_set.contains(&pre2);
            if p1_in && !p2_in {
                pre2
            } else if p2_in && !p1_in {
                pre1
            } else if !p1_in {
                pre1
            } else {
                pre2
            }
        })
        .collect();

    gap_vertices.sort_unstable();
    gap_vertices
}

/// Edges of the convex polygon inscribed in ∂D with given vertices.
pub fn polygon_edges(angles: &[Rational64]) -> Vec<(Rational64, Rational64)> {
    let n = angles.len();
    let mut sa: Vec<Rational64> = angles.to_vec();
    sa.sort_unstable();
    (0..n)
        .filter_map(|i| normalize_leaf(sa[i], sa[(i + 1) % n]))
        .collect()
}

/// Core builder: iterative pullback with all-4-candidates and crossing checks.
fn build_with_crossing_check(
    seed_leaves: &[(Rational64, Rational64)],
    depth: usize,
) -> std::collections::HashMap<usize, Vec<(Rational64, Rational64)>> {
    use std::collections::{HashMap, HashSet};

    let mut all_leaves: Vec<(Rational64, Rational64)> = Vec::new();
    let mut leaf_set: HashSet<(Rational64, Rational64)> = HashSet::new();
    let mut generations: HashMap<usize, Vec<(Rational64, Rational64)>> = HashMap::new();

    // Generation 0: seeds
    let mut gen0: Vec<(Rational64, Rational64)> = Vec::new();
    for &lf in seed_leaves {
        if leaf_set.insert(lf) {
            all_leaves.push(lf);
            gen0.push(lf);
        }
    }
    generations.insert(0, gen0);

    let mut current: Vec<(Rational64, Rational64)> = generations[&0].clone();

    for g in 1..=depth {
        let mut new_leaves: Vec<(Rational64, Rational64)> = Vec::new();

        for parent in &current {
            for cand in all_preimage_candidates(parent) {
                if leaf_set.contains(&cand) {
                    continue;
                }
                if all_leaves.iter().any(|ex| leaves_cross(&cand, ex)) {
                    continue;
                }
                leaf_set.insert(cand);
                all_leaves.push(cand);
                new_leaves.push(cand);
            }
        }

        if new_leaves.is_empty() {
            break;
        }
        current = new_leaves.clone();
        generations.insert(g, new_leaves);
    }

    generations
}

/// Build a satellite lamination from an orbit portrait.
/// Seed: portrait polygon edges + critical gap polygon edges.
pub fn build_lamination(
    portrait: &[Rational64],
    depth: usize,
) -> std::collections::HashMap<usize, Vec<(Rational64, Rational64)>> {
    let gap = compute_critical_gap(portrait);
    let mut seed = polygon_edges(portrait);
    seed.extend(polygon_edges(&gap));
    build_with_crossing_check(&seed, depth)
}

/// Build a Misiurewicz lamination from the critical value angle.
/// The critical leaf is the diameter (θ/2, (θ+1)/2).
pub fn build_misiurewicz_lamination(
    theta: Rational64,
    depth: usize,
) -> anyhow::Result<std::collections::HashMap<usize, Vec<(Rational64, Rational64)>>> {
    let half = Rational64::new(1, 2);
    let one = Rational64::new(1, 1);
    let crit_leaf = normalize_leaf(theta * half, (theta + one) * half)
        .ok_or_else(|| anyhow::anyhow!("Degenerate critical leaf for θ = {}", theta))?;
    Ok(build_with_crossing_check(&[crit_leaf], depth))
}
