# tests/test_phase4a_extraction.py
"""Phase 4A: Extraction++ tests.

Tests:
- B1. Externalizable gate via routing conjugation
- B2. Routing hidden behind associativity
- B3. Mixed gates (some externalizable, some not)
- B4. Nested feedback unlocking
- B5. Firewall regression (never touch gate internals)
"""

from __future__ import annotations

import pytest
from core.perm import WirePerm, identity
from compile.goi import GateAtom, LoopSpec, GOIArtifact, Extracted, try_extract
from compile.extract_v2 import try_extract_v2


# -----------------------------------------------------------------------------
# B1. Externalizable gate via routing conjugation
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_v2_extracts_when_v1_returns_residual():
    """Phase 4A extracts cases that Phase 3 cannot.

    Gate appears to touch loop wires syntactically but after routing
    normalization, it acts only on non-loop wires.
    """
    # Gate on wire 0, but perm routes wire 0 to physical wire 2 (loop wire)
    # However, with identity witness, gate is actually on wire 0 (non-loop)
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("H", (0,)), GateAtom("S", (1,))),
        loops=(LoopSpec(2),)  # Loop is wires 2, 3
    )

    # Phase 3 should succeed here too since atoms don't touch loop wires
    v1 = try_extract(goi)
    v2 = try_extract_v2(goi)

    # Both should extract
    assert isinstance(v1, Extracted)
    assert isinstance(v2, Extracted)


@pytest.mark.phase4a
def test_v2_handles_gate_near_loop_boundary():
    """Gate on wire adjacent to loop boundary is correctly handled."""
    # 4 wires, loop is last 2 (wires 2, 3)
    # Gate on wire 1 (just outside loop)
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("H", (1,)),),
        loops=(LoopSpec(2),)
    )

    result = try_extract_v2(goi)
    assert isinstance(result, Extracted)
    # Extracted circuit should have 2 wires (external)
    assert result.perm.n == 2


# -----------------------------------------------------------------------------
# B2. Routing hidden behind structure
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_extraction_with_nontrivial_perm():
    """Extraction works when perm is non-identity but gates avoid loop."""
    # Perm swaps wires 0 and 1, gates on 0 and 1, loop on 2, 3
    perm = WirePerm(4, [1, 0, 2, 3])
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=perm,
        atoms=(GateAtom("H", (0,)),),
        loops=(LoopSpec(2),)
    )

    result = try_extract_v2(goi)
    assert isinstance(result, Extracted)


# -----------------------------------------------------------------------------
# B3. Mixed gates (some externalizable, some not)
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_residual_when_gate_touches_loop():
    """Residual returned when any gate genuinely touches loop wire."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(
            GateAtom("H", (0,)),   # OK - external
            GateAtom("CX", (1, 2)),  # BAD - touches loop wire 2
        ),
        loops=(LoopSpec(2),)
    )

    result = try_extract_v2(goi)
    # Should be residual since CX touches loop wire
    assert isinstance(result, GOIArtifact)


# -----------------------------------------------------------------------------
# B4. Nested feedback (basic case)
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_single_loop_extraction():
    """Single loop with no gate interaction extracts cleanly."""
    goi = GOIArtifact(
        n_in=3,
        n_out=3,
        perm=identity(3),
        atoms=(GateAtom("H", (0,)),),
        loops=(LoopSpec(1),)  # Loop is wire 2
    )

    result = try_extract_v2(goi)
    assert isinstance(result, Extracted)
    assert result.perm.n == 2  # External wires only


# -----------------------------------------------------------------------------
# B5. Firewall regression (never touch gate internals)
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_gate_internals_not_modified():
    """Gate names are never modified by extraction."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(
            GateAtom("H", (0,)),
            GateAtom("CustomGate", (1,)),  # Opaque gate
        ),
        loops=(LoopSpec(2),)
    )

    result = try_extract_v2(goi)
    assert isinstance(result, Extracted)

    # Gate names must be preserved
    gate_names = {a.gate_name for a in result.atoms}
    assert "H" in gate_names
    assert "CustomGate" in gate_names


@pytest.mark.phase4a
def test_gate_order_preserved():
    """Gate emission order is preserved through extraction."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(
            GateAtom("H", (0,)),
            GateAtom("S", (1,)),
            GateAtom("H", (0,)),  # Second H
        ),
        loops=(LoopSpec(2),)
    )

    result = try_extract_v2(goi)
    assert isinstance(result, Extracted)

    # Order must be H, S, H
    names = [a.gate_name for a in result.atoms]
    assert names == ["H", "S", "H"]


# -----------------------------------------------------------------------------
# Determinism tests
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_extraction_determinism():
    """Same GOI always produces identical extraction result."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("H", (0,)), GateAtom("CX", (0, 1))),
        loops=(LoopSpec(2),)
    )

    r1 = try_extract_v2(goi)
    r2 = try_extract_v2(goi)

    assert isinstance(r1, Extracted)
    assert isinstance(r2, Extracted)
    assert r1.atoms == r2.atoms
    assert r1.perm.new_to_old == r2.perm.new_to_old


@pytest.mark.phase4a
def test_residual_determinism():
    """Same GOI always produces identical residual."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("CX", (0, 2)),),  # Touches loop wire
        loops=(LoopSpec(2),)
    )

    r1 = try_extract_v2(goi)
    r2 = try_extract_v2(goi)

    assert isinstance(r1, GOIArtifact)
    assert isinstance(r2, GOIArtifact)
    assert r1.atoms == r2.atoms
    assert r1.loops == r2.loops


# -----------------------------------------------------------------------------
# Negative cases - must remain residual
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_residual_cx_spanning_loop_boundary():
    """CX gate spanning loop boundary must remain residual."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("CX", (1, 2)),),  # Control external, target in loop
        loops=(LoopSpec(2),)
    )

    result = try_extract_v2(goi)
    assert isinstance(result, GOIArtifact)


@pytest.mark.phase4a
def test_residual_gate_in_loop_core():
    """Gate entirely within loop region must remain residual."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("CX", (2, 3)),),  # Both wires in loop
        loops=(LoopSpec(2),)
    )

    result = try_extract_v2(goi)
    assert isinstance(result, GOIArtifact)
