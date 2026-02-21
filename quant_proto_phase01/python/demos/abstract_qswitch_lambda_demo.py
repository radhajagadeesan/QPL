#!/usr/bin/env python3
"""Abstract QSwitch: Higher-Order Lambda Term

Builds the ABSTRACT QSwitch as a Lam term and compiles it.
This shows the circuit for the lambda BEFORE f and g are instantiated.

    QSwitch : (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q ⊸ Bool ⊗ Q

Wire layout (8-wire Lambda interface):
    A_slot [0..6): [f_arg | f_res | g_arg | g_res | tag | x]
    B_slot [6..8): [tag'  | result]

The body is pure first-order structural operations:
    rearrange ; dist_l ; PlusMap(branch_left, branch_right) ; undist_l ; rearrange_out
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.types import Q, Unit, Ten, Plus, Arrow, width
from lang.terms import (
    Id, Seq, TenTerm, Lam, Apply, FunVar, Var,
    TwistTen, AssocTenL, AssocTenR,
    DistL, UndistL, PlusMap,
)
from typing_.check import type_of
from compile.to_pytket import compile


def main():
    print("=" * 74)
    print("  Abstract QSwitch: Higher-Order Lambda Term")
    print("=" * 74)

    # ======================================================================
    # Type definitions
    # ======================================================================
    I = Unit()
    Bool = Plus(I, I)
    QtoQ = Arrow(Q(), Q())

    # Input: (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q
    input_ty = Ten(QtoQ, Ten(QtoQ, Ten(Bool, Q())))
    # Output: Bool ⊗ Q
    output_ty = Ten(Bool, Q())

    print(f"""
TYPE DEFINITIONS:
    Q ⊸ Q     width = {width(QtoQ)} (arg wire + res wire)
    Bool      width = {width(Bool)} (tag qubit)
    Input:    {input_ty}  width = {width(input_ty)}
    Output:   {output_ty}  width = {width(output_ty)}

Wire layout for input (6 wires):
    [f_arg=0 | f_res=1 | g_arg=2 | g_res=3 | tag=4 | x=5]

