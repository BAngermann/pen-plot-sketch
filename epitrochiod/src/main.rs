use whiskers::prelude::*;
use std::f64::consts::PI;
use num_integer::lcm;
use vsvg::{Color, COLORS};

#[sketch_app]  
struct EpitrochoidSketch {
    #[param(slider, min = 3, max = 500)]
    num_points: usize,

    #[param(slider, min = 1, max = 100)]
    numerator: usize,

    #[param(slider, min = 1, max = 100)]
    denominator: usize,

    #[param(slider, min = 0.00001, max = 1.0)]
    winding: f64,

    #[param(slider, min = 1., max = 300.)]
    radius: f64,

    #[param(slider, min = -4., max = 4.)]
    d_min: f64,

    #[param(slider, min = 0.0, max = 4.)]
    d_step: f64,

    #[param(slider, min = 1, max = 100)]
    d_num: usize,

    close_path: bool,
    hypotrochoid: bool,
    #[param(slider, min = 1, max = 20)]
    d_values_layers_modulus: usize,
        
    #[param(slider, min = 0.0, max = 1.)]
    angle_offset_per_d: f64,

    #[param(slider, min = 0.0, max = 1.)]
    angle_offset: f64,
}

impl Default for EpitrochoidSketch {
    fn default() -> Self {
        Self {
            num_points: 100,
            numerator: 1,
            denominator: 3,
            winding: 1.0,
            radius:50.0,
            d_min: 1.0,
            d_step: 0.1,
            d_num:1,
            close_path:true,
            hypotrochoid:false,
            d_values_layers_modulus: 3,
            angle_offset_per_d: 0.0,
            angle_offset: 0.0,
        }
    }
}

impl App for EpitrochoidSketch {
    fn update(&mut self, sketch: &mut Sketch, _ctx: &mut Context) -> anyhow::Result<()> {
        sketch.color(Color::DARK_RED)
        .scale(Unit::Mm)
        .stroke_width(0.3*Unit::Mm);


        let ratio = self.numerator as f64 / self.denominator as f64;
        let r = self.radius;
        let cent = 0.0;
        let sign: f64 = if self.hypotrochoid {-1.0} else {1.0};
        let start_angle = self.angle_offset * 2. * PI;
        for d_i in 0..self.d_num
        {
            let mut points = Vec::<Point>::new();
            let d = self.d_min + d_i as f64 * self.d_step;
            let numpoints: usize = (self.num_points as f64 *lcm(self.numerator,self.denominator) as f64 / self.denominator as f64 * self.winding) as usize;
            for i in 0..numpoints
            {
                let angle =  start_angle + 2. * PI * self.angle_offset_per_d * d_i as f64 + (i as f64 * 2. * PI ) / self.num_points as f64;
                let angle2 = ((1. + sign * ratio) / ratio) * angle;

                let mut cx1 = cent + (r + sign * r * ratio) * angle.cos();
                let mut cy1 = cent + (r + sign * r * ratio) * angle.sin();

                cx1 -= d * sign * r * ratio * angle2.cos();
                cy1 -= d * r * ratio * angle2.sin();
                points.push(Point::new(cx1,cy1))
            }
           

            sketch.set_layer(d_i % self.d_values_layers_modulus );
          
            // Set the color to one of the predefined colors based on the layer index
            sketch.color( COLORS[d_i % std::cmp::min(self.d_values_layers_modulus ,19)]);
            
            sketch.polyline(
            points,
            self.close_path,
        );
        }    

        Ok(())
    }
}

fn main() -> Result {
 EpitrochoidSketch::runner()
        .with_page_size_options(PageSize::A5H)
        .run()
}