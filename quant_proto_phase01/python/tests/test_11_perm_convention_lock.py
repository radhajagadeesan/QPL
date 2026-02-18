# tests/test_11_perm_convention_lock.py
"""Locks the WirePerm mapping convention.

This is the single most important regression test for wiring correctness.
If this fails, gates may land on the wrong wires under structure.

Edit EXPECTED values below *once* to match your current convention, then treat
this as non-negotiable going forward.
"""

import pytest
from tests.helpers import get_wireperm_cls, perm_apply, perm_to_list


@pytest.mark.phase1
def test_wireperm_swap_01_convention():
    WirePerm = get_wireperm_cls()

    # Convention lock example for n=4.
    # A common representation is WirePerm([1,0,2,3]) meaning swap 0<->1.
    p = WirePerm([1, 0, 2, 3])

    # If your convention differs, update these expectations.
    # We *intentionally* make this explicit and small.
    assert perm_apply(p, 0) == 1, f"perm={perm_to_list(p)}"
    assert perm_apply(p, 1) == 0, f"perm={perm_to_list(p)}"
    assert perm_apply(p, 2) == 2, f"perm={perm_to_list(p)}"
    assert perm_apply(p, 3) == 3, f"perm={perm_to_list(p)}"
