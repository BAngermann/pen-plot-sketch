# Asemic Writing System — Project Specification

## Overview

A modular system for generating asemic writing (writing-like marks that carry no semantic meaning) for pen plotters. The system is built as a set of related whiskers apps (Rust, using the `whiskers`/`vsvg` framework) organized as a pipeline: **glyph editor → word composer → sentence layout**.

Each stage has its own whiskers `#[sketch_app]` with a tailored UI, but all share a common library crate for data types, serialization, graph geometry, path generation, rendering, and the transition rule engine. The apps exchange data via serialized JSON config files.

The primary target is native desktop, but the project structure must be compatible with wasm deployment using the whiskers gallery pattern (lib/bin split with `wasm_sketch!` macro). See the `whiskers-gallery` crate in `https://github.com/abey79/vsvg` for the gallery/web-app structure — the owner will provide a detailed implementation guide for the wasm web app setup.

## Crate Structure

```
asemic-writing/
├── Cargo.toml                  # workspace
├── crates/
│   ├── asemic-core/            # shared library
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── graph.rs        # hex graph geometry, vertex/edge types
│   │   │   ├── path.rs         # path generation (random walks with constraints)
│   │   │   ├── decoration.rs   # branching stroke generation
│   │   │   ├── glyph.rs        # glyph data types, property computation
│   │   │   ├── render.rs       # BezPath rendering from edge sequences
│   │   │   ├── library.rs      # glyph library serialization/deserialization
│   │   │   ├── transition.rs   # generic Markov transition engine
│   │   │   └── properties.rs   # property trait definitions
│   │   └── Cargo.toml
│   ├── glyph-editor/           # whiskers app: design glyph constraints, sample & curate
│   │   ├── src/
│   │   │   ├── lib.rs          # sketch code + wasm_sketch! macro
│   │   │   └── main.rs         # native entry point
│   │   └── Cargo.toml
│   ├── word-composer/          # whiskers app: word grammar and layout (future)
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   └── main.rs
│   │   └── Cargo.toml
│   └── sentence-layout/        # whiskers app: sentence/text layout (future)
│       ├── src/
│       │   ├── lib.rs
│       │   └── main.rs
│       └── Cargo.toml
```

## Phase 1: asemic-core + glyph-editor

The initial implementation focuses on the shared library and the glyph editor app. The word composer and sentence layout apps are deferred until the visual character of the glyphs is established, but the core library types should anticipate their needs.

---

## Hex Graph (asemic-core::graph)

### Geometry

The graph is a tiling of flat-top hexagons (parallel sides are horizontal) arranged in 3 vertical columns:

- Left column: 2 hexagons
- Middle column: 3 hexagons
- Right column: 2 hexagons

All hexagons have the same size. The columns are arranged so that the left and right columns are offset vertically (as in a standard hex grid with flat-top hexes in an offset column layout).

### Data Structures

The graph is defined by:

- **Vertices**: all unique vertices of the hex tiling, identified by index. Each vertex has a 2D position.
- **Edges**: all unique edges of the hex tiling, identified by index. Each edge connects two vertex indices.
- **Entry point**: the leftmost vertex at the vertical midline of the tiling.
- **Exit point**: the rightmost vertex at the vertical midline of the tiling.

The graph definition is fixed for a given hex layout and is computed once at initialization. It is shared (not duplicated) across all glyphs in a library.

### Requirements

- Compute the full vertex and edge lists from hexagon size and layout parameters.
- Identify the entry and exit vertices.
- Provide adjacency queries: for a given vertex, return all incident edges; for a given edge, return both endpoint vertices.
- The graph should be parameterizable (hex size, potentially different layouts later) but the 2-3-2 flat-top layout is the initial and default configuration.

---

## Path Generation (asemic-core::path)

### Constraints (user-editable parameters)

- **Path length distribution**: minimum and maximum number of edges in a path (or a target distribution to sample from).
- **Max edge visits**: how many times a single edge may be traversed (1 = Hamiltonian-like, 2 = allows revisiting).
- **Max vertex visits**: how many times a single vertex may be traversed.
- **No immediate backtracking**: the path may not traverse the same edge in consecutive steps (i.e., no going back and forth on the same edge).

