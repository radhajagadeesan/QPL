(** QS_3 dummy-register simulator (Araújo–Costa–Brukner controlled-SWAP/ancilla
    construction) with control register directly encoding P_3 = ℂ[S_3].

    Type:
      qs3_sim : S3 ⊗ Regs  ⟶  S3 ⊗ Regs
      S3   = arity-8 datatype (3 tag qubits, balanced binary encoding);
             6 slots hold the S_3 permutations, 2 padding slots duplicate
             the |id⟩ branch so every tag basis state has a well-defined,
             consistent action (avoids `control`'s no-op-on-invalid-state
             behavior when arity is not a power of 2)
      Regs = Q ⊗ (Q ⊗ (Q ⊗ Q))   -- T ⊗ D_1 ⊗ D_2 ⊗ D_3, 4 qubits

    Total: 3 + 4 = 7 qubits.

    S_3 basis labelled by one-line notation π = (π(1), π(2), π(3)):
      | id      = (1, 2, 3)           | swap_23 = (1, 3, 2)
      | swap_12 = (2, 1, 3)           | cyc_123 = (2, 3, 1)
      | swap_13 = (3, 2, 1)           | cyc_132 = (3, 1, 2)

    Round k applies R(π(k)); F; R(π(k)), where R(c) coherently swaps T with
    D_c. R is built via `control` on the arity-6 S_3 datatype: at each of
    the 6 basis states of π, the branch performs the specific SWAP for π(k).
    Branch tables:
      Round 1  (extract π(1) per row) : [1, 2, 3, 1, 2, 3]
      Round 2  (extract π(2) per row) : [2, 1, 2, 3, 3, 1]
      Round 3  (extract π(3) per row) : [3, 3, 1, 2, 1, 2]

    `control` compiles the arity-6 dispatch via the datatype's balanced
    binary encoding on 3 tag qubits — a log-depth binary tree, not a
    linear cascade.

    F = id_T ⊗ (X on D_1) ⊗ (H on D_2) ⊗ (Z on D_3). All three chosen
    gates are involutions, so F² = I, giving round² = id.

    Verification. On every basis |π⟩ (all 6 states are valid — the whole
    control register IS P_3, no invalid states), the target ends with
    f_{π(3)} ∘ f_{π(2)} ∘ f_{π(1)} |ψ⟩ and dummies end unchanged
    (f_i² = I). We compare qs3_sim to a semantic reference qs3_ref that
    directly implements this via `control` on S_3 applied to the target,
    with identity on dummies — full 7-qubit unitary equality.

    Composition table (target unitary for each π):
      π = id       : Z·H·X          π = swap_23 : H·Z·X
      π = swap_12  : Z·X·H          π = cyc_123 : X·Z·H
      π = swap_13  : X·H·Z          π = cyc_132 : H·X·Z
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(* ========================================================================= *)
(* Types                                                                     *)
(* ========================================================================= *)

let dummies3_ty = q ** (q ** q)                 (* D_1 ⊗ (D_2 ⊗ D_3), 3 qubits *)
let regs_ty     = q ** dummies3_ty              (* T + 3 dummies, 4 qubits *)

(* Arity-6 datatype = S_3 directly. 6 summands ↔ 6 permutations of S_3. *)
(* Datatype: 6 real S_3 permutations padded to arity 8 with 2 identity-copy
   slots. arity-8 fits cleanly in 3 tag qubits with no invalid states, so
   `control`'s dispatch behavior agrees on the full 8-way tag basis. The
   padding slots duplicate the |id⟩ branch, so tag states 6 and 7 are
   semantically indistinguishable from |id⟩ — a "safe default". *)
let s3_datatype =
  datatype ~name:"S3padded" ~arity:8
    ~labels:["id"; "swap_12"; "swap_13"; "swap_23"; "cyc_123"; "cyc_132";
             "pad_id_a"; "pad_id_b"]
    ~ops:[]

let s3_ty = rep_ty s3_datatype

let _full_ty = s3_ty ** regs_ty

(* Target-only type (for the reference: control ⊗ target). *)
let _target_only_ty = s3_ty ** q

(* ========================================================================= *)
(* SWAP T with D_c on the 4-qubit register block                             *)
(* Built from structural twist_tensor + assoc primitives. Adjacent-swap      *)
(* chain (0,1)-(1,2)-(2,3)-(1,2)-(0,1) reaches SWAP(0,3), and analogous      *)
(* shorter chains reach SWAP(0,2), SWAP(0,1).                                 *)
(* ========================================================================= *)

(* SWAP(0, 1) on Regs = Q ⊗ (Q ⊗ (Q ⊗ Q)) *)
let swap_wires_0_1 =
  let d23 = q ** q in  (* D_2 ⊗ D_3 nested *)
  seq0 (assoc_tensor_r q q d23)
    (seq0 (par0 (twist_tensor q q) (id d23))
          (assoc_tensor_l q q d23))

(* SWAP(1, 2) on Regs — leaves T (wire 0) alone; swaps D_1 and D_2 *)
let swap_wires_1_2 =
  par0 (id q) (
    seq0 (assoc_tensor_r q q q)
      (seq0 (par0 (twist_tensor q q) (id q))
            (assoc_tensor_l q q q)))

(* SWAP(2, 3) on Regs — leaves T and D_1 alone; swaps D_2 and D_3 *)
let swap_wires_2_3 =
  par0 (id q) (par0 (id q) (twist_tensor q q))

(* SWAP(T, D_1) = SWAP(0, 1) *)
let swap_1 = swap_wires_0_1

(* SWAP(T, D_2) = SWAP(0,1); SWAP(1,2); SWAP(0,1) *)
let swap_2 =
  seq0 swap_wires_0_1 (seq0 swap_wires_1_2 swap_wires_0_1)

(* SWAP(T, D_3) = SWAP(0,1); SWAP(1,2); SWAP(2,3); SWAP(1,2); SWAP(0,1) *)
let swap_3 =
  seq0 swap_wires_0_1 (
  seq0 swap_wires_1_2 (
  seq0 swap_wires_2_3 (
  seq0 swap_wires_1_2 swap_wires_0_1)))

(* ========================================================================= *)
(* R_k(π) : coherent SWAP(T, D_{π(k)}) via `control` on S_3                  *)
(*                                                                            *)
(* Branch table per round k, indexed by permutation π:                        *)
(*   round 1: π(1) = [1, 2, 3, 1, 2, 3]                                       *)
(*   round 2: π(2) = [2, 1, 2, 3, 3, 1]                                       *)
(*   round 3: π(3) = [3, 3, 1, 2, 1, 2]                                       *)
(* Order of π: [id; swap_12; swap_13; swap_23; cyc_123; cyc_132]              *)
(* ========================================================================= *)

(* Branch tables padded to arity 8: the last 2 slots duplicate the |id⟩ branch's
   swap choice (swap_1 for round 1, swap_2 for round 2, swap_3 for round 3),
   so tag states 6 and 7 behave semantically like |id⟩. *)
let r_round_1 =
  control s3_datatype regs_ty
    [| swap_1; swap_2; swap_3; swap_1; swap_2; swap_3; swap_1; swap_1 |]

let r_round_2 =
  control s3_datatype regs_ty
    [| swap_2; swap_1; swap_2; swap_3; swap_3; swap_1; swap_2; swap_2 |]

let r_round_3 =
  control s3_datatype regs_ty
    [| swap_3; swap_3; swap_1; swap_2; swap_1; swap_2; swap_3; swap_3 |]

(* ========================================================================= *)
(* F : parallel apply of concrete f_1 = X, f_2 = H, f_3 = Z (T left alone)   *)
(* ========================================================================= *)

let f_op =
  par0 (id q) (par0 gate_x (par0 gate_h gate_z))
  (* Type: Q ⊗ (Q ⊗ (Q ⊗ Q)) → same. *)

(* ========================================================================= *)
(* round_k = R_k ; (id_S3 ⊗ F) ; R_k                                          *)
(* ========================================================================= *)

let make_round r =
  let id_d_and_F = par0 (id s3_ty) f_op in
  seq0 r (seq0 id_d_and_F r)

let round_1 = make_round r_round_1
let round_2 = make_round r_round_2
let round_3 = make_round r_round_3

(* ========================================================================= *)
(* Full qs3_sim = round_1 ; round_2 ; round_3                                *)
(* No inter-round routing: the S_3 control register threads through each     *)
(* round unchanged (coherent case preserves the tag), same layout each time. *)
(* ========================================================================= *)

let qs3_sim = seq0 round_1 (seq0 round_2 round_3)

(* ========================================================================= *)
(* Semantic reference qs3_ref: apply the composed target unitary per π,      *)
(* with identity on dummies. Since f² = I for X, H, Z, dummies stay put.     *)
(* ========================================================================= *)

(* Composed target unitary per permutation:
     π = id      : Z ∘ H ∘ X            (seq0-order: X then H then Z)
     π = swap_12 : Z ∘ X ∘ H            (H then X then Z)
     π = swap_13 : X ∘ H ∘ Z            (Z then H then X)
     π = swap_23 : H ∘ Z ∘ X            (X then Z then H)
     π = cyc_123 : X ∘ Z ∘ H            (H then Z then X)
     π = cyc_132 : H ∘ X ∘ Z            (Z then X then H) *)

let compose_seq gates =
  List.fold_left (fun acc g -> seq0 acc g) (id q) gates

let target_id      = compose_seq [gate_x; gate_h; gate_z]
let target_swap_12 = compose_seq [gate_h; gate_x; gate_z]
let target_swap_13 = compose_seq [gate_z; gate_h; gate_x]
let target_swap_23 = compose_seq [gate_x; gate_z; gate_h]
let target_cyc_123 = compose_seq [gate_h; gate_z; gate_x]
let target_cyc_132 = compose_seq [gate_z; gate_x; gate_h]

(* Coherently-controlled composed unitary on the target Q wire. *)
(* Padded to arity 8: last 2 slots duplicate target_id so tag states 6, 7
   behave like |id⟩, agreeing with the padding choice in R_1/R_2/R_3. *)
let target_only_ctrl =
  control s3_datatype q
    [| target_id; target_swap_12; target_swap_13;
       target_swap_23; target_cyc_123; target_cyc_132;
       target_id; target_id |]

(* qs3_ref lifts target_only_ctrl to the full (S_3 ⊗ Regs) layout by
   tensoring with identity on the 3 dummies. Layout: S_3 ⊗ (Q ⊗ (Q ⊗ Q ⊗ Q))
   = S_3 ⊗ Q ⊗ Q ⊗ Q ⊗ Q. We split off T from the dummies, apply the
   controlled unitary on (S_3, T), then reassemble.
*)
let qs3_ref =
  (* Input: s3_ty ⊗ (q ⊗ dummies3_ty)
     → (s3_ty ⊗ q) ⊗ dummies3_ty      [assoc_r]
     → apply (target_only_ctrl ⊗ id dummies3_ty)
     → back                            [assoc_l] *)
  let step1 = assoc_tensor_r s3_ty q dummies3_ty in
  let step2 = par0 target_only_ctrl (id dummies3_ty) in
  let step3 = assoc_tensor_l s3_ty q dummies3_ty in
  seq0 step1 (seq0 step2 step3)

(* ========================================================================= *)
(* Verification harness                                                       *)
(* ========================================================================= *)

let had_failure = ref false
let verifications_run = ref 0
let verifications_passed = ref 0

let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile term with
  | Bridge.CompileOk (_, sz) ->
      Printf.printf "  compiled successfully (gate count: %d)\n" sz
  | Bridge.CompileError err ->
      Printf.printf "  ✗ compile error: %s\n" err;
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
(* Demo                                                                       *)
(* ========================================================================= *)

let () =
  banner "QS_3 dummy-register simulator  (P_3 = ℂ[S_3] control, log-tree dispatch)";

  print_endline "";
  print_endline "  Control    P_3 = ℂ[S_3]   arity-8 padded datatype, 3 tag qubits";
  print_endline "             (6 real S_3 slots + 2 |id⟩ duplicates for power-of-2 arity)";
  print_endline "  Regs       T ⊗ D_1 ⊗ D_2 ⊗ D_3   4 qubits";
  print_endline "  Total      3 + 4 = 7 qubits";
  print_endline "";
  print_endline "  Six permutations of S_3 each occupy one summand:";
  print_endline "    id      : π = (1, 2, 3)    swap_23 : π = (1, 3, 2)";
  print_endline "    swap_12 : π = (2, 1, 3)    cyc_123 : π = (2, 3, 1)";
  print_endline "    swap_13 : π = (3, 2, 1)    cyc_132 : π = (3, 1, 2)";
  print_endline "";
  print_endline "  R_k(π)  = coherent SWAP(T, D_{π(k)}) via `control` on S_3";
  print_endline "           (dispatch via log-depth binary tree over 3 tag qubits)";
  print_endline "  F       = id_T ⊗ X on D_1 ⊗ H on D_2 ⊗ Z on D_3   (F² = I)";
  print_endline "  round_k = R_k ; (id_S3 ⊗ F) ; R_k                 (round_k² = id)";
  print_endline "  qs3_sim = round_1 ; round_2 ; round_3            (n = 3 rounds)";
  print_endline "";
  print_endline "  Total oracle calls: n² = 9  (each f_i applied n = 3 times).";
  print_endline "  Total circuit depth (algorithmic): n·log n = 3·log 6 ≈ 8.";

  banner "PART 1: Building blocks compile";

  compile_and_report "R_1(π) (control on S_3, log-tree over 3 tag qubits)" (emit r_round_1);
  compile_and_report "R_2(π)"                                                (emit r_round_2);
  compile_and_report "R_3(π)"                                                (emit r_round_3);
  compile_and_report "F  (id ⊗ X ⊗ H ⊗ Z)"                                   (emit f_op);
  compile_and_report "round_1 = R_1 ; F ; R_1"                               (emit round_1);
  compile_and_report "qs3_sim  (all three rounds)"                           (emit qs3_sim);
  compile_and_report "qs3_ref  (semantic reference: control-composed target)" (emit qs3_ref);

  banner "PART 2: Structural involutions";

  print_endline "";
  let br_ty = s3_ty ** regs_ty in
  verify_eq "R_1 ; R_1 = id  (branch-SWAP involution, round 1 table)"
    (emit (seq0 r_round_1 r_round_1)) (emit (id br_ty));
  verify_eq "R_2 ; R_2 = id"
    (emit (seq0 r_round_2 r_round_2)) (emit (id br_ty));
  verify_eq "R_3 ; R_3 = id"
    (emit (seq0 r_round_3 r_round_3)) (emit (id br_ty));
  verify_eq "round_1 ; round_1 = id  (uses F² = I from X² = H² = Z² = I)"
    (emit (seq0 round_1 round_1)) (emit (id br_ty));

  banner "PART 3: Clean-garbage lemma — qs3_sim = qs3_ref";

  print_endline "";
  print_endline "  The critical semantic claim: on every |π⟩ ∈ P_3, qs3_sim's action";
  print_endline "  on the target is f_{π(3)} ∘ f_{π(2)} ∘ f_{π(1)} and the dummies";
  print_endline "  return to their initial state (because f_i² = I here).";
  print_endline "  Equivalently: qs3_sim = qs3_ref where qs3_ref applies the composed";
  print_endline "  target unitary per π directly (via `control` on S_3), leaving dummies";
  print_endline "  untouched. Full 7-qubit unitary equality:";
  print_endline "";
  verify_eq "qs3_sim  =  qs3_ref  (clean-garbage lemma across all 6 permutations)"
    (emit qs3_sim) (emit qs3_ref);

  banner "SUMMARY";

  Printf.printf "\n  Verifications: %d/%d passed\n"
    !verifications_passed !verifications_run;
  print_endline "";
  print_endline "  QS_3 fixed-order simulator with P_3 = ℂ[S_3] as direct control,";
  print_endline "  Araújo–Costa–Brukner controlled-SWAP/ancilla construction.";
  print_endline "  6 summands = 6 permutations of S_3, dispatched by `control` via";
  print_endline "  log-depth binary tree on 3 tag qubits. Clean-garbage lemma verified";
  print_endline "  by full 7-qubit unitary equality against a target-only reference.";
  if !had_failure then exit 1
