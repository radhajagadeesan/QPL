(* Vertical-slice validation of the Source frontend rewriter.

   The PPX is a SEMANTIC compiler component: the sealed GADT re-checks
   typing, linearity, context partitioning and the first-order sum
   restriction, but only these tests establish that the rewriter preserved
   the intended meaning.  Every concise program below is therefore compared
   against a HANDWRITTEN sealed-API oracle through the Python bridge's
   circuit-equality check, and its measured circuit facts are pinned. *)

open Qpl_surface
open Source

let failures = ref 0

let check name condition detail =
  if condition then Printf.printf "  PASS  %s\n%!" name
  else begin
    incr failures;
    Printf.printf "  FAIL  %s (%s)\n%!" name detail
  end

let show name term =
  match Bridge.compile_show term with
  | Bridge.CompileOk (perm, gates) ->
      Printf.printf "%s: gates=%d wires=%d perm=[%s]\n%!" name gates perm.n
        (String.concat ","
           (List.map string_of_int perm.Bridge.new_to_old));
      Some (perm, gates)
  | Bridge.CompileError e ->
      incr failures;
      Printf.printf "  FAIL  %s did not compile: %s\n%!" name e;
      None

let equal_circuits name a b =
  match Bridge.eq_circ a b with
  | Bridge.EqCircOk (eq, fidelity) ->
      check name (eq && fidelity > 0.999999)
        (Printf.sprintf "equal=%b fidelity=%f" eq fidelity)
  | Bridge.EqCircError e -> check name false e

let perm_is (perm : Bridge.wire_perm) expected =
  perm.Bridge.new_to_old = expected

(* ================================================================== *)
(* A. source_quickstart                                                *)
(* ================================================================== *)

(* concise, PPX-elaborated *)
let%source quickstart_sugar (p : (q, q) tensor) =
  let (l, r) = split p in
  (h l, s r)

(* handwritten sealed oracle (the committed demo construction) *)
let quickstart_oracle =
  lam ~name:"pair" (S.tensor q q) (S.tensor q q)
    { run_lam =
        fun pair_value ->
          let_tensor ~left_name:"left" ~right_name:"right"
            q q (use pair_value)
            { run_split =
                fun left right ->
                  pair
                    (Op.apply Op.h (use left))
                    (Op.apply Op.s (use right))
                    (UL (UR U0)) }
            (UL U0) }

(* ================================================================== *)
(* B. genuinely polymorphic qswitch                                    *)
(* ================================================================== *)

(* The witness convention is explicit and visible: one leading
   [(a : 'a P.t)] parameter per first-order type variable.  The body is
   the mandated shape. *)
let%source qswitch (a : 'a P.t)
    (f : ('a, 'a) lolli) (g : ('a, 'a) lolli) (p : (qbool, 'a) tensor) =
  let (b, x) = split p in
  case b
    ~zero:(f (g x))
    ~one_:(g (f x))

(* first-order specialization at q, same body with the gates in place *)
let%source qswitch_hs (p : (qbool, q) tensor) =
  let (b, x) = split p in
  case b
    ~zero:(h (s x))
    ~one_:(s (h x))

let qswitch_hs_oracle =
  lam ~name:"p" (S.tensor qbool q) (S.tensor qbool q)
    { run_lam =
        fun p ->
          let_tensor ~left_name:"b" ~right_name:"x" qbool q (use p)
            { run_split =
                fun b x ->
                  case_bool ~result:P.q ~scrutinee:(use b)
                    ~zero:(Op.apply Op.h (Op.apply Op.s (use x)))
                    ~one_:(Op.apply Op.s (Op.apply Op.h (use x)))
                    ~using:(UL (UR U0)) }
            (UL U0) }

(* ================================================================== *)
(* C. Datatype.Make selector: five labels, five operations, no GADT    *)
(*    vector constructors in user code                                  *)
(* ================================================================== *)

type z5 = E0 | E1 | E2 | E3 | E4 [@@source.datatype]

let z5_gate = Z5.select ~target:P.q [ Op.h; Op.s; Op.t; Op.x; Op.z ]

let%source selector_sugar (p : (Z5.t, q) tensor) = z5_gate p

module Z5_oracle =
  Datatype.Make
    (struct
      type tail = Datatype.n4
      let name = "z5"
      let labels =
        Datatype.("E0" @: "E1" @: "E2" @: "E3" @: "E4" @: VNil)
    end) ()

let z5_gate_oracle =
  Z5_oracle.select ~target:P.q
    Datatype.(Op.h @: Op.s @: Op.t @: Op.x @: Op.z @: VNil)

let selector_oracle =
  lam ~name:"p" (S.tensor Z5_oracle.s q) (S.tensor Z5_oracle.s q)
    { run_lam = fun p -> Op.apply z5_gate_oracle (use p) }

(* ================================================================== *)

let () =
  Printf.printf "== A. source_quickstart\n";
  (match show "quickstart_sugar" (emit quickstart_sugar) with
  | Some (perm, gates) ->
      check "quickstart facts" (gates = 2 && perm.n = 4
                                && perm_is perm [2; 3; 0; 1])
        "expected 4 qubits, 2 gates, perm [2,3,0,1]"
  | None -> ());
  equal_circuits "quickstart == handwritten oracle"
    (emit quickstart_sugar) (emit quickstart_oracle);

  Printf.printf "== B. polymorphic qswitch\n";
  (* the polymorphic abstraction typechecks and its q instance is a
     closed higher-order Source term that compiles *)
  (match show "qswitch (abstract, at q)" (emit (qswitch P.q)) with
  | Some _ -> ()
  | None -> ());
  (match show "qswitch_hs" (emit qswitch_hs) with
  | Some (perm, gates) ->
      check "qswitch_hs facts" (gates = 6 && perm.n = 4
                                && perm_is perm [2; 3; 0; 1])
        "expected 4 qubits, 6 gates, perm [2,3,0,1]"
  | None -> ());
  equal_circuits "qswitch_hs == handwritten oracle"
    (emit qswitch_hs) (emit qswitch_hs_oracle);

  Printf.printf "== C. five-way selector\n";
  check "Z5 arity" (Z5.arity = 5)
    (Printf.sprintf "arity=%d" Z5.arity);
  check "Z5 labels" (Z5.labels = [ "E0"; "E1"; "E2"; "E3"; "E4" ])
    (String.concat "," Z5.labels);
  (match show "selector_sugar" (emit selector_sugar) with
  | Some (perm, gates) ->
      check "selector facts" (gates = 25 && perm.n = 8
                              && perm_is perm [4; 5; 6; 7; 0; 1; 2; 3])
        "expected 8 qubits, 25 gates, perm [4,5,6,7,0,1,2,3]"
  | None -> ());
  equal_circuits "selector == handwritten oracle"
    (emit selector_sugar) (emit selector_oracle);

  if !failures = 0 then Printf.printf "ALL SLICE CHECKS PASSED\n%!"
  else begin
    Printf.printf "%d slice checks FAILED\n%!" !failures;
    exit 1
  end
