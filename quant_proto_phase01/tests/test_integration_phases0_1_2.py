from __future__ import annotations

import pytest
from ._phase2_helpers import (
    Q, Ten, width, qpow,
    Id, Seq, TenTerm, H, S, CX, TwistTen,
    compile_term, assert_no_swaps, non_swap_signature, materialize_manual, op_name, qubit_idxs
)

@pytest.mark.integration
def test_integration_phases0_1_2_executable_doc():
    """
    Top-level narrative test: Phases 0–2 end-to-end.

    Depicts:
      - Structure is metadata (TwistTen updates perm; no SWAPs emitted by default).
      - Gates are reindexed through perm.
      - TenTerm provides parallel composition with offsets.
      - Output is a flat first-order circuit.
      - Materialization can insert SWAPs but preserves non-SWAP gate order.
    """
    A = qpow(2)          # left block
    B = qpow(2)          # right block

    # Phase 1-style structural wiring + computation on left block:
    # TwistTen swaps the two wires of A (structure only), then H on local wire 0 of A.
    left = Seq(TwistTen(Q(), Q()), H(0, A))

    # Right block computation: CX on its local wires.
    right = CX(0, 1, B)

    prog = TenTerm(left, right)

    res = compile_term(prog, materialize=False)
    assert_no_swaps(res.circuit)

    # Must contain H and CX.
    names = [op_name(c).upper() for c in res.circuit.get_commands()]
    assert "H" in names
    assert "CX" in names

    # Flat: it's just a command list.
    assert len(res.circuit.get_commands()) >= 2

    # Materialization preserves non-SWAP order.
    sig_before = non_swap_signature(res.circuit)
    circ2 = materialize_manual(res)
    sig_after = non_swap_signature(circ2)
    assert sig_before == sig_after
