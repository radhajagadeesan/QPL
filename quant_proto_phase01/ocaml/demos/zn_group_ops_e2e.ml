(** Z_n Group Operations: actual unitary implementations of [add] and [neg].

    Builds the reversible Z_n group operations from existing structural
    primitives (TwistPlus, AssocPlus, omap0, control).

      add : Z_n ⊗ Z_n ⊸ Z_n ⊗ Z_n     (a, b) ↦ (a, a+b mod n)
      neg : Z_n      ⊸ Z_n            a     ↦ -a mod n

    Strategy
    --------
    - [shift_+1] : Z_n ⊸ Z_n  built from (n-2) AssocPlusR + TwistPlus + rebrackets.
    - [shift_+k] = (shift_+1)^k.
    - [neg]      : reflects 1..n-1; explicit for each n via omap0 + twist chains.
    - [add]      : [control z_n] dispatching shifts on the right register.

    Verified by composition identities (shift^n = id, add^n = id, neg^2 = id).
*)

open Qpl_surface
open Linear

let tests_run = ref 0
let tests_passed = ref 0

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

let verify name term1 term2 =
  incr tests_run;
  match Bridge.eq_circ term1 term2 with
  | Bridge.EqCircOk (true, f) ->
      Printf.printf "  ✓ %s (fidelity=%.6f)\n" name f;
      incr tests_passed
  | Bridge.EqCircOk (false, f) ->
      Printf.printf "  ✗ %s FAILED (fidelity=%.6f)\n" name f
  | Bridge.EqCircError err ->
      Printf.printf "  ✗ %s ERROR: %s\n" name err

(* ========================================================================= *)
(* Z_2                                                                        *)
(* ========================================================================= *)

let z2 = datatype ~name:"Z2" ~arity:2
  ~labels:["0"; "1"]
  ~ops:[("add", lolli (self **. self) (self **. self));
        ("neg", lolli self self)]

let z2_ty = one ++ one          (* Z_2 = I + I; 1 tag qubit *)

(** neg_z2 = id (since -1 ≡ 1 mod 2). *)
let neg_z2 = id z2_ty

(** shift_z2_+1 = twist_plus  (compiles to X on tag bit). *)
let shift_z2_plus1 = twist_plus one one

(** add_z2 = control z2 [id; X]  (compiles to CNOT on tag bits). *)
let add_z2 = control z2 z2_ty [| id z2_ty; shift_z2_plus1 |]


(* ========================================================================= *)
(* Z_3                                                                        *)
(* ========================================================================= *)

let z3 = datatype ~name:"Z3" ~arity:3
  ~labels:["0"; "1"; "2"]
  ~ops:[("add", lolli (self **. self) (self **. self));
        ("neg", lolli self self)]

let z3_ty = one ++ (one ++ one)

(** neg_z3 = swap 1 ↔ 2 (since -1 ≡ 2 mod 3). *)
let neg_z3 = omap0 one (one ++ one) (id one) (twist_plus one one)

(** shift_z3_+1: 0→1, 1→2, 2→0  via assoc_r + twist trick. *)
let shift_z3_plus1 =
  seq0 (assoc_plus_r one one one)
       (twist_plus (one ++ one) one)

let shift_z3_plus2 = seq0 shift_z3_plus1 shift_z3_plus1

let add_z3 =
  control z3 z3_ty [| id z3_ty; shift_z3_plus1; shift_z3_plus2 |]


(* ========================================================================= *)
(* Z_4                                                                        *)
(* ========================================================================= *)

let z4 = datatype ~name:"Z4" ~arity:4
  ~labels:["0"; "1"; "2"; "3"]
  ~ops:[("add", lolli (self **. self) (self **. self));
        ("neg", lolli self self)]

let z4_ty = one ++ (one ++ (one ++ one))   (* 2 tag qubits *)

(** shift_z4_+1: 0→1, 1→2, 2→3, 3→0.
    Generalized trick: (n-2)=2 AssocPlusR to fully left-associate, twist, then
    1 AssocPlusL via omap0 to restore right-associated shape. *)
