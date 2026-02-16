//! Transition engine — design only for Phase 1.
//!
//! The transition engine will operate as follows:
//! - Maintains a state of the last k elements (order-k Markov chain).
//! - Given the state, computes transition probabilities for each candidate
//!   next element using a score function over properties.
//! - Score functions are composable (sum/product of individual property-based rules).
//! - The rule configuration is serializable.
//!
//! This module provides the trait definitions and placeholder types.
//! Full implementation is deferred to the word composer phase.

use crate::properties::GlyphProperties;

/// A scoring rule that evaluates how well a candidate follows a history of elements.
///
/// Implementations will score based on property differences, similarity, contrast, etc.
pub trait ScoringRule: Send + Sync {
    /// Compute a non-negative score for a candidate given the recent history.
    /// Higher scores mean the candidate is more likely to be chosen.
    fn score(&self, history: &[&GlyphProperties], candidate: &GlyphProperties) -> f64;
}

/// Configuration for a transition rule, serializable for storage in grammar files.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TransitionConfig {
    /// Order of the Markov chain (how many previous elements to consider).
    pub order: usize,
    /// Placeholder for rule configurations. Will be expanded in Phase 2.
    pub rules: Vec<RuleConfig>,
}

/// A single rule configuration (placeholder).
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct RuleConfig {
    /// Name/type of the rule.
    pub rule_type: String,
    /// Weight for combining multiple rules.
    pub weight: f64,
    /// Rule-specific parameters as key-value pairs.
    pub params: std::collections::HashMap<String, f64>,
}
