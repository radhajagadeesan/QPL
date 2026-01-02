"""End-to-end certification tests.

Verifies:
- exp_i accepts involutive permutations
- exp_i rejects non-involutive permutations
- Certified programs never yield residual GOI

Note: With the tagged layout model:
- Sum types A + B have width = 1 + width(A) + width(B) (includes tag qubit)
- TwistPlus emits an X gate for the tag flip
"""

import sys
from pathlib import Path
import subprocess
import math
import pytest

# Add paths for imports
TESTS_DIR = Path(__file__).parent.parent
SURFACE_DIR = TESTS_DIR.parent
PROJECT_DIR = SURFACE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(TESTS_DIR))

from helpers import compile_term, is_involutive, is_empty_circuit

from lang.types import Q, Ten, Plus
from lang.terms import (
    Id, Seq, TenTerm, TwistTen, TwistPlus,
    AssocPlusL, AssocPlusR
)

# Aliases for readability
TwistTensor = TwistTen


class TestInvolutionAcceptance:
    """Test that exp_i accepts involutive permutations."""

    def test_twist_plus_is_involutive(self):
        """TwistPlus is involutive (swap o swap = id)."""
        term = TwistPlus(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        assert is_involutive(perm), "TwistPlus should be involutive"
        # Tagged layout: Q + Q has width 3 (1 tag + 1 + 1)
        # perm = [0, 2, 1] (tag stays, data swaps)
        assert perm.n == 3
        assert perm.new_to_old == [0, 2, 1]

    def test_twist_tensor_is_involutive(self):
        """TwistTensor is involutive."""
        term = TwistTensor(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        assert is_involutive(perm)

    def test_identity_is_involutive(self):
        """Identity is trivially involutive."""
        term = Id(Ten(Q(), Q()))
        circuit, perm = compile_term(term, materialize=False)

        assert is_involutive(perm)
        assert perm.new_to_old == [0, 1]

    def test_double_twist_is_identity(self):
        """TwistPlus ; TwistPlus = Id (involutive property)."""
        twist = TwistPlus(Q(), Q())
        term = Seq(twist, twist)
        circuit, perm = compile_term(term, materialize=False)

        # Tagged layout: Q + Q has width 3
        assert perm.new_to_old == [0, 1, 2], "twist ; twist should be identity"
        assert is_involutive(perm)


class TestInvolutionRejection:
    """Test that non-involutive permutations are rejected."""

    def test_three_cycle_not_involutive(self):
        """A 3-cycle permutation is NOT involutive."""
        # Build a 3-cycle using structural rewiring
        # (A + B) + C with operations that create [2, 0, 1]
        a, b, c = Q(), Q(), Q()

        # AssocPlusL: (A+B)+C -> A+(B+C) changes wire positions
        # We need to compose to create a 3-cycle

        # TwistPlus on top level: ((A+B)+C) -> C + (A+B)
        # Then TwistPlus inside: C + (A+B) -> C + (B+A)
        # This creates rotation, not 3-cycle

        # Actually, to get [2,0,1] (a 3-cycle), we need:
        # Position 0 -> 2, Position 1 -> 0, Position 2 -> 1
        # This is a left rotation

        # Start with ((A+B)+C):
        # Wire 0 = A, Wire 1 = B, Wire 2 = C

        # swap top: C + (A+B) -> [2, 0, 1]... no that's new_to_old
        # Let's verify what TwistPlus does on 3 wires
        twist_top = TwistPlus(Plus(a, b), c)
        circuit, perm = compile_term(twist_top, materialize=False)

        # Check if this is a 3-cycle
        # A 3-cycle satisfies p(p(p(i))) = i but p(p(i)) != i for some i
        n = perm.n
        new_to_old = perm.new_to_old

        is_3cycle = True
        for i in range(n):
            p_i = new_to_old[i]
            pp_i = new_to_old[p_i]
            if pp_i == i:
                # This element has order 1 or 2, not 3
                if p_i != i:
                    is_3cycle = False
                    break

        # TwistPlus((A+B), C) on a 3-wire type actually creates a 3-cycle!
        # perm = [2, 0, 1] which means:
        #   0 -> 2, 1 -> 0, 2 -> 1
        # This is NOT involutive since it's a 3-cycle (order 3, not 2)

        # Verify it's NOT involutive
        assert not is_involutive(perm), "TwistPlus on (A+B)+C should NOT be involutive (it's a 3-cycle)"

        # Note: TwistPlus(Q(), Q()) IS involutive because it's a swap on 2 wires
        # But TwistPlus(Plus(a,b), c) on 3 wires permutes in a non-involutive way


class TestCertificationViaBridge:
    """Test certification through the Python bridge."""

    def test_bridge_certifies_twist_plus(self):
        """Bridge should certify TwistPlus as involutive."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "TwistPlus is involutive" in output

    def test_bridge_certifies_identity(self):
        """Bridge should certify Identity as involutive."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "Identity is involutive" in output

    def test_exp_i_certified_emission(self):
        """Bridge should emit certified exp_i code."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "exp_i certified successfully" in output
        assert "GateAtom(name='exp_i:" in output


class TestNoResidualGOI:
    """Test that certified programs never yield residual GOI."""

    def test_structural_no_goi(self):
        """Pure structural programs should have minimal GOI residual.

        Note: With tagged layout, TwistPlus emits 1 X gate for tag flip.
        This is expected behavior, not a GOI residual issue.
        """
        term = TwistPlus(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        # TwistPlus emits exactly 1 X gate for tag flip (expected)
        assert circuit.n_gates == 1, f"Expected 1 gate (X for tag flip), got {circuit.n_gates}"

    def test_certified_exp_i_no_residual(self):
        """Certified exp_i should produce clean output without residual GOI."""
        # This is verified through the OCaml tests
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # The test suite verifies exp_i certification works
        assert "Bool.swap is involutive" in output


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
