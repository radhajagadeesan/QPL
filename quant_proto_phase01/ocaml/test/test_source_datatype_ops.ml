(* Invariant tests for the datatype operation/elimination layer:
   certified label permutations, permutation involutions, and the
   exhaustive tag-preserving datatype case.

   Conventions pinned here:
   - the hidden representation is the canonical LEFT-associated expansion
     fixed by the clean calculus (narymonoidal.tex:
     bigplus_{i<=n} A_i := (bigplus_{i<n} A_i) ⊕ A_n), pinned
     STRUCTURALLY below through the serialized representation — an exact
     tree, which flattening cannot fake;
   - right-associated legacy oracles are related through the explicit
     certified sum associator, never silently retyped;
   - declaration order is the sole label/code authority;
   - permutations are FORWARD: position i carries the destination of
     constructor i, |i⟩ ↦ |p(i)⟩ (the 3-cycle test below fails under an
     inverse-convention implementation);
   - padding states of non-power-of-two arities stay fixed, checked both
     by a DIRECT single-application comparison against an explicit
     full-space reference and by cycle-order identities;
   - a non-involutive permutation is rejected by involution_permute;
   - two same-arity declarations remain nominally separate. *)

open Qpl_surface
open Source

let failures = ref 0

let check name condition detail =
  if condition then Printf.printf "  PASS  %s\n%!" name
  else begin
    incr failures;
    Printf.printf "  FAIL  %s (%s)\n%!" name detail
  end

let eq name a b =
  match Bridge.eq_circ a b with
  | Bridge.EqCircOk (equal, fidelity) ->
      check name (equal && fidelity > 0.999999)
        (Printf.sprintf "equal=%b fidelity=%f" equal fidelity)
  | Bridge.EqCircError e -> check name false e

let compiles name t =
  match Bridge.compile_show t with
  | Bridge.CompileOk (perm, gates) ->
      Printf.printf "  info  %s: wires=%d gates=%d\n%!" name
        perm.Bridge.n gates;
      check name true ""
  | Bridge.CompileError e -> check name false e

let rejects name expected thunk =
  match thunk () with
  | _ -> check name false "no exception"
  | exception Invalid_argument message ->
      let contains =
        let hl = String.length message and nl = String.length expected in
        let rec search at =
          nl = 0
          || (at + nl <= hl
              && (String.sub message at nl = expected || search (at + 1)))
        in
        search 0
      in
      check name contains message

(* ================================================================== *)
(* Declarations: arities 2, 3, 5, 8, 11, plus a nominal twin of R3     *)
(* ================================================================== *)

module R2 =
  Datatype.Make (struct
    type tail = Datatype.n1
    let name = "r2"
    let labels = Datatype.("A0" @: "A1" @: VNil)
  end) ()

module R3 =
  Datatype.Make (struct
    type tail = Datatype.n2
    let name = "r3"
    let labels = Datatype.("R0" @: "R1" @: "R2" @: VNil)
  end) ()

module R3twin =
  Datatype.Make (struct
    type tail = Datatype.n2
    let name = "r3twin"
    let labels = Datatype.("S0" @: "S1" @: "S2" @: VNil)
  end) ()

module R4 =
  Datatype.Make (struct
    type tail = Datatype.n3
    let name = "r4"
    let labels = Datatype.("D0" @: "D1" @: "D2" @: "D3" @: VNil)
  end) ()

module R5 =
  Datatype.Make (struct
    type tail = Datatype.n4
    let name = "r5"
    let labels = Datatype.("F0" @: "F1" @: "F2" @: "F3" @: "F4" @: VNil)
  end) ()

module R8 =
  Datatype.Make (struct
    type tail = Datatype.n7
    let name = "r8"
    let labels =
      Datatype.("G0" @: "G1" @: "G2" @: "G3" @: "G4" @: "G5" @: "G6"
                @: "G7" @: VNil)
  end) ()

