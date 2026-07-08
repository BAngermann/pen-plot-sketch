use noise::MultiFractal;
use noise::{Fbm, NoiseFn, Perlin};
use std::f32::consts::PI;
use whiskers::prelude::*;
use rand::Rng;
use rand_distr::StandardNormal;
use grid::*;

#[derive(Clone, Copy, Debug)]
pub struct Point {
    pub x: f32,
    pub y: f32,
}

impl Point {
    pub fn new(x: f32, y: f32) -> Self {
        Self { x, y }
    }
    
    pub fn dist(&self, other: &Point) -> f32 {
        (*self - *other).length()
    }
    
    pub fn length(&self) -> f32 {
        (self.x * self.x + self.y * self.y).sqrt()
    }
    
    pub fn to_unit(&self) -> Self {
        let len = self.length();
        if len == 0.0 {
            Self::new(0.0, 0.0)
        } else {
            Self::new(self.x / len, self.y / len)
        }
    }
    
    pub fn normal(&self, before: &Point, after: &Point) -> Self {
        let v1 = *self - *before;
        let v2 = *after - *self;
        let mean = (v1 + v2).to_unit();
        Point::new(mean.y, -mean.x)
    }
    
    pub fn scale(&self, s: f32) -> Self {
        Self::new(self.x * s, self.y * s)
    }
}

impl std::ops::Sub for Point {
    type Output = Point;
    fn sub(self, other: Point) -> Point {
        Point::new(self.x - other.x, self.y - other.y)
    }
}

impl std::ops::Add for Point {
    type Output = Point;
    fn add(self, other: Point) -> Point {
        Point::new(self.x + other.x, self.y + other.y)
    }
}

impl From<Point> for whiskers::prelude::Point {
    fn from(p: Point) -> Self {
        Self::new(p.x as f64, p.y as f64)
    }
}

impl PartialEq for Point {
    fn eq(&self, other: &Self) -> bool {
        let d_sq =
        (self.x - other.x) * (self.x - other.x) + (self.y - other.y) * (self.y - other.y);
        d_sq < 1e-20
    }
}

impl From<(f32, f32)> for Point {
    fn from(t: (f32, f32)) -> Self {
        Point::new(t.0, t.1)
    }
}

#[sketch_app]
struct TreeRingsSketch {
    #[param(slider, min = 0.25, max = 1.5)]
    global_scale: f64,
        #[param(slider, min = 0.0, max = 10.)]
    margin_x: f64,
        #[param(slider, min = 0.0, max = 10.)]
    margin_y: f64,

    #[param(slider, min = 20, max = 3000)]
    n_segments: usize,
    #[param(slider, min = 10, max = 100)]
    n_rings: usize, 
    #[param(slider, min = 0.01, max = 1.0)]
    r_start: f32, 
    #[param(slider, min = 0.01, max = 1.0)]
    linear_thickness: f32, 
    #[param(slider, min = 0.01, max = 0.5)]
    relaxation_increment: f32, 
    #[param(slider, min = 0, max = 100)]
    relaxation_iterations: usize, 
    #[param(slider, min = 1, max = 20)]
    growth_iterations: usize, 
    #[param(slider, min = 0.01, max = 1.0)]
    fixed_growth: f32, 
    #[param(slider, min = 0.0, max = 0.25)]
    growth_noise: f32, 
    #[param(slider, min = -3.0, max = 3.0)]
    noise_offset_x: f32, 
    #[param(slider, min = 0.01, max = 1.0)]
    slice_thickness: f32,
    #[param(slider, min = 0.5, max = 1.5)]
    ring_scale: f64,
    #[param(min = 0, max = 6)]
    num_tiles: usize,
    layout_index: usize,
    draw_outline: bool,

}

impl Default for TreeRingsSketch {
    fn default() -> Self {
        Self {
            global_scale:0.9,
            margin_x:1.0,
            margin_y:1.0,
            n_segments: 250,
            n_rings: 20,
            r_start: 0.1,
            linear_thickness: 0.1,
            relaxation_increment: 0.1,
            relaxation_iterations: 2,
            growth_iterations: 5,
            fixed_growth: 0.1,
            growth_noise: 0.07,
            noise_offset_x: 1.0,
            slice_thickness: 0.1,
            ring_scale:0.9,
            num_tiles: 4,
            layout_index: 4,
            draw_outline: true,
        }
    }
}

