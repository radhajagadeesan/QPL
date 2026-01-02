# Phase 3 Implementation: Explicit GOI Feedback

Phase 3 adds explicit Geometry-of-Interaction (GOI) feedback semantics to the compiler.

## Overview

Phase 3 introduces:
- **Feedback term**: `Feedback(k, body)` - explicit, fenced feedback operator
- **GOI IR**: `GOIArtifact` with atoms, loops, and routing permutation
- **Extraction**: Sound (but incomplete) mechanism to collapse loops to boundary permutations

## Key Invariants (preserved from Phases 0-2)

1. **Structure vs Computation**: Structural terms compile only to `WirePerm` metadata
2. **No SWAPs by Default**: Compilation emits no SWAPs unless `materialize=True`
3. **Flat Execution Artifact**: Successful extraction yields flat circuit + boundary perm
4. **GOI Checkpoint**: When extraction succeeds, GOI routing collapses to boundary permutation

## New API

### compile_goi(term, materialize=False) -> CompiledGOI | GOIArtifact

Phase 3 compiler entry point. Returns:
- `CompiledGOI(circuit, perm)` if extraction succeeds
- `GOIArtifact` (residual) if extraction fails

### Feedback(k, body)

New term constructor for explicit feedback.

```python
from lang.terms import Feedback

# Body: 3 wires, loop last 1 wire
# External: 2 wires
body = Seq(H(0, qpow(3)), S(1, qpow(3)))
term = Feedback(k=1, body=body)

result = compile_goi(term)
```

## Data Structures

### GateAtom
```python
@dataclass(frozen=True)
class GateAtom:
    gate_name: str
    wires: Tuple[int, ...]  # physical wire indices
```

### LoopSpec
```python
@dataclass(frozen=True)
class LoopSpec:
    k: int  # number of loop wires (last k outputs → last k inputs)
```

### GOIArtifact
```python
@dataclass(frozen=True)
class GOIArtifact:
    n_in: int
    n_out: int
    perm: WirePerm
    atoms: Tuple[GateAtom, ...]
    loops: Tuple[LoopSpec, ...]
```

## GOI Functions

### normalize_goi(goi) -> GOIArtifact
Push all structural effects (permutation) into gate atom wire indices.
After normalization, `perm` is identity.

### is_yankable(goi) -> bool
Check if all loops are eliminable. A loop is yankable iff no gate atom
touches any loop wire after normalization.

### collapse_feedback(goi) -> WirePerm
Compute the induced boundary permutation when feedback is yankable.
Loop wires are existentially eliminated.

### try_extract(goi) -> Extracted | GOIArtifact
Attempt extraction. Returns `Extracted(atoms, perm)` if yankable,
otherwise returns the original GOIArtifact as residual.

## Yankability Criterion

A feedback loop is eliminable iff:
> No gate atom touches any loop wire after normalization.

Formally: For every `GateAtom g`, `support(g) ∩ L = ∅` where L is the set of loop wire indices.

## Example Usage

```python
from lang.types import Q, Ten
from lang.terms import Feedback, Seq, H, S
from compile.to_pytket import compile_goi

def qpow(n):
    """Build Q^n type."""
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty

# Yankable case: gates on wires 0,1 only, loop on wire 2
ty = qpow(3)
body = Seq(H(0, ty), S(1, ty))
term = Feedback(k=1, body=body)

result = compile_goi(term)
# Returns CompiledGOI with 2-wire circuit (wire 2 eliminated)

# Non-yankable case: gate touches loop wire
body2 = H(2, ty)  # touches loop wire
term2 = Feedback(k=1, body=body2)

result2 = compile_goi(term2)
# Returns GOIArtifact (residual)
```

## Test Coverage

Phase 3 tests are organized per the test plans:

- `test_phase3_local_invariants.py` - Feedback fencing, no implicit GOI
- `test_phase3_normalization_firewall.py` - Firewall rule (atoms opaque)
- `test_phase3_feedback_elimination.py` - Yankability and collapse
- `test_phase3_residual_preservation.py` - Residual preservation
- `test_phase3_integration.py` - End-to-end integration with Phases 0-2

## Files Modified/Added

### Modified
- `src/lang/terms.py` - Added `Feedback` term
- `src/typing_/check.py` - Added type checking for `Feedback`
- `src/compile/to_pytket.py` - Added `compile_goi` entry point
- `src/core/perm.py` - Added `restrict` method to `WirePerm`
- `tests/conftest.py` - Added `phase3` marker

### Added
- `src/compile/goi.py` - GOI data structures and functions
- `tests/_phase3_helpers.py` - Test helpers
- `tests/test_phase3_*.py` - Test files (4 total)

## Design Notes

1. **Failure is not an error**: `try_extract` returns residual GOI on failure
2. **Sound but incomplete**: Extraction is conservative; false negatives acceptable
3. **Firewall rule**: Normalization never rewrites inside gate atoms
4. **Additive design**: Phase 3 code does not modify Phases 0-2 behavior
