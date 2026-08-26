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

    Quantum Extension (phase kickback: phased route composed with unphased inverse):
      routeW^q := dist_l⁻¹ ;
                  ⊕-map( -1 · (id_I ⊗ toggle_W),
                          1 · (id_I ⊗ id_W) ) ;
                  dist_l
              : Bool ⊗ W → Bool ⊗ W
        - When b1 = 0 (left summand): apply id_I ⊗ toggle_W, branch picks up -1
        - When b1 = 1 (right summand): apply id_I ⊗ id_W with phase +1

      routeW_kickback := routeW^q ; ctrl_W(toggle_W, id_W)
              : Bool ⊗ W → Bool ⊗ W
        - Applies the phased route, then the unphased inverse routing.
        - Since toggle_W² = id_W, the second application coherently undoes
          the witness toggle on the b1 = 0 branch, leaving:
              (-1)·|0⟩⟨0|_{b1} ⊗ id_W  +  |1⟩⟨1|_{b1} ⊗ id_W  =  (-Z_{b1}) ⊗ id_W
        - The witness temporarily records the route; the unphased inverse
          coherently removes that record; the relative phase remains
          available for interference on b1.

      and_sc_q := route_in ; (routeW_kickback ⊗ id_Bool) ; route_out
        - Same wiring as and_sc, with routeW replaced by routeW_kickback.
        - The -1 phase is conditioned on the short-circuit predicate (b1 = 0)
          itself and carries "short-circuit happened" directly into the
          amplitude of b1, with no residual entanglement between b1 and w.
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
(* Quantum Extension: phase inside the controlled ⊕-Map                      *)
(* ========================================================================= *)

let neg_one = Complex.neg Complex.one

(** route_w_q : Bool ⊗ W → Bool ⊗ W  — phased route (raw building block)

    Spec form:
      route_w_q := dist_l⁻¹ ; ⊕-map( -1 · (id_I ⊗ toggle_W) , 1 · (id_I ⊗ id_W) ) ; dist_l

    Same wiring as ctrl_W(toggle_W, id_W), but the controlled ⊕-Map has a
    branch-local -1 phase coefficient on the LEFT (b1 = 0) summand. When the
    first boolean is 0, the witness is toggled *and* the branch picks up a -1;
    when the first boolean is 1, the witness passes through with phase +1.

    NOTE: applied alone, this entangles the witness with b1 (toggle fires on
    the b1 = 0 branch). Use [route_w_kickback] below for the disentangled
    phase-kickback form actually used in [and_sc_q].
*)
let route_w_q =
  let iw = one ** w_ty in
  let left_branch  = par0 (id one) toggle_w   in   (* tag=0: phase -1, id ⊗ toggle *)
  let right_branch = par0 (id one) (id w_ty)  in   (* tag=1: phase +1, id ⊗ id     *)
  let phased_branches =
    phased_omap0 neg_one iw iw left_branch right_branch in
  seq0 (dist_l one one w_ty)
       (seq0 phased_branches (undist_l one one w_ty))


(** route_w_kickback : Bool ⊗ W → Bool ⊗ W  — phase-only, witness restored

      route_w_kickback := route_w_q ; ctrl_W(toggle_W, id_W)

    Since toggle_W is an involution (toggle² = id), applying the unphased
    ctrl_W(toggle, id) after the phased route coherently undoes the witness
    toggle on the b1 = 0 branch while leaving the -1 phase in place.

    Net action on basis states:
      |0⟩ ⊗ |w⟩  ↦  -|0⟩ ⊗ |w⟩       (branch-local phase -1, witness restored)
      |1⟩ ⊗ |w⟩  ↦   |1⟩ ⊗ |w⟩       (no phase, no change)

    i.e. route_w_kickback = (-Z_{b1}) ⊗ id_W. The witness temporarily
    records the route, then the unphased inverse coherently removes that
    record; the relative phase remains available for interference.

    This is the "phase kickback" pattern: a branch-local unitary + its
    inverse leaves phase on the control without any residual entanglement
    on the target — provided the branch action is an involution.
*)
let route_w_kickback =
  let unphased_route = ctrl_w toggle_w (id w_ty) in
  seq0 route_w_q unphased_route


