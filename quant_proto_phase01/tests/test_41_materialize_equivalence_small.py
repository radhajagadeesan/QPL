# tests/test_41_materialize_equivalence_small.py
"""Materialization equivalence (small sanity).

Materialization may introduce SWAPs, but should not reorder or alter the
non-SWAP gates emitted by the compiler.
"""

import pytest
from tests.helpers import get_compile_to_pytket, non_swap_fingerprint

from lang.types import Q
from lang.terms import Seq, TensorTwist, CX, H


@pytest.mark.phase1
def test_materialize_only_adds_swaps():
    compile_to_pytket = get_compile_to_pytket()

    term = Seq(
        TensorTwist(Q(), Q()),
        CX(),
        H(),
    )

    c_meta = compile_to_pytket(term, materialize=False)
    c_mat  = compile_to_pytket(term, materialize=True)

    assert non_swap_fingerprint(c_meta) == non_swap_fingerprint(c_mat)
