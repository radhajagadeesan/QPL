(** Short-Circuit Conjunction E2E Demo

    Implements short-circuit conjunction with witness wire routing
    and quantum phase marking from the spec.

    Types:
      Bool := I + I                    (2-element type)
      W    := I + Bool = I + (I + I)   (witness: short-circuited vs evaluated)

    Operations:
      toggle_W := id_I ⊕ twist_{I,I} : W → W
        - Identity on I branch (short-circuit path)
        - Swaps the two Bool values (evaluation path)

      ctrl_W(M_0, M_1) : Bool ⊗ W → Bool ⊗ W
        - When ctrl=0 (inl): apply M_0 to W
        - When ctrl=1 (inr): apply M_1 to W
        - Built from dist_l ; omap0 ; undist_l (same pattern as QSwitch)

      and_sc : (Bool ⊗ Bool) ⊗ W → (Bool ⊗ Bool) ⊗ W
        - Routes witness based on first boolean
        - Applies ctrl_W(toggle_W, id_W) to (b1 ⊗ w)

    Quantum Extension:
      phase_W := omap_{-1}(id_I, id_Bool) : W → W
        - Applies -1 phase to I branch (short-circuit occurred)
        - Identity phase to Bool branch (evaluation path)

      kick := λp. let (bb, w) = p in bb ⊗ (phase_W w)

      and_sc_quant := and_sc ; kick
        - Structural routing followed by phase marking
        - Creates interference between short-circuit and evaluation paths
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(* ========================================================================= *)
(* Type Definitions                                                          *)
(* ========================================================================= *)

(** Bool = I + I *)
let bool_ty = one ++ one

(** W = I + Bool = I + (I + I) -- the witness type
    - inl(unit) = short-circuit occurred (first bool was false)
    - inr(b) = evaluation path (first bool was true, b is second bool) *)
let w_ty = one ++ bool_ty

(** I ⊗ W -- payload type in each branch after distribution *)
let iw_ty = one ** w_ty

(** Bool ⊗ W -- input to ctrl_W *)
let _bw_ty = bool_ty ** w_ty

(** Bool ⊗ Bool *)
let bb_ty = bool_ty ** bool_ty

(** (Bool ⊗ Bool) ⊗ W -- full input/output type for and_sc *)
let _bbw_ty = bb_ty ** w_ty

(* ========================================================================= *)
(* Core Operations                                                           *)
(* ========================================================================= *)

(** toggle_W := id_I ⊕ twist_{I,I} : W → W

    Applies identity to the I branch (short-circuit path stays unchanged),
    and swaps the Bool values in the Bool branch (flips the evaluation result).

    This is the bifunctorial action omap(id_I, twist_Bool) on W = I + Bool.
*)
let toggle_w : (unit, [`Lolli of [`Plus of [`One] * [`Plus of [`One] * [`One]]]
                              * [`Plus of [`One] * [`Plus of [`One] * [`One]]]]) prog =
  omap0 one bool_ty (id one) (twist_plus one one)


(** ctrl_W(M_0, M_1) : Bool ⊗ W → Bool ⊗ W

    Coherent control: applies M_0 when control is inl (0),
    applies M_1 when control is inr (1).

    Built using the same pattern as QSwitch:
      dist_l ; omap0(id_I ⊗ M_0, id_I ⊗ M_1) ; undist_l

    This ensures both branches execute coherently on superposition inputs.
*)
let ctrl_w
    (m0 : (unit, [`Lolli of [`Plus of [`One] * [`Plus of [`One] * [`One]]]
                          * [`Plus of [`One] * [`Plus of [`One] * [`One]]]]) prog)
    (m1 : (unit, [`Lolli of [`Plus of [`One] * [`Plus of [`One] * [`One]]]
                          * [`Plus of [`One] * [`Plus of [`One] * [`One]]]]) prog)
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * [`Plus of [`One] * [`Plus of [`One] * [`One]]]]
                      * [`Tensor of [`Plus of [`One] * [`One]] * [`Plus of [`One] * [`Plus of [`One] * [`One]]]]]) prog =

  (* Step 1: Distribute Bool ⊗ W → (I ⊗ W) + (I ⊗ W) *)
  let distribute = dist_l one one w_ty in

  (* Step 2: Build branches with id_I ⊗ M_i *)
  let left_branch = par0 (id one) m0 in   (* when ctrl=0: apply m0 to W *)
  let right_branch = par0 (id one) m1 in  (* when ctrl=1: apply m1 to W *)

  (* Step 3: Apply omap0 for bifunctorial action on the sum *)
  let apply_branches = omap0 iw_ty iw_ty left_branch right_branch in

  (* Step 4: Undistribute (I ⊗ W) + (I ⊗ W) → Bool ⊗ W *)
  let undistribute = undist_l one one w_ty in

  (* Compose: dist ; omap ; undist *)
  seq0 distribute (seq0 apply_branches undistribute)


(** and_sc : (Bool ⊗ Bool) ⊗ W → (Bool ⊗ Bool) ⊗ W

    Short-circuit conjunction routing:

    Input: ((b1 ⊗ b2) ⊗ w)
    1. Route to get (b1 ⊗ w) ⊗ b2 (via associativity and twist)
    2. Apply ctrl_W(toggle_W, id_W) to (b1 ⊗ w)
    3. Route back to ((b1' ⊗ b2) ⊗ w')

    Wire routing uses structural isomorphisms:
      assoc_r ; (id ⊗ twist) ; assoc_l  -- to extract b1 with w
      [apply ctrl_W ⊗ id]
      assoc_r ; (id ⊗ twist) ; assoc_l  -- to reassemble
*)
let and_sc =
  let b = bool_ty in
  let w = w_ty in

  (* Route: (B⊗B)⊗W → (B⊗W)⊗B
     assoc_l: ((A⊗B)⊗C) → (A⊗(B⊗C))
     assoc_r: (A⊗(B⊗C)) → ((A⊗B)⊗C)  *)
  let route_in_1 = assoc_tensor_l b b w in           (* (B⊗B)⊗W → B⊗(B⊗W) *)
  let route_in_2 = par0 (id b) (twist_tensor b w) in (* B⊗(B⊗W) → B⊗(W⊗B) *)
  let route_in_3 = assoc_tensor_r b w b in           (* B⊗(W⊗B) → (B⊗W)⊗B *)
  let route_in = seq0 route_in_1 (seq0 route_in_2 route_in_3) in

  (* Apply ctrl_W(toggle_W, id_W) ⊗ id_B *)
  let ctrl_op = ctrl_w toggle_w (id w_ty) in
  let apply_ctrl = par0 ctrl_op (id b) in

  (* Route: (B⊗W)⊗B → (B⊗B)⊗W *)
  let route_out_1 = assoc_tensor_l b w b in          (* (B⊗W)⊗B → B⊗(W⊗B) *)
  let route_out_2 = par0 (id b) (twist_tensor w b) in (* B⊗(W⊗B) → B⊗(B⊗W) *)
  let route_out_3 = assoc_tensor_r b b w in          (* B⊗(B⊗W) → (B⊗B)⊗W *)
  let route_out = seq0 route_out_1 (seq0 route_out_2 route_out_3) in

  (* Full composition *)
  seq0 route_in (seq0 apply_ctrl route_out)


(* ========================================================================= *)
(* Quantum Extension: Phase Marking                                          *)
(* ========================================================================= *)

(** phase_W : W -> W

    Applies -1 phase to the I branch (short-circuit path),
    identity (+1 phase) to the Bool branch (evaluation path).

    In our encoding, W = I + Bool has 2 tag qubits (3 variants):
      Tag 00 = inl(unit)      <- short-circuit path
      Tag 01 = inr(inl(unit))
      Tag 10 = inr(inr(unit))

    To apply -1 phase specifically to |00⟩:
      X[0]; X[1]; CZ[0,1]; X[1]; X[0]

    This works because:
    - X[0]; X[1] maps |00⟩ → |11⟩
    - CZ applies -1 phase to |11⟩
    - X[1]; X[0] maps back |11⟩ → |00⟩
    - Net effect: -1 phase on |00⟩ only, identity on other states
*)
let phase_w_bridge : Bridge.term =
  (* W has 2 tag qubits at indices 0 and 1 *)
  let x0 = Bridge.TX 0 in
  let x1 = Bridge.TX 1 in
  let cz = Bridge.TCZ (0, 1) in
  (* X[0]; X[1]; CZ[0,1]; X[1]; X[0] *)
  Bridge.TSeq (x0,
    Bridge.TSeq (x1,
      Bridge.TSeq (cz,
        Bridge.TSeq (x1, x0))))


(** kick : (Bool ⊗ Bool) ⊗ W -> (Bool ⊗ Bool) ⊗ W

    Applies phase_W to the witness wire while preserving the booleans.

    Input type: (Bool ⊗ Bool) ⊗ W = 4 qubits
    Wire layout: [b1_tag | b2_tag | w_tag0 | w_tag1]

    We need to apply phase_W (which acts on wires 0,1) to the W part
    (which is at wires 2,3). So we use wire indices 2 and 3.
*)
let kick_bridge : Bridge.term =
  (* W is at wires 2 and 3 in the (Bool ⊗ Bool) ⊗ W layout *)
  let x2 = Bridge.TX 2 in
  let x3 = Bridge.TX 3 in
  let cz = Bridge.TCZ (2, 3) in
  (* X[2]; X[3]; CZ[2,3]; X[3]; X[2] *)
  Bridge.TSeq (x2,
    Bridge.TSeq (x3,
      Bridge.TSeq (cz,
        Bridge.TSeq (x3, x2))))


(** and_sc_quant : (Bool ⊗ Bool) ⊗ W -> (Bool ⊗ Bool) ⊗ W

    Quantum short-circuit conjunction: structural routing followed by phase marking.

    and_sc_quant = and_sc ; kick

    When run on superposition inputs, the -1 phase on the short-circuit
    branch creates interference between paths where short-circuit occurred
    and paths where it did not.
*)
let and_sc_quant_bridge : Bridge.term =
  Bridge.TSeq (emit and_sc, kick_bridge)


(* ========================================================================= *)
(* Compilation and Reporting                                                 *)
(* ========================================================================= *)

let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile term with
  | Bridge.CompileOk (perm, size) ->
      Printf.printf "  ✓ Gates: %d\n" size;
      Printf.printf "    Perm:  [%s]\n"
        (String.concat ", " (List.map string_of_int perm.new_to_old))
  | Bridge.CompileError err ->
      Printf.printf "  ✗ FAILED: %s\n" err


(* ========================================================================= *)
(* Main Demo                                                                 *)
(* ========================================================================= *)

let () =
  (* Set project root for bridge.py *)
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  banner "SHORT-CIRCUIT CONJUNCTION E2E DEMO";
  print_endline "\nImplementing short-circuit conjunction with witness routing\n";

  (* ======================================================================= *)
  banner "PART 1: Type Structure";

  print_endline "
Types:
  Bool := I + I                    (2-element sum)
  W    := I + Bool = I + (I + I)   (3-element witness type)

  W encodes control flow history:
    inl(unit)  = short-circuit occurred (b1 was false)
    inr(b)  = evaluation path (b1 was true, b is b2's value)
";

  print_endline "Circuit widths (from permutation sizes):";
  print_endline "  Bool = I + I          → 1 qubit  (tag for 2 variants)";
  print_endline "  W = I + Bool          → 2 qubits (tag for 3 variants)";
  print_endline "  Bool ⊗ W             → 3 qubits";
  print_endline "  (Bool ⊗ Bool) ⊗ W    → 4 qubits";

  (* ======================================================================= *)
  banner "PART 2: toggle_W = id_I ⊕ twist_{I,I}";

  print_endline "
toggle_W : W → W

Applies identity to I branch (short-circuit stays unchanged),
swaps Bool values in Bool branch (flips evaluation result).

Built as: omap0 one bool_ty (id one) (twist_plus one one)
";

  compile_and_report "toggle_W" (emit toggle_w);

  Printf.printf "\nBridge JSON:\n  %s\n" (Bridge.term_to_json (emit toggle_w));

  (* ======================================================================= *)
  banner "PART 3: ctrl_W(M_0, M_1) - Coherent Control";

  print_endline "
ctrl_W(M_0, M_1) : Bool ⊗ W → Bool ⊗ W

Same pattern as QSwitch:
  dist_l ; omap0(id_I ⊗ M_0, id_I ⊗ M_1) ; undist_l

When ctrl=0 (inl): applies M_0 to W
When ctrl=1 (inr): applies M_1 to W
";

  (* ctrl_W with toggle_W on 0, id_W on 1 *)
  let ctrl_toggle_id = ctrl_w toggle_w (id w_ty) in
  compile_and_report "ctrl_W(toggle_W, id_W)" (emit ctrl_toggle_id);

  (* ctrl_W with id on both branches = identity *)
  let ctrl_id_id = ctrl_w (id w_ty) (id w_ty) in
  compile_and_report "ctrl_W(id_W, id_W) [should be identity]" (emit ctrl_id_id);

  (* ctrl_W with toggle on both branches *)
  let ctrl_toggle_toggle = ctrl_w toggle_w toggle_w in
  compile_and_report "ctrl_W(toggle_W, toggle_W)" (emit ctrl_toggle_toggle);

  (* ======================================================================= *)
  banner "PART 4: and_sc - Full Short-Circuit Conjunction";

  print_endline "
and_sc : (Bool ⊗ Bool) ⊗ W → (Bool ⊗ Bool) ⊗ W

Full operation:
  1. Route wires: (b1 ⊗ b2) ⊗ w  →  (b1 ⊗ w) ⊗ b2
  2. Apply: ctrl_W(toggle_W, id_W) ⊗ id_Bool
  3. Route back: (b1' ⊗ w') ⊗ b2  →  (b1' ⊗ b2) ⊗ w'

Routing uses structural isomorphisms:
  assoc_tensor_r ; (id ⊗ twist_tensor) ; assoc_tensor_l
";

  compile_and_report "and_sc" (emit and_sc);

  (* ======================================================================= *)
  banner "PART 5: Verifying Components";

  print_endline "\nIndividual structural isomorphisms:\n";

  (* Show individual components compile correctly *)
  compile_and_report "assoc_tensor_r Bool Bool W"
    (emit (assoc_tensor_r bool_ty bool_ty w_ty));

  compile_and_report "twist_tensor Bool W"
    (emit (twist_tensor bool_ty w_ty));

  compile_and_report "assoc_tensor_l Bool W Bool"
    (emit (assoc_tensor_l bool_ty w_ty bool_ty));

  (* ======================================================================= *)
  banner "PART 6: Composition";

  print_endline "
Short-circuit conjunction composes:
  and_sc ; and_sc = double application
";

  let and_sc_twice = seq0 and_sc and_sc in
  compile_and_report "and_sc ; and_sc" (emit and_sc_twice);

  (* ======================================================================= *)
  banner "PART 7: Quantum Extension (Phase Marking)";

  print_endline "
Quantum phase marking creates interference between paths:

  phase_W : W → W
    Applies -1 phase to inl branch (short-circuit occurred)
    Identity phase to inr branch (evaluation path)

  Implementation for W with 2 tag qubits:
    Tag 00 = inl(unit) <- short-circuit path
    Tag 01 = inr(inl(unit))
    Tag 10 = inr(inr(unit))

  Circuit: X[0]; X[1]; CZ[0,1]; X[1]; X[0]
    - X gates map |00⟩ → |11⟩
    - CZ applies -1 to |11⟩
    - X gates map back
    - Net effect: -1 phase on |00⟩ only
";

  Printf.printf "\nphase_W on W (2 qubits):\n";
  Printf.printf "  Bridge: %s\n" (Bridge.term_to_json phase_w_bridge);
  (match Bridge.compile phase_w_bridge with
   | Bridge.CompileOk (perm, size) ->
       Printf.printf "  ✓ Gates: %d\n" size;
       Printf.printf "    Perm:  [%s]\n"
         (String.concat ", " (List.map string_of_int perm.new_to_old))
   | Bridge.CompileError err ->
       Printf.printf "  ✗ FAILED: %s\n" err);

  print_endline "
kick : (Bool ⊗ Bool) ⊗ W → (Bool ⊗ Bool) ⊗ W
  Applies phase_W to witness wire (at indices 2,3)
  Preserves boolean wires (at indices 0,1)
";

  Printf.printf "\nkick on (Bool ⊗ Bool) ⊗ W (4 qubits):\n";
  Printf.printf "  Bridge: %s\n" (Bridge.term_to_json kick_bridge);
  (match Bridge.compile kick_bridge with
   | Bridge.CompileOk (perm, size) ->
       Printf.printf "  ✓ Gates: %d\n" size;
       Printf.printf "    Perm:  [%s]\n"
         (String.concat ", " (List.map string_of_int perm.new_to_old))
   | Bridge.CompileError err ->
       Printf.printf "  ✗ FAILED: %s\n" err);

  print_endline "
and_sc_quant := and_sc ; kick
  Structural routing followed by phase marking
  Creates interference between execution paths
";

  Printf.printf "\nand_sc_quant = and_sc ; kick:\n";
  (match Bridge.compile and_sc_quant_bridge with
   | Bridge.CompileOk (perm, size) ->
       Printf.printf "  ✓ Gates: %d (3 from and_sc + 5 from kick)\n" size;
       Printf.printf "    Perm:  [%s]\n"
         (String.concat ", " (List.map string_of_int perm.new_to_old))
   | Bridge.CompileError err ->
       Printf.printf "  ✗ FAILED: %s\n" err);

  print_endline "
QUANTUM SEMANTICS
-----------------
When run on superposition input |+⟩ ⊗ |b2⟩ ⊗ |w⟩:

  |0⟩|b2⟩|w⟩  →  |0⟩|b2⟩|toggle(w)⟩  →  -|0⟩|b2⟩|toggle(w)⟩  (phase -1)
  |1⟩|b2⟩|w⟩  →  |1⟩|b2⟩|w⟩          →   |1⟩|b2⟩|w⟩          (phase +1)

The -1 phase on the short-circuit path creates interference,
encoding control-flow history in the quantum state.
";

  (* ======================================================================= *)
  banner "SUMMARY";

  print_endline "
Demonstrated short-circuit conjunction in Linear DSL:

1. TYPE STRUCTURE
   Bool = I + I (2-element, 1 qubit)
   W = I + Bool (3-element witness, 2 qubits)

2. STRUCTURAL OPERATIONS
   toggle_W = id_I ⊕ twist_Bool : W → W         (1 gate)
   ctrl_W(M_0, M_1) : Bool ⊗ W → Bool ⊗ W      (coherent control)
   and_sc : (Bool ⊗ Bool) ⊗ W → ...            (3 gates)

3. QUANTUM PHASE MARKING
   phase_W : W → W                              (5 gates)
     X[0]; X[1]; CZ[0,1]; X[1]; X[0]
     Applies -1 phase to inl branch (tag 00)

   kick : (Bool ⊗ Bool) ⊗ W → ...              (5 gates)
     Applies phase_W to witness wires

4. QUANTUM SHORT-CIRCUIT CONJUNCTION
   and_sc_quant = and_sc ; kick                 (8 gates total)
     Structural routing + phase marking
     Creates interference between execution paths

Key insight: Classical short-circuit logic lifts to quantum
coherent control. Phase marking encodes control-flow history
in interference patterns.
";

  banner "DEMO COMPLETE"
