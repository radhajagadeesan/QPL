# tests/test_23_structure_no_swaps_regression.py
"""Structure must not emit SWAPs by default.

Invariant: structure = wiring metadata (WirePerm), computation = gates.
Therefore compile(..., materialize=False) should never contain SWAP operations.
"""

import pytest
from tests.helpers import get_compile_to_pytket, has_swap

# Project imports (expected from Phase 1 summary)
from lang.types import Q, Ten, Plus
from lang.terms import Seq, TensorAssocL, TensorTwist, SumAssocL, SumTwist


@pytest.mark.phase1
def test_tensor_structure_emits_no_swaps():
    compile_to_pytket = get_compile_to_pytket()

    term = Seq(
        TensorAssocL(Q(), Q(), Q()),
        TensorTwist(Q(), Ten(Q(), Q())),
        TensorAssocL(Q(), Q(), Q()),
    )
    circ = compile_to_pytket(term, materialize=False)
    assert not has_swap(circ)


@pytest.mark.phase1
def test_sum_structure_emits_no_swaps():
    compile_to_pytket = get_compile_to_pytket()

    term = Seq(
        SumAssocL(Q(), Q(), Q()),
        SumTwist(Q(), Plus(Q(), Q())),
    )
    circ = compile_to_pytket(term, materialize=False)
    assert not has_swap(circ)
