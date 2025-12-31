# tests/test_32_compile_determinism.py
"""Compilation determinism.

Same AST must compile to the same operation list every time. This prevents
accidental nondeterminism from dict/set iteration or refactors.
"""

import pytest
from tests.helpers import get_compile_to_pytket, circuit_fingerprint

from lang.types import Q, Ten
from lang.terms import Seq, TensorTwist, H, CX


@pytest.mark.phase1
def test_compile_is_deterministic():
    compile_to_pytket = get_compile_to_pytket()

    # Minimal program using both structure and gates.
    term = Seq(
        TensorTwist(Q(), Q()),
        CX(),
        H(),
    )

    c1 = compile_to_pytket(term, materialize=False)
    c2 = compile_to_pytket(term, materialize=False)
    assert circuit_fingerprint(c1) == circuit_fingerprint(c2)