### Algorithm

- Paths start at the entry vertex and end at the exit vertex.
- Path generation is a constrained random walk on the graph: at each step, choose a random edge from the set of valid edges (those that don't violate visit counts or backtracking rules) incident to the current vertex. If no valid edges remain before reaching the exit, discard and retry.
- The sampler should support generating batches of candidate paths efficiently for display in the UI.
- A path is represented as an ordered sequence of edge indices.

### Requirements

- Implement the constrained random walk sampler.
- Provide batch generation: given constraints, produce N candidate paths.
- Validate paths against constraints (for testing and for loading saved libraries).
- The path generation must be deterministic given a seed (use `rand` with a seedable RNG).

---

## Decorations (asemic-core::decoration)

### Concept

A decoration is a short branching stroke attached to the main connecting path. It adds visual variation without affecting the main path's connectivity.

### Generation Rules

A decoration is an ordered sequence of edges where:

1. The **first edge** is an edge that is part of the main path (the shared/anchor edge). This ensures the decoration starts tangent to the main stroke — the tangent continuity is a structural consequence of sharing the first edge with the main path, not something that needs to be enforced in the renderer.
2. The **subsequent edges** (1 or 2) branch off from the endpoint of the shared edge onto edges that are **not part of the main path** (or at least diverge from it).

The decoration's BezPath rendering starts partway along the shared edge and continues along the branch edges, so it visually sprouts from the main stroke.

### Constraints (user-editable)

- **Decoration probability**: probability of generating a decoration at each eligible vertex along the main path.
- **Max branch length**: number of edges beyond the shared edge (1 or 2).
- **Max decorations per glyph**: upper limit on total decoration count.

### Requirements

- Given a main path, identify eligible branch points (vertices on the main path that have incident edges not fully used by the main path).
- Sample decorations according to the probability and length constraints.
- Store each decoration as: anchor vertex index (on the main path), the shared edge index, and the branch edge sequence.

---

## Glyph Data Types (asemic-core::glyph)

### Glyph Definition

A glyph stored in the library consists of:

```rust
struct GlyphDef {
    /// Unique identifier within the library
    id: String,
    /// Main connecting path: ordered sequence of edge indices (entry → exit)
    main_path: Vec<usize>,
    /// Decorations: branching strokes attached to the main path
    decorations: Vec<DecorationDef>,
    /// Per-glyph rendering overrides (optional, falls back to library defaults)
    rendering: Option<RenderingParams>,
    /// Pre-computed properties for the transition engine
    properties: GlyphProperties,
}

struct DecorationDef {
    /// Vertex on the main path where the decoration anchors
    anchor_vertex: usize,
    /// The shared edge (part of main path)
    shared_edge: usize,
    /// Branch edges (not part of main path)
    branch_edges: Vec<usize>,
}
```

### Glyph Properties

Pre-computed from the path and decorations, stored alongside each glyph:

```rust
struct GlyphProperties {
    /// Number of edges in the main path
    path_length: usize,
    /// Number of unique vertices visited
    vertex_count: usize,
    /// Number of direction changes (angles between consecutive edges)
    direction_changes: usize,
    /// Total absolute turning angle (sum of angles between consecutive edges)
    total_turning: f64,
    /// Number of decorations
    decoration_count: usize,
    /// Total decoration edge length
    total_decoration_edges: usize,
    /// Bounding box width/height ratio of the path (computed from vertex positions)
    aspect_ratio: f64,
    /// Fraction of the glyph bounding box covered by the path
    coverage: f64,
}
```

Properties are computed by the glyph editor when a glyph is accepted into the library and are stored in the serialized library file. The word and sentence layers consume only the property table; they do not need to understand glyph internals.

### GlyphProperties Trait

```rust
trait HasProperties {
    fn properties(&self) -> &GlyphProperties;
    fn path_length(&self) -> usize { self.properties().path_length }
    fn complexity(&self) -> f64 { self.properties().total_turning }
    fn decoration_count(&self) -> usize { self.properties().decoration_count }
    // ... convenience accessors
}
```

This trait will later be generalized or paralleled by a `WordProperties` trait for the sentence-level transition engine.

---

## Rendering (asemic-core::render)

### BezPath Generation

Convert an edge sequence (main path or decoration) into a `kurbo::BezPath` by:

1. Map the edge sequence to its ordered vertex positions.
2. Apply per-vertex positional jitter (random offset within a configurable radius).
3. Fit a smooth curve through the jittered points using Catmull-Rom interpolation (vsvg provides `CatmullRom` support), then convert to cubic Béziers.
4. A **tightness parameter** (0.0–1.0) controls how closely the curve follows the original vertex positions. At 1.0, the curve passes almost exactly through vertices (polygonal feel). At lower values, the curve smooths out and merely passes near the vertices.

### Rendering Parameters

```rust
struct RenderingParams {
    /// How closely the BezPath follows the hex graph vertices (0.0 = loose, 1.0 = tight)
    tightness: f64,
    /// Maximum random offset per vertex, in units of hex edge length
    vertex_jitter: f64,
    /// Additional random offset applied to BezPath control points
    control_point_jitter: f64,
}
```

### Requirements

- Render a glyph (main path + decorations) as a collection of `kurbo::BezPath`.
- The main path is one continuous BezPath; each decoration is a separate BezPath.
- Rendering must be deterministic given a seed.
- The hex graph skeleton should be renderable as a ghost overlay (for the editor UI).

---

## Glyph Library (asemic-core::library)

### Library File Format

JSON file containing:

```rust
struct GlyphLibrary {
    /// Version for forward compatibility
    version: String,
    /// Hex graph parameters (so the graph can be reconstructed)
    graph_params: GraphParams,
    /// Sampling constraints used to generate the glyphs
    sampling_constraints: SamplingConstraints,
    /// Default rendering parameters
    default_rendering: RenderingParams,
    /// The glyphs
    glyphs: Vec<GlyphDef>,
}

struct GraphParams {
    hex_size: f64,
    // layout is fixed at 2-3-2 for now, but stored for future extensibility
    layout: HexLayout,
}

struct SamplingConstraints {
    min_path_length: usize,
    max_path_length: usize,
    max_edge_visits: usize,
    max_vertex_visits: usize,
    decoration_probability: f64,
    max_decoration_branch_length: usize,
    max_decorations_per_glyph: usize,
}
```

### Requirements

- Serialize/deserialize with serde_json.
- Validate on load: verify all edge/vertex indices are valid for the stored graph params.
- The library file is the interface contract between the glyph editor and the word/sentence apps.

---

## Transition Engine (asemic-core::transition) — Design Only for Phase 1

The transition engine is not needed for the glyph editor but should be anticipated in the trait design. The engine operates as follows:

- Maintains a state of the last k elements (order-k Markov chain).
- Given the state, computes transition probabilities for each candidate next element using a score function over properties: `score(history: &[&GlyphProperties], candidate: &GlyphProperties) -> f64`.
- Score functions are composable (sum/product of individual property-based rules).
- The rule configuration is serializable (stored in the word/sentence grammar JSON files).

This will be implemented in a later phase. For Phase 1, ensure the `GlyphProperties` struct and `HasProperties` trait are sufficient to support this use case.

---

## Glyph Editor App (glyph-editor)

### Whiskers App Structure

Implements `#[sketch_app]` with the following UI parameters:

**Graph parameters:**
- Hex size

**Sampling constraint parameters:**
- Min/max path length
- Max edge visits (1 or 2)
- Max vertex visits
- Decoration probability
- Max decoration branch length (1 or 2)
- Max decorations per glyph

**Rendering parameters:**
- Tightness
- Vertex jitter
- Control point jitter

**Actions:**
- Generate batch: produce N candidate glyphs with current constraints/rendering and display them in a grid.
- Accept/reject individual glyphs from the batch into the library.
- View current library: display all accepted glyphs.
- Remove glyph from library.
- Save library to JSON file.
- Load library from JSON file.

### Display

- The `update` method renders either:
  - A grid of candidate glyphs (batch generation mode), each showing the BezPath rendering with the hex graph as a faint ghost overlay.
  - The current library contents (library view mode).
- Entry and exit points should be visually marked.
- Each glyph in the grid should be labeled with its key properties (path length, decoration count, complexity) for quick assessment.

### Workflow

1. Set constraints and rendering parameters.
2. Generate a batch of candidates.
3. Browse candidates, accept the ones you want.
4. Adjust parameters, generate more.
5. Review the full library.
6. Save.

---

## Connector Strokes — Design Note (Future)

When composing words, glyphs are chained together. The connection between consecutive glyphs is a short BezPath segment whose start matches the exit point/tangent of the preceding glyph and whose end matches the entry point/tangent of the next glyph. This is generated by the word composer, not stored in the glyph library. Since all glyphs share the same entry and exit points (determined by the hex graph), connectors are uniform in attachment geometry but can vary in curvature/length. This will be implemented in the word composer phase.

---

## Writing Path — Design Note (Future)

The sentence layout app places words along a *writing path* — an abstraction that yields placement positions and local coordinate frames. The simplest writing path is a horizontal line (left-to-right), but the system should not assume this. Future writing paths include: curves, spirals, circles, branching trees. The writing path is a trait that the sentence layout app uses; glyph and word layers are agnostic to it. Exact trait design deferred to the sentence layout phase.

---

## Non-Goals for Phase 1

- Word composition and transition rules (design only, no implementation).
- Sentence layout.
- Wasm deployment (structure must be compatible, but wasm build/deploy is deferred).
- Interactive path editing (glyphs are sampled from constraints, not hand-drawn).
- Ligature support.

---

## Testing Requirements

**IMPORTANT: Write comprehensive tests throughout development. Every module must have tests. Do not defer testing to a later phase — write tests alongside the implementation. Tests are not optional.**

### Unit Tests (asemic-core)

- **graph.rs**: Verify vertex/edge counts for the 2-3-2 layout. Verify entry/exit vertex identification. Verify adjacency queries return correct edges/vertices. Test that all edges connect valid vertices and all vertex positions are distinct.
- **path.rs**: Test that generated paths start at entry and end at exit. Test constraint enforcement: edge visit counts, vertex visit counts, no immediate backtracking, path length within bounds. Test determinism: same seed produces same path. Test that the sampler handles impossible constraints gracefully (e.g., path length longer than the graph allows). Test batch generation produces the requested number of paths (or reports inability). Verify path validation accepts valid paths and rejects invalid ones.
- **decoration.rs**: Test that decorations anchor to main path vertices. Test that the shared edge is part of the main path. Test that branch edges are not part of the main path. Test decoration count respects max constraint. Test branch length respects max constraint.
- **glyph.rs**: Test property computation against known paths (manually computed expected values). Test that properties are consistent with the path (e.g., path_length matches edge count).
- **render.rs**: Test that BezPath generation produces valid BezPaths (no NaN, no degenerate segments). Test that tightness=1.0 produces a curve that passes close to all vertex positions. Test determinism: same seed + same params → same BezPath. Test that decorations produce separate BezPaths.
- **library.rs**: Test round-trip serialization: save → load → compare. Test validation on load: reject libraries with invalid edge indices. Test version handling.

### Integration Tests

- Generate a full library (constraints → paths → decorations → properties → serialize → deserialize) and verify end-to-end consistency.
- Test that glyph properties computed before and after serialization round-trip are identical.

### Property-Based Tests

Consider using `proptest` or `quickcheck` for:
- Any valid path satisfies all constraints.
- Any valid decoration satisfies all decoration constraints.
- Serialization round-trips are lossless.

---

## Dependencies

- `whiskers` (with viewer feature) — sketch framework
- `vsvg` — vector graphics core, `kurbo::BezPath`
- `serde`, `serde_json` — serialization
- `rand`, `rand_chacha` — deterministic RNG
- `anyhow` — error handling
- `proptest` or `quickcheck` (dev dependency) — property-based testing
