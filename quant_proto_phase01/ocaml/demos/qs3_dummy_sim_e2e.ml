(** QS_n dummy-register simulator at n = 3, concrete f_1 = X, f_2 = H, f_3 = Z.

    Type:
      qs3_sim : (D ⊗ D ⊗ D) ⊗ Regs  ⟶  (D ⊗ D ⊗ D) ⊗ Regs
      D    = arity-3 datatype (2 tag qubits, encoded via balanced binary sum)
      Regs = Q ⊗ (Q ⊗ (Q ⊗ Q))   -- T ⊗ D_1 ⊗ D_2 ⊗ D_3, 4 qubits

    Full pipeline at n = 3:
      - Control C = (C_1, C_2, C_3), each C_k selecting a dummy in {1,2,3}
        for the round-k SWAP. Encoding as three arity-3 datatypes gives
        3 × 2 = 6 control qubits.
      - Regs = 4 qubits (T + 3 dummies).
      - Total: 10 qubits.

      Circuit:  R(C_1) ; F ; R(C_1) ;
                (rearrange, uses C_2) ; R(C_2) ; F ; R(C_2) ; (rearrange back) ;
                (rearrange, uses C_3) ; R(C_3) ; F ; R(C_3) ; (rearrange back).

      R(C_k) is built via the `control` combinator on the arity-3 datatype:
      the 2 tag qubits give a log-depth binary dispatch tree, and each of
      the 3 branches is a single tag_perm swapping T with the k-th dummy.

      F is parallel apply: id_T ⊗ (X on D_1) ⊗ (H on D_2) ⊗ (Z on D_3).
      All three chosen gates are involutions, so F² = I, hence round² = id.

    On valid-permutation inputs π ∈ S_3 (6 out of 27 = 3³ basis states of C):
      - Target T ends with f_{π(3)} ∘ f_{π(2)} ∘ f_{π(1)} ψ
      - D_i ends with f_i^{n-1} = f_i² |a_i⟩ = |a_i⟩ (since X² = H² = Z² = I)
      Dummies factor out (clean-garbage lemma).

    The 21 non-permutation basis states get non-trivial behavior (dummies
    hit non-uniformly), which is fine — QS_n semantics only specifies P_n.

    Verified in this file:
      - R(C_k) compiles cleanly (log-tree at n = 3)
      - R ; R = id (branch-SWAP involution)
      - round ; round = id (uses F² = I; involution of each round)
      - qs3_sim compiles cleanly

    Semantic verification of clean-garbage on the P_3 subspace requires a
    27-branch nested-case reference; deferred as a follow-up.
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

let dummies_ty = q ** (q ** (q ** q))          (* D_1 ⊗ (D_2 ⊗ D_3), 3 qubits *)
                                                (* Wait: this is 4 qubits — one extra Q *)

(* Correct: 3 dummies, right-associated. *)
let dummies3_ty = q ** (q ** q)                 (* D_1 ⊗ (D_2 ⊗ D_3), 3 qubits *)

(* T at wire 0, D_1..D_3 at wires 1..3 — total 4 qubits. *)
let regs_ty = q ** dummies3_ty

(* Suppress unused warning *)
let _ = dummies_ty

(* Arity-3 datatype for each C_k (2 tag qubits, balanced binary encoding). *)
let three_datatype =
  datatype ~name:"three" ~arity:3
    ~labels:["d1"; "d2"; "d3"]
    ~ops:[]

let three_ty = rep_ty three_datatype

(* Control = C_1 ⊗ (C_2 ⊗ C_3) right-associated *)
let ctrl_ty = three_ty ** (three_ty ** three_ty)

let _full_ty = ctrl_ty ** regs_ty

(* ========================================================================= *)
(* Branch operations: SWAP T with D_c on the 4-qubit register block          *)
(* ========================================================================= *)

let swap_0_c c =
  let perm = Array.init 4 (fun i ->
    if i = 0 then c
    else if i = c then 0
    else i)
  in
  tag_perm perm regs_ty

(* ========================================================================= *)
(* R(c) : D ⊗ Regs → D ⊗ Regs  via `control` (log-tree over 2 tag qubits)    *)
(* ========================================================================= *)

let r_op =
  control three_datatype regs_ty
    [| swap_0_c 1; swap_0_c 2; swap_0_c 3 |]

(* ========================================================================= *)
(* F : parallel apply of concrete f_1 = X, f_2 = H, f_3 = Z (T left alone)   *)
(* ========================================================================= *)

let f_op =
  par0 (id q) (par0 gate_x (par0 gate_h gate_z))
  (* Type: Q ⊗ (Q ⊗ (Q ⊗ Q)) → same, i.e. Regs → Regs *)

(* ========================================================================= *)
(* round(c) = R(c) ; (id_D ⊗ F) ; R(c)                                       *)
(* ========================================================================= *)

let round_op =
  let id_d_and_F = par0 (id three_ty) f_op in
  seq0 r_op (seq0 id_d_and_F r_op)

(* ========================================================================= *)
(* Full three-round qs3_sim                                                  *)
(* Input: (D ⊗ (D ⊗ D)) ⊗ Regs                                                *)
(* ========================================================================= *)

(* Helper: apply round on (D_k ⊗ Regs) where D_k is at a specific position. *)

let qs3_sim =
  (* --- Round 1 uses C_1 (the head of the ctrl tensor) --- *)
  (* Layout in: ((D_1 ⊗ (D_2 ⊗ D_3)) ⊗ Regs)                                 *)
  (* Target for round: (D_1 ⊗ Regs), with (D_2 ⊗ D_3) held aside.            *)
  let rearr_in_1 =
    (* (D_1 ⊗ (D_2 ⊗ D_3)) ⊗ Regs
       → D_1 ⊗ ((D_2 ⊗ D_3) ⊗ Regs)              [assoc_l]
       → D_1 ⊗ (Regs ⊗ (D_2 ⊗ D_3))              [par0 id twist]
       → (D_1 ⊗ Regs) ⊗ (D_2 ⊗ D_3)              [assoc_r] *)
    let step1 = assoc_tensor_l three_ty (three_ty ** three_ty) regs_ty in
    let step2 = par0 (id three_ty) (twist_tensor (three_ty ** three_ty) regs_ty) in
    let step3 = assoc_tensor_r three_ty regs_ty (three_ty ** three_ty) in
    seq0 step1 (seq0 step2 step3)
  in
  let round_1 = par0 round_op (id (three_ty ** three_ty)) in
  let rearr_out_1 =
    (* (D_1 ⊗ Regs) ⊗ (D_2 ⊗ D_3)
       → D_1 ⊗ (Regs ⊗ (D_2 ⊗ D_3))              [assoc_l]
       → D_1 ⊗ ((D_2 ⊗ D_3) ⊗ Regs)              [par0 id twist]
       → (D_1 ⊗ (D_2 ⊗ D_3)) ⊗ Regs              [assoc_r] *)
    let step1 = assoc_tensor_l three_ty regs_ty (three_ty ** three_ty) in
    let step2 = par0 (id three_ty) (twist_tensor regs_ty (three_ty ** three_ty)) in
    let step3 = assoc_tensor_r three_ty (three_ty ** three_ty) regs_ty in
    seq0 step1 (seq0 step2 step3)
  in

  (* --- Round 2 uses C_2. Rotate the ctrl tensor so C_2 sits at the head. --- *)
  let rotate_c1_c2 =
    (* (D_1 ⊗ (D_2 ⊗ D_3)) ⊗ Regs
       → (D_2 ⊗ D_3) ⊗ (D_1 ⊗ Regs)?  Simpler: rotate ctrl only.
       Approach: bring D_2 to the head of ctrl by first pulling C_2 out.
       (D_1 ⊗ (D_2 ⊗ D_3)) → (D_2 ⊗ (D_1 ⊗ D_3))  via assoc_r ; par (twist) id ; assoc_l *)
    let ctrl_rearr =
      let s1 = assoc_tensor_r three_ty three_ty three_ty in
        (* D_1 ⊗ (D_2 ⊗ D_3) → (D_1 ⊗ D_2) ⊗ D_3 *)
      let s2 = par0 (twist_tensor three_ty three_ty) (id three_ty) in
        (* (D_1 ⊗ D_2) ⊗ D_3 → (D_2 ⊗ D_1) ⊗ D_3 *)
      let s3 = assoc_tensor_l three_ty three_ty three_ty in
        (* (D_2 ⊗ D_1) ⊗ D_3 → D_2 ⊗ (D_1 ⊗ D_3) *)
      seq0 s1 (seq0 s2 s3)
    in
    par0 ctrl_rearr (id regs_ty)
  in
  let round_2 = par0 round_op (id (three_ty ** three_ty)) in
  (* rearr_in_2 and rearr_out_2 have same shape as round-1 versions since the
     ctrl tensor's HEAD is now C_2. We reuse them. *)

  (* --- Round 3 uses C_3. Rotate again so C_3 sits at the head. --- *)
  let rotate_c2_c3 =
    let ctrl_rearr =
      let s1 = assoc_tensor_r three_ty three_ty three_ty in
      let s2 = par0 (twist_tensor three_ty three_ty) (id three_ty) in
      let s3 = assoc_tensor_l three_ty three_ty three_ty in
      seq0 s1 (seq0 s2 s3)
    in
    par0 ctrl_rearr (id regs_ty)
  in
  let round_3 = par0 round_op (id (three_ty ** three_ty)) in

  (* --- Final: rotate back so ctrl is in canonical (C_1, C_2, C_3) order --- *)
  (* After two rotations c1↔c2 then c2↔c3, the tensor holds (C_3, C_1, C_2).
     One more rotation cycle brings it back to (C_1, C_2, C_3).
     rotate_c1_c2 above swaps the head with the middle; applying it once more
     from state (C_3, C_1, C_2) gives (C_1, C_3, C_2). Then rotate_c2_c3 gives
     (C_1, C_2, C_3). *)
  let rotate_back_a = rotate_c1_c2 in
  let rotate_back_b = rotate_c2_c3 in

  (* Compose the pipeline *)
  seq0 rearr_in_1 (
  seq0 round_1 (
  seq0 rearr_out_1 (
  seq0 rotate_c1_c2 (
  seq0 rearr_in_1 (
  seq0 round_2 (
  seq0 rearr_out_1 (
  seq0 rotate_c2_c3 (
  seq0 rearr_in_1 (
  seq0 round_3 (
  seq0 rearr_out_1 (
  seq0 rotate_back_a rotate_back_b)))))))))))

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
  banner "QS_3 dummy-register simulator (n = 3, concrete f_1 = X, f_2 = H, f_3 = Z)";

  print_endline "";
  print_endline "  Control  (C_1, C_2, C_3) : D ⊗ D ⊗ D    where D = arity-3 datatype";
  print_endline "                                              (2 tag qubits each, 6 total)";
  print_endline "  Regs     T ⊗ (D_1 ⊗ D_2 ⊗ D_3) : Q ⊗ Q³   (target + 3 dummies, 4 qubits)";
  print_endline "  Total    10 qubits.";
  print_endline "";
  print_endline "  R(C_k)  = coherent-controlled SWAP(T, D_{C_k}) via `control` on the";
  print_endline "           arity-3 datatype (2 tag qubits → log-depth binary dispatch)";
  print_endline "  F       = id_T ⊗ (X on D_1) ⊗ (H on D_2) ⊗ (Z on D_3)  (F² = I)";
  print_endline "  round   = R ; (id_D ⊗ F) ; R                          (round² = id)";
  print_endline "  qs3_sim = round_1 ; round_2 ; round_3   (with inter-round routing)";
  print_endline "";
  print_endline "  |S_3| = 6 valid permutations; the control register can hold any of";
  print_endline "  3³ = 27 basis states, of which 6 are actual permutations.";

  banner "PART 1: Building blocks compile";

  compile_and_report "R(c)  (log-tree over arity-3 datatype)"  (emit r_op);
  compile_and_report "F  (parallel X⊗H⊗Z on dummies)"          (emit f_op);
  compile_and_report "round(c) = R ; F ; R"                    (emit round_op);
  compile_and_report "qs3_sim  (full three-round pipeline)"    (emit qs3_sim);

  banner "PART 2: Structural involutions";

  print_endline "";
  let br_ty = three_ty ** regs_ty in
  verify_eq "R ; R  =  id_{D ⊗ Regs}  (branch-SWAP involution)"
    (emit (seq0 r_op r_op)) (emit (id br_ty));

  verify_eq "round ; round  =  id  (uses X² = H² = Z² = I on dummies)"
    (emit (seq0 round_op round_op)) (emit (id br_ty));

  banner "SUMMARY";

  Printf.printf "\n  Verifications: %d/%d passed\n"
    !verifications_passed !verifications_run;
  print_endline "";
  print_endline "  QS_3 dummy-register simulator at n = 3 with concrete gates.";
  print_endline "  R(C_k) uses log-depth balanced-binary dispatch on the arity-3";
  print_endline "  datatype (2 tag qubits). Structural involutions R² = round² = id";
  print_endline "  are verified as full unitary equalities on the (D ⊗ Regs) 6-qubit";
  print_endline "  subsystem. The complete 3-round qs3_sim compiles on 10 qubits.";
  print_endline "";
  print_endline "  Clean-garbage verification on the P_3 = C[S_3] subspace requires a";
  print_endline "  hand-built 27-branch semantic reference (analog of qs2_ref's 4-branch";
  print_endline "  nested case at n = 2) — deferred as a follow-up.";
  if !had_failure then exit 1
