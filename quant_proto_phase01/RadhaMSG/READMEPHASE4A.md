# Phase 4A: Extraction++ Implementation

## Overview

Phase 4A adds enhanced extraction capabilities to the GOI (Geometry-of-Interaction) compiler. It is **strictly additive** over Phase 3 - all Phase 0-3 behavior remains unchanged.

## Architecture

### New Modules

- `src/compile/loop_analysis.py` - Loop interaction analysis and ExternalizeWitness
- `src/compile/routing_nf2.py` - Outer-only routing normalization
- `src/compile/extract_v2.py` - Enhanced extraction entry point

### Key Data Structures

```python
@dataclass(frozen=True)
class ExternalizeWitness:
    """Witness that feedback body can be restructured to be loop-free."""
    p_in: WirePerm
    p_out: WirePerm
    externalized_support: Set[int]
    loop_wire_set: Set[int]
```

## API

### Entry Point

```python
from compile.extract_v2 import try_extract_v2

result = try_extract_v2(goi)
# Returns: Extracted(atoms, perm) | GOIArtifact (residual)
```

The `compile_goi()` function now uses `try_extract_v2()` internally.

### Pipeline

1. **Phase 3 delegation**: Calls `try_extract()` (v1) first
2. **Routing normalization**: Applies `normalize_routing_v2()` to residuals
3. **Feedback analysis**: Analyzes each loop for eliminability
4. **Global extraction**: Flattens if all loops eliminated

## Invariants

All Phase 0-3 invariants are preserved:

1. **No SWAPs by default**: `compile_goi(..., materialize=False)` emits zero SWAPs
2. **Determinism**: Same AST produces identical results
3. **Firewall**: Gate atoms are never inspected or modified
4. **Soundness**: Extraction only succeeds when provably correct
5. **Residual preservation**: Failed extraction returns valid GOIArtifact

## Limitations

In the current architecture, gate atoms have physical wire indices baked in during compilation. This limits Phase 4A's ability to "move" gates via permutation. The implementation correctly handles this by only returning witnesses when gates are already disjoint from loop wires.

Future enhancements may store logical indices in atoms to enable more powerful extraction strategies.

## Testing

Run Phase 4A tests:
```bash
PYTHONPATH=src pytest -v -m phase4a
```

Run all tests:
```bash
PYTHONPATH=src pytest -v --ignore=tests/Phase3Goldens
```

## Files

```
src/compile/
├── extract_v2.py       # try_extract_v2()
├── loop_analysis.py    # ExternalizeWitness, analyze_feedback_eliminable()
├── routing_nf2.py      # normalize_routing_v2()
└── to_pytket.py        # Updated to use try_extract_v2

tests/
├── test_phase4a_extraction.py      # B1-B5 tests
├── test_phase4a_integration.py     # End-to-end tests
└── test_phase4a_loop_analysis.py   # A1-A3 unit tests
```