impl App for TreeRingsSketch {
    fn update(&mut self, sketch: &mut Sketch, ctx: &mut Context) -> anyhow::Result<()> {
        sketch.color(Color::BLACK).stroke_width(0.03 * Unit::Mm);
        
        
        let smaller_size = sketch.width().min(sketch.height());
        let n = self.n_segments;
        let n_rings = self.n_rings;
        let yearly_growth: Vec<f32> = (0..n_rings)
        .map(|_| {
            self.linear_thickness * (ctx.rng.sample::<f32, _>(StandardNormal) / 1.5).exp()
        })
        .collect();

        let mut slice: usize = 0;
        let seed = ctx.rng.get_seed();

        let perlin = Fbm::<Perlin>::new(seed[0] as u32 + seed[1] as u32 * 256 + seed[2] as u32 * 256 * 256)
        .set_frequency(1.0)
        .set_persistence(0.5)
        .set_lacunarity(2.0)
        .set_octaves(4);

        let grid_layout = SquareGrid::new(self.num_tiles, Some(self.layout_index)) ;
        let squares: Vec<_> = grid_layout.iter_squares().copied().collect();

        // Pre-calculate every ring, for every square, before any drawing happens.
        let mut squares_rings: Vec<Vec<Vec<Point>>> = Vec::with_capacity(squares.len());
        for _square in &squares {
            let mut ring: Vec<Point> = (0..n)
            .map(|i| {
                let angle = i as f32 * 2.0 * PI / n as f32;
                Point::new(
                    (self.r_start as f32) * angle.cos(),
                    (self.r_start as f32) * angle.sin(),
                )
            })
            .collect();
            let mut growth: Vec<Point> = vec![Point::new(0.0, 0.0); n];
            let mut rings: Vec<Vec<Point>> = Vec::with_capacity(n_rings);
            for year in 0..n_rings {
                let thickness = yearly_growth[year];
                // record current ring
                rings.push(ring.clone());

                for _growth_iter in 0..self.growth_iterations {
                    let growth_scale = 1.0 / self.growth_iterations as f32;
                    for i in 0..n {
                        let p = ring[i];
                        let p_a = ring[(i + 1) % n];
                        let left_index = if i == 0 { n - 1 } else { i - 1 };
                        let p_b = ring[left_index];


                        let noise_value = perlin.get([
                            (self.noise_offset_x + p.x) as f64,
                            p.y as f64,
                            slice as f64 * self.slice_thickness as f64,
                            ]) as f32;
                            growth[i] = p
                            .normal(&p_b, &p_a)
                            .scale( growth_scale * thickness * (self.fixed_growth + self.growth_noise * noise_value));
                    }
                        for i in 0..n {
                            ring[i] = ring[i] + growth[i];
                        }
                    }


                    for _i in 0..self.relaxation_iterations {
                        let distances: Vec<f32> =
                        (0..n).map(|i| ring[i].dist(&ring[(i + 1) % n])).collect();
                        let mean_dist: f32 = distances.iter().sum::<f32>() / n as f32;
                        for j in 0..n {
                            if distances[j] < mean_dist {
                                let left_direct_neighbor  : usize = if j == 0 { n - 1 } else { j - 1 };
                                let right_direct_neighbor  : usize = ((j as i32 + 1) % (n as i32))as usize;
                                let right_2nd_neighbor  : usize = ((j as i32 + 2) % (n as i32))as usize;
                                //  depending which adjacent segment is longer, move the vertex along the other shorter segment to increase the length of the segment
                                if distances[right_direct_neighbor] > distances[left_direct_neighbor]
                                {
                                    let old = ring[right_direct_neighbor];
                                    let next = ring[right_2nd_neighbor];
                                    let delta = (next - old).scale(self.relaxation_increment);
                                    ring[right_direct_neighbor] = old + delta;
                                }
                                else {
                                    let old = ring[j];
                                    let next = ring[left_direct_neighbor];
                                    let delta = (next - old).scale(self.relaxation_increment);
                                    ring[j] = old + delta;
                                }
                            }
                        }
                    }
                slice += 1;
            }
            squares_rings.push(rings);
        }

        // Find the largest extent, in either direction, of any square's bounding box,
        // and use it to derive a single scale shared by every square's rings.
        let mut max_extent: f32 = 0.0;
        for rings in &squares_rings {
            let mut min_x = f32::INFINITY;
            let mut max_x = f32::NEG_INFINITY;
            let mut min_y = f32::INFINITY;
            let mut max_y = f32::NEG_INFINITY;
            for ring in rings {
                for p in ring {
                    min_x = min_x.min(p.x);
                    max_x = max_x.max(p.x);
                    min_y = min_y.min(p.y);
                    max_y = max_y.max(p.y);
                }
            }
            let extent = max_x.abs().max(min_x.abs()).max(max_y.abs()).max(min_y.abs());
            max_extent = max_extent.max(extent);
        }
        let scale = smaller_size / (2.0 * max_extent as f64);

        sketch.translate(self.margin_x* Unit::Cm,self.margin_y* Unit::Cm);
        sketch.scale(self.global_scale);
        for (square, rings) in squares.iter().zip(squares_rings.iter())
        {
            // set the translation and scale.
            sketch.push_matrix();

            sketch.translate(square.render_pos.0 * smaller_size, -square.render_pos.1 * smaller_size);
            sketch.scale(square.render_scale);

            sketch.set_layer( 1);

            if self.draw_outline {
                sketch.rect(smaller_size * 0.5, smaller_size * 0.5, smaller_size, smaller_size);
            }

            sketch.scale(scale );
            sketch.translate(0.5 / scale *  smaller_size ,0.5 / scale *  smaller_size );
            sketch.scale(self.ring_scale);
            for ring in rings {
                sketch.polyline(ring.iter().copied(), true);
            }

            sketch.pop_matrix();
        }

        Ok(())
    }
}

fn main() -> Result {
    TreeRingsSketch::runner()
    .with_page_size_options(PageSize::A5H)
    .with_layout_options(LayoutOptions::Off)
    .with_info_options(InfoOptions::default()
        .description("Slices through procedural tree trunks arranged in a grid layout."))
    .run()
}
