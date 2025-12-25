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
    
    #[param(min = 0, max = 6)]
    num_tiles: usize,
    layout_index: usize,

    #[param(slider, min = 0.0, max = 1.)]
    top_margin: f64,
    #[param(slider, min = 0.0, max = 1.)]
    left_margin: f64,
    #[param(slider, min = 0.01, max = 1.)]
    relative_sketch_size: f64,
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
            layout_index: 0,
            top_margin: 0.05,
            left_margin: 0.05,
            relative_sketch_size: 0.9,
        }
    }
}

impl App for EpitrochoidSketch {
    fn update(&mut self, sketch: &mut Sketch, ctx: &mut Context) -> anyhow::Result<()> {
        sketch.color(Color::DARK_RED)
        .stroke_width(0.3*Unit::Mm);
        
        let ratio = self.numerator as f64 / self.denominator as f64;
        let cent = 0.0;
        let sign: f64 = if self.hypotrochoid {-1.0} else {1.0};
        let wrapping_factor = lcm(self.numerator,self.denominator) as f64 / self.denominator as f64;
        let mut start_angle = self.angle_offset * 2. * PI;
        let grid_layout = SquareGrid::new(self.num_tiles, Some(self.layout_index)) ;
        let smaller_size = sketch.width().min(sketch.height());
        
        // allocate a vector of vectors to hold points for each d value
        let mut allpoints = Vec::<Vec<Point>>::new();


        let numpoints: usize = (1000.0 * wrapping_factor ) as usize;

        // first pass: compute all points to find bounding box
        for d_i in 0..self.d_num
        {
            let r = 20. + d_i as f64 * self.radius_step;
            let mut points = Vec::<Point>::new();
            let d = self.d_min + d_i as f64 * self.d_step;
            for i in 0..numpoints
            {
                let angle =  wrapping_factor * start_angle + 2. * PI * self.angle_offset_per_d * d_i as f64 + (i as f64 * 2. * PI ) / 1000.;
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
        
        let scale_x = smaller_size/bbox_width * 0.8;
        let scale_y = smaller_size/bbox_height * 0.8;
        let scale = scale_x.min(scale_y);
        
        ctx.inspect("Overall scale", scale);
        
        // split the winding number acroos the number of tiles available in square grid
        let num_tiles = grid_layout.squares().len();
        ctx.inspect("Number of tiles", num_tiles);
        let winding = self.winding / num_tiles as f64;
        ctx.inspect("Winding per tile", winding);
        
        
        let numpoints: usize = 1 + (self.num_points as f64 * lcm(self.numerator,self.denominator) as f64 / self.denominator as f64 ) as usize;
        // iterate over the squares in grid layout
        sketch.translate(sketch.width() * self.left_margin, sketch.height() * self.top_margin );
        sketch.scale(self.relative_sketch_size);
        for square in grid_layout.iter_squares()
        {
            // get the translation and scale.
            //  then draw the partial sketch with the reduced winding 
            
            sketch.push_matrix();
            
            sketch.translate(square.render_pos.0 * smaller_size, -square.render_pos.1 * smaller_size);
            sketch.scale(square.render_scale);
            // print the render_scale to the console for debugging
            println!("Render scale: {}, start {}", square.render_scale,start_angle/2.0/PI);
            sketch.set_layer( self.d_values_layers_modulus );
            sketch.color( COLORS[0]);
            sketch.rect(smaller_size * 0.5,smaller_size * 0.5,smaller_size,smaller_size);
            sketch.scale(scale);
            sketch.translate(0.5 / scale *  smaller_size ,0.5 / scale *  smaller_size ); 
            for d_i in 0..self.d_num
            {
                let r = 20. + d_i as f64 * self.radius_step;
                let mut points = Vec::<Point>::new();
                let d = self.d_min + d_i as f64 * self.d_step;
                for i in 0..numpoints
                {
                    let angle =  wrapping_factor * start_angle + 2. * PI * self.angle_offset_per_d * d_i as f64 + (i as f64 * 2. * PI * winding ) / self.num_points as f64;
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
                
                sketch.polyline( points,self.close_path);
            } 
            
            sketch.pop_matrix();
            start_angle += 2. * PI * winding ;
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