module R11 =
  Datatype.Make (struct
    type tail = Datatype.n8 Datatype.succ Datatype.succ
    let name = "r11"
    let labels =
      Datatype.("K0" @: "K1" @: "K2" @: "K3" @: "K4" @: "K5" @: "K6"
                @: "K7" @: "K8" @: "K9" @: "K10" @: VNil)
  end) ()

(* Raw oracles copied from zn_group_ops_e2e.ml *)
let shift_z3_raw =
  Linear.(seq0 (assoc_plus_r one one one) (twist_plus (one ++ one) one))

let shift_z5_raw =
  Linear.(
    seq0 (assoc_plus_r one one (one ++ (one ++ one)))
      (seq0 (assoc_plus_r (one ++ one) one (one ++ one))
         (seq0 (assoc_plus_r ((one ++ one) ++ one) one one)
            (seq0 (twist_plus (((one ++ one) ++ one) ++ one) one)
               (omap0 one (((one ++ one) ++ one) ++ one)
                  (id one)
                  (seq0 (assoc_plus_l (one ++ one) one one)
                     (assoc_plus_l one one (one ++ one))))))))

(* certified sum associators: the raw oracles are right-associated *)
let lassoc3_ty = Linear.((one ++ one) ++ one)
let lassoc5_ty = Linear.((((one ++ one) ++ one) ++ one) ++ one)
let lassoc11_ty =
  Linear.(((((((((((one ++ one) ++ one) ++ one) ++ one) ++ one) ++ one)
              ++ one) ++ one) ++ one) ++ one))

let l2r3 = Linear.(assoc_plus_l one one one)
let r2l3 = Linear.(assoc_plus_r one one one)

let l2r5 =
  Linear.(
    seq0 (assoc_plus_l ((one ++ one) ++ one) one one)
      (seq0 (assoc_plus_l (one ++ one) one (one ++ one))
         (assoc_plus_l one one (one ++ (one ++ one)))))
let r2l5 =
  Linear.(
    seq0 (assoc_plus_r one one (one ++ (one ++ one)))
      (seq0 (assoc_plus_r (one ++ one) one (one ++ one))
         (assoc_plus_r ((one ++ one) ++ one) one one)))

let on_left l2r r2l m = Linear.(seq0 l2r (seq0 m r2l))

let value_of dom cod m =
  Linear.(emit_oterm
            (olam "p" dom cod (oapp (oembed m) (ovar "p" dom) (SRight SNil))))


(* forward vectors *)
let cyc3 = Datatype.(1 @: 2 @: 0 @: VNil)          (* 0→1, 1→2, 2→0 *)
let cyc3_sq = Datatype.(2 @: 0 @: 1 @: VNil)
let swap01_3 = Datatype.(1 @: 0 @: 2 @: VNil)
let id3 = Datatype.(0 @: 1 @: 2 @: VNil)
let cyc5 = Datatype.(1 @: 2 @: 3 @: 4 @: 0 @: VNil)
let cyc8 = Datatype.(1 @: 2 @: 3 @: 4 @: 5 @: 6 @: 7 @: 0 @: VNil)
let cyc11 =
  Datatype.(1 @: 2 @: 3 @: 4 @: 5 @: 6 @: 7 @: 8 @: 9 @: 10 @: 0 @: VNil)
let neg11 =
  Datatype.(0 @: 10 @: 9 @: 8 @: 7 @: 6 @: 5 @: 4 @: 3 @: 2 @: 1 @: VNil)
let swap2 = Datatype.(1 @: 0 @: VNil)

let seal_endo m = Op.value m
let idop d = Op.value (Op.id d)

let repeat_op n op0 =
  let rec loop k acc = if k = 0 then acc else loop (k - 1) (Op.compose acc op0) in
  loop (n - 1) op0

