use whiskers::prelude::*;
use std::f64::consts::PI;
use num_integer::lcm;
use vsvg::{Color, COLORS};
use grid::*;

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
    
    #[param(slider, min = 0., max = 3.)]
    radius_step: f64,
    
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

    num_tiles: usize,
}

impl Default for EpitrochoidSketch {
    fn default() -> Self {
        Self {
            num_points: 100,
            numerator: 1,
            denominator: 3,
            winding: 1.0,
            radius_step:0.0,
            d_min: 1.0,
            d_step: 0.1,
            d_num:1,
            close_path:true,
            hypotrochoid:false,
            d_values_layers_modulus: 3,
            angle_offset_per_d: 0.0,
            angle_offset: 0.0,
            num_tiles: 1,
        }
    }
}

impl App for EpitrochoidSketch {
    fn update(&mut self, sketch: &mut Sketch, _ctx: &mut Context) -> anyhow::Result<()> {
        sketch.color(Color::DARK_RED)
        .stroke_width(0.3*Unit::Mm);
        
        let ratio = self.numerator as f64 / self.denominator as f64;
        let cent = 0.0;
        let sign: f64 = if self.hypotrochoid {-1.0} else {1.0};
        let start_angle = self.angle_offset * 2. * PI;
        
        // allocate a vector of vectors to hold points for each d value
        let mut allpoints = Vec::<Vec<Point>>::new();
        // first pass: compute all points to find bounding box
        for d_i in 0..self.d_num
        {
            let r = 20. + d_i as f64 * self.radius_step;
            let mut points = Vec::<Point>::new();
            let d = self.d_min + d_i as f64 * self.d_step;
            let numpoints: usize = (1000.0*lcm(self.numerator,self.denominator) as f64 / self.denominator as f64 ) as usize;
            for i in 0..numpoints
            {
                let angle =  start_angle + 2. * PI * self.angle_offset_per_d * d_i as f64 + (i as f64 * 2. * PI ) / 1000.;
                let angle2 = ((1. + sign * ratio) / ratio) * angle;
                
                let mut cx1 = cent + (r + sign * r * ratio) * angle.cos();
                let mut cy1 = cent + (r + sign * r * ratio) * angle.sin();
                
                cx1 -= d * sign * r * ratio * angle2.cos();
                cy1 -= d * r * ratio * angle2.sin();
                points.push(Point::new(cx1,cy1))
            }
            allpoints.push(points);
        } 
        // find the bounding box of the points
        let mut min_x = std::f64::MAX;
        let mut max_x = std::f64::MIN;
        let mut min_y = std::f64::MAX;
        let mut max_y = std::f64::MIN;
        for points in &allpoints {
            for p in points {
                if p.x() < min_x { min_x = p.x(); }
                if p.x() > max_x { max_x = p.x(); }
                if p.y() < min_y { min_y = p.y(); }
                if p.y() > max_y { max_y = p.y(); }
            }
        }
        let bbox_width = max_x - min_x;   
        let bbox_height = max_y - min_y;
        
        let scale_x = sketch.width()/bbox_width * 0.8;
        let scale_y = sketch.height()/bbox_height * 0.8;
        let scale = scale_x.min(scale_y);
        
        
        allpoints = Vec::<Vec<Point>>::new();
        
        for d_i in 0..self.d_num
        {
            let r = 20. + d_i as f64 * self.radius_step;
            let mut points = Vec::<Point>::new();
            let d = self.d_min + d_i as f64 * self.d_step;
            let numpoints: usize = 1 + (self.num_points as f64 *lcm(self.numerator,self.denominator) as f64 / self.denominator as f64 ) as usize;
            for i in 0..numpoints
            {
                let angle =  start_angle + 2. * PI * self.angle_offset_per_d * d_i as f64 + (i as f64 * 2. * PI * self.winding ) / self.num_points as f64;
                let angle2 = ((1. + sign * ratio) / ratio) * angle;
                
                let mut cx1 = cent + (r + sign * r * ratio) * angle.cos();
                let mut cy1 = cent + (r + sign * r * ratio) * angle.sin();
                
                cx1 -= d * sign * r * ratio * angle2.cos();
                cy1 -= d * r * ratio * angle2.sin();
                points.push(Point::new(cx1,cy1))
            }
            allpoints.push(points);
        } 

        
        sketch.scale(scale);
        sketch.translate(0.5 / scale *  sketch.width() ,
        0.5 / scale *  sketch.height() ); 
        for d_i in 0..self.d_num
        {
            sketch.set_layer(d_i % self.d_values_layers_modulus );
            
            // Set the color to one of the predefined colors based on the layer index
            sketch.color( COLORS[d_i % std::cmp::min(self.d_values_layers_modulus ,19)]);
            
            sketch.polyline( std::mem::take(&mut allpoints[d_i]),self.close_path);
        }
        
        
        Ok(())
    }
}

fn main() -> Result {
    EpitrochoidSketch::runner()
    .with_page_size_options(PageSize::A5H)
    .with_layout_options(LayoutOptions::Off)
    .run()
}