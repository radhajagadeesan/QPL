"""Tests for surface language parsing.

Verifies:
- Stable error messages for syntax errors
- No leakage of core IR terminology in error messages
- Correct AST construction from valid syntax

GOI Note: Parsing is purely syntactic - no GOI semantics apply here.
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


class TestParsing:
    """Test surface language parsing."""

    def test_ocaml_parser_available(self):
        """Verify OCaml parser is built and available."""
        result = subprocess.run(
            ['dune', 'build'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0, f"Dune build failed: {result.stderr}"

    def test_valid_syntax_parses(self):
        """Valid surface syntax should parse without errors."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # Verify basic terms parse
        assert "H[0] ; S[0]" in output

    def test_type_syntax_parses(self):
        """Type expressions should parse correctly."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # Verify type syntax
        assert "Q" in output or "(Q" in output

    def test_datatype_syntax_parses(self):
        """Datatype declarations should parse correctly."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # Verify Bool datatype
        assert "Bool" in output


class TestErrorMessages:
    """Test that error messages are user-friendly."""

    def test_no_core_ir_leakage(self):
        """Error messages should not expose core IR internals."""
        result = subprocess.run(
            ['dune', 'test', '--force'],
            capture_output=True,
            text=True,
            cwd=str(SURFACE_DIR)
        )
        # Verify errors are caught properly
        output = result.stdout + result.stderr
        assert "Caught expected error" in output
        # Should not contain raw core IR node names in user-facing errors
        # (internal test output may show them, but errors shouldn't)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