Lambda interface (8 wires):
    A_slot [0..6): input
    B_slot [6..8): output [tag' | result]
""")

    # ======================================================================
    # Approach: Use the established dist_l ; omap0 ; undist_l pattern
    # BUT with Arrow types in the payload
    # ======================================================================

    # The body operates on the 6 input wires.
    # Step 1: Rearrange to put Bool first: Bool ⊗ (Q⊸Q) ⊗ (Q⊸Q) ⊗ Q
    #   From: F ⊗ (G ⊗ (B ⊗ X))
    #   To:   B ⊗ (F ⊗ (G ⊗ X))

    F = QtoQ  # width 2
    G = QtoQ  # width 2
    B = Bool  # width 1
    X = Q()   # width 1

    # Structural iso sequence to move Bool to front:
    # F ⊗ (G ⊗ (B ⊗ X))
    #   → F ⊗ ((G ⊗ B) ⊗ X)       via id_F ⊗ AssocTenR(G, B, X)
    #   → F ⊗ ((B ⊗ G) ⊗ X)       via id_F ⊗ (TwistTen(G, B) ⊗ id_X)
    #   → F ⊗ (B ⊗ (G ⊗ X))       via id_F ⊗ AssocTenL(B, G, X)
    #   → (F ⊗ B) ⊗ (G ⊗ X)       via AssocTenR(F, B, G⊗X)
    #   → (B ⊗ F) ⊗ (G ⊗ X)       via TwistTen(F, B) ⊗ id_{G⊗X}
    #   → B ⊗ (F ⊗ (G ⊗ X))       via AssocTenL(B, F, G⊗X)

    GX = Ten(G, X)

    rearrange_fwd = Seq(
        TenTerm(Id(F), AssocTenR(G, B, X)),                  # F ⊗ ((G⊗B) ⊗ X)
        Seq(
            TenTerm(Id(F), TenTerm(TwistTen(G, B), Id(X))),  # F ⊗ ((B⊗G) ⊗ X)
            Seq(
                TenTerm(Id(F), AssocTenL(B, G, X)),           # F ⊗ (B ⊗ (G⊗X))
                Seq(
                    AssocTenR(F, B, GX),                      # (F⊗B) ⊗ (G⊗X)
                    Seq(
                        TenTerm(TwistTen(F, B), Id(GX)),      # (B⊗F) ⊗ (G⊗X)
                        AssocTenL(B, F, GX),                   # B ⊗ (F ⊗ (G⊗X))
                    )
                )
            )
        )
    )

    # Verify type
    rearrange_dom, rearrange_cod = type_of(rearrange_fwd)
    print(f"Rearrange: {rearrange_dom} → {rearrange_cod}")
    print(f"  dom width = {width(rearrange_dom)}, cod width = {width(rearrange_cod)}")

    # Step 2: dist_l(I, I, payload) where payload = F ⊗ (G ⊗ X)
    payload_ty = Ten(F, GX)   # (Q⊸Q) ⊗ ((Q⊸Q) ⊗ Q)  width = 5
    distribute = DistL(I, I, payload_ty)

    dist_dom, dist_cod = type_of(distribute)
    print(f"\nDistribute: {dist_dom} → {dist_cod}")
    print(f"  dom width = {width(dist_dom)}, cod width = {width(dist_cod)}")

    # Step 3: PlusMap with wiring-only branches
    # Each branch operates on Ten(I, payload) = payload (since I has width 0)
    # Branch payload wires: [f_arg=0, f_res=1, g_arg=2, g_res=3, x=4]
    branch_ty = Ten(I, payload_ty)  # I ⊗ (F ⊗ (G ⊗ X))

    print(f"\nBranch type: {branch_ty}  width = {width(branch_ty)}")

    # Left branch: apply g then f to x
    # Permutation on 5 wires: [f_arg, f_res, g_arg, g_res, x]
    # Data flow: x → g_arg, g_res → f_arg, result = f_res
    # Want result (f_res=1) at x's position (4) for output routing
    #
    # Using structural isos to implement the wiring permutation:
    # We need to express this as type-level rewriting of I ⊗ (F ⊗ (G ⊗ X))
    #
    # Specifically on (Q⊗Q) ⊗ ((Q⊗Q) ⊗ Q):
    # [f_arg, f_res] ⊗ ([g_arg, g_res] ⊗ [x])
    #
    # Left branch wiring (g then f):
    #   x → g_arg: TwistTen on G⊗X block moves x to g's arg
    #   g_res → f_arg: TwistTen on F and G moves g's output to f's arg
    #
    # At the type level:
    # F ⊗ (G ⊗ X) → F ⊗ (X ⊗ G)   [swap G and X: x goes next to g]
    #             → ... complex

    # Actually, the simplest approach: use TwistTen at the right granularity.
    # The payload is F ⊗ (G ⊗ X) = (Q⊗Q) ⊗ ((Q⊗Q) ⊗ Q)
    # = 5 qubits: [f_a, f_r, g_a, g_r, x]

    # For g_then_f: we want the output at position x (wire 4)
    # Permutation (new_to_old): need result at wire 4
    # [2, 4, 3, 0, 1] puts f_res(1) at wire 0... not quite what we want.

    # Actually, after PlusMap + undist_l, the layout is:
    #   Bool ⊗ (branch_output)
    # = [tag | branch_output_wires]
    #
    # We then need to rearrange back so the overall Lambda body produces
    # output_ty = Bool ⊗ Q at the start of the wire range.
    #
    # After undist_l: [tag | f_arg' | f_res' | g_arg' | g_res' | x']
    # We need: [tag | result | ...function_wires...]
    #
    # For left branch, result = f_res. After the branch, f_res should be
    # at the x position (position 4 in the payload), giving:
    # After undist: [tag | ... | f_res_at_4]
    # Then rearrange output to: [tag | f_res | f_arg | g_arg | g_res | x]

    # Let me try a simpler approach: id branches first to validate the plumbing
    left_branch = TenTerm(Id(I), Id(payload_ty))   # identity on I ⊗ payload
    right_branch = TenTerm(Id(I), Id(payload_ty))

    branches = PlusMap(branch_ty, branch_ty, left_branch, right_branch)
    br_dom, br_cod = type_of(branches)
    print(f"\nPlusMap: {br_dom} → {br_cod}")
    print(f"  dom width = {width(br_dom)}, cod width = {width(br_cod)}")

    # Step 4: undist_l
    undistribute = UndistL(I, I, payload_ty)

    # Inverse rearrange: B ⊗ (F ⊗ (G ⊗ X)) → F ⊗ (G ⊗ (B ⊗ X))
    # This is the reverse of rearrange_fwd
    rearrange_rev = Seq(
        AssocTenR(B, F, GX),                              # (B⊗F) ⊗ (G⊗X)
        Seq(
            TenTerm(TwistTen(B, F), Id(GX)),               # (F⊗B) ⊗ (G⊗X)
            Seq(
                AssocTenL(F, B, GX),                        # F ⊗ (B ⊗ (G⊗X))
                Seq(
                    TenTerm(Id(F), AssocTenR(B, G, X)),     # F ⊗ ((B⊗G) ⊗ X)
                    Seq(
                        TenTerm(Id(F), TenTerm(TwistTen(B, G), Id(X))),  # F ⊗ ((G⊗B) ⊗ X)
                        TenTerm(Id(F), AssocTenL(G, B, X)),  # F ⊗ (G ⊗ (B⊗X))
                    )
                )
            )
        )
    )

    # Full body: rearrange ; dist ; branches ; undist ; rearrange_back
    body = Seq(rearrange_fwd,
           Seq(distribute,
           Seq(branches,
           Seq(undistribute,
               rearrange_rev))))

    body_dom, body_cod = type_of(body)
    print(f"\nFull body: {body_dom} → {body_cod}")
    print(f"  dom width = {width(body_dom)}, cod width = {width(body_cod)}")

    # ======================================================================
    # First test: compile just the body (without Lambda wrapper)
    # ======================================================================
    print("\n" + "=" * 74)
    print("  Test 1: Compile body (id branches, no Lambda)")
    print("=" * 74)

    try:
        result_body = compile(body, materialize=False, explain=True)
        print(f"\n  Circuit size: {result_body.circuit.n_gates} gates")
        print(f"  Wire count: {result_body.circuit.n_qubits}")
        print(f"  Permutation: {result_body.perm.new_to_old}")
        if result_body.log:
            print("\n  Compilation log:")
            for entry in result_body.log[:20]:
                print(f"    {entry}")
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()

    # ======================================================================
    # Test 2: Compile body with actual branches (H/S wiring)
    # ======================================================================
    print("\n" + "=" * 74)
    print("  Test 2: Compile with H;S / S;H branches")
    print("=" * 74)

    from lang.terms import H, S

    # Branch payload type for H;S: operate on I ⊗ payload
    # But we need the branches to apply H and S to the x wire (position 4 in payload)
    # In the branch, x is at wire 4. H operates on wire i.
    # We need H on wire 4, S on wire 4 of the 5-wire branch.

    # Actually, the branches should apply the gate composition to the TARGET qubit.
    # In the payload [f_arg, f_res, g_arg, g_res, x], x is at wire 4.
    # But the branch morphism is on I ⊗ payload. I has width 0, so it's just payload.
    # We need TenTerm to apply id on [f,g] wires and gates on x wire.

    # payload_ty = Ten(F, Ten(G, X)) = Ten(Arrow(Q,Q), Ten(Arrow(Q,Q), Q()))
    # width(F) = 2, width(G) = 2, width(X) = 1

    # Left branch: apply id on F, (id on G followed by gate on X)
    # = TenTerm(Id(F), TenTerm(Id(G), Seq(S(0), H(0))))  -- S then H on the X wire
    #
    # But wait, gate S(0) operates on wire 0 of its ty_total. In TenTerm(Id(G), S(0, X)),
    # the S gate is on the rightmost Q wire.

    IQ = Ten(I, Q())
    left_hs = TenTerm(Id(I), TenTerm(Id(F), TenTerm(Id(G), Seq(S(0, X), H(0, X)))))
    right_hs = TenTerm(Id(I), TenTerm(Id(F), TenTerm(Id(G), Seq(H(0, X), S(0, X)))))

    lhs_dom, lhs_cod = type_of(left_hs)
    print(f"\n  Left branch type: {lhs_dom} → {lhs_cod}  width={width(lhs_dom)}")

    branches_hs = PlusMap(branch_ty, branch_ty, left_hs, right_hs)

    body_hs = Seq(rearrange_fwd,
              Seq(distribute,
              Seq(branches_hs,
              Seq(undistribute,
                  rearrange_rev))))

    try:
        result_hs = compile(body_hs, materialize=False, explain=True)
        print(f"\n  Circuit size: {result_hs.circuit.n_gates} gates")
        print(f"  Wire count: {result_hs.circuit.n_qubits}")
        print(f"  Permutation: {result_hs.perm.new_to_old}")
        if result_hs.log:
            print("\n  Compilation log (first 20):")
            for entry in result_hs.log[:20]:
                print(f"    {entry}")
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()

    # ======================================================================
    # Test 3: Wrap in Lambda
    # ======================================================================
    print("\n" + "=" * 74)
    print("  Test 3: Full Lambda term")
    print("=" * 74)

    # Lam("input", input_ty, output_ty, body)
    # body operates on input wires [0..6)
    # Lambda routes body output [0..wB) to B_slot [wA..wA+wB)
    abstract_qs = Lam("input", input_ty, output_ty, body)

    lam_dom, lam_cod = type_of(abstract_qs)
    print(f"\n  Lambda type: {lam_dom} → {lam_cod}")
    print(f"    dom width = {width(lam_dom)}, cod width = {width(lam_cod)}")
    print(f"    wA (input) = {width(input_ty)}, wB (output) = {width(output_ty)}")
    print(f"    Total wires = {width(input_ty) + width(output_ty)}")

    try:
        result_lam = compile(abstract_qs, materialize=True, explain=True)
        print(f"\n  Circuit size: {result_lam.circuit.n_gates} gates")
        print(f"  Wire count: {result_lam.circuit.n_qubits}")
        if result_lam.log:
            print("\n  Compilation log (first 30):")
            for entry in result_lam.log[:30]:
                print(f"    {entry}")

        # Show the unitary matrix
        import numpy as np
        U = result_lam.circuit.get_unitary()
        print(f"\n  Unitary matrix ({U.shape[0]}x{U.shape[1]}):")
        np.set_printoptions(precision=3, suppress=True, linewidth=120)
        print(U)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 74)
    print("  DONE")
    print("=" * 74)


if __name__ == "__main__":
    main()
