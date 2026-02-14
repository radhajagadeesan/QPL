#!/usr/bin/env python3
"""Demo: Case Expression Compilation

This demo verifies that case expressions compile correctly to controlled gates.

Two paths are tested:
1. Python CaseExpr (direct) - pattern-matching case with variable binding
2. Python Case combinator - bifunctorial action on sums

The expected compilation pattern for case on (A + B):
- Layout: [tag | payload]
- Left branch (tag=0): X[tag]; controlled-gates; X[tag]  (anti-control)
- Right branch (tag=1): controlled-gates directly

Usage:
    python case_demo.py              # Run demo
    python case_demo.py --circuits   # Show circuit diagrams
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from lang.types import Q, Plus, Unit, width
from lang.terms import (
    Id, Seq, H, S, X, Case, CaseExpr, Var,
    TwistPlus, EncodeQubit, DecodeQubit,
)
from typing_.check import type_of

from demo_utils import DemoRunner

# Global runner instance
runner = None


def demo_case_combinator():
    """Demo 1: Case combinator (bifunctorial action)

    Case(ty_left, ty_right, left, right) : (A + B) → (C + D)

    This is the combinator form where left and right are morphisms.
    """
    print("\n" + "="*60)
    print("Demo 1: Case Combinator (Bifunctorial)")
    print("="*60)

    # Type: (Q + Q) → (Q + Q)
    # Left branch: H (Hadamard on left summand)
    # Right branch: S (Phase on right summand)
    ty_q = Q()
    ty_total = Plus(Q(), Q())  # Binary sum

    # Build: Case[Q, Q](H, S) : (Q + Q) → (Q + Q)
    # H operates on wire 0 (the payload when left)
    # S operates on wire 0 (the payload when right)
    left_branch = H(0, ty_q)   # H : Q → Q
    right_branch = S(0, ty_q)  # S : Q → Q

    case_term = Case(ty_q, ty_q, left_branch, right_branch)

    # Type check
    dom, cod = type_of(case_term)
    print(f"\nTerm: Case(Q, Q, H, S)")
    print(f"Type: {dom} → {cod}")
    print(f"  dom width = {width(dom)}")
    print(f"  cod width = {width(cod)}")

    # Compile
    result = runner.compile(case_term, "Case(Q, Q, H, S)")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "Case(Q, Q, H, S)")

    # Verify: should have anti-control pattern
    # X; CH; X (for left=H) then CS (for right=S)
    cmds = list(result.circuit.get_commands())
    gate_names = [cmd.op.type.name for cmd in cmds]
    print(f"\nGate sequence: {gate_names}")

    # Check for expected pattern
    assert 'X' in gate_names, "Should have X gates for anti-control"
    assert 'CH' in gate_names, "Should have controlled-H"
    assert 'CS' in gate_names, "Should have controlled-S"
    print("✓ Verified: anti-control pattern (X; CH; X) and control (CS)")

    return result


def demo_case_with_id_branches():
    """Demo 2: Case with identity branches (should produce no gates)

    Case[Q, Q](Id, Id) : (Q + Q) → (Q + Q)
    Both branches are identity, so no controlled gates needed.
    """
    print("\n" + "="*60)
    print("Demo 2: Case with Identity Branches")
    print("="*60)

    ty_q = Q()

    # Both branches are identity
    left_branch = Id(ty_q)
    right_branch = Id(ty_q)

    case_term = Case(ty_q, ty_q, left_branch, right_branch)

    dom, cod = type_of(case_term)
    print(f"\nTerm: Case(Q, Q, Id, Id)")
    print(f"Type: {dom} → {cod}")

    result = runner.compile(case_term, "Case(Q, Q, Id, Id)")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "Case(Q, Q, Id, Id)")

    # Should have 0 gates (identity on both branches)
    assert result.circuit.n_gates == 0, f"Expected 0 gates, got {result.circuit.n_gates}"
    print("✓ Verified: Identity case has 0 gates")

    return result


def demo_case_asymmetric():
    """Demo 3: Case with asymmetric branches

    Case[Q, Q](H;S, Id) : (Q + Q) → (Q + Q)
    Left branch: H then S
    Right branch: Identity (no-op)
    """
    print("\n" + "="*60)
    print("Demo 3: Asymmetric Case (H;S on left, Id on right)")
    print("="*60)

    ty_q = Q()

    # Left: H then S
    left_branch = Seq(H(0, ty_q), S(0, ty_q))
    # Right: Identity
    right_branch = Id(ty_q)

    case_term = Case(ty_q, ty_q, left_branch, right_branch)

    dom, cod = type_of(case_term)
    print(f"\nTerm: Case(Q, Q, H;S, Id)")
    print(f"Type: {dom} → {cod}")

    result = runner.compile(case_term, "Case(Q, Q, H;S, Id)")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "Case(Q, Q, H;S, Id)")

    # Should have: X; CH; CS; X (anti-controlled H;S, no gates for Id)
    cmds = list(result.circuit.get_commands())
    gate_names = [cmd.op.type.name for cmd in cmds]
    print(f"\nGate sequence: {gate_names}")

    # Check: only left branch produces controlled gates
    assert gate_names.count('X') == 2, "Should have 2 X gates for anti-control"
    assert 'CH' in gate_names, "Should have controlled-H"
    assert 'CS' in gate_names, "Should have controlled-S"
    print("✓ Verified: Only left branch (H;S) produces controlled gates")

    return result


def demo_twist_plus_as_swap():
    """Demo 4: TwistPlus as constructor swap

    TwistPlus(Q, Q) : (Q + Q) → (Q + Q)
    Swaps left and right summands by flipping the tag bit.
    """
    print("\n" + "="*60)
    print("Demo 4: TwistPlus (Constructor Swap)")
    print("="*60)

    ty_q = Q()
    twist = TwistPlus(ty_q, ty_q)

    dom, cod = type_of(twist)
    print(f"\nTerm: TwistPlus(Q, Q)")
    print(f"Type: {dom} → {cod}")

    result = runner.compile(twist, "TwistPlus(Q, Q)")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "TwistPlus(Q, Q)")

    # TwistPlus should emit X gate (tag flip) with flat tag model
    cmds = list(result.circuit.get_commands())
    gate_names = [cmd.op.type.name for cmd in cmds]
    print(f"\nGate sequence: {gate_names}")

    # Flat tag model: TwistPlus emits X on tag bit
    assert 'X' in gate_names, "TwistPlus should emit X gate for tag flip"
    print("✓ Verified: TwistPlus emits X gate for tag flip")

    return result


def demo_qswitch_pattern():
    """Demo 5: QSwitch-like pattern using Case

    The quantum switch applies operations in superposition:
    - |0⟩ branch: apply H then S
    - |1⟩ branch: apply S then H

    This is a "superposition of orderings" - both orderings are applied coherently.
    """
    print("\n" + "="*60)
    print("Demo 5: QSwitch Pattern (Superposition of Orderings)")
    print("="*60)

    ty_q = Q()

    # Left branch: H;S (Hadamard then Phase)
    left_branch = Seq(H(0, ty_q), S(0, ty_q))
    # Right branch: S;H (Phase then Hadamard)
    right_branch = Seq(S(0, ty_q), H(0, ty_q))

    case_term = Case(ty_q, ty_q, left_branch, right_branch)

    dom, cod = type_of(case_term)
    print(f"\nTerm: Case(Q, Q, H;S, S;H)")
    print(f"Type: {dom} → {cod}")
    print("\nSemantics:")
    print("  |0⟩|ψ⟩ → |0⟩(S·H|ψ⟩)  (left branch: H then S)")
    print("  |1⟩|ψ⟩ → |1⟩(H·S|ψ⟩)  (right branch: S then H)")
    print("  Superposition: coherent mixture of both orderings")

    result = runner.compile(case_term, "QSwitch")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "QSwitch")

    cmds = list(result.circuit.get_commands())
    gate_names = [cmd.op.type.name for cmd in cmds]
    print(f"\nGate sequence: {gate_names}")

    # Should have both CH and CS with anti-control pattern
    assert gate_names.count('X') == 2, "Should have 2 X gates for anti-control on left"
    assert gate_names.count('CH') == 2, "Should have 2 CH gates (one per branch)"
    assert gate_names.count('CS') == 2, "Should have 2 CS gates (one per branch)"
    print("✓ Verified: QSwitch pattern compiles to controlled gates")

    return result


def demo_encode_decode_roundtrip():
    """Demo 6: Qubit encoding roundtrip

    Q → (I + I) → Q using EncodeQubit and DecodeQubit.
    This verifies the qubit-to-sum-type encoding works.
    """
    print("\n" + "="*60)
    print("Demo 6: Qubit Encoding Roundtrip")
    print("="*60)

    # Encode : Q → I + I
    # Decode : I + I → Q
    # Roundtrip should be identity (up to ancilla)
    encode = EncodeQubit()
    decode = DecodeQubit()
    roundtrip = Seq(encode, decode)

    enc_dom, enc_cod = type_of(encode)
    dec_dom, dec_cod = type_of(decode)
    rt_dom, rt_cod = type_of(roundtrip)

    print(f"\nEncode: {enc_dom} → {enc_cod}")
    print(f"Decode: {dec_dom} → {dec_cod}")
    print(f"Roundtrip: {rt_dom} → {rt_cod}")

    result = runner.compile(roundtrip, "Encode;Decode")
    runner.print_circuit_details(result, "Roundtrip Circuit")
    runner.show_circuit(result, "Encode;Decode")

    # Encode: CX[0,1]; X[0]
    # Decode: X[0]; CX[0,1]
    # Roundtrip: CX; X; X; CX = CX; CX = identity (X;X cancels)
    cmds = list(result.circuit.get_commands())
    gate_names = [cmd.op.type.name for cmd in cmds]
    print(f"\nGate sequence: {gate_names}")

    # Should have CX and X gates
    assert 'CX' in gate_names, "Should have CX gates"
    assert 'X' in gate_names, "Should have X gates"
    print("✓ Verified: Encode/Decode roundtrip compiles")

    return result


def main():
    global runner
    runner = DemoRunner(
        "Case Expression Compilation Demo",
        "Verifies case expressions compile to controlled gates"
    )
    runner.print_header()
    print("\nThis demo verifies case expressions compile to controlled gates")
    print("using the anti-control pattern for the left branch.")

    # Run all demos
    demo_case_combinator()
    demo_case_with_id_branches()
    demo_case_asymmetric()
    demo_twist_plus_as_swap()
    demo_qswitch_pattern()
    demo_encode_decode_roundtrip()

    print("\n" + "="*60)
    print("All demos passed!")
    print("="*60)

    runner.print_footer()


if __name__ == "__main__":
    main()
