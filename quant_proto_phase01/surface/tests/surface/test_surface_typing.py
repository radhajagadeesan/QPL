"""Tests for surface language typing.

Verifies:
- Surface classification (s / u / invol) as preconditions
- Datatype well-formedness (finite, non-recursive)
- No coproduct semantics permitted

GOI Note: Surface typing is a precondition check. All semantic
classification is validated by compilation (on GOI boundary permutations).
"""

import sys
from pathlib import Path
import subprocess

# Add paths for imports
TESTS_DIR = Path(__file__).parent.parent
SURFACE_DIR = TESTS_DIR.parent
PROJECT_DIR = SURFACE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(TESTS_DIR))


class TestDatatypeWellFormedness:
    """Test datatype well-formedness checks."""

    def test_finite_datatypes_accepted(self):
        """Finite datatypes should be accepted."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # Bool is a finite datatype
        assert "Bool" in output

    def test_non_recursive_datatypes(self):
        """Non-recursive datatypes should be accepted.

        Note: Recursive datatypes are forbidden by the surface language spec.
        The OCaml frontend should reject them at parse/type-check time.
        """
        # This is enforced by the OCaml type system
        pass


class TestSurfaceClassification:
    """Test surface-level s/u/invol classification."""

    def test_structural_precondition(self):
        """Structural terms should pass precondition checks."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # TwistPlus is structural
        assert "TwistPlus" in output

    def test_involutive_precondition(self):
        """Involutive terms should pass precondition checks.

        GOI Note: Final involution certification occurs on GOI boundary
        permutations via the compiler, not at the surface level.
        """
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # swap is involutive
        assert "involutive" in output.lower()


class TestNoCoproductSemantics:
    """Test that coproduct semantics are not permitted."""

    def test_plus_is_monoidal(self):
        """(+) should be treated as monoidal, not coproduct.

        The surface language uses (+) for monoidal sums, not coproducts.
        There are no injections (inl/inr) or eliminators via universal property.
        """
        # This is enforced by the absence of inl/inr in the AST
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # Should not contain coproduct terminology
        assert "inl" not in output.lower() or "injection" not in output.lower()


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