(** and_sc_q : (Bool ⊗ Bool) ⊗ W → (Bool ⊗ Bool) ⊗ W

    Same surrounding routing as and_sc, but the inner controlled op is
    [route_w_kickback] (phased route composed with its unphased inverse,
    leaving a clean phase on b1 and restoring the witness).
*)
let and_sc_q =
  let b = bool_ty in
  let w = w_ty in
  let route_in_1 = assoc_tensor_l b b w in
  let route_in_2 = par0 (id b) (twist_tensor b w) in
  let route_in_3 = assoc_tensor_r b w b in
  let route_in   = seq0 route_in_1 (seq0 route_in_2 route_in_3) in

  let apply_ctrl = par0 route_w_kickback (id b) in

  let route_out_1 = assoc_tensor_l b w b in
  let route_out_2 = par0 (id b) (twist_tensor w b) in
  let route_out_3 = assoc_tensor_r b b w in
  let route_out   = seq0 route_out_1 (seq0 route_out_2 route_out_3) in

  seq0 route_in (seq0 apply_ctrl route_out)


(** Phase-only reference for the semantic claim about [route_w_kickback]:

      phase_neg_z_on_bool ⊗ id_W  =  (-|0⟩⟨0| + |1⟩⟨1|) ⊗ id_W

    where phase_neg_z_on_bool : Bool → Bool applies phase -1 on the inl(unit)
    summand and phase +1 on the inr(unit) summand — exactly (-Z) on the
    Bool tag qubit. Used in PART 9 to certify that
    route_w_kickback equals this operator (witness genuinely disentangled).
*)
let phase_neg_z_on_bool =
  phased_omap0 neg_one one one (id one) (id one)


(* ========================================================================= *)
(* Compilation and Reporting                                                 *)
(* ========================================================================= *)

let had_failure = ref false
let verifications_run = ref 0
let verifications_passed = ref 0

let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile_show term with
  | Bridge.CompileOk _ -> ()
  | Bridge.CompileError err ->
      Printf.printf "  ✗ FAILED: %s\n" err;
      had_failure := true

let verify_eq name term1 term2 =
  incr verifications_run;
  match Bridge.eq_circ term1 term2 with
  | Bridge.EqCircOk (true, fidelity) ->
      Printf.printf "  ✓ %s (fidelity=%.6f)\n" name fidelity;
      incr verifications_passed
  | Bridge.EqCircOk (false, fidelity) ->
      Printf.printf "  ✗ %s FAILED (fidelity=%.6f)\n" name fidelity;
      had_failure := true
  | Bridge.EqCircError err ->
      Printf.printf "  ✗ %s ERROR: %s\n" name err;
      had_failure := true


(* ========================================================================= *)
(* Main Demo                                                                 *)
(* ========================================================================= *)

let () =
  (* Set project root for bridge.py *)


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
  banner "PART 7: Quantum Extension (phase kickback via unphased inverse route)";

  print_endline "
The classical and_sc above is purely structural — it routes the witness
based on b1 but emits no phase. The quantum extension builds a phase-only
operator on b1 by composing a phased route with its unphased inverse:

  routeW^q := dist_l⁻¹ ;
              ⊕-map( -1 · (id_I ⊗ toggle_W),
                      1 · (id_I ⊗ id_W) ) ;
              dist_l                              -- phased route

  routeW_kickback := routeW^q ; ctrl_W(toggle_W, id_W)
                                                  -- ⋯ then unphased inverse

  and_sc_q := route_in ; (routeW_kickback ⊗ id_Bool) ; route_out
           : (Bool ⊗ Bool) ⊗ W → (Bool ⊗ Bool) ⊗ W

Why the composition rather than routeW^q alone?

  Applied alone, routeW^q entangles the witness with b1: the b1 = 0
  branch outputs |toggle(w)⟩ on the witness, the b1 = 1 branch outputs
  |w⟩. On a superposition of b1 the two branches live on orthogonal
  witness states, and no Hadamard on b1 alone can recover interference —
  the witness has classically recorded which branch fired.

  Composing with the unphased inverse routing ctrl_W(toggle_W, id_W) is a
  standard phase-kickback trick: since toggle_W is an involution
  (toggle² = id), a second application on the b1 = 0 branch coherently
  undoes the witness modification while leaving the branch-local -1 phase
  untouched.

  Net action of routeW_kickback on basis states:

      |0⟩|w⟩  ↦  -|0⟩|w⟩         (branch-local phase -1, witness restored)
      |1⟩|w⟩  ↦   |1⟩|w⟩         (identity)

  i.e. routeW_kickback = (-Z_{b1}) ⊗ id_W.

  Interference on superposition. With b1 in |+⟩ = (|0⟩+|1⟩)/√2:

      routeW_kickback (|+⟩|w⟩) = -|-⟩|w⟩
      H_{b1} applied            = -|1⟩|w⟩

  The unphased route–unroute analog (ctrl_W(toggle,id) applied twice) is
  the identity, so the same starting state maps under it to |+⟩|w⟩ ↦ |0⟩|w⟩
  after H_{b1}. The Hadamard outcome genuinely switches from 0 (no
  short-circuit branch) to 1 (short-circuit branch phased), while the
  witness is restored and disentangled.

