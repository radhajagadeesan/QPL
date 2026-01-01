#!/usr/bin/env python3
"""Bridge script for OCaml surface language integration.

This script provides a JSON-based interface for the OCaml surface compiler
to call the Phase 0-4C Python compiler.

Usage:
    echo '{"type": "compile", "term": {...}}' | python bridge.py
    echo '{"type": "check_involution", "term": {...}}' | python bridge.py

Input JSON format for terms:
    {"node": "TwistPlus", "a": {"node": "Q"}, "b": {"node": "Q"}}
    {"node": "Id", "ty": {"node": "Plus", "left": {"node": "Q"}, "right": {"node": "Q"}}}
"""

import json
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from lang.types import Q, Ten, Plus, Ty
from lang.terms import (
    Term, Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
)
from core.perm import WirePerm, identity, compose
from compile.to_pytket import compile


def parse_type(j: dict) -> Ty:
    """Parse a JSON type representation into a Ty."""
    node = j["node"]
    if node == "Q":
        return Q()
    elif node == "Ten":
        return Ten(parse_type(j["left"]), parse_type(j["right"]))
    elif node == "Plus":
        return Plus(parse_type(j["left"]), parse_type(j["right"]))
    else:
        raise ValueError(f"Unknown type node: {node}")


def parse_term(j: dict) -> Term:
    """Parse a JSON term representation into a Term."""
    node = j["node"]

    if node == "Id":
        return Id(parse_type(j["ty"]))

    elif node == "Seq":
        return Seq(parse_term(j["f"]), parse_term(j["g"]))

    elif node == "TenTerm":
        return TenTerm(parse_term(j["f"]), parse_term(j["g"]))

    elif node == "TwistTen":
        return TwistTen(parse_type(j["a"]), parse_type(j["b"]))

    elif node == "AssocTenL":
        return AssocTenL(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    elif node == "AssocTenR":
        return AssocTenR(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    elif node == "TwistPlus":
        return TwistPlus(parse_type(j["a"]), parse_type(j["b"]))

    elif node == "AssocPlusL":
        return AssocPlusL(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    elif node == "AssocPlusR":
        return AssocPlusR(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    else:
        raise ValueError(f"Unknown term node: {node}")


def perm_to_json(p: WirePerm) -> dict:
    """Convert a WirePerm to JSON."""
    return {
        "n": p.n,
        "new_to_old": p.new_to_old
    }


def is_involution(p: WirePerm) -> bool:
    """Check if p ∘ p = identity."""
    p_squared = compose(p, p)
    id_perm = identity(p.n)
    return p_squared == id_perm


def handle_compile(request: dict) -> dict:
    """Handle a compile request."""
    try:
        term = parse_term(request["term"])
        result = compile(term, materialize=False)

        return {
            "success": True,
            "perm": perm_to_json(result.perm),
            "circuit_size": result.circuit.n_gates
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def handle_check_involution(request: dict) -> dict:
    """Handle an involution check request."""
    try:
        term = parse_term(request["term"])
        result = compile(term, materialize=False)

        # Check if circuit is empty (structural term)
        if result.circuit.n_gates > 0:
            return {
                "success": False,
                "error": "Term is not structural (contains gates)"
            }

        # Check involution
        is_invol = is_involution(result.perm)

        return {
            "success": True,
            "is_involution": is_invol,
            "perm": perm_to_json(result.perm)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def main():
    """Main entry point."""
    # Read JSON from stdin
    input_data = sys.stdin.read()

    try:
        request = json.loads(input_data)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    req_type = request.get("type", "compile")

    if req_type == "compile":
        response = handle_compile(request)
    elif req_type == "check_involution":
        response = handle_check_involution(request)
    else:
        response = {"success": False, "error": f"Unknown request type: {req_type}"}

    print(json.dumps(response))


if __name__ == "__main__":
    main()
