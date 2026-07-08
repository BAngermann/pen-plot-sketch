use whiskers::prelude::*;
use std::f64::consts::PI;

// a function to convert a string of comma separated numbers into a vector of i64, tokens that are not numbers are interpreted as 0
fn parse_comma_separated_numbers(s: &String) -> Vec<i64> {
    s.split(',')
        .map(|x| x.trim().parse::<i64>().unwrap_or(0))
        .collect()
}

// shift a sequence of (possibly negative) integers so the smallest term becomes 1,
// so every term can drive a circle radius/ratio without hitting zero or negative values
fn shift_to_natural(values: &[i64]) -> Vec<u64> {
    let min = *values.iter().min().unwrap();
    let offset = 1 - min.min(1);
    values.iter().map(|v| (v + offset) as u64).collect()
}

// two ways to turn a sequence of (possibly negative) integers into circle radii plus a
// per-circle starting phase for its contact point with the previous circle: either shift
// the whole sequence into the naturals, or keep magnitudes as radii directly and instead
// start negative terms' contact point 180 degrees around the previous circle
fn radii_and_phase(values: &[i64], use_phase_for_negatives: bool) -> (Vec<u64>, Vec<f64>) {
    if use_phase_for_negatives {
        let terms = values.iter().map(|&v| v.unsigned_abs().max(1)).collect();
        let phase = values.iter().map(|&v| if v < 0 { PI } else { 0.0 }).collect();
        (terms, phase)
    } else {
        (shift_to_natural(values), vec![0.0; values.len()])
    }
}

fn gcd(a: i64, b: i64) -> i64 {
    if b == 0 { a.abs() } else { gcd(b, a % b) }
}

fn lcm(a: i64, b: i64) -> i64 {
    a / gcd(a, b) * b
}

// reduce a fraction to lowest terms (denominator kept positive)
fn reduce_frac(n: i64, d: i64) -> (i64, i64) {
    let g = gcd(n, d).max(1);
    if d < 0 { (-n / g, -d / g) } else { (n / g, d / g) }
}

fn add_frac(a: (i64, i64), b: (i64, i64)) -> (i64, i64) {
    reduce_frac(a.0 * b.1 + b.0 * a.1, a.1 * b.1)
}

// each stage's spin angle is spin_(k-1) + ((r_prev+r_k)/r_k) * theta, i.e. a rational
// multiple of theta; the drawing only closes once theta has swept enough full
// revolutions that every such rational multiple lands back on a whole number of turns
fn revolutions_to_close(terms: &[u64]) -> i64 {
    let mut spin = (0i64, 1i64); // cumulative spin, as a fraction of theta
    let mut revolutions = 1i64;
    for k in 1..terms.len() {
        let r_prev = terms[k - 1] as i64;
        let r_k = terms[k] as i64;
        let freq = reduce_frac(r_prev + r_k, r_k);
        spin = add_frac(spin, freq);
        revolutions = lcm(revolutions, spin.1);
    }
    revolutions
}


#[sketch_app]  
struct RollingCirclesSketch {
    #[param(slider, min = 3, max = 20000)]
    num_points: usize,

    radii: String,

    #[param(slider, min = 1., max = 100.)]
    radius: f64,

    #[param(slider, min = -4., max = 4.)]
    d_min: f64,

    #[param(slider, min = 0.01, max = 4.)]
    d_step: f64,

    #[param(slider, min = 1, max = 100)]
    d_num: usize,

    use_phase_for_negatives: bool,

    // the shape is drawn once per cell of a grid_rows x grid_cols grid, with the number
    // of points increasing across the grid from 3+point_offset up to num_points (which
    // acts as the point count of the last, most detailed shape)
    #[param(slider, min = 1, max = 20)]
    grid_rows: usize,

    #[param(slider, min = 1, max = 20)]
    grid_cols: usize,

    #[param(slider, min = 0, max = 1000)]
    point_offset: usize,