Structural note on W:
  W = E ⊕ QBool where E is the first-order \"empty\" summand (unit) and
  QBool records the intermediate route. The kickback pattern requires the
  QBool action to be an involution (toggle_W² = id_W): a toggle-sensitive
  witness records the intermediate route, and the coherent inverse then
  removes that record. Not every possible witness-modifying combinator has
  this property — the involution is what makes disentanglement clean.
";

  print_endline "\n--- routeW^q (phased ⊕-Map sandwich) ---\n";
  compile_and_report "routeW^q (raw phased route)" (emit route_w_q);

  print_endline "\n--- routeW_kickback (phased route ; unphased inverse) ---\n";
  compile_and_report "routeW_kickback" (emit route_w_kickback);

  print_endline "\n--- and_sc_q (uses routeW_kickback in place of routeW) ---\n";
  compile_and_report "and_sc_q" (emit and_sc_q);

  (* ======================================================================= *)
  banner "PART 8: N-ary Phased Control (phased_control)";

  print_endline "
The phased_control combinator generalizes phased_omap0 to n-ary datatypes:

  phased_control : D → Complex.t array → A ty → (A → A) array → D ⊗ A → D ⊗ A

For datatype D with arity k and phases [z₀; ...; z_{k-1}]:
  - Applies phase zᵢ when control is in branch i
  - Uses efficient log₂(k) tag encoding

Example: W = I + Bool is a 3-element type (W_datatype with arity 3)
  Tag 00 = inl(·)        short-circuit path
  Tag 01 = inr(inl(·))   evaluation with false
  Tag 10 = inr(inr(·))   evaluation with true

Phases [-1, +1, +i] would apply:
  - θ₀ = π   on tag 00  (branch 0)
  - θ₁ = 0   on tag 01  (branch 1, trivial)
  - θ₂ = π/2 on tag 10  (branch 2)
";

  (* Create a datatype descriptor for W *)
  let w_datatype = datatype
    ~name:"W"
    ~arity:3
    ~labels:["sc"; "eval_false"; "eval_true"]
    ~ops:[]
  in

  (* Phases: -1 on branch 0, +1 on branch 1, +i on branch 2 *)
  let pi = Float.pi in
  let phases = [|
    Complex.polar 1.0 pi;       (* -1 = e^{iπ} *)
    Complex.one;                 (* +1 = e^{0} *)
    Complex.polar 1.0 (pi /. 2.0)  (* +i = e^{iπ/2} *)
  |] in

  let phase_w_nary = phased_control w_datatype phases one [| id one; id one; id one |] in

  print_endline "\n--- phased_control on W (3 branches, 2 tag qubits) ---\n";
  Printf.printf "phases = [-1, +1, +i] = [e^{iπ}, e^{0}, e^{iπ/2}]\n";
  Printf.printf "phase_w_nary = phased_control w_datatype phases one [id; id; id]\n\n";
  (match Bridge.compile_show (emit phase_w_nary) with
   | Bridge.CompileOk _ ->
       print_endline "\n  Expected gate pattern:";
       print_endline "    Branch 0 (tag=00, phase=π): X[0]; X[1]; CU1(1.0); X[1]; X[0]";
       print_endline "    Branch 1 (tag=01, phase=0): skipped (trivial phase +1)";
       print_endline "    Branch 2 (tag=10, phase=π/2): X[0]; CU1(0.5); X[0]"
   | Bridge.CompileError err ->
       Printf.printf "  ✗ FAILED: %s\n" err);

  (* ======================================================================= *)
  banner "PART 9: Semantic Verification (Unitary Equivalence)";

  print_endline "
