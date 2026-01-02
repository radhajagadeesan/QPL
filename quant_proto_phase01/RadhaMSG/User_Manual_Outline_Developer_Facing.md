
# User Manual Outline (Developer-Facing)
## Certified Surface Language & Compiler Pipeline

**Project status:** programming complete, pipeline locked  
**License:** MIT (open source)  
**Corresponding author:** Radha Jagadeesan (<rjagadee@depaul.edu>)

---

## 1. Purpose of This Manual

This manual is the **authoritative user-facing guide** for the repository.

Its goals are to:
- explain what the system does and does *not* do,
- show users how to run it correctly,
- document supported surface-language features,
- provide curated examples that demonstrate capability,
- make the project usable without reading compiler internals.

This is **not** a theory paper and **not** a developer-internals document.

---

## 2. What This Repository Provides

At a high level, this repository provides:

- a **surface programming language** for composing quantum and structural programs,
- a **certified compilation pipeline** with locked semantics,
- guaranteed extraction for certified programs,
- deterministic, reproducible compilation artifacts.

Key properties:
- no recursion or feedback,
- no runtime branching,
- all higher-order constructs elaborate away,
- surface language is purely a frontend,
- compilation results are stable across runs.

---

## 3. What This Repository Does *Not* Provide

To avoid confusion, the following are **explicit non-features**:

- no dynamic control flow,
- no recursion or fixpoints,
- no measurement or classical branching,
- no implicit copying or projection,
- no user-visible optimization passes.

If you are looking for these features, this system is not the right tool.

---

## 4. Getting Started

### 4.1 Prerequisites
- Supported OS: Linux / macOS / Windows
- Required language runtimes (as specified in repo README)
- Python and/or OCaml toolchain (depending on frontend usage)

### 4.2 Installation
- Clone the repository
- Install dependencies
- Verify installation by running the minimal example

### 4.3 Quick Sanity Check
- Run a structural example
- Confirm deterministic output
- Confirm extraction succeeds

---

## 5. Surface Language Overview

### 5.1 Core Concepts
- programs as compositions of structure and unitary atoms,
- tensor composition and sequencing,
- finite datatypes and pattern matching (`case`),
- global phase annotation,
- exponentials of certified involutions.

### 5.2 Structural vs Unitary Programs
- **Structural programs**: routing only, no gates
- **Unitary programs**: may contain opaque unitary atoms
- Certification and admissibility are semantic, not syntactic

### 5.3 Datatypes and `case`
- finite, non-recursive datatypes only,
- `case` is a compile-time macro,
- no runtime branching semantics.

---

## 6. Using the Toolchain

### 6.1 Writing a Program
- defining datatypes,
- writing structural programs,
- composing unitary atoms,
- using `expᵢ(θ, J)` correctly.

### 6.2 Running the Compiler
- canonical entry points (CLI / script / host DSL),
- recommended flags,
- where outputs are written.

### 6.3 Outputs
- extracted circuit artifacts,
- permutation / routing artifacts,
- determinism guarantees.

---

## 7. Examples (Curated and Canonical)

The examples directory is structured as a **progressive learning path**.
Each example answers one concrete user question.

### 7.1 Structural Basics
Purpose: onboarding and confidence.

Examples:
- identity and composition,
- tensor and sum reassociation,
- simple swaps,
- datatype-based routing.

### 7.2 Datatypes as Control Structure
Purpose: expressiveness without runtime branching.

Examples:
- boolean-controlled routing,
- finite enums with multiple cases,
- nested (but finite) datatype usage.

### 7.3 Basic Quantum Constructions
Purpose: first use of unitary atoms.

Examples:
- single-qubit gates,
- two-qubit gates,
- Bell state preparation,
- GHZ state preparation.

### 7.4 Certified Involutions
Purpose: admissible inputs to exponentials.

Examples:
- tensor swap involution,
- sum swap involution,
- datatype swap involution.

### 7.5 Exponentials (`expᵢ`)
Purpose: core advanced feature.

Examples:
- valid exponential of a structural involution,
- composition with other programs,
- documented rejection of non-involutive input.

### 7.6 Algorithmic Smoke Tests
Purpose: demonstrate real-world capability.

Examples (provided):
- Deutsch–Jozsa,
- Hidden Subgroup Problem (standard),
- Hidden Subgroup Problem (phase kickback),
- Simon’s algorithm.

These are **smoke tests**, not tutorials:
they demonstrate that complex programs compile, certify, and extract.

---

## 8. Error Messages and Troubleshooting

- common user errors and how to fix them,
- interpretation of certification failures,
- how to minimize failing examples for bug reports.

---

## 9. Reproducibility and Stability Guarantees

- deterministic compilation,
- stable naming and serialization,
- reproducible artifacts across runs.

---

## 10. Open Source and Contribution Notes

- Project is open source under the **MIT License**
- Contributions welcome via standard PR workflow
- All contributions must respect locked pipeline invariants

**Corresponding author:**  
Radha Jagadeesan  
<rjagadee@depaul.edu>

---

## 11. Appendix (Optional)

- formal surface syntax summary,
- reference of supported constructs,
- extended example walkthroughs.
