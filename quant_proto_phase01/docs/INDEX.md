# Documentation Index

## Current — public

| Document | Role |
|---|---|
| [`PROGRAMMING_GUIDE.md`](PROGRAMMING_GUIDE.md) | **The authoritative language guide** (`let%source` Source syntax); examples compiled by `ocaml/examples/doc_examples.ml` |
| [`../ocaml/demos/README.md`](../ocaml/demos/README.md) | Examples/demo guide; relation of concise counterparts to the 34 retained demos; `coverage.tsv` is the ledger authority |
| [`LIMITATIONS.md`](LIMITATIONS.md) | **Sole current limitations authority** |
| [`VERIFICATION.md`](VERIFICATION.md) | Reproduction commands and expected results |

## Current — developer / internal

| Document | Role |
|---|---|
| [`OCAML_DSL.md`](OCAML_DSL.md) | The sealed `Source` API and the internal Raw/Linear layers |
| [`DATATYPE_ELABORATION.md`](DATATYPE_ELABORATION.md) | Datatype operation/elimination layer as implemented (Qudit(n), permutations, cases, canonical left association) |
| [`COMPILER_API_GUIDE.md`](COMPILER_API_GUIDE.md) | Compilation pipeline (internal) |
| [`API_REFERENCE.md`](API_REFERENCE.md) | Internal type/term reference (Raw + Python IR) |
| [`TOOLCHAIN.md`](TOOLCHAIN.md) | Two-stage pipeline architecture |
| [`IR_DESIGN.md`](IR_DESIGN.md) | Bridge IR design |
| [`COMPILER_INVARIANTS.md`](COMPILER_INVARIANTS.md) | Compiler invariants (SeqCut, beta boundaries, blocks, frames) |
| [`BRANCH_CONTEXT_LINEARITY.md`](BRANCH_CONTEXT_LINEARITY.md) | Branch-context transport discipline |
| [`typing_rules_reference.md`](typing_rules_reference.md) | Typing-rule quick reference (internal layers) |
| [`ALIGN_NORMALIZATION.md`](ALIGN_NORMALIZATION.md) | **Open, post-v1.0.0**: Align normalization (cost/optimization debt, not a correctness blocker) |
| [`SUM_INTRODUCTION_DESIGN.md`](SUM_INTRODUCTION_DESIGN.md) | Coherent ⊕-introduction: design and as-built record (closed-premise Raw/backend) |
| [`LAYOUT_FRAME_REPAIR.md`](LAYOUT_FRAME_REPAIR.md) | Gate-free distributivity repair — implemented record |
| [`N_SWITCH.md`](N_SWITCH.md) | The n-quantum-switch constructions and scaling notes |

## Historical records ([`history/`](history/))

Checkpoint and design documents retained verbatim for provenance; each
carries a banner naming its checkpoint/date.  They describe the state of
the system *at that time*, not the current system.

| Document | What it recorded |
|---|---|
| [`history/SOURCE_FRONTEND_SLICE_REPORT.md`](history/SOURCE_FRONTEND_SLICE_REPORT.md) | The PPX vertical-slice report (checkpoint `source-ppx-slice-20260905`) |
| [`history/SOURCE_FRONTEND_LEDGER.md`](history/SOURCE_FRONTEND_LEDGER.md) | The Phase-1 feasibility ledger, superseded by `ocaml/counterparts/coverage.tsv` |
| [`history/RELEASE_SAFETY_STATUS.md`](history/RELEASE_SAFETY_STATUS.md) | The red/green witness record of the SeqCut/beta-boundary repair rounds (all green as of checkpoint `beta-boundary-20260905`) |
| [`history/STAGING_SOUNDNESS.md`](history/STAGING_SOUNDNESS.md) | A staging design study; the described `staging.ml/.mli` was never part of the shipped implementation |
