(** Abstract QSwitch E2E Demo - Using Linear DSL Properly

    Full pipeline: OCaml Linear DSL -> Bridge -> Python compile -> Circuit

    This demonstrates the abstract QSwitch pattern using the PROPER Linear DSL:
    - QSwitch[f, g] : Bool ⊗ Q → Bool ⊗ Q
    - Built using dist_l, omap0, and undist_l
    - GADT-enforced linearity throughout
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(** Bool = I + I (the 2-element type) *)
let _bool_ty = one ++ one

(** I ⊗ Q type (payload in each branch after distribution) *)
let iq_ty = one ** q

(** QSwitch[f, g] : Bool ⊗ Q → Bool ⊗ Q

    Built properly using the Linear DSL structural isomorphisms:

    1. dist_l : (I+I) ⊗ Q → (I⊗Q) + (I⊗Q)
       Distribute tensor over sum

    2. omap0 : Apply different operations to each branch
       Left branch (ctrl=0):  I ⊗ Q → I ⊗ Q via id_I ⊗ (g ; f)
       Right branch (ctrl=1): I ⊗ Q → I ⊗ Q via id_I ⊗ (f ; g)

    3. undist_l : (I⊗Q) + (I⊗Q) → (I+I) ⊗ Q
       Undistribute back to Bool ⊗ Q

    Semantics:
      |0⟩ ⊗ |ψ⟩ → |0⟩ ⊗ f(g(|ψ⟩))   (apply g then f)
      |1⟩ ⊗ |ψ⟩ → |1⟩ ⊗ g(f(|ψ⟩))   (apply f then g)
*)
let qswitch
    (f : (unit, [`Lolli of [`Q] * [`Q]]) prog)
    (g : (unit, [`Lolli of [`Q] * [`Q]]) prog)
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * [`Q]]
                      * [`Tensor of [`Plus of [`One] * [`One]] * [`Q]]]) prog =

  (* Step 1: Distribute (I+I) ⊗ Q → (I⊗Q) + (I⊗Q) *)
  let distribute = dist_l one one q in

  (* Step 2: Build branches *)
  (* Left branch: when ctrl=0, apply g then f *)
  let left_branch = par0 (id one) (seq0 g f) in
  (* Right branch: when ctrl=1, apply f then g *)
  let right_branch = par0 (id one) (seq0 f g) in

  (* Step 3: Apply omap0 to create bifunctorial action on the sum *)
  let apply_branches = omap0 iq_ty iq_ty left_branch right_branch in

  (* Step 4: Undistribute (I⊗Q) + (I⊗Q) → (I+I) ⊗ Q *)
  let undistribute = undist_l one one q in

  (* Compose: dist ; omap ; undist *)
  seq0 distribute (seq0 apply_branches undistribute)


let () =
  (* Set project root for bridge.py *)
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  banner "ABSTRACT QSWITCH E2E DEMO (Linear DSL)";
  print_endline "\nFull pipeline: OCaml Linear DSL -> Bridge -> Python compile -> Circuit\n";

  (* =========================================================================
     PART 1: QSwitch Type Structure
     ========================================================================= *)
  banner "PART 1: QSwitch Type Structure";

  print_endline "
QSwitch[f, g] : Bool ⊗ Q → Bool ⊗ Q

where Bool = I + I (the 2-element sum type)

Structure:
  dist_l    : (I+I) ⊗ Q → (I⊗Q) + (I⊗Q)    [distribute]
  omap0     : Apply f⊕g bifunctorially       [branch operations]
  undist_l  : (I⊗Q) + (I⊗Q) → (I+I) ⊗ Q    [undistribute]

This is PURELY LINEAR DSL - no Bridge term hacking!
";

  (* =========================================================================
     PART 2: Build QSwitch[H, S]
     ========================================================================= *)
  banner "PART 2: QSwitch[H, S] - Full Linear DSL Construction";

  let qswitch_hs = qswitch gate_h gate_s in

  print_endline "
QSwitch[H, S] semantics:
  |0⟩ ⊗ |ψ⟩ → |0⟩ ⊗ H(S(|ψ⟩))   (apply S then H)
  |1⟩ ⊗ |ψ⟩ → |1⟩ ⊗ S(H(|ψ⟩))   (apply H then S)
