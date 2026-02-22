use rand::Rng;

/// Transition matrix with phonotactic structure.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TransitionMatrix {
    /// N×N row-stochastic matrix. `matrix[i][j]` = P(next = j | current = i).
    pub matrix: Vec<Vec<f64>>,
    /// Probability of each letter starting a word.
    pub start_probs: Vec<f64>,
    /// Whether each letter index is a "vowel" (true) or "consonant" (false).
    pub is_vowel: Vec<bool>,
}

/// Generate a phonotactically-inspired sparse transition matrix.
///
/// The matrix has block structure:
/// - C→V transitions: dense (most consonants can be followed by most vowels)
/// - V→C transitions: dense (most vowels can be followed by most consonants)
/// - C→C transitions: sparse (~25% of pairs allowed, modeling consonant clusters)
/// - V→V transitions: sparse (~12% of pairs allowed, modeling diphthongs)
///
/// Within allowed transitions, weights are sampled from an exponential distribution
/// to produce natural-looking frequency variation (some transitions dominate).
pub fn generate_transition_matrix(
    alphabet_size: usize,
    vowel_fraction: f64,
    seed: u64,
) -> TransitionMatrix {
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    let mut rng = ChaCha8Rng::seed_from_u64(seed);
    let n = alphabet_size;

    // Assign vowel/consonant roles.
    let n_vowels = ((n as f64) * vowel_fraction).round().max(1.0) as usize;
    let mut is_vowel = vec![false; n];
    // Spread vowels evenly through the alphabet for variety.
    let mut vowel_indices: Vec<usize> = (0..n).collect();
    // Fisher-Yates shuffle with our seeded rng.
    for i in (1..vowel_indices.len()).rev() {
        let j = rng.r#gen_range(0..=i);
        vowel_indices.swap(i, j);
    }
    for &idx in &vowel_indices[..n_vowels.min(n)] {
        is_vowel[idx] = true;
    }

    // Connection probability for each block type.
    let p_cv = 0.85; // C→V: dense
    let p_vc = 0.80; // V→C: dense
    let p_cc = 0.25; // C→C: sparse (consonant clusters)
    let p_vv = 0.12; // V→V: sparse (diphthongs)

    // Build the matrix.
    let mut matrix = vec![vec![0.0f64; n]; n];

    for i in 0..n {
        let from_vowel = is_vowel[i];

        // Sample which successors are allowed.
        let mut row_total = 0.0;
        for j in 0..n {
            let to_vowel = is_vowel[j];
            let connect_prob = match (from_vowel, to_vowel) {
                (false, true) => p_cv,  // C→V
                (true, false) => p_vc,  // V→C
                (false, false) => p_cc, // C→C
                (true, true) => p_vv,   // V→V
            };

            if rng.r#gen::<f64>() < connect_prob {
                // Sample weight from exponential (rate=1) for natural variation.
                let weight = (-rng.r#gen::<f64>().max(1e-30).ln()).max(1e-6);
                matrix[i][j] = weight;
                row_total += weight;
            }
        }

        // Normalize row to sum to 1. If no successors (unlikely), uniform over all.
        if row_total < 1e-10 {
            for j in 0..n {
                matrix[i][j] = 1.0 / n as f64;
            }
        } else {
            for j in 0..n {
                matrix[i][j] /= row_total;
            }
        }
    }

    // Start distribution: consonants slightly more likely to start words.
    let mut start_probs = vec![0.0f64; n];
    let mut start_total = 0.0;
    for i in 0..n {
        let base = if is_vowel[i] { 0.6 } else { 1.0 };
        let weight = base * (-rng.r#gen::<f64>().max(1e-30).ln()).max(1e-6);
        start_probs[i] = weight;
        start_total += weight;
    }
    for p in &mut start_probs {
        *p /= start_total;
    }

    TransitionMatrix {
        matrix,
        start_probs,
        is_vowel,
    }
}

/// Sample a word length from NegBinomial(r, p) + 1 (minimum 1 letter).
///
/// Uses the gamma-Poisson mixture representation:
/// 1. Sample λ ~ Gamma(r, (1-p)/p)
/// 2. Sample k ~ Poisson(λ)
/// 3. Return k + 1
pub fn sample_word_length(r: f64, p: f64, rng: &mut impl Rng) -> usize {
    let r_clamped = r.max(0.1);
    let p_clamped = p.clamp(0.01, 0.99);

    // Sample from Gamma(r, (1-p)/p) using Marsaglia & Tsang's method.
    let scale = (1.0 - p_clamped) / p_clamped;
    let lambda = sample_gamma(r_clamped, scale, rng);

    // Sample from Poisson(lambda).
    let k = sample_poisson(lambda, rng);
    k + 1 // minimum 1 letter
}

/// Sample from Gamma(shape, scale) using Marsaglia & Tsang's method.
fn sample_gamma(shape: f64, scale: f64, rng: &mut impl Rng) -> f64 {
    if shape < 1.0 {
        // For shape < 1, use the relation: Gamma(a) = Gamma(a+1) * U^(1/a)
        let g = sample_gamma(shape + 1.0, 1.0, rng);
        let u: f64 = rng.r#gen::<f64>().max(1e-30);
        return scale * g * u.powf(1.0 / shape);
    }

    let d = shape - 1.0 / 3.0;
    let c = 1.0 / (9.0 * d).sqrt();

    loop {
        let x = sample_standard_normal(rng);
        let v = (1.0 + c * x).powi(3);
        if v <= 0.0 {
            continue;
        }
        let u: f64 = rng.r#gen::<f64>().max(1e-30);
        if u < 1.0 - 0.0331 * x * x * x * x {
            return scale * d * v;
        }
        if u.ln() < 0.5 * x * x + d * (1.0 - v + v.ln()) {
            return scale * d * v;
        }
    }
}

/// Sample from a standard normal distribution (Box-Muller).
fn sample_standard_normal(rng: &mut impl Rng) -> f64 {
    let u1: f64 = rng.r#gen::<f64>().max(1e-30);
    let u2: f64 = rng.r#gen::<f64>();
    (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos()
}

/// Sample from Poisson(lambda) using Knuth's algorithm for small lambda,
/// or the rejection method for larger lambda.
fn sample_poisson(lambda: f64, rng: &mut impl Rng) -> usize {
    if lambda < 30.0 {
        // Knuth's algorithm.
        let l = (-lambda).exp();
        let mut k = 0usize;
        let mut p = 1.0f64;
        loop {
            k += 1;
            p *= rng.r#gen::<f64>();
            if p <= l {
                return k - 1;
            }
        }
    } else {
        // For large lambda, use normal approximation.
        let x = sample_standard_normal(rng) * lambda.sqrt() + lambda;
        x.round().max(0.0) as usize
    }
}

/// Sample a single word as a sequence of letter indices.
pub fn sample_word(
    tm: &TransitionMatrix,
    length: usize,
    rng: &mut impl Rng,
) -> Vec<usize> {
    if length == 0 {
        return vec![];
    }

    let n = tm.matrix.len();
    let mut word = Vec::with_capacity(length);

    // Sample first letter from start distribution.
    let first = sample_categorical(&tm.start_probs, rng);
    word.push(first);

    // Sample subsequent letters from transition matrix.
    for _ in 1..length {
        let current = *word.last().unwrap();
        let next = sample_categorical(&tm.matrix[current % n], rng);
        word.push(next);
    }

    word
}

/// Generate a batch of words.
pub fn generate_words(
    tm: &TransitionMatrix,
    nb_r: f64,
    nb_p: f64,
    count: usize,
    rng: &mut impl Rng,
) -> Vec<Vec<usize>> {
    (0..count)
        .map(|_| {
            let len = sample_word_length(nb_r, nb_p, rng);
            sample_word(tm, len, rng)
        })
        .collect()
}

/// Sample from a categorical distribution (probability vector).
fn sample_categorical(probs: &[f64], rng: &mut impl Rng) -> usize {
    let u: f64 = rng.r#gen();
    let mut cumulative = 0.0;
    for (i, &p) in probs.iter().enumerate() {
        cumulative += p;
        if u < cumulative {
            return i;
        }
    }
    // Fallback for floating-point edge case.
    probs.len() - 1
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    #[test]
    fn test_transition_matrix_rows_sum_to_one() {
        let tm = generate_transition_matrix(20, 0.35, 42);
        for (i, row) in tm.matrix.iter().enumerate() {
            let sum: f64 = row.iter().sum();
            assert!(
                (sum - 1.0).abs() < 1e-10,
                "row {} sums to {}, expected 1.0",
                i,
                sum
            );
        }
    }

    #[test]
    fn test_start_probs_sum_to_one() {
        let tm = generate_transition_matrix(20, 0.35, 42);
        let sum: f64 = tm.start_probs.iter().sum();
        assert!((sum - 1.0).abs() < 1e-10, "start_probs sum to {}", sum);
    }

    #[test]
    fn test_vowel_count() {
        let tm = generate_transition_matrix(20, 0.35, 42);
        let n_vowels = tm.is_vowel.iter().filter(|&&v| v).count();
        assert_eq!(n_vowels, 7); // round(20 * 0.35) = 7
    }

    #[test]
    fn test_matrix_sparsity() {
        let tm = generate_transition_matrix(20, 0.35, 42);
        let n = tm.matrix.len();
        let nonzero = tm
            .matrix
            .iter()
            .flat_map(|row| row.iter())
            .filter(|&&v| v > 0.0)
            .count();
        let total = n * n;
        let density = nonzero as f64 / total as f64;
        // Should be substantially less than 1.0 (sparse).
        assert!(
            density < 0.75,
            "matrix density {} is too high (should be sparse)",
            density
        );
        // But not totally empty.
        assert!(
            density > 0.1,
            "matrix density {} is too low",
            density
        );
    }

    #[test]
    fn test_word_length_minimum() {
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        for _ in 0..100 {
            let len = sample_word_length(2.0, 0.4, &mut rng);
            assert!(len >= 1, "word length {} < 1", len);
        }
    }

    #[test]
    fn test_word_indices_in_bounds() {
        let tm = generate_transition_matrix(15, 0.35, 42);
        let mut rng = ChaCha8Rng::seed_from_u64(99);
        let words = generate_words(&tm, 2.0, 0.4, 50, &mut rng);
        for word in &words {
            assert!(!word.is_empty());
            for &idx in word {
                assert!(idx < 15, "letter index {} out of bounds", idx);
            }
        }
    }

    #[test]
    fn test_deterministic_with_same_seed() {
        let mut rng1 = ChaCha8Rng::seed_from_u64(123);
        let mut rng2 = ChaCha8Rng::seed_from_u64(123);
        let tm = generate_transition_matrix(20, 0.35, 42);

        let words1 = generate_words(&tm, 2.0, 0.4, 20, &mut rng1);
        let words2 = generate_words(&tm, 2.0, 0.4, 20, &mut rng2);
        assert_eq!(words1, words2);
    }
}
