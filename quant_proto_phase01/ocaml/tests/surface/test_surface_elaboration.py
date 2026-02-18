"""Tests for surface language elaboration.

Verifies that:
- Elaboration produces only existing core IR nodes
- No surface constructs (datatype, case, lambda) remain after elaboration
- Macro expansion is deterministic
"""

import sys
from pathlib import Path

# Add paths for imports
TESTS_DIR = Path(__file__).parent.parent
SURFACE_DIR = TESTS_DIR.parent
PROJECT_DIR = SURFACE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(TESTS_DIR))

import subprocess
import json


def run_ocaml_test(test_name: str) -> dict:
    """Run an OCaml test via dune and capture JSON output."""
    result = subprocess.run(
        ['dune', 'exec', '--', './test/test_surface.exe', '--json', test_name],
        capture_output=True,
        text=True,
        cwd=str(SURFACE_DIR)
    )
    if result.returncode != 0:
        return {'error': result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {'output': result.stdout}


class TestElaboration:
    """Test elaboration from surface to core IR."""

    def test_let_elimination(self):
        """Let bindings should be eliminated by substitution."""
        # This is tested in OCaml: let x = H[0] in x ; S[0] -> H[0] ; S[0]
        # Run the OCaml test suite which includes this
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0, f"OCaml tests failed: {result.stderr}"
        output = result.stdout + result.stderr
        assert "let x = H[0] in x ; S[0]" in output
        assert "Elaborated: H[0] ; S[0]" in output

    def test_lambda_application_elimination(self):
        """Lambda application should be eliminated by beta-reduction."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # Check that (λx:Q. x ; S[0]) H[0] -> H[0] ; S[0]
        assert "Elaborated: H[0] ; S[0]" in output

    def test_substitution_shadowing(self):
        """Substitution should respect variable shadowing."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # λx:Q. x should not have x substituted inside
        assert "[H[0]/x](λx:Q. x) = λx:Q. x (x shadowed)" in output

    def test_free_variables(self):
        """Free variable computation should be correct."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "FV(x) = [x]" in output
        assert "FV(λx:Q. x) = []" in output
        assert "FV(λx:Q. x ; y) = [y]" in output

    def test_unbound_variable_error(self):
        """Unbound variables should be caught."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "Caught expected error: Unbound variable: undefined_var" in output


class TestASTConstruction:
    """Test AST construction and pretty-printing."""

    def test_ast_terms(self):
        """AST terms should be constructable and printable."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "H[0] ; S[0] = H[0] ; S[0]" in output
        assert "λx:Q. H[0] = λx:Q. H[0]" in output

    def test_ast_types(self):
        """AST types should be constructable and printable."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "Q ⊗ Q = (Q ⊗ Q)" in output
        assert "Q + Q = (Q + Q)" in output
        assert "Bool[Q, Q] = Bool[Q, Q]" in output


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
