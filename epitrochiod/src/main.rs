use whiskers::prelude::*;
use std::f64::consts::PI;
use num_integer::lcm;
use vsvg::{Color, COLORS};
use grid::*;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Clone)]
struct SavedParams {
    num_points: Option<usize>,
    numerator: Option<usize>,
    denominator: Option<usize>,
    winding: Option<f64>,
    radius_step: Option<f64>,
    d_min: Option<f64>,
    d_step: Option<f64>,
    d_num: Option<usize>,
    close_path: Option<bool>,
    hypotrochoid: Option<bool>,
    d_values_layers_modulus: Option<usize>,
    angle_offset_per_d: Option<f64>,
    angle_offset: Option<f64>,
    num_tiles: Option<usize>,
    layout_index: Option<usize>,
    top_margin: Option<f64>,
    left_margin: Option<f64>,
    relative_sketch_size: Option<f64>,
    draw_bounding_box: Option<bool>,
    color_by_tile: Option<bool>,
}

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
    #[param(slider, min = 0.1, max = 1.5)]
    relative_sketch_size: f64,
    draw_bounding_box: bool,
    color_by_tile: bool,
    
    // Save/Load controls - these will appear in the UI
    save_preset_name: String,
    save_preset: bool,
    load_preset_name: String,
    load_preset: bool,
    refresh_presets: bool,
}

impl Default for EpitrochoidSketch {
    fn default() -> Self {
        Self {
            num_points: 100,
            numerator: 1,
            denominator: 3,
            winding: 1.0,
            radius_step: 0.0,
            d_min: 1.0,
            d_step: 0.1,
            d_num: 1,
            close_path: true,
            hypotrochoid: false,
            d_values_layers_modulus: 3,
            angle_offset_per_d: 0.0,
            angle_offset: 0.0,
            num_tiles: 1,
            layout_index: 0,
            top_margin: 0.05,
            left_margin: 0.05,
            relative_sketch_size: 0.9,
            draw_bounding_box: true,
            color_by_tile: false,
            save_preset_name: String::new(),
            save_preset: false,
            load_preset_name: String::new(),
            load_preset: false,
            refresh_presets: false,
        }
    }
}

impl EpitrochoidSketch {
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
            num_points: Some(self.num_points),
            numerator: Some(self.numerator),
            denominator: Some(self.denominator),
            winding: Some(self.winding),
            radius_step: Some(self.radius_step),
            d_min: Some(self.d_min),
            d_step: Some(self.d_step),
            d_num: Some(self.d_num),
            close_path: Some(self.close_path),
            hypotrochoid: Some(self.hypotrochoid),
            d_values_layers_modulus: Some(self.d_values_layers_modulus),
            angle_offset_per_d: Some(self.angle_offset_per_d),
            angle_offset: Some(self.angle_offset),
            num_tiles: Some(self.num_tiles),
            layout_index: Some(self.layout_index),
            top_margin: Some(self.top_margin),
            left_margin: Some(self.left_margin),
            relative_sketch_size: Some(self.relative_sketch_size),
            draw_bounding_box: Some(self.draw_bounding_box),
            color_by_tile: Some(self.color_by_tile),
        }
    }
    
    fn from_saved_params(&mut self, saved: SavedParams) {
        if let Some(v) = saved.num_points { self.num_points = v; }
        if let Some(v) = saved.numerator { self.numerator = v; }
        if let Some(v) = saved.denominator { self.denominator = v; }
        if let Some(v) = saved.winding { self.winding = v; }
        if let Some(v) = saved.radius_step { self.radius_step = v; }
        if let Some(v) = saved.d_min { self.d_min = v; }
        if let Some(v) = saved.d_step { self.d_step = v; }
        if let Some(v) = saved.d_num { self.d_num = v; }
        if let Some(v) = saved.close_path { self.close_path = v; }
        if let Some(v) = saved.hypotrochoid { self.hypotrochoid = v; }
        if let Some(v) = saved.d_values_layers_modulus { self.d_values_layers_modulus = v; }
        if let Some(v) = saved.angle_offset_per_d { self.angle_offset_per_d = v; }
        if let Some(v) = saved.angle_offset { self.angle_offset = v; }
        if let Some(v) = saved.num_tiles { self.num_tiles = v; }
        if let Some(v) = saved.layout_index { self.layout_index = v; }
        if let Some(v) = saved.top_margin { self.top_margin = v; }
        if let Some(v) = saved.left_margin { self.left_margin = v; }
        if let Some(v) = saved.relative_sketch_size { self.relative_sketch_size = v; }
        if let Some(v) = saved.draw_bounding_box { self.draw_bounding_box = v; }
        if let Some(v) = saved.color_by_tile { self.color_by_tile = v; }
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

impl App for EpitrochoidSketch {
    fn update(&mut self, sketch: &mut Sketch, ctx: &mut Context) -> anyhow::Result<()> {
        // Handle save/load button presses
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
        
        sketch.color(Color::DARK_RED)
            .stroke_width(0.3*Unit::Mm);
        
        let ratio = self.numerator as f64 / self.denominator as f64;
        let cent = 0.0;
        let sign: f64 = if self.hypotrochoid {-1.0} else {1.0};
        let wrapping_factor = lcm(self.numerator,self.denominator) as f64 / self.denominator as f64;
        let mut start_angle = self.angle_offset * 2. * PI;
        let grid_layout = SquareGrid::new(self.num_tiles, Some(self.layout_index)) ;
        let smaller_size = sketch.width().min(sketch.height());
        
        let mut allpoints = Vec::<Vec<Point>>::new();

        let numpoints: usize = (1000.0 * wrapping_factor ) as usize;

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
        
        let num_tiles = grid_layout.squares().len();
        ctx.inspect("Number of tiles", num_tiles);
        let winding = self.winding / num_tiles as f64;
        ctx.inspect("Winding per tile", winding);
        
        let numpoints: usize = 1 + (self.num_points as f64 * lcm(self.numerator,self.denominator) as f64 / self.denominator as f64 ) as usize;
        
        sketch.translate(sketch.width() * self.left_margin, sketch.height() * self.top_margin );
        sketch.scale(self.relative_sketch_size);
        for square in grid_layout.iter_squares()
        {
            sketch.push_matrix();
            
            sketch.translate(square.render_pos.0 * smaller_size, -square.render_pos.1 * smaller_size);
            sketch.scale(square.render_scale);
            
            println!("Render scale: {}, start {}", square.render_scale,start_angle/2.0/PI);
            if self.draw_bounding_box {
                sketch.set_layer( self.d_values_layers_modulus );
                sketch.color( COLORS[0]);
                sketch.rect(smaller_size * 0.5,smaller_size * 0.5,smaller_size,smaller_size);
            }

            if self.color_by_tile 
            {
                sketch.set_layer(square.id as usize % self.d_values_layers_modulus );
                sketch.color( COLORS[square.id as usize % std::cmp::min(self.d_values_layers_modulus ,19)]);
            }
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

                if !self.color_by_tile 
                {
                    sketch.set_layer(d_i % self.d_values_layers_modulus );
                    sketch.color( COLORS[d_i % std::cmp::min(self.d_values_layers_modulus ,19)]);
                }
 
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