use grid::find_squarings;

#[test]
fn solution_counts_small() {
    // Known counts for n = 1,2,3
    let expected = [1usize,1usize, 2, 6,40,472,10_668];
    for (i, &exp) in expected.iter().enumerate() {
        let sols = find_squarings(i);
        assert_eq!(sols.len(), exp, "n = {} should have {} solutions", i, exp);
    }
}