let shift_z4_plus1 =
  seq0 (assoc_plus_r one one (one ++ one))
  (seq0 (assoc_plus_r (one ++ one) one one)
  (seq0 (twist_plus ((one ++ one) ++ one) one)
        (omap0 one ((one ++ one) ++ one)
          (id one)
          (assoc_plus_l one one one))))

let shift_z4_plus2 = seq0 shift_z4_plus1 shift_z4_plus1
let shift_z4_plus3 = seq0 shift_z4_plus2 shift_z4_plus1

(** neg_z4: 0↦0, 1↦3, 2↦2, 3↦1.
    Inner action on Z_3 = I+(I+I) is (1 3)(2)  [Z_4 positions]
    = (0 2)(1)  [as morphism on standalone Z_3]
    = (0 1)(1 2)(0 1)  [conjugate of (1 2) by (0 1)]. *)
let swap_1_2_on_z3 =   (* (0 1) on standalone Z_3 *)
  seq0 (assoc_plus_r one one one)
  (seq0 (omap0 (one ++ one) one (twist_plus one one) (id one))
        (assoc_plus_l one one one))

let swap_2_3_on_z3 =   (* (1 2) on standalone Z_3 *)
  omap0 one (one ++ one) (id one) (twist_plus one one)

let neg_z3_inner =     (* (0 2)(1) on standalone Z_3 = (1 3)(2) on Z_4's inner *)
  seq0 swap_1_2_on_z3 (seq0 swap_2_3_on_z3 swap_1_2_on_z3)

let neg_z4 =
  omap0 one (one ++ (one ++ one)) (id one) neg_z3_inner

let add_z4 =
  control z4 z4_ty
    [| id z4_ty; shift_z4_plus1; shift_z4_plus2; shift_z4_plus3 |]


(* ========================================================================= *)
(* Z_5                                                                        *)
(* ========================================================================= *)

let z5 = datatype ~name:"Z5" ~arity:5
  ~labels:["0"; "1"; "2"; "3"; "4"]
  ~ops:[("add", lolli (self **. self) (self **. self));
        ("neg", lolli self self)]

let z5_ty = one ++ (one ++ (one ++ (one ++ one)))

(** shift_z5_+1: 5-cycle. Same pattern: 3 assoc_plus_r ; 1 twist ; 2 inner assoc_plus_l. *)
let shift_z5_plus1 =
  seq0 (assoc_plus_r one one (one ++ (one ++ one)))
  (seq0 (assoc_plus_r (one ++ one) one (one ++ one))
  (seq0 (assoc_plus_r ((one ++ one) ++ one) one one)
  (seq0 (twist_plus (((one ++ one) ++ one) ++ one) one)
        (omap0 one (((one ++ one) ++ one) ++ one)
          (id one)
          (seq0 (assoc_plus_l (one ++ one) one one)
                (assoc_plus_l one one (one ++ one)))))))

let shift_z5_plus2 = seq0 shift_z5_plus1 shift_z5_plus1
let shift_z5_plus3 = seq0 shift_z5_plus2 shift_z5_plus1
let shift_z5_plus4 = seq0 shift_z5_plus3 shift_z5_plus1

(** neg_z5: 0↦0, 1↦4, 2↦3, 3↦2, 4↦1.
    Inner action on standalone Z_4: (0 3)(1 2).
    Build: shift_z4_+2 ; (0 1)-swap ; (2 3)-swap (verified algebraically). *)
let swap_0_1_on_z4 =
  seq0 (assoc_plus_r one one (one ++ one))
  (seq0 (omap0 (one ++ one) (one ++ one) (twist_plus one one) (id (one ++ one)))
        (assoc_plus_l one one (one ++ one)))

let swap_2_3_on_z4 =
  omap0 one (one ++ (one ++ one))
    (id one)
    (omap0 one (one ++ one) (id one) (twist_plus one one))

let neg_z4_perm_for_z5_inner =   (* (0 3)(1 2) on standalone Z_4 *)
  seq0 (seq0 shift_z4_plus2 swap_0_1_on_z4) swap_2_3_on_z4

let neg_z5 =
  omap0 one z4_ty (id one) neg_z4_perm_for_z5_inner

let add_z5 =
  control z5 z5_ty
    [| id z5_ty;
       shift_z5_plus1; shift_z5_plus2; shift_z5_plus3; shift_z5_plus4 |]


(* ========================================================================= *)
(* Z_8                                                                        *)
(* ========================================================================= *)

let z8 = datatype ~name:"Z8" ~arity:8
  ~labels:["0";"1";"2";"3";"4";"5";"6";"7"]
  ~ops:[("add", lolli (self **. self) (self **. self));
        ("neg", lolli self self)]

(* Right-associated Z_8. *)
let z8_ty = one ++ (one ++ (one ++ (one ++ (one ++ (one ++ (one ++ one))))))

(** shift_z8_+1: 8-cycle. 6 assoc_plus_r ; 1 twist ; 5 inner assoc_plus_l. *)
let shift_z8_plus1 =
  let z2 = one ++ one in
  let z3 = one ++ z2 in
  let z4 = one ++ z3 in
  let z5 = one ++ z4 in
  let z6 = one ++ z5 in
  let _ = z6 in
  let lassoc_2 = one ++ one in
  let lassoc_3 = lassoc_2 ++ one in
  let lassoc_4 = lassoc_3 ++ one in
  let lassoc_5 = lassoc_4 ++ one in
  let lassoc_6 = lassoc_5 ++ one in
  let lassoc_7 = lassoc_6 ++ one in
  seq0 (assoc_plus_r one one z6)         (* I+(I+z6) → (I+I)+z6                  *)
  (seq0 (assoc_plus_r lassoc_2 one z5)   (* (I+I)+(I+z5) → ((I+I)+I)+z5          *)
  (seq0 (assoc_plus_r lassoc_3 one z4)
  (seq0 (assoc_plus_r lassoc_4 one z3)
  (seq0 (assoc_plus_r lassoc_5 one z2)
  (seq0 (assoc_plus_r lassoc_6 one one)  (* lassoc_6+(I+I) → lassoc_7+I          *)
  (seq0 (twist_plus lassoc_7 one)        (* outer twist: lassoc_7+I → I+lassoc_7 *)
        (omap0 one lassoc_7
          (id one)
          (seq0 (assoc_plus_l lassoc_5 one one)
          (seq0 (assoc_plus_l lassoc_4 one z2)
          (seq0 (assoc_plus_l lassoc_3 one z3)
          (seq0 (assoc_plus_l lassoc_2 one z4)
                (assoc_plus_l one one z5))))))))))))

let shift_z8_plus2 = seq0 shift_z8_plus1 shift_z8_plus1
let shift_z8_plus3 = seq0 shift_z8_plus2 shift_z8_plus1
let shift_z8_plus4 = seq0 shift_z8_plus3 shift_z8_plus1
let shift_z8_plus5 = seq0 shift_z8_plus4 shift_z8_plus1
let shift_z8_plus6 = seq0 shift_z8_plus5 shift_z8_plus1
let shift_z8_plus7 = seq0 shift_z8_plus6 shift_z8_plus1

let add_z8 =
  control z8 z8_ty
    [| id z8_ty;
       shift_z8_plus1; shift_z8_plus2; shift_z8_plus3;
       shift_z8_plus4; shift_z8_plus5; shift_z8_plus6; shift_z8_plus7 |]

(** neg_z8: 0↦0, 1↦7, 2↦6, 3↦5, 4↦4, 5↦3, 6↦2, 7↦1.
    Implemented via [tag_perm] — basis-state permutation primitive
    compiled via pytket ToffoliBox. *)
let neg_z8 = tag_perm [| 0; 7; 6; 5; 4; 3; 2; 1 |] z8_ty


(* ========================================================================= *)
(* Z_11 (asymmetric n requiring 4 tag qubits)                                 *)
(* ========================================================================= *)

let z11 = datatype ~name:"Z11" ~arity:11
  ~labels:(List.init 11 string_of_int)
  ~ops:[("add", lolli (self **. self) (self **. self));
        ("neg", lolli self self)]

let z11_ty =
  let z2 = one ++ one in
  let z3 = one ++ z2 in
  let z4 = one ++ z3 in
  let z5 = one ++ z4 in
  let z6 = one ++ z5 in
  let z7 = one ++ z6 in
  let z8 = one ++ z7 in
  let z9 = one ++ z8 in
  let z10 = one ++ z9 in
  one ++ z10

(** shift_z11_+1: 11-cycle.  9 assoc_plus_r ; 1 twist ; 8 inner assoc_plus_l. *)
let shift_z11_plus1 =
  let z2 = one ++ one in
  let z3 = one ++ z2 in
  let z4 = one ++ z3 in
  let z5 = one ++ z4 in
  let z6 = one ++ z5 in
  let z7 = one ++ z6 in
  let z8 = one ++ z7 in
  let z9 = one ++ z8 in
  let _ = z9 in
  let lassoc_2 = one ++ one in
  let lassoc_3 = lassoc_2 ++ one in
  let lassoc_4 = lassoc_3 ++ one in
  let lassoc_5 = lassoc_4 ++ one in
  let lassoc_6 = lassoc_5 ++ one in
  let lassoc_7 = lassoc_6 ++ one in
  let lassoc_8 = lassoc_7 ++ one in
  let lassoc_9 = lassoc_8 ++ one in
  let lassoc_10 = lassoc_9 ++ one in
  seq0 (assoc_plus_r one one z9)
  (seq0 (assoc_plus_r lassoc_2 one z8)
  (seq0 (assoc_plus_r lassoc_3 one z7)
  (seq0 (assoc_plus_r lassoc_4 one z6)
  (seq0 (assoc_plus_r lassoc_5 one z5)
  (seq0 (assoc_plus_r lassoc_6 one z4)
  (seq0 (assoc_plus_r lassoc_7 one z3)
  (seq0 (assoc_plus_r lassoc_8 one z2)
  (seq0 (assoc_plus_r lassoc_9 one one)
  (seq0 (twist_plus lassoc_10 one)
        (omap0 one lassoc_10
          (id one)
          (seq0 (assoc_plus_l lassoc_8 one one)
          (seq0 (assoc_plus_l lassoc_7 one z2)
          (seq0 (assoc_plus_l lassoc_6 one z3)
          (seq0 (assoc_plus_l lassoc_5 one z4)
          (seq0 (assoc_plus_l lassoc_4 one z5)
          (seq0 (assoc_plus_l lassoc_3 one z6)
          (seq0 (assoc_plus_l lassoc_2 one z7)
                (assoc_plus_l one one z8))))))))))))))))))

let shift_z11_plus2  = seq0 shift_z11_plus1 shift_z11_plus1
let shift_z11_plus3  = seq0 shift_z11_plus2 shift_z11_plus1
let shift_z11_plus4  = seq0 shift_z11_plus3 shift_z11_plus1
let shift_z11_plus5  = seq0 shift_z11_plus4 shift_z11_plus1
let shift_z11_plus6  = seq0 shift_z11_plus5 shift_z11_plus1
let shift_z11_plus7  = seq0 shift_z11_plus6 shift_z11_plus1
let shift_z11_plus8  = seq0 shift_z11_plus7 shift_z11_plus1
let shift_z11_plus9  = seq0 shift_z11_plus8 shift_z11_plus1
let shift_z11_plus10 = seq0 shift_z11_plus9 shift_z11_plus1

let add_z11 =
  control z11 z11_ty
    [| id z11_ty;
       shift_z11_plus1;  shift_z11_plus2;  shift_z11_plus3;
       shift_z11_plus4;  shift_z11_plus5;  shift_z11_plus6;
       shift_z11_plus7;  shift_z11_plus8;  shift_z11_plus9;
       shift_z11_plus10 |]

(** neg_z11: 0↦0, i↦11-i for i ≥ 1.  Via [tag_perm]. *)
let neg_z11 = tag_perm
  [| 0; 10; 9; 8; 7; 6; 5; 4; 3; 2; 1 |]
  z11_ty


(* ========================================================================= *)
(* Demo and verification                                                      *)
(* ========================================================================= *)

let () =
  banner "Z_N GROUP OPERATIONS: verified implementations";

  (* ---------- Z_2 ---------- *)
  banner "Z_2";
  Printf.printf "  %s: arity=%d, 1 tag qubit\n" z2.name z2.arity;

  Printf.printf "\n  add_z2:\n";
  (match Bridge.compile_show (emit add_z2) with
   | Bridge.CompileOk _ -> () | Bridge.CompileError e -> Printf.printf "  %s\n" e);

  verify "add_z2 ∘ add_z2 = id  (Z_2: each elt is self-inverse)"
    (emit (seq0 add_z2 add_z2)) (emit (id (z2_ty ** z2_ty)));
  verify "neg_z2 = id" (emit neg_z2) (emit (id z2_ty));

  (* ---------- Z_3 ---------- *)
  banner "Z_3";
  Printf.printf "  %s: arity=%d, 2 tag qubits\n" z3.name z3.arity;

  Printf.printf "\n  add_z3:\n";
  (match Bridge.compile_show (emit add_z3) with
   | Bridge.CompileOk _ -> () | Bridge.CompileError e -> Printf.printf "  %s\n" e);

  verify "shift_z3_+1^3 = id"
    (emit (seq0 (seq0 shift_z3_plus1 shift_z3_plus1) shift_z3_plus1))
    (emit (id z3_ty));
  verify "shift_+1 ∘ shift_+2 = id" (emit (seq0 shift_z3_plus1 shift_z3_plus2))
    (emit (id z3_ty));
  verify "neg_z3 ∘ neg_z3 = id" (emit (seq0 neg_z3 neg_z3)) (emit (id z3_ty));
  verify "add_z3^3 = id  ((a,b)↦(a,a+b) iterated thrice)"
    (emit (seq0 (seq0 add_z3 add_z3) add_z3))
    (emit (id (z3_ty ** z3_ty)));

  (* ---------- Z_4 ---------- *)
  banner "Z_4";
  Printf.printf "  %s: arity=%d, 2 tag qubits\n" z4.name z4.arity;

  Printf.printf "\n  add_z4:\n";
  (match Bridge.compile_show (emit add_z4) with
   | Bridge.CompileOk _ -> () | Bridge.CompileError e -> Printf.printf "  %s\n" e);

  verify "shift_z4_+1^4 = id"
    (emit (seq0 (seq0 (seq0 shift_z4_plus1 shift_z4_plus1) shift_z4_plus1) shift_z4_plus1))
    (emit (id z4_ty));
  verify "shift_+1 ∘ shift_+3 = id" (emit (seq0 shift_z4_plus1 shift_z4_plus3))
    (emit (id z4_ty));
  verify "shift_+2 ∘ shift_+2 = id" (emit (seq0 shift_z4_plus2 shift_z4_plus2))
    (emit (id z4_ty));
  verify "neg_z4 ∘ neg_z4 = id  (1↔3 involution)"
    (emit (seq0 neg_z4 neg_z4)) (emit (id z4_ty));
  verify "add_z4^4 = id"
    (emit (seq0 (seq0 (seq0 add_z4 add_z4) add_z4) add_z4))
    (emit (id (z4_ty ** z4_ty)));

  (* ---------- Z_5 ---------- *)
  banner "Z_5";
  Printf.printf "  %s: arity=%d, 3 tag qubits\n" z5.name z5.arity;

  Printf.printf "\n  add_z5 (gates suppressed; many QControlBoxes):\n";
  (match Bridge.compile_show (emit add_z5) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError e -> Printf.printf "  %s\n" e);

  verify "shift_z5_+1^5 = id"
    (emit (seq0 (seq0 (seq0 (seq0 shift_z5_plus1 shift_z5_plus1) shift_z5_plus1)
                      shift_z5_plus1)
                shift_z5_plus1))
    (emit (id z5_ty));
  verify "shift_+1 ∘ shift_+4 = id" (emit (seq0 shift_z5_plus1 shift_z5_plus4))
    (emit (id z5_ty));
  verify "shift_+2 ∘ shift_+3 = id" (emit (seq0 shift_z5_plus2 shift_z5_plus3))
    (emit (id z5_ty));
  verify "neg_z5 ∘ neg_z5 = id"
    (emit (seq0 neg_z5 neg_z5)) (emit (id z5_ty));
  verify "add_z5^5 = id"
    (emit (seq0 (seq0 (seq0 (seq0 add_z5 add_z5) add_z5) add_z5) add_z5))
    (emit (id (z5_ty ** z5_ty)));

  (* ---------- Z_8 ---------- *)
  banner "Z_8";
  Printf.printf "  %s: arity=%d, 3 tag qubits\n" z8.name z8.arity;

  verify "shift_z8_+1^8 = id"
    (emit (seq0 (seq0 (seq0 (seq0
      (seq0 (seq0 (seq0 shift_z8_plus1 shift_z8_plus1) shift_z8_plus1)
            shift_z8_plus1)
      shift_z8_plus1) shift_z8_plus1) shift_z8_plus1) shift_z8_plus1))
    (emit (id z8_ty));
  verify "shift_+1 ∘ shift_+7 = id" (emit (seq0 shift_z8_plus1 shift_z8_plus7))
    (emit (id z8_ty));
  verify "shift_+2 ∘ shift_+6 = id" (emit (seq0 shift_z8_plus2 shift_z8_plus6))
    (emit (id z8_ty));
  verify "shift_+4 ∘ shift_+4 = id  (order 2)"
    (emit (seq0 shift_z8_plus4 shift_z8_plus4)) (emit (id z8_ty));
  verify "neg_z8 ∘ neg_z8 = id  (involution)"
    (emit (seq0 neg_z8 neg_z8)) (emit (id z8_ty));
  verify "add_z8^8 = id"
    (emit (seq0 (seq0 (seq0 (seq0
      (seq0 (seq0 (seq0 add_z8 add_z8) add_z8) add_z8)
      add_z8) add_z8) add_z8) add_z8))
    (emit (id (z8_ty ** z8_ty)));

  (* ---------- Z_11 (asymmetric n needing 4 tag qubits) ---------- *)
  banner "Z_11";
  Printf.printf "  %s: arity=%d, 4 tag qubits\n" z11.name z11.arity;
  Printf.printf "  Exercises k > 3 PlusMap (ToffoliBox path).\n";

  verify "shift_z11_+1^11 = id"
    (let rec compose n =
       if n = 1 then shift_z11_plus1
       else seq0 (compose (n-1)) shift_z11_plus1
     in emit (compose 11))
    (emit (id z11_ty));
  verify "shift_+1 ∘ shift_+10 = id"
    (emit (seq0 shift_z11_plus1 shift_z11_plus10)) (emit (id z11_ty));
  verify "shift_+5 ∘ shift_+6 = id"
    (emit (seq0 shift_z11_plus5 shift_z11_plus6)) (emit (id z11_ty));
  verify "shift_+3 ∘ shift_+8 = id"
    (emit (seq0 shift_z11_plus3 shift_z11_plus8)) (emit (id z11_ty));
  verify "neg_z11 ∘ neg_z11 = id"
    (emit (seq0 neg_z11 neg_z11)) (emit (id z11_ty));
  verify "add_z11^11 = id"
    (let rec compose n =
       if n = 1 then add_z11
       else seq0 (compose (n-1)) add_z11
     in emit (compose 11))
    (emit (id (z11_ty ** z11_ty)));

  banner "Summary";
  Printf.printf "\n  Tests: %d/%d passed\n" !tests_passed !tests_run;
  if !tests_passed = !tests_run then
    print_endline "\n  ALL TESTS PASSED"
  else begin
    Printf.printf "\n  %d TESTS FAILED\n" (!tests_run - !tests_passed);
    exit 1
  end;
  print_endline ""
