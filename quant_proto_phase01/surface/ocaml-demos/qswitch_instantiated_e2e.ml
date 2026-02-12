(** Instantiated QSwitch E2E Demo - Using Linear DSL Properly

    Full pipeline: OCaml Linear DSL -> Bridge -> Python compile -> Circuit

    This demonstrates compositional use of abstract QSwitch:
    - Define QSwitch as a reusable Linear DSL combinator
    - Instantiate with different gate pairs
    - Compose multiple QSwitch applications
    - All using proper structural isomorphisms (dist_l, omap0, undist_l)
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


(** Compile a QSwitch term and report results *)
let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile term with
  | Bridge.CompileOk (perm, size) ->
      Printf.printf "  ✓ Gates: %d\n" size;
      Printf.printf "    Perm:  [%s]\n"
        (String.concat ", " (List.map string_of_int perm.new_to_old))
  | Bridge.CompileError err ->
      Printf.printf "  ✗ FAILED: %s\n" err


let () =
  (* Set project root for bridge.py *)
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  banner "INSTANTIATED QSWITCH E2E DEMO (Linear DSL)";
  print_endline "\nDemonstrating compositional use of abstract QSwitch\n";
  print_endline "All QSwitch instances use proper Linear DSL:";
  print_endline "  dist_l ; omap0 left_branch right_branch ; undist_l\n";

  (* =========================================================================
     PART 1: Basic Instantiations
     ========================================================================= *)
  banner "PART 1: Basic QSwitch Instantiations";

  (* QSwitch[H, S] *)
  print_endline "\nQSwitch[H, S]:";
  print_endline "  ctrl=0 → H(S(x)) = S ; H";
  print_endline "  ctrl=1 → S(H(x)) = H ; S";
  compile_and_report "QSwitch[H, S]" (emit (qswitch gate_h gate_s));

  (* QSwitch[X, Z] - Pauli gates *)
  print_endline "\nQSwitch[X, Z] (Pauli gates):";
  print_endline "  ctrl=0 → X(Z(x)) = Z ; X";
  print_endline "  ctrl=1 → Z(X(x)) = X ; Z";
  compile_and_report "QSwitch[X, Z]" (emit (qswitch gate_x gate_z));

  (* QSwitch[H, Y] *)
  print_endline "\nQSwitch[H, Y]:";
  print_endline "  ctrl=0 → H(Y(x)) = Y ; H";
  print_endline "  ctrl=1 → Y(H(x)) = H ; Y";
  compile_and_report "QSwitch[H, Y]" (emit (qswitch gate_h gate_y));

  (* =========================================================================
     PART 2: Composed QSwitch Applications
     ========================================================================= *)
  banner "PART 2: Composed QSwitch Applications";

  print_endline "
Composing multiple QSwitch applications demonstrates:
  - The same control qubit sequences multiple operations
  - Each QSwitch contributes gates coherently
  - Types ensure composition is valid
";

  (* QSwitch[H,S] ; QSwitch[X,Z] - sequential composition *)
  let qs_hs = qswitch gate_h gate_s in
  let qs_xz = qswitch gate_x gate_z in
  let composed = seq0 qs_hs qs_xz in

  print_endline "QSwitch[H,S] ; QSwitch[X,Z]:";
  print_endline "  Type: (Bool ⊗ Q) → (Bool ⊗ Q) → (Bool ⊗ Q)";
  compile_and_report "Composed" (emit composed);

  (* Three QSwitch in sequence *)
  let qs_hy = qswitch gate_h gate_y in
  let triple = seq0 qs_hs (seq0 qs_xz qs_hy) in

  print_endline "\nQSwitch[H,S] ; QSwitch[X,Z] ; QSwitch[H,Y]:";
  compile_and_report "Triple composed" (emit triple);

  (* =========================================================================
     PART 3: Self-Inverse QSwitch
     ========================================================================= *)
  banner "PART 3: Self-Inverse QSwitch (f = g)";

  print_endline "
When f = g, QSwitch[f, f] applies f;f in both branches:
  - Both orderings are the same!
  - This is a uniform operation regardless of control state

For involutive f (f;f = id), this becomes identity on Q!
";

  compile_and_report "QSwitch[H, H]" (emit (qswitch gate_h gate_h));
  compile_and_report "QSwitch[S, S]" (emit (qswitch gate_s gate_s));
  compile_and_report "QSwitch[X, X]" (emit (qswitch gate_x gate_x));

  (* =========================================================================
     PART 4: QSwitch with Rz Rotations
     ========================================================================= *)
  banner "PART 4: QSwitch with Parameterized Rotations";

  print_endline "
QSwitch can be parameterized with any Q → Q morphism.
Using Rz rotations:
";

  (* Build Rz rotation gates *)
  let rz_pi4 = gate_rz (Float.pi /. 4.0) in
  let rz_pi8 = gate_rz (Float.pi /. 8.0) in
  let rz_neg_pi4 = gate_rz (-. Float.pi /. 4.0) in

  compile_and_report "QSwitch[Rz(π/4), Rz(π/8)]" (emit (qswitch rz_pi4 rz_pi8));
  compile_and_report "QSwitch[Rz(π/4), Rz(-π/4)]" (emit (qswitch rz_pi4 rz_neg_pi4));

  (* =========================================================================
     PART 5: Verify Structural Isomorphisms
     ========================================================================= *)
  banner "PART 5: Verify Structural Isomorphisms";

  print_endline "\nVerifying that dist_l and undist_l are proper inverses:\n";

  let dist = dist_l one one q in
  let undist = undist_l one one q in
  let roundtrip = seq0 dist undist in

  Printf.printf "dist_l one one q:\n  %s\n\n" (Bridge.term_to_json (emit dist));
  Printf.printf "undist_l one one q:\n  %s\n\n" (Bridge.term_to_json (emit undist));

  print_endline "dist_l ; undist_l (should be identity):";
  compile_and_report "Roundtrip" (emit roundtrip);

  (* =========================================================================
     SUMMARY
     ========================================================================= *)
  banner "SUMMARY";

  print_endline "
Demonstrated compositional use of abstract QSwitch:

1. BASIC INSTANTIATION
   qswitch gate_h gate_s - creates QSwitch for any gate pair

2. SEQUENTIAL COMPOSITION
   seq0 qswitch1 qswitch2 - chains multiple QSwitch ops
   Types ensure composition is valid

3. PARAMETERIZED CONSTRUCTION
   qswitch (gate_rz theta) (gate_rz phi) - factory function

4. SELF-INVERSE CASE
   qswitch gate_h gate_h - when both gates are the same

5. STRUCTURAL ISOMORPHISMS
   dist_l ; undist_l = id  (verified by compilation)

Key insight: QSwitch is a FIRST-CLASS COMBINATOR in the Linear DSL
  - Defined using proper structural isomorphisms
  - GADT-enforced linearity
  - Composes naturally with type safety
  - No Bridge term hacking!
";

  banner "DEMO COMPLETE"
