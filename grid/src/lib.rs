//! Library API for finding squarings of an n x n grid and working with a chosen solution.
use rand::Rng;
use std::collections::BTreeMap;

/// Finds all possible ways to divide an `n x n` grid into smaller squares.
///
/// Returns a vector of matrices; each matrix is a tiling where each distinct
/// square has a unique positive integer id.
pub fn find_squarings(n: usize) -> Vec<Vec<Vec<i32>>> {
    if n == 0 {
        return vec![vec![]];
    }
    if n > 6 {
        panic!("This implementation is designed for n < 7 for performance reasons.");
    }

    let mut solutions = Vec::new();
    let initial_grid = vec![vec![0; n]; n];
    solve(n, initial_grid, 1, &mut solutions);
    solutions
}

fn solve(n: usize, grid: Vec<Vec<i32>>, next_id: i32, solutions: &mut Vec<Vec<Vec<i32>>>) {
    if let Some((r, c)) = find_first_empty(&grid) {
        let max_s = std::cmp::min(n - r, n - c);
        for s in 1..=max_s {
            if can_place(&grid, r, c, s) {
                let mut new_grid = grid.clone();
                place_square(&mut new_grid, r, c, s, next_id);
                solve(n, new_grid, next_id + 1, solutions);
            }
        }
    } else {
        solutions.push(grid);
    }
}

fn find_first_empty(grid: &Vec<Vec<i32>>) -> Option<(usize, usize)> {
    for r in 0..grid.len() {
        for c in 0..grid[r].len() {
            if grid[r][c] == 0 {
                return Some((r, c));
            }
        }
    }
    None
}

fn can_place(grid: &Vec<Vec<i32>>, r_start: usize, c_start: usize, s: usize) -> bool {
    for r in r_start..r_start + s {
        for c in c_start..c_start + s {
            if grid[r][c] != 0 {
                return false;
            }
        }
    }
    true
}

fn place_square(grid: &mut Vec<Vec<i32>>, r_start: usize, c_start: usize, s: usize, id: i32) {
    for r in r_start..r_start + s {
        for c in c_start..c_start + s {
            grid[r][c] = id;
        }
    }
}

/// Print a matrix to stdout.
pub fn print_matrix(matrix: &Vec<Vec<i32>>) {
    if matrix.is_empty() || matrix[0].is_empty() {
        println!("[ ]");
        return;
    }
    for row in matrix {
        for &val in row {
            print!("{: >2} ", val);
        }
        println!();
    }
}

/// position and size of a square within the grid
#[derive(Debug, Clone, Copy)]
pub struct Square {
    /// row index of the top-left corner
    pub row: usize,
    /// column index of the top-left corner
    pub col: usize,
    /// size of the square in units of tiles of the grid
    pub size: usize,
    /// x and y position when rendered, relative to a fraction of the total width/height.
    pub render_pos: (f64, f64),
    /// scale of the tile when rendered, relative to the total width/height.
    pub render_scale: f64,
}

/// A chosen solution within the set of tilings for an `n x n` grid.
pub struct SquareGrid {
    /// Side length of the grid
    pub side: usize,
    /// Index into the solutions vector
    pub solution_index: usize,
    /// The selected solution matrix
    pub matrix: Vec<Vec<i32>>,
    /// Cached list of `Square` structs for iteration
    pub squares: Vec<Square>,
    /// The withd of the gutter beteween squares when printed, as fraction of the width of the entire grid.
    pub gutter: f64,
}

impl SquareGrid {
    /// Create a new `SquareGrid` for `side` selecting the solution at `index`.
    /// If `index` is `None`, a random solution is chosen.
    pub fn new(side: usize, index: Option<usize>) -> Self {
        let solutions = find_squarings(side);
        if solutions.is_empty() {
            return SquareGrid { side, solution_index: 0, matrix: vec![], squares: vec![], gutter: 0.0 };
        }

        let chosen = match index {
            Some(i) => {
                let idx = if i < solutions.len() { i } else { 0 };
                idx
            }
            None => {
                let mut rng = rand::thread_rng();
                rng.gen_range(0..solutions.len())
            }
        };

        let gutter= 1. / (side as f64) * 0.05 ;
        let matrix = solutions[chosen].clone();
        let squares = compute_squares(side, &matrix, gutter);
        SquareGrid { side, solution_index: chosen, matrix, squares, gutter }
    }

    /// Convenience constructor that always picks a random solution.
    pub fn new_random(side: usize) -> Self {
        Self::new(side, None)
    }

    /// Get a reference to the chosen solution matrix.
    pub fn solution(&self) -> &Vec<Vec<i32>> {
        &self.matrix
    }

    /// Return a slice of computed `Square` structs for the chosen solution.
    /// Each `Square` contains the top-left `row`/`col`, `size` in tiles,
    /// and `render_pos`/`render_scale` already adjusted for `gutter`.
    pub fn squares(&self) -> &[Square] {
        &self.squares
    }

    /// Return an iterator yielding references to `Square` entries.
    pub fn iter_squares(&self) -> std::slice::Iter<'_, Square> {
        self.squares.iter()
    }
}

fn compute_squares(side: usize, matrix: &Vec<Vec<i32>>, gutter: f64) -> Vec<Square> {
    let mut map: BTreeMap<i32, (usize, usize, usize, usize)> = BTreeMap::new();
    for r in 0..side {
        for c in 0..side {
            let id = matrix[r][c];
            if id <= 0 { continue; }
            map.entry(id)
                .and_modify(|e| {
                    e.0 = e.0.min(r);
                    e.1 = e.1.min(c);
                    e.2 = e.2.max(r);
                    e.3 = e.3.max(c);
                })
                .or_insert((r, c, r, c));
        }
    }

    let tile_size = (1.0 - gutter * ((side as f64) - 1.0)) / (side as f64);
    let gap = gutter;

    let mut squares = Vec::with_capacity(map.len());
    for (_id, (min_r, min_c, max_r, max_c)) in map {
        let size_r = max_r - min_r + 1;
        let size_c = max_c - min_c + 1;
        debug_assert_eq!(size_r, size_c, "non-square bounding box for id");
        let size = size_r;
        let render_scale = tile_size * (size as f64) + gap * ((size as f64) - 1.0);
        // row -> x increases to the right, col -> y increases downward.
        // Per your request, downward maps to increasingly negative y values.
        let render_pos_x = (min_r as f64) * (tile_size + gap);
        let render_pos_y = - (min_c as f64) * (tile_size + gap);
        squares.push(Square {
            row: min_r,
            col: min_c,
            size,
            render_pos: (render_pos_x, render_pos_y),
            render_scale,
        });
    }
    squares
}