";

  print_endline "Emitting to Bridge term...";
  let bridge_term = emit qswitch_hs in
  Printf.printf "\nBridge JSON:\n%s\n\n" (Bridge.term_to_json bridge_term);

  Printf.printf "Compiling via Python backend...\n";
  (match Bridge.compile bridge_term with
   | Bridge.CompileOk (perm, size) ->
       Printf.printf "\n✓ Compilation SUCCESS!\n";
       Printf.printf "  Circuit size: %d gates\n" size;
       Printf.printf "  Wire permutation: [%s]\n"
         (String.concat ", " (List.map string_of_int perm.new_to_old))
   | Bridge.CompileError err ->
       Printf.printf "\n✗ Compilation FAILED: %s\n" err);

  (* =========================================================================
     PART 3: Other Instantiations
     ========================================================================= *)
  banner "PART 3: Other QSwitch Instantiations";

  let compile_qswitch name f g =
    let qs = qswitch f g in
    let term = emit qs in
    Printf.printf "\n%s:\n" name;
    match Bridge.compile term with
    | Bridge.CompileOk (perm, size) ->
        Printf.printf "  ✓ Circuit size: %d gates\n" size;
        Printf.printf "    Permutation: [%s]\n"
          (String.concat ", " (List.map string_of_int perm.new_to_old))
    | Bridge.CompileError err ->
        Printf.printf "  ✗ FAILED: %s\n" err
  in

  compile_qswitch "QSwitch[H, X]" gate_h gate_x;
  compile_qswitch "QSwitch[S, Y]" gate_s gate_y;
  compile_qswitch "QSwitch[X, Z]" gate_x gate_z;

  (* Self-inverse case: f = g *)
  print_endline "\nSelf-inverse case (f = g):";
  compile_qswitch "QSwitch[H, H]" gate_h gate_h;
  compile_qswitch "QSwitch[S, S]" gate_s gate_s;

  (* =========================================================================
     PART 4: Show Individual Components
     ========================================================================= *)
  banner "PART 4: Linear DSL Components";

  print_endline "\nShowing that each component is a proper Linear DSL term:\n";

  let show_term name term =
    Printf.printf "%s:\n  %s\n\n" name (Bridge.term_to_json (emit term))
  in

  show_term "dist_l one one q" (dist_l one one q);
  show_term "undist_l one one q" (undist_l one one q);
  show_term "par0 (id one) gate_h" (par0 (id one) gate_h);
  show_term "omap0 iq iq (id_I⊗H) (id_I⊗S)"
    (omap0 iq_ty iq_ty (par0 (id one) gate_h) (par0 (id one) gate_s));

  (* =========================================================================
     PART 5: Composition of QSwitch
     ========================================================================= *)
  banner "PART 5: Composing QSwitch Operations";

  print_endline "\nQSwitch composes because it's a proper morphism Bool⊗Q → Bool⊗Q:\n";

  let qs1 = qswitch gate_h gate_s in
  let qs2 = qswitch gate_x gate_z in
  let composed = seq0 qs1 qs2 in

  Printf.printf "QSwitch[H,S] ; QSwitch[X,Z]:\n";
  (match Bridge.compile (emit composed) with
   | Bridge.CompileOk (_, size) ->
       Printf.printf "  ✓ Circuit size: %d gates\n" size
   | Bridge.CompileError err ->
       Printf.printf "  ✗ FAILED: %s\n" err);

  (* =========================================================================
     SUMMARY
     ========================================================================= *)
  banner "SUMMARY";

  print_endline "
This demo shows PROPER Linear DSL usage for QSwitch:

1. TYPE-SAFE CONSTRUCTION
   - qswitch : (Q→Q) → (Q→Q) → (Bool⊗Q → Bool⊗Q)
   - GADT-enforced linearity

2. STRUCTURAL ISOMORPHISMS
   - dist_l  : (A+B) ⊗ C → (A⊗C) + (B⊗C)
   - undist_l: (A⊗C) + (B⊗C) → (A+B) ⊗ C
   - Proper inverses!

3. BIFUNCTORIAL ACTION
   - omap0 : (A→C) → (B→D) → ((A+B) → (C+D))
   - Applies different operations per branch

4. COMPOSITIONALITY
   - QSwitch[f,g] ; QSwitch[h,k] composes naturally
   - Types ensure correctness

NO Bridge term hacking - this is the REAL Linear DSL!
";

  banner "DEMO COMPLETE"
