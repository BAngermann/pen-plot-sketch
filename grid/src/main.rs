use grid::{find_squarings, print_matrix, SquareGrid};

fn main() {
    // Example: show counts for 1..=6 and print one random solution for n=5
    for n in 1..=6 {
        let sols = find_squarings(n);
        println!("n = {} -> {} solution(s)", n, sols.len());
    }

    println!("\nExample: pick a random solution for n = 5\n");
    let grid = SquareGrid::new_random(5);
    println!("Chosen solution index: {}", grid.solution_index);
    print_matrix(grid.solution());
}
