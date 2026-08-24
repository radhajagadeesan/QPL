(** Verify that the term
      let (f, x') = (qif x then X else I) in f x'
    elaborated as make_branch + case_hom is exactly CNOT.

    Two independent checks:
      (1) verify_ctrl_unitary against mathematical ground truth ctrl^1(X)
      (2) eq_circ against the standard `ctrl` combinator (from
          verify_nested_ctrl_e2e.ml) instantiated with gate_x.

    Also derives the truth table from the term semantics for pedagogy.

    ------------------------------------------------------------------------
    NOTE on higher-order qif — two readings, one sound, one unsound
    ------------------------------------------------------------------------

    The surface string  "let (f, x') = (qif x then X else I) in f x'"
    is genuinely ambiguous. Depending on the typing rule you adopt, it
    denotes either a well-defined CNOT (Reading A) or a physically
    impossible operation the type system should reject (Reading B).
    We spell both out and show which one this demo verifies.

    ------------------------
    READING A — Granthi-sound. The pair emerges from an AMBIENT WIRE.
    ------------------------

    Assumption: x : Bool  and  x' : Q  are two DISTINCT free variables
    owning disjoint wire slices. The 'qif' is sugar for a case_hom with
    a shared context Q that gets threaded through both branches and
    paired with the tag on the way out:

        qif x then X else I  ≡  make_branch + case_hom
                             :  Bool ⊗ Q  ⊸  Bool ⊗ Q

    The pair (f, x') is then a real tensor of independent components:
      f  is a wire bundle for the selected gate applied at x',
      x' is the (modified) ambient wire.
    Apply f(x') is a genuine CNOT with x = control, x' = target.
    Truth table:

        |0,0⟩ → |0,0⟩       |1,0⟩ → |1,1⟩
        |0,1⟩ → |0,1⟩       |1,1⟩ → |1,0⟩

    THIS is what qif_apply denotes in this demo. Checks 1 and 2 below
    verify against ctrl^1(X) and against the independent `ctrl` combinator.

    ------------------------
    READING B — the naïve rule (⋆) from the literature. UNSOUND.
    ------------------------

    A naïve typing rule promotes 'qif' to arbitrary result types A:

        Γ ⊢ M : qbit    Γ' ⊢ N1 : A    Γ' ⊢ N2 : A
        ─────────────────────────────────────────────    (⋆)
        Γ, Γ' ⊢ qif M then N1 else N2 : qbit ⊗ A

    Under (⋆), taking A = qbit ⊸ qbit gives the following typeable term:

        let x' ⊗ f : qbit ⊗ (qbit ⊸ qbit)
            = qif x then X else id
          in f(x')                                          (⋆⋆)

    Here 'qif' consumes x and returns the pair (x-renamed-to-x', selected-fn).
    There is no ambient wire — the qubit half of the pair IS the original
    control. When you then apply f(x'), the "function" is entangled with
    the "qubit", so this is CX with control = target:

        |0⟩ → id|0⟩ = |0⟩       |1⟩ → X|1⟩ = |0⟩

    Both basis states collapse to |0⟩. NOT unitary. The rule (⋆) is
    unsound whenever A is higher-order.

    ------------------------
    Why Reading B does not arise in Granthi (the type-system-level story)
    ------------------------

    IMPORTANT correction to an earlier version of this note: pure linearity
    alone does NOT forbid Reading B. In the syntactic term
    "let (x' ⊗ f) = case x of {L1 ↦ I | L0 ↦ X} in f x'", each variable
    (x, x', f) appears exactly once, so a plain linear discipline is
    satisfied. What actually prevents the pathology in Granthi is a
    stronger design choice visible in Table 1 of the formal development:

      ⊕ is a ROUTING INTERFACE, not a coproduct.

    Concretely (Table 1):
      ⊕-I    : Γ1 ⊢ V1 : A    Γ2 ⊢ V2 : B    ⊢ [V1 | V2] : A ⊕ B
      ⊕-Map  : Γ1 ⊢ f : A ⊸ C  Γ2 ⊢ g : B ⊸ D  ⊢ f ⊕ g : A ⊕ B ⊸ C ⊕ D

    The only sum-elimination rule is ⊕-Map, and it PRESERVES the sum in
    the codomain. There is no case-eliminator that collapses a coherent
    branch into a classically-selected function value — precisely the
    rule the paper's naïve (⋆) grants and Granthi denies.

    Structural repackaging via the quantum extension's dist/undist
    isomorphisms can wrap a sum inside a tensor as Bool ⊗ C, so the
    SHAPE of the reader's construction is reachable. But dist and undist
    are pure wire rearrangement: the tag qubit and the branch payload
    remain on physically distinct wires throughout. Consequently:

      - The destructured (x', f) sit on different physical qubits.
      - Apply f x' splices the tag qubit into f's input slot across
        distinct wires — a wire operation, not a same-qubit gate.
      - There is no control = target coincidence available at the
        wire level; the causal-loop that Reading B's (⋆⋆) exhibits
        under a coproduct-style case eliminator cannot arise here.

    OCaml Linear GADT surface:
      Reading A — expressible (this demo). Sound.
      Reading B — the linear GADT does not reject the syntactic shape by
                  itself (linearity is satisfied). What prevents the
                  pathology is the ⊕-as-routing-interface design above.
                  Any construction built from ⊕-Map + dist/undist keeps
                  the tag and payload on physically distinct wires, so
                  the destructured "function" and "qubit" never coincide
                  at the wire level.

    Python core (python/src/lang/terms.py):
      Reading A — expressible and correct.
      Reading B — ALSO expressible. Python's type_of checks widths and
                  domain/codomain but does NOT enforce linearity (see
                  CLAUDE.md 'Linearity Checking'). The following literal
                  transcription of the paper's (⋆⋆), using PlusMap +
                  UndistL for qif and LetPair + Apply for the body,

                    qif = Seq(PlusMap(Unit, Unit,
                                      Pair(Id(Unit), else_val),
                                      Pair(Id(Unit), then_val)),
                              UndistL(Unit, Unit, endo))
                    body = LetPair("x'", "f", Bool, endo,
                                   Seq(Var("x", Bool), qif),
                                   Apply(Var("f"), Var("x'")))
                    program = Lam("x", Bool, Bool, body)

                  with then_val = identity_Lam and else_val = X_Lam,
                  is accepted by assert_well_typed and compiled without
                  error. Empirically observed (see scratchpad
                  reader_qif_demo.py), the compiler produces:

                    3 qubits, 1 gate: SWAP q[0], q[2]
                    PlusMap(k=1): 0 left gates, 0 right gates

                  Both |0⟩ and |1⟩ inputs give P(visible=0) = 1.0. And
                  the "then I else X" circuit is byte-identical to the
                  "then I else I" (identity) circuit — the X branch is
                  SILENTLY DROPPED.

                  Root cause: PlusMap materializes branch operations as
                  gates coherently controlled by the tag qubit. When a
                  branch is a Lam VALUE, its internal gates live inside
                  the Lam's boundary; PlusMap sees 0 top-level gates and
                  lifts nothing. The higher-order case-value's semantics
                  vanish.

                  So on the Python side the pathology is actually WORSE
                  than the paper's (⋆⋆): rule (⋆⋆) denotes a
                  non-unitary control=target map, but Python compiles
                  to a circuit denoting NEITHER Reading A NOR the naïve
                  (⋆⋆) — just plumbing + ancilla, no meaningful
                  operation at all. Typecheck accepts; compilation
                  succeeds; the result has none of the intended
                  semantics. This is the exact miscompile mode CLAUDE.md
                  warns about under 'Linearity Checking (Python)'.

    Bottom line: the paper's warning targets a naïve typing rule (⋆) that
    provides a case eliminator producing 'qbit ⊗ A' from a coherent branch.
    Granthi's formal development does not have such a rule — ⊕ is a routing
    interface (Table 1), so the "classically-selected function value" that
    (⋆) depends on is not produced by any rule. Granthi's construction of
    Bool ⊗ endo via ⊕-Map + dist/undist is a wire-level rearrangement that
    keeps the tag and payload on distinct physical qubits, so the causal
    loop the paper flags does not manifest. The demo below verifies the
    canonical Reading A elaboration against the mathematical ctrl^1(X)
    ground truth with fidelity 1.0.
    ------------------------------------------------------------------------
*)

open Qpl_surface
open Linear

let bool_ty = one ++ one

(** The term under test: qif_apply : Bool ⊗ Q ⊸ Bool ⊗ Q *)
let qif_apply
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * [`Q]]
                      * [`Tensor of [`Plus of [`One] * [`One]] * [`Q]]]) prog =
  let else_branch = make_branch q one (id q)  in  (* tag = inl (false) : apply I *)
  let then_branch = make_branch q one gate_x in   (* tag = inr (true)  : apply X *)
  seq0
    (twist_tensor bool_ty q)
    (case_hom one one q q else_branch then_branch)

(** Reference ctrl combinator (copy of the one in verify_nested_ctrl_e2e.ml) *)
let ctrl (a_ty : 'a ty) (f : (unit, [`Lolli of 'a * 'a]) prog)
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * 'a]
                       * [`Tensor of [`Plus of [`One] * [`One]] * 'a]]) prog =
  let ia_ty = one ** a_ty in
  let distribute = dist_l one one a_ty in
  let left_branch  = id ia_ty in
  let right_branch = par0 (id one) f in
  let apply_branches = omap0 ia_ty ia_ty left_branch right_branch in
  let undistribute = undist_l one one a_ty in
  seq0 distribute (seq0 apply_branches undistribute)

(** X gate matrix: [[0,1],[1,0]] real, all-zero imag *)
let x_re = [[0.0; 1.0]; [1.0; 0.0]]
let x_im = [[0.0; 0.0]; [0.0; 0.0]]

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

let had_failure = ref false

let () =
  banner "QIF-AS-CNOT VERIFICATION";
  print_endline "";
  print_endline "  Term: let (f, x') = (qif x then X else I) in f x'";
  print_endline "  Elaborated: make_branch + case_hom (see qif_apply above)";
  print_endline "  Claim: this term is exactly CNOT with x as control, x' as target.";

  (* ---------------------------------------------------------------------- *)
  banner "CHECK 1: verify_ctrl_unitary against mathematical ctrl^1(X)";
  (match Bridge.verify_ctrl_unitary (emit qif_apply) x_re x_im 1 with
   | Bridge.EqCircOk (true, fid) ->
     Printf.printf "  PASS  qif_apply == ctrl^1(X)  fidelity=%.10f\n" fid
   | Bridge.EqCircOk (false, fid) ->
     Printf.printf "  FAIL  qif_apply != ctrl^1(X)  fidelity=%.10f\n" fid;
     had_failure := true
   | Bridge.EqCircError e ->
     Printf.printf "  ERROR: %s\n" e; had_failure := true);

  (* ---------------------------------------------------------------------- *)
  banner "CHECK 2: eq_circ against independent `ctrl gate_x` construction";
  let ref_cnot = ctrl q gate_x in
  (match Bridge.eq_circ (emit qif_apply) (emit ref_cnot) with
   | Bridge.EqCircOk (true, fid) ->
     Printf.printf "  PASS  qif_apply == ctrl q gate_x  fidelity=%.10f\n" fid
   | Bridge.EqCircOk (false, fid) ->
     Printf.printf "  FAIL  qif_apply != ctrl q gate_x  fidelity=%.10f\n" fid;
     had_failure := true
   | Bridge.EqCircError e ->
     Printf.printf "  ERROR: %s\n" e; had_failure := true);

  (* ---------------------------------------------------------------------- *)
  banner "TRUTH TABLE (derived from term semantics)";
  print_endline "";
  print_endline "  Notation: |x⟩ ⊗ |x'⟩ = |x, x'⟩   (x is the Bool tag; x' is Q)";
  print_endline "";
  print_endline "  |0, 0⟩ → case picks I  → I|0⟩ = |0⟩ → |0, 0⟩";
  print_endline "  |0, 1⟩ → case picks I  → I|1⟩ = |1⟩ → |0, 1⟩";
  print_endline "  |1, 0⟩ → case picks X  → X|0⟩ = |1⟩ → |1, 1⟩";
  print_endline "  |1, 1⟩ → case picks X  → X|1⟩ = |0⟩ → |1, 0⟩";
  print_endline "";
  print_endline "  That is the CNOT truth table with x = control, x' = target.";
  print_endline "  Check 1 above verified this via full 4x4 unitary equality";
  print_endline "  against the mathematically-constructed ctrl^1(X) matrix,";
  print_endline "  which covers every basis state (and every superposition).";

  banner "DONE";
  if !had_failure then exit 1
