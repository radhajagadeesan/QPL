# tests/integration/test_e2e_dist_compile_failures.py
"""Integration Suite 6: DistL/DistR Compilation (Now Supported).

Purpose: Verify distributivity compiles correctly with tagged layout model.

Key invariants (updated):
- DistL/DistR terms typecheck and compile
- DistL is identity on wires under sharing model
- DistR moves tag to the front
- Compilation is deterministic
"""
from __future__ import annotations

import pytest

from lang.types import Q, Ten
from lang.terms import Id, Seq, DistL, DistR
from compile.to_pytket import compile, compile_goi, CompiledGOI
from typing_.check import assert_well_typed
from core.perm import identity

from .helpers import mk_dist_failure_corpus


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------

@pytest.fixture(scope="module")
def dist_terms():
    return mk_dist_failure_corpus()


# -----------------------------------------------------------------
# Distributivity now compiles successfully
# -----------------------------------------------------------------

DIST_NAMES = [
    "dist_distl",
    "dist_distr",
    "dist_seq_distl",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", DIST_NAMES)
def test_dist_typechecks(dist_terms, name):
    """Distributivity terms typecheck."""
    term = dist_terms[name]
    # This should not raise
    assert_well_typed(term)


@pytest.mark.integration
@pytest.mark.parametrize("name", DIST_NAMES)
def test_dist_compiles(dist_terms, name):
    """compile() now succeeds for distributivity with tagged layout model."""
    term = dist_terms[name]

    # Should compile without error
    result = compile(term, materialize=False)
    assert result.circuit is not None
    # Distributivity terms don't emit gates (pure permutation/identity)
    assert len(result.circuit.get_commands()) == 0


@pytest.mark.integration
@pytest.mark.parametrize("name", DIST_NAMES)
def test_dist_compile_goi_succeeds(dist_terms, name):
    """compile_goi() now succeeds for distributivity."""
    term = dist_terms[name]

    # Should compile without error
    result = compile_goi(term, materialize=False)
    # Should return CompiledGOI since it extracts successfully
    assert isinstance(result, CompiledGOI)


@pytest.mark.integration
@pytest.mark.parametrize("name", DIST_NAMES)
def test_dist_compilation_deterministic(dist_terms, name):
    """Distributivity compilation is deterministic."""
    term = dist_terms[name]

    results = []
    for _ in range(3):
        result = compile(term, materialize=False)
        results.append((
            result.circuit.n_qubits,
            len(result.circuit.get_commands()),
            result.perm.new_to_old
        ))

    # All should be identical
    assert all(r == results[0] for r in results), "Compilation not deterministic"


@pytest.mark.integration
def test_distl_is_identity():
    """DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C) is identity on wires."""
    term = DistL(Q(), Q(), Q())

    result = compile(term, materialize=False)
    # Width: (1 + 1 + 1) + 1 = 4 for (Q ⊕ Q) ⊗ Q
    assert result.circuit.n_qubits == 4
    assert result.perm.new_to_old == identity(4).new_to_old


@pytest.mark.integration
def test_distr_moves_tag():
    """DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C) moves tag to front."""
    term = DistR(Q(), Q(), Q())

    result = compile(term, materialize=False)
    # Width: 1 + (1 + 1 + 1) = 4 for Q ⊗ (Q ⊕ Q)
    assert result.circuit.n_qubits == 4
    # Tag moves from position 1 to position 0
    # [A=0, tag=1, B=2, C=3] -> [tag=0, A=1, B=2, C=3]
    expected_perm = [1, 0, 2, 3]
    assert result.perm.new_to_old == expected_perm


# -----------------------------------------------------------------
# Negative controls: Similar terms without Dist compile fine
# -----------------------------------------------------------------

@pytest.mark.integration
def test_non_dist_compiles_fine():
    """Terms without distributivity compile normally."""
    from lang.terms import TwistTen, H

    # Similar structure but no DistL/DistR
    term = Seq(
        TwistTen(Q(), Q()),
        H(0, Ten(Q(), Q()))
    )

    # Should not raise
    result = compile(term, materialize=False)
    assert result.circuit is not None


@pytest.mark.integration
def test_non_dist_in_feedback_compiles():
    """Feedback without distributivity compiles/extracts normally."""
    from lang.terms import Feedback, H

    q3 = Ten(Q(), Ten(Q(), Q()))

    # Feedback without distributivity
    term = Feedback(k=1, body=H(0, q3))

    # Should not raise
    result = compile_goi(term, materialize=False)
    # May extract or return residual - both are valid
    assert result is not None