let () =
  Printf.printf "== forward convention and declaration order\n";
  (* the 3-cycle: forward |i⟩↦|i+1 mod 3⟩ must equal the raw right-assoc
     shift oracle; an inverse-convention implementation fails here *)
  eq "R3.permute [1;2;0] == raw shift_z3_+1 (forward pin, associator-related)"
    (emit (seal_endo (R3.permute cyc3)))
    (value_of lassoc3_ty lassoc3_ty (on_left l2r3 r2l3 shift_z3_raw));
  (* and it must NOT be self-inverse: its square is the other 3-cycle *)
  eq "R3.permute [1;2;0] squared == R3.permute [2;0;1]"
    (emit (seal_endo (Op.compose (R3.permute cyc3) (R3.permute cyc3))))
    (emit (seal_endo (R3.permute cyc3_sq)));
  eq "R3 identity permutation == certified id"
    (emit (seal_endo (R3.permute id3)))
    (emit (idop R3.s));

  Printf.printf "== arities 2, 3, 5, 8, 11 with padding pins\n";
  eq "R2 transposition == Op.not_bool analogue (1 wire)"
    (emit (seal_endo (R2.permute swap2)))
    (value_of Linear.(one ++ one) Linear.(one ++ one)
       Linear.(twist_plus one one));
  eq "R5 5-cycle == raw shift_z5_+1 (associator-related)"
    (emit (seal_endo (R5.permute cyc5)))
    (value_of lassoc5_ty lassoc5_ty (on_left l2r5 r2l5 shift_z5_raw));
  eq "R5 5-cycle to the 5th power == id (full 8-dim space, padding fixed)"
    (emit (seal_endo (repeat_op 5 (R5.permute cyc5))))
    (emit (idop R5.s));
  eq "R8 8-cycle to the 8th power == id"
    (emit (seal_endo (repeat_op 8 (R8.permute cyc8))))
    (emit (idop R8.s));
  eq "R11 11-cycle to the 11th power == id (16-dim space, padding fixed)"
    (emit (seal_endo (repeat_op 11 (R11.permute cyc11))))
    (emit (idop R11.s));
  eq "R11 negation squared == id"
    (emit (seal_endo (Op.compose (R11.permute neg11) (R11.permute neg11))))
    (emit (idop R11.s));

  Printf.printf "== structural representation pins (left association)\n";
  let unit_j = {|{"node": "Unit"}|} in
  let plus_j a b =
    Printf.sprintf {|{"node": "Plus", "left": %s, "right": %s}|} a b
  in
  let left3_j = plus_j (plus_j unit_j unit_j) unit_j in
  let right3_j = plus_j unit_j (plus_j unit_j unit_j) in
  let left4_j = plus_j left3_j unit_j in
  let contains hay needle =
    let hl = String.length hay and nl = String.length needle in
    let rec go at =
      nl = 0 || (at + nl <= hl && (String.sub hay at nl = needle || go (at + 1)))
    in
    go 0
  in
  let perm3_json =
    Bridge.term_to_json (emit (seal_endo (R3.permute id3)))
  in
  check "arity 3 permute carries exactly Plus(Plus(Unit,Unit),Unit)"
    (contains perm3_json left3_j) perm3_json;
  check "arity 3 permute carries no right-associated tree"
    (not (contains perm3_json right3_j)) perm3_json;
  let perm4_json =
    Bridge.term_to_json
      (emit (seal_endo (R4.permute Datatype.(0 @: 1 @: 2 @: 3 @: VNil))))
  in
  check "arity 4 permute carries exactly Plus(Plus(Plus(Unit,Unit),Unit),Unit)"
    (contains perm4_json left4_j) perm4_json;
  let select3_json =
    Bridge.term_to_json
      (emit (seal_endo
               (R3.select ~target:P.q Datatype.(Op.h @: Op.s @: Op.t @: VNil))))
  in
  check "arity 3 select dispatch carries the left-associated representation"
    (contains select3_json left3_j && not (contains select3_json right3_j))
    select3_json;

  Printf.printf "== direct padding pins (single application)\n";
  (* explicit full-space references: every valid label permuted exactly as
     requested AND every invalid physical code individually fixed *)
  eq "R5 5-cycle == explicit full 8-state reference (codes 5, 6, 7 fixed)"
    (emit (seal_endo (R5.permute cyc5)))
    (value_of lassoc5_ty lassoc5_ty
       (Linear.tag_perm [| 1; 2; 3; 4; 0; 5; 6; 7 |] lassoc5_ty));
  eq "R11 11-cycle == explicit full 16-state reference (codes 11..15 fixed)"
    (emit (seal_endo (R11.permute cyc11)))
    (value_of lassoc11_ty lassoc11_ty
       (Linear.tag_perm
          [| 1; 2; 3; 4; 5; 6; 7; 8; 9; 10; 0; 11; 12; 13; 14; 15 |]
          lassoc11_ty));

  Printf.printf "== involution certification\n";
  rejects "3-cycle rejected as involution" "not an involution"
    (fun () -> R3.involution_permute cyc3);
  rejects "out-of-range image rejected" "outside 0.."
    (fun () -> R3.permute Datatype.(1 @: 3 @: 0 @: VNil));
  rejects "repeated image rejected" "not a bijection"
    (fun () -> R3.permute Datatype.(1 @: 1 @: 0 @: VNil));
  eq "exp_i(pi/4, swap01 involution) squared == exp_i(pi/2, swap01)"
    (emit (seal_endo
             (Op.compose
                (Op.exp_i (Float.pi /. 4.0) (R3.involution_permute swap01_3))
                (Op.exp_i (Float.pi /. 4.0) (R3.involution_permute swap01_3)))))
    (emit (seal_endo
             (Op.exp_i (Float.pi /. 2.0) (R3.involution_permute swap01_3))));

  Printf.printf "== nominal separation\n";
  (* both declarations have arity 3, but their sealed types differ; the
     permutations still agree circuit-wise on the same representation *)
  check "R3 and R3twin are distinct declarations"
    (R3.name <> R3twin.name && R3.arity = R3twin.arity) "";
  eq "same-arity twins produce identical permutation circuits"
    (emit (seal_endo (R3.permute cyc3)))
    (emit (seal_endo (R3twin.permute Datatype.(1 @: 2 @: 0 @: VNil))));

  Printf.printf "== exhaustive tag-preserving datatype case\n";
  let match_hst =
    lam ~name:"d" (S.data R3.p) (S.lolli q (S.tensor (S.data R3.p) q))
      { run_lam =
          fun d ->
            lam ~name:"y" q (S.tensor (S.data R3.p) q)
              { run_lam =
                  fun y ->
                    R3.cases ~result:P.q ~scrutinee:(use d)
                      ~branches:
                        Datatype.(
                          Op.apply Op.h (use y)
                          @: Op.apply Op.s (use y)
                          @: Op.apply Op.t (use y)
                          @: VNil)
                      ~using:(UR (UL U0)) } }
  in
  compiles "cases over R3 with shared context" (emit match_hst);
  (let cases3_json = Bridge.term_to_json (emit match_hst) in
   check "arity 3 cases pipeline carries the left-associated representation"
     (contains cases3_json left3_j && not (contains cases3_json right3_j))
     "cases JSON");
  (* semantic oracle: the sealed select applied through an equally-curried
     wrapper (select itself is oracle-checked against the meta-level
     control in the counterpart harness) *)
  let select_curried =
    let gate = R3.select ~target:P.q Datatype.(Op.h @: Op.s @: Op.t @: VNil) in
    lam ~name:"d" (S.data R3.p) (S.lolli q (S.tensor (S.data R3.p) q))
      { run_lam =
          fun d ->
            lam ~name:"y" q (S.tensor (S.data R3.p) q)
              { run_lam =
                  fun y ->
                    Op.apply gate (pair (use d) (use y) (UR (UL U0))) } }
  in
  eq "cases [h; s; t] == select [h; s; t] (curried boundary)"
    (emit match_hst) (emit select_curried);

  if !failures = 0 then Printf.printf "ALL DATATYPE-OPS CHECKS PASSED\n%!"
  else begin
    Printf.printf "%d datatype-ops checks FAILED\n%!" !failures;
    exit 1
  end
