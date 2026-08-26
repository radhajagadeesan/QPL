(** QS_n dummy-register simulator, concrete instance at n = 2, A = Q.

    Background. The pure higher-order n-quantum-switch has type

      QS_n :  P_n ⊗ ⨂_{i=1..n} (A ⊸ A)   ⟶   P_n ⊗ (A ⊸ A)

    where P_n = ℂ[S_n] is the coherent control over permutations, and
    the action is

      |π⟩ ⊗ (f_1, …, f_n)  ↦  |π⟩ ⊗ f_{π(n)} ∘ ⋯ ∘ f_{π(1)}.

    A FIXED-ORDER unitary simulator recovers this behavior using n²
    oracle calls and n dummy registers (Araújo–Costa–Brukner Appendix C,
    Taddei et al. Appendix A.2). Encode π as C = (C_1, …, C_n) with
    C_k = π(k). With target register T ≃ A and one dummy D_i ≃ A per f_i,
    define

      R(c)  =  Σ_i |i⟩⟨i|_c ⊗ SWAP_{T, D_i}
      F     =  I_T ⊗ f_1^{D_1} ⊗ ⋯ ⊗ f_n^{D_n}

    and

      QSn_sim  =  ∏_{k=1..n} (R(C_k) F R(C_k))     : P_n ⊗ T ⊗ ⨂ D_i  ⟶  …

    Trace-through gives, for every π ∈ S_n,

      |π⟩|ψ⟩_T ⨂_i |a_i⟩_{D_i}
        ↦ |π⟩ · (f_{π(n)} ⋯ f_{π(1)} |ψ⟩)_T  ⊗  ⨂_i (f_i^{n-1} |a_i⟩)_{D_i}.

    The dummies pick up f_i^{n-1} INDEPENDENT of π — this is the
    "clean-garbage" argument: dummies factor out as a π-independent
    tensor factor. A superposition of permutations is preserved exactly.

    Why this fits the sums-only-at-base-type restriction.
    -----------------------------------------------------
    The higher-order type QS_n : P_n ⊗ ⨂(A⊸A) → P_n ⊗ (A⊸A) has a
    function-typed OUTPUT. The dummy-register simulator is a natural
    η-expansion of that output: the target argument is pulled to the
    outside as an explicit A wire, and the return is an A wire (no
    function type in the output). The n dummies are the state
    accompanying that η-expansion.

    In the fully-abstract formulation with the f_i as function values,
    the simulator has type

      QSn_sim,η : P_n ⊗ (A ⊸ A)^{⊗ n²} ⊗ A ⊗ (⨂ A)  ⟶  P_n ⊗ A ⊗ (⨂ A)

    which is η-expanded on the target and takes each f_i as n separate
    function value slots (one per round — linearity forbids reuse). No
    sum type in this signature carries a Lolli, so the first-order
    sum-payload restriction is satisfied.

    This demo. n = 2, A = Q. To keep the term first-order end-to-end
    without any oapp/olam plumbing, we bake in concrete f_1 = X and
    f_2 = H. The signature becomes

      qs2_sim_concrete :
        (Bool ⊗ Bool) ⊗ (Q ⊗ (Q ⊗ Q))  ⟶  (Bool ⊗ Bool) ⊗ (Q ⊗ (Q ⊗ Q))

    encoding the control register as two Bools (C_1, C_2) and the
    register block as T ⊗ D_1 ⊗ D_2. The full-parametric form is a
    straightforward η-expansion following the pattern in
    qswitch_eta_endoQ_e2e.ml: replace the concrete gate_x / gate_h at
    the four F sites with oapp of function values bound in an outer
    olam context. All the routing (R, F, round, two-round composition)
    is identical to the concrete version below.

    Round bookkeeping (n = 2, C_k = 1 encoded as Bool inl, C_k = 2 as inr):
      π = id   ↔  C = (1, 2) ↔ (inl, inr) ↔ raw bits (0, 1)
      π = swap ↔  C = (2, 1) ↔ (inr, inl) ↔ raw bits (1, 0)
      Non-permutation basis states (0,0) and (1,1) compile to identity
      (since f_i² = X² = H² = I on the doubly-hit dummy — a coincidence
      of this particular choice of gates; not a general property).
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

let bool_ty  = one ++ one                       (* control bit *)
let regs_ty  = q ** (q ** q)                    (* T ⊗ (D_1 ⊗ D_2), 3 qubits *)
let ctrl_ty  = bool_ty ** bool_ty               (* (C_1, C_2), 2 tag qubits *)
let _full_ty = ctrl_ty ** regs_ty               (* full pipeline i/o *)

(* ========================================================================= *)
(* SWAP helpers (structural wire permutations on Regs = Q ⊗ (Q ⊗ Q))         *)
(* ========================================================================= *)

(** swap_T_D1 : swap the first two Q wires (T ↔ D_1).
    Regs → Regs, i.e. Q ⊗ (Q ⊗ Q) → Q ⊗ (Q ⊗ Q). *)
let swap_T_D1 =
  seq0 (assoc_tensor_r q q q)                       (* Q⊗(Q⊗Q) → (Q⊗Q)⊗Q  *)
    (seq0 (par0 (twist_tensor q q) (id q))          (* value swap of first pair *)
          (assoc_tensor_l q q q))                    (* back to Q⊗(Q⊗Q) *)

(** swap_T_D2 : swap the first and third Q wires (T ↔ D_2).
    Q ⊗ (Q ⊗ Q) → Q ⊗ (Q ⊗ Q).
    Achieved via three adjacent swaps: (D_1 ↔ D_2) ; (T ↔ D_1) ; (D_1 ↔ D_2). *)
let swap_T_D2 =
  let s12 = par0 (id q) (twist_tensor q q) in        (* swap D_1 and D_2 *)
  seq0 s12
    (seq0 swap_T_D1                                  (* swap T (pos 0) and D_2 (now pos 1) *)
          s12)                                        (* swap D_1 back into place *)

(* ========================================================================= *)
(* R(c) : coherent controlled-SWAP of T with D_c                             *)
(* ========================================================================= *)

(** R : Bool ⊗ Regs → Bool ⊗ Regs.

    case c of
      | inl (c=0) → SWAP(T, D_1) on Regs, tag preserved
      | inr (c=1) → SWAP(T, D_2) on Regs, tag preserved

    Uses case_hom which materializes the SWAP body to real SWAP gates
    (3 CNOTs each) before controlling by the tag, giving genuine
    coherent-controlled-SWAPs. *)
let r_op =
  (* case_hom expects G ⊗ (A ⊕ B), so twist Bool ⊗ Regs → Regs ⊗ Bool first. *)
  let branch_L =
    seq0 (par0 swap_T_D1 (id one))                   (* Regs ⊗ one → Regs ⊗ one *)
         (twist_tensor regs_ty one)                   (* Regs ⊗ one → one ⊗ Regs *)
  in
  let branch_R =
    seq0 (par0 swap_T_D2 (id one))
         (twist_tensor regs_ty one)
  in
  seq0 (twist_tensor bool_ty regs_ty)                 (* Bool ⊗ Regs → Regs ⊗ Bool *)
       (case_hom one one regs_ty regs_ty branch_L branch_R)
       (* result: (one ⊕ one) ⊗ Regs = Bool ⊗ Regs ✓ *)

(* ========================================================================= *)
(* F : parallel apply of concrete f_1 = X and f_2 = H (leaves T alone)        *)
(* ========================================================================= *)

(** F : Regs → Regs
      id_T ⊗ (X on D_1) ⊗ (H on D_2)
*)
let f_op =
  par0 (id q) (par0 gate_x gate_h)

(* ========================================================================= *)
(* One round: round(c) = R(c) ; (id_Bool ⊗ F) ; R(c)                         *)
(* ========================================================================= *)

let round_op =
  let id_bool_and_F = par0 (id bool_ty) f_op in
  seq0 r_op (seq0 id_bool_and_F r_op)

(* ========================================================================= *)
(* Two-round composition: qs2_sim on (Bool ⊗ Bool) ⊗ Regs                    *)
(* ========================================================================= *)

(** qs2_sim : (Bool ⊗ Bool) ⊗ Regs → (Bool ⊗ Bool) ⊗ Regs

    Round 1 uses C_1, round 2 uses C_2. Between rounds we swap which
    control bit is adjacent to Regs, then swap back at the end. All
    inter-round routing is structural (wire permutations, 0 gates). *)
let qs2_sim =
  (* Rearrange 1: (Bool ⊗ Bool) ⊗ Regs → (Bool_c1 ⊗ Regs) ⊗ Bool_c2 *)
  let rearr_1 =
    seq0 (assoc_tensor_l bool_ty bool_ty regs_ty)
      (seq0 (par0 (id bool_ty) (twist_tensor bool_ty regs_ty))
            (assoc_tensor_r bool_ty regs_ty bool_ty))
  in

  (* Apply round on (Bool_c1 ⊗ Regs), leave Bool_c2 alone *)
  let round_1 = par0 round_op (id bool_ty) in

  (* Rearrange 2: (Bool_c1 ⊗ Regs) ⊗ Bool_c2 → (Bool_c2 ⊗ Regs) ⊗ Bool_c1 *)
  let rearr_2 =
    seq0 (twist_tensor (bool_ty ** regs_ty) bool_ty)   (* → Bool_c2 ⊗ (Bool_c1 ⊗ Regs) *)
      (seq0 (par0 (id bool_ty) (twist_tensor bool_ty regs_ty))
                                                       (* → Bool_c2 ⊗ (Regs ⊗ Bool_c1) *)
            (assoc_tensor_r bool_ty regs_ty bool_ty))  (* → (Bool_c2 ⊗ Regs) ⊗ Bool_c1 *)
  in

  (* Apply round on (Bool_c2 ⊗ Regs), leave Bool_c1 alone *)
  let round_2 = par0 round_op (id bool_ty) in

  (* Rearrange 3: (Bool_c2 ⊗ Regs) ⊗ Bool_c1 → (Bool_c1 ⊗ Bool_c2) ⊗ Regs *)
  let rearr_3 =
    seq0 (assoc_tensor_l bool_ty regs_ty bool_ty)      (* → Bool_c2 ⊗ (Regs ⊗ Bool_c1) *)
      (seq0 (par0 (id bool_ty) (twist_tensor regs_ty bool_ty))
                                                       (* → Bool_c2 ⊗ (Bool_c1 ⊗ Regs) *)
        (seq0 (assoc_tensor_r bool_ty bool_ty regs_ty) (* → (Bool_c2 ⊗ Bool_c1) ⊗ Regs *)
              (par0 (twist_tensor bool_ty bool_ty) (id regs_ty))))
                                                       (* → (Bool_c1 ⊗ Bool_c2) ⊗ Regs *)
  in

  seq0 rearr_1 (seq0 round_1 (seq0 rearr_2 (seq0 round_2 rearr_3)))

(* ========================================================================= *)
(* Verification harness                                                      *)
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
(* Reference for the clean-garbage lemma at n = 2, f_1 = X, f_2 = H          *)
(* ========================================================================= *)

(** qs2_ref : the semantically-specified 5-qubit unitary that qs2_sim should
    equal on ALL basis inputs (P_n and non-P_n alike, since f_i² = I here).

      (c_1, c_2) = (0, 0): identity on Regs             (both rounds swap T↔D_1;
                                                          F is applied twice with X² = I)
      (c_1, c_2) = (0, 1): π = id     — target ← f_2 f_1 = H·X;  D_1 ← f_1 = X,  D_2 ← f_2 = H
      (c_1, c_2) = (1, 0): π = swap   — target ← f_1 f_2 = X·H;  D_1 ← X,        D_2 ← H
      (c_1, c_2) = (1, 1): identity on Regs             (H² = X² = I)

    Built as a nested case_hom on the two control bits. Both non-permutation
    branches are identity; the two permutation branches implement the
    "target composition + constant dummy transformation", which IS the
    clean-garbage claim as an equation of unitaries. *)

(* Base ops on Regs used inside the branches: *)
let regs_apply_HX_X_H =            (* H·X on T,  X on D_1,  H on D_2 *)
  par0 (seq0 gate_x gate_h) (par0 gate_x gate_h)

let regs_apply_XH_X_H =            (* X·H on T,  X on D_1,  H on D_2 *)
  par0 (seq0 gate_h gate_x) (par0 gate_x gate_h)

(** Inner case on c_2, given a "hit" branch and a "miss" (identity) branch,
    both of type Regs → Regs. Returns a closed Bool ⊗ Regs → Bool ⊗ Regs. *)
let inner_case_c2 ~zero_branch ~one_branch =
  let mk_branch body =
    seq0 (par0 body (id one))                        (* Regs ⊗ one → Regs ⊗ one *)
         (twist_tensor regs_ty one)                   (* Regs ⊗ one → one ⊗ Regs *)
  in
  seq0 (twist_tensor bool_ty regs_ty)
       (case_hom one one regs_ty regs_ty
          (mk_branch zero_branch)
          (mk_branch one_branch))

(** Reference for qs2_sim. Nested case on (c_1, c_2). *)
let qs2_ref =
  (* Outer case on c_1. G = Bool_c2 ⊗ Regs. A = B = one. C = Regs.
     Input: (Bool_c2 ⊗ Regs) ⊗ Bool_c1  (after rearranging (c1,c2)⊗R).
     Output: Bool_c1 ⊗ Regs.  Then rearrange to (Bool_c1 ⊗ Bool_c2) ⊗ Regs. *)

  (* c_1 = 0 branch: run inner case on c_2 with (id, H·X-X-H) *)
  let c1_zero =
    let inner = inner_case_c2
        ~zero_branch:(id regs_ty)          (* (c_1, c_2) = (0, 0): identity *)
        ~one_branch:regs_apply_HX_X_H      (* (c_1, c_2) = (0, 1): π = id *)
    in
    (* Adapt inner (Bool_c2 ⊗ Regs → Bool_c2 ⊗ Regs) to the branch signature
       (Bool_c2 ⊗ Regs) ⊗ one → one ⊗ (Bool_c2 ⊗ Regs) *)
    seq0 (par0 inner (id one))
         (twist_tensor (bool_ty ** regs_ty) one)
  in

  (* c_1 = 1 branch: run inner case on c_2 with (X·H-X-H, id) *)
  let c1_one =
    let inner = inner_case_c2
        ~zero_branch:regs_apply_XH_X_H     (* (c_1, c_2) = (1, 0): π = swap *)
        ~one_branch:(id regs_ty)           (* (c_1, c_2) = (1, 1): identity *)
    in
    seq0 (par0 inner (id one))
         (twist_tensor (bool_ty ** regs_ty) one)
  in

  (* Outer case_hom on c_1:
       input  (Bool_c2 ⊗ Regs) ⊗ Bool_c1
       output  Bool_c1 ⊗ (Bool_c2 ⊗ Regs) *)
  let outer_case =
    case_hom one one (bool_ty ** regs_ty) (bool_ty ** regs_ty)
      c1_zero c1_one
  in

  (* Wrap: (Bool ⊗ Bool) ⊗ Regs → (Bool_c2 ⊗ Regs) ⊗ Bool_c1 → Bool_c1 ⊗ (Bool_c2 ⊗ Regs)
                              → (Bool_c1 ⊗ Bool_c2) ⊗ Regs *)
  let rearr_in =
    (* (Bool_c1 ⊗ Bool_c2) ⊗ Regs → Bool_c1 ⊗ (Bool_c2 ⊗ Regs) → (Bool_c2 ⊗ Regs) ⊗ Bool_c1 *)
    seq0 (assoc_tensor_l bool_ty bool_ty regs_ty)
         (twist_tensor bool_ty (bool_ty ** regs_ty))
  in
  let rearr_out =
    (* Bool_c1 ⊗ (Bool_c2 ⊗ Regs) → (Bool_c1 ⊗ Bool_c2) ⊗ Regs *)
    assoc_tensor_r bool_ty bool_ty regs_ty
  in
  seq0 rearr_in (seq0 outer_case rearr_out)

(* ========================================================================= *)
(* Demo                                                                      *)
(* ========================================================================= *)

let () =
  banner "QS_n DUMMY-REGISTER SIMULATOR  (concrete n = 2, A = Q)";

  print_endline "\nBuilds the fixed-order dummy-register simulator of QS_n at n = 2,";
  print_endline "concrete f_1 = X, f_2 = H. Type:";
  print_endline "  (Bool ⊗ Bool) ⊗ (Q ⊗ (Q ⊗ Q))  ⟶  (Bool ⊗ Bool) ⊗ (Q ⊗ (Q ⊗ Q))";
  print_endline "";
  print_endline "  Control  (C_1, C_2) : Bool ⊗ Bool     (2 tag qubits)";
  print_endline "  Regs     T ⊗ (D_1 ⊗ D_2) : Q ⊗ (Q⊗Q)  (target + 2 dummies, 3 qubits)";
  print_endline "  Total    5 qubits.";
  print_endline "";
  print_endline "  Circuit: R(C_1) ; F ; R(C_1) ; R(C_2) ; F ; R(C_2)";
  print_endline "  with routing rearrangements between rounds (0-gate wire perms).";
  print_endline "  R(c) is a coherent controlled-SWAP of T with D_c (via case_hom).";
  print_endline "  F applies X to D_1 and H to D_2 in parallel (leaves T alone).";

  banner "PART 1: Structural building blocks compile";

  compile_and_report "swap_T_D1  (structural wire perm)"    (emit swap_T_D1);
  compile_and_report "swap_T_D2  (structural wire perm)"    (emit swap_T_D2);
  compile_and_report "R(c)  (coherent controlled-SWAP)"     (emit r_op);
  compile_and_report "F  (parallel X⊗H on dummies)"         (emit f_op);
  compile_and_report "round(c)  = R(c) ; F ; R(c)"          (emit round_op);
  compile_and_report "qs2_sim  (full two-round pipeline)"   (emit qs2_sim);

  banner "PART 2: Structural involutions";

  print_endline "";
  verify_eq "R ; R  =  id_{Bool ⊗ Regs}  (controlled-SWAP squared)"
    (emit (seq0 r_op r_op)) (emit (id (bool_ty ** regs_ty)));

  verify_eq "round ; round  =  id  (each round is an involution: X² = H² = I)"
    (emit (seq0 round_op round_op)) (emit (id (bool_ty ** regs_ty)));

  banner "PART 3: Clean-garbage lemma (dummies factor out)";

  print_endline "\nThe defining semantic claim of the dummy-register construction:";
  print_endline "on every basis (c_1, c_2), the dummies pick up f_i^{n-1} independent";
  print_endline "of π. For n = 2, f_1 = X, f_2 = H:";
  print_endline "";
  print_endline "  (c_1, c_2) = (0, 0):  identity on Regs   (X² = H² = I on doubly-hit)";
  print_endline "  (c_1, c_2) = (0, 1):  target ← H·X ψ,   D_1 ← X a_1,  D_2 ← H a_2";
  print_endline "  (c_1, c_2) = (1, 0):  target ← X·H ψ,   D_1 ← X a_1,  D_2 ← H a_2";
  print_endline "  (c_1, c_2) = (1, 1):  identity on Regs";
  print_endline "";
  print_endline "  qs2_ref encodes this specification as a nested case on (c_1, c_2).";
  print_endline "  If the dummies genuinely factor out (i.e., they carry no π-dependent";
  print_endline "  information), qs2_sim MUST equal qs2_ref as a full 5-qubit unitary.";
  print_endline "";
  compile_and_report "qs2_ref  (nested-case specification)" (emit qs2_ref);
  verify_eq "qs2_sim  =  qs2_ref  (clean-garbage lemma; π-independent dummies)"
    (emit qs2_sim) (emit qs2_ref);

  banner "SUMMARY";

  Printf.printf "\n  Verifications: %d/%d passed\n"
    !verifications_passed !verifications_run;
  print_endline "";
  print_endline "Demonstrated: the QS_2 higher-order n-switch is faithfully";
  print_endline "simulated by a first-order dummy-register circuit with n² = 4";
  print_endline "oracle calls. Under η-expansion of the target, the whole term";
  print_endline "is first-order (no sum type carries a function payload), so the";
  print_endline "soundness restriction is respected. The dummies genuinely factor";
  print_endline "out — proved as a unitary equality between the operational";
  print_endline "circuit (qs2_sim) and the semantic reference (qs2_ref).";
  print_endline "";
  print_endline "The fully-parametric form (each f_i as an abstract function value)";
  print_endline "is obtained by wrapping qs2_sim's shape in an outer olam over four";
  print_endline "(Q ⊸ Q) function slots and replacing each concrete gate site with";
  print_endline "an oapp of the corresponding slot. See qswitch_eta_endoQ_e2e.ml";
  print_endline "for the destructuring / split-witness pattern.";
  if !had_failure then exit 1