Verifying key algebraic properties by comparing compiled unitaries:
";

  (* 1. toggle_W is an involution: toggle ; toggle = id *)
  let toggle_twice = seq0 toggle_w toggle_w in
  verify_eq "toggle_W ; toggle_W = id_W (involution)"
    (emit toggle_twice) (emit (id w_ty));

  (* 2. ctrl_W(id, id) = id_{Bool⊗W} (trivial control) *)
  let bw_ty = bool_ty ** w_ty in
  verify_eq "ctrl_W(id, id) = id_{Bool⊗W} (trivial control)"
    (emit ctrl_id_id) (emit (id bw_ty));

  (* 3. and_sc is an involution: and_sc ; and_sc = id *)
  let bbw_ty = bb_ty ** w_ty in
  verify_eq "and_sc ; and_sc = id (involution)"
    (emit and_sc_twice) (emit (id bbw_ty));

  (* 4. routeW^q is an involution: routeW^q ; routeW^q = id_{Bool⊗W}
        Left branch squared: (-1·toggle)² = (+1)·toggle² = id.
        Right branch squared: (+1·id)² = id. *)
  let bw_ty2 = bool_ty ** w_ty in
  let route_q_twice = seq0 route_w_q route_w_q in
  verify_eq "routeW^q ; routeW^q = id_{Bool⊗W} (phased involution)"
    (emit route_q_twice) (emit (id bw_ty2));

  (* 5. routeW_kickback = (-Z_{b1}) ⊗ id_W  (witness genuinely disentangled).
        This is the core semantic claim: the composition
          routeW^q ; ctrl_W(toggle_W, id_W)
        equals a pure phase on the Bool tag with no witness action.  *)
  let phase_only_ref = par0 phase_neg_z_on_bool (id w_ty) in
  verify_eq "routeW_kickback = (-Z_{b1}) ⊗ id_W (witness disentangled)"
    (emit route_w_kickback) (emit phase_only_ref);

  (* 6. routeW_kickback is an involution: (-Z)² = Z² = I, id² = id. *)
  let kickback_twice = seq0 route_w_kickback route_w_kickback in
  verify_eq "routeW_kickback ; routeW_kickback = id_{Bool⊗W} (kickback involution)"
    (emit kickback_twice) (emit (id bw_ty2));

  (* 7. and_sc_q ; and_sc_q = id (full involution at the quantum extension) *)
  let q_twice = seq0 and_sc_q and_sc_q in
  verify_eq "and_sc_q ; and_sc_q = id (full involution)"
    (emit q_twice) (emit (id bbw_ty));

  Printf.printf "\nVerification: %d/%d passed\n" !verifications_passed !verifications_run;

  (* ======================================================================= *)
  banner "SUMMARY";

  print_endline "
Demonstrated short-circuit conjunction in Linear DSL:

1. TYPE STRUCTURE
   Bool = I + I            (2-element, 1 qubit)
   W    = I + Bool         (3-element witness, 2 qubits)

2. STRUCTURAL (CLASSICAL) OPERATIONS
   toggle_W : W → W                            id_I ⊕ twist_Bool
   ctrl_W(M_0, M_1) : Bool ⊗ W → Bool ⊗ W     coherent control
   and_sc : (Bool ⊗ Bool) ⊗ W → ...            structural routing only

3. QUANTUM SHORT-CIRCUIT CONJUNCTION
   routeW^q : Bool ⊗ W → Bool ⊗ W       (raw phased route — entangles w with b1)
     dist_l⁻¹ ; ⊕-map( -1 · (id_I ⊗ toggle_W),
                        1 · (id_I ⊗ id_W) ) ; dist_l

   routeW_kickback : Bool ⊗ W → Bool ⊗ W  (phase-only, witness disentangled)
     routeW^q ; ctrl_W(toggle_W, id_W)
     Since toggle_W is an involution, the second application coherently undoes
     the witness modification, leaving  (-Z_{b1}) ⊗ id_W.

   and_sc_q : (Bool ⊗ Bool) ⊗ W → (Bool ⊗ Bool) ⊗ W
     route_in ; (routeW_kickback ⊗ id_Bool) ; route_out
     Same wiring as and_sc, routeW replaced by routeW_kickback.

Key insight: the phase-kickback pattern (phased branch action + unphased
inverse branch action) requires the branch action to be an involution.
When it is, the witness temporarily records the intermediate route, then
the inverse coherently removes that record — leaving a pure phase on the
control (b1) available for interference. A Hadamard on b1 turns this into
a measurable computational-basis outcome distinction between the
short-circuit and evaluation paths, with no residual entanglement.
";

  banner "DEMO COMPLETE";
  if !had_failure then exit 1
