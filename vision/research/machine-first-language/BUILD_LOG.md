# Build Log - Machine-First Compiler

## 2026-05-31 - Initial Compiler Breakdown

### Decision

The machine-first language is now framed as a bounded graph compiler, not as a syntax-first
programming language.

### Current Thesis

Human and AI collaborate on node/path blocks. The compiler enforces a 50-node boundary, validates
typed relationships, anchors relationships to executable mechanisms, and emits deterministic
projections.

### Key Components Added

- `COMPILER_OVERVIEW.md` - compiler purpose, pipeline, Day 0/Day 1 framing.
- `COMPILER_FUNCTIONS.md` - entities, node/path kinds, compiler function list, errors.
- `NEURAL_RELATIONSHIP_MAPPER.md` - local neural mapper architecture and learning boundary.

### Open Questions

- What is the minimal JSON Schema for a `Block`?
- Should the deterministic compiler core be Rust first or TypeScript first?
- Which graph UI library should host the Day 1 workbench?
- How should `crwl --json-extract --schema` outputs be normalized into proposals?
- What initial eval set proves the mapper is useful without overfitting?

### Next Build Slice

Create `schema/` with:

- `node.schema.json`
- `path.schema.json`
- `block.schema.json`
- `proposal.schema.json`
- `compile-error.schema.json`

Then implement a tiny validator that rejects:

- over-50-node blocks;
- unknown node/path kinds;
- dangling paths;
- unanchored effects;
- AI proposals treated as accepted graph facts.
