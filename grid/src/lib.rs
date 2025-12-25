//! Library API for finding squarings of an n x n grid and working with a chosen solution.
use rand::Rng;

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

/// A chosen solution within the set of tilings for an `n x n` grid.
pub struct SquareGrid {
    /// Side length of the grid
    pub side: usize,
    /// Index into the solutions vector
    pub solution_index: usize,
    /// The selected solution matrix
    pub matrix: Vec<Vec<i32>>,
}

impl SquareGrid {
    /// Create a new `SquareGrid` for `side` selecting the solution at `index`.
    /// If `index` is `None`, a random solution is chosen.
    pub fn new(side: usize, index: Option<usize>) -> Self {
        let solutions = find_squarings(side);
        if solutions.is_empty() {
            return SquareGrid { side, solution_index: 0, matrix: vec![] };
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

        SquareGrid { side, solution_index: chosen, matrix: solutions[chosen].clone() }
    }

    /// Convenience constructor that always picks a random solution.
    pub fn new_random(side: usize) -> Self {
        Self::new(side, None)
    }

    /// Get a reference to the chosen solution matrix.
    pub fn solution(&self) -> &Vec<Vec<i32>> {
        &self.matrix
    }
}