    #[param(slider, min = 1., max = 200.)]
    cell_spacing: f64,
}

impl Default for RollingCirclesSketch {
    fn default() -> Self {
        Self {
            num_points: 100,
            radii: "1".to_string(),
            radius:50.0,
            d_min: 1.0,
            d_step: 0.1,
            d_num:1,
            use_phase_for_negatives: false,
            grid_rows: 1,
            grid_cols: 1,
            point_offset: 0,
            cell_spacing: 120.0,
        }
    }
}

impl App for RollingCirclesSketch {
    fn update(&mut self, sketch: &mut Sketch, _ctx: &mut Context) -> anyhow::Result<()> {
        sketch.color(Color::DARK_RED)
        .scale(Unit::Mm)
        .stroke_width(0.3*Unit::Mm);

        let sequence = parse_comma_separated_numbers(&self.radii);
        if sequence.is_empty() {
            return Err(anyhow::anyhow!("Radii must not be empty"));
        }
        let (terms, phase) = radii_and_phase(&sequence, self.use_phase_for_negatives);

        // each sequence term is the radius of one circle in the chain (term 0 = fixed
        // base circle, term k = the circle rolling on circle k-1); self.radius rescales
        // the whole chain so the base circle has that physical size
        let unit = self.radius / terms[0] as f64;
        let radii_chain: Vec<f64> = terms.iter().map(|&t| t as f64 * unit).collect();
        let n = radii_chain.len() - 1; // number of rolling circles beyond the fixed base
        let revolutions = revolutions_to_close(&terms);
        let theta_max = 2. * PI * revolutions as f64;

        // point count for grid cell j (0-based, row-major): 3+point_offset, incrementing
        // by 1 per cell, except the last cell of the grid which is always drawn at the
        // full num_points resolution (the current max)
        let total_cells = self.grid_rows * self.grid_cols;
        let points_for_cell = |j: usize| -> usize {
            if j == total_cells - 1 {
                self.num_points
            } else {
                3 + self.point_offset + j
            }
        };

        for row in 0..self.grid_rows {
            for col in 0..self.grid_cols {
                let cell = row * self.grid_cols + col;
                let numpoints = points_for_cell(cell);
                let ox = (col as f64 - (self.grid_cols - 1) as f64 / 2.0) * self.cell_spacing;
                let oy = (row as f64 - (self.grid_rows - 1) as f64 / 2.0) * self.cell_spacing;

                for d_i in 0..self.d_num {
                    let mut points = Vec::<Point>::new();
                    let d = self.d_min + d_i as f64 * self.d_step;
                    for i in 0..numpoints {
                        let theta = (i as f64 * theta_max) / numpoints as f64;

                        // walk the chain: each circle rolls without slipping on the previous one
                        let mut cx = 0.0;
                        let mut cy = 0.0;
                        let mut spin = 0.0_f64;
                        for k in 1..=n {
                            let r_prev = radii_chain[k - 1];
                            let r_k = radii_chain[k];
                            let arm = r_prev + r_k;
                            let carry_angle = spin + theta + phase[k];
                            cx += arm * carry_angle.cos();
                            cy += arm * carry_angle.sin();
                            spin += (arm / r_k) * theta;
                        }

                        let r_last = radii_chain[n];
                        // with a single term there's no rolling stage (n == 0), so spin
                        // never advances with theta; trace the lone circle's own rim instead
                        let (px, py) = if n == 0 {
                            (d * r_last * theta.cos(), d * r_last * theta.sin())
                        } else {
                            (cx - d * r_last * spin.cos(), cy - d * r_last * spin.sin())
                        };

                        points.push(Point::new(px + ox, py + oy))
                    }
                    sketch.polyline(points, true);
                }
            }
        }

        Ok(())
    }
}

fn main() -> Result {
 RollingCirclesSketch::runner()
        .with_page_size_options(PageSize::A5H)
        .run()
}