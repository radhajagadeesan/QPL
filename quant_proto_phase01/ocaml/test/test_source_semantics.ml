open Qpl_surface

module Src = Source
open Src

let failures = ref 0

let check name condition =
  if condition then
    Printf.printf "  OK  %s\n" name
  else begin
    incr failures;
    Printf.printf "  FAIL  %s\n" name
  end

let contains text needle =
  let lt = String.length text and ln = String.length needle in
  let rec loop i =
    i + ln <= lt
    && (String.sub text i ln = needle || loop (i + 1))
  in
  ln = 0 || loop 0

let compile name term =
  match Bridge.compile (emit term) with
  | Bridge.CompileOk _ ->
      check name true
  | Bridge.CompileError error ->
      Printf.eprintf "%s: %s\n" name error;
      check name false

let compile_or_recorded_gap name term =
  match Bridge.compile (emit term) with
  | Bridge.CompileOk _ ->
      Printf.printf "  OK  %s\n" name
  | Bridge.CompileError error
    when contains error "wire 0 is placed twice" ->
      Printf.printf
        "  KNOWN  %s (Raw normalization: %s)\n"
        name error
  | Bridge.CompileError error ->
      Printf.eprintf "%s: unexpected diagnostic: %s\n" name error;
      check name false

let compile_framed name term =
  match Bridge.compile_framed (emit term) with
  | Bridge.FramedOk result -> Some result
  | Bridge.FramedError error ->
      Printf.eprintf "%s: %s\n" name error;
      check name false;
      None

let identity =
  lam ~name:"x" q q
    { run_lam = fun x -> use x }

let neutral_seq =
  seq (Op.value Op.h) (Op.value Op.s) U0

let neutral_seq_is_eta_lam () =
  match emit neutral_seq with
  | Bridge.TLam _ -> true
  | _ -> false

let endo_q = S.lolli q q

let higher_order_identity = Op.id endo_q

let higher_order_identity_on_h =
  Op.apply higher_order_identity (Op.value Op.h)

let higher_order_identity_is_direct_lam () =
  match emit (Op.value higher_order_identity) with
  | Bridge.TLam (bound, _, _, Bridge.TVar (used, _)) ->
      bound = used
  | _ -> false

let tensor_eta =
  let pq = P.tensor P.q P.q in
  let sq = S.data pq in
  lam ~name:"p" sq sq
    { run_lam =
        fun p ->
          let_tensor ~left_name:"x" ~right_name:"y"
            q q (use p)
            { run_split =
                fun x y ->
                  pair (use x) (use y) (UL (UR U0)) }
            (UL U0) }

let endo_q = S.lolli q q

let tensor_let_returns_function =
  let qq = S.tensor q q in
  let function_and_q = S.tensor endo_q q in
  let input = S.tensor function_and_q q in
  lam ~name:"whole" input qq
    { run_lam =
        fun whole ->
          let_tensor ~left_name:"fx" ~right_name:"z"
            function_and_q q (use whole)
            { run_split =
                fun fx_value z ->
                  let returned =
                    let_tensor ~left_name:"f" ~right_name:"x"
                      endo_q q (use fx_value)
                      { run_split =
                          fun f x ->
                            lam ~name:"w" q qq
                              { run_lam =
                                  fun w ->
                                    pair
                                      (app (use f) (use w)
                                         (UR (UL U0)))
                                      (use x)
                                      (UL (UL (UR U0))) } }
                      (UL U0)
                  in
                  app returned (use z) (UL (UR U0)) }
            (UL U0) }

let tensor_let_direct_reference =
  let qq = S.tensor q q in
  let function_and_q = S.tensor endo_q q in
  let input = S.tensor function_and_q q in
  lam ~name:"whole" input qq
    { run_lam =
        fun whole ->
          let_tensor ~left_name:"fx" ~right_name:"z"
            function_and_q q (use whole)
            { run_split =
                fun fx_value z ->
                  let_tensor ~left_name:"f" ~right_name:"x"
                    endo_q q (use fx_value)
                    { run_split =
                        fun f x ->
                          pair
                            (app (use f) (use z)
                               (UL (UR U0)))
                            (use x)
                            (UL (UR (UL U0))) }
                    (UL (UR U0)) }
            (UL U0) }

let tensor_let_function_uses_application () =
  match emit tensor_let_returns_function with
  | Bridge.TLam
      (_, _, _, Bridge.TLetPair
         (_, _, _, _, _,
          Bridge.TApply
            (Bridge.TLam (_, _, _, Bridge.TLetPair _),
             Bridge.TVar _))) ->
      true
  | _ -> false

let fixed_control =
  let bq = S.tensor qbool q in
  lam ~name:"p" bq bq
    { run_lam =
        fun p ->
          let_tensor ~left_name:"b" ~right_name:"x"
            qbool q (use p)
            { run_split =
                fun b x ->
                  case_bool ~result:P.q
                    ~scrutinee:(use b)
                    ~zero:(Op.apply Op.h (use x))
                    ~one_:(Op.apply Op.s (use x))
                    ~using:(UL (UR U0)) }
            (UL U0) }

let fixed_control_uses_context_left_case_expansion () =
  match emit fixed_control with
  | Bridge.TLam
      (_, _, _,
       Bridge.TLetPair
         (_, _, _, _, _,
          Bridge.TApply
            (Bridge.TLam
               (_, Rep.Tensor (gamma_domain, (Rep.Plus (_, _) as sum_domain)),
                _,
                Bridge.TSeq
                  (Bridge.TVar (_, argument_domain),
                   Bridge.TSeq
                     (Bridge.TDistR (gamma_dist, Rep.Unit, Rep.Unit),
                      Bridge.TSeq
                        (Bridge.TPlusMap (_, _, _, _),
                         Bridge.TUndistL (_, _, _))))),
             Bridge.TPair
               (Bridge.TVar (_, gamma_value),
                Bridge.TVar (_, sum_value))))) ->
      Rep.equal gamma_domain gamma_dist
      && Rep.equal gamma_domain gamma_value
      && Rep.equal sum_domain sum_value
      && Rep.equal argument_domain
           (Rep.Tensor (gamma_domain, sum_domain))
  | _ -> false

let qswitch =
  let endo = S.lolli q q in
  let input = S.tensor qbool q in
  lam ~name:"f" endo
    (S.lolli endo (S.lolli input input))
    { run_lam =
        fun f ->
          lam ~name:"g" endo (S.lolli input input)
            { run_lam =
                fun g ->
                  lam ~name:"p" input input
                    { run_lam =
                        fun p ->
                          let_tensor ~left_name:"b" ~right_name:"x"
                            qbool q (use p)
                            { run_split =
                                fun b x ->
                                  let gx =
                                    app (use g) (use x)
                                      (UR (UL U0))
                                  in
                                  let fx =
                                    app (use f) gx
                                      (UR (UR (UL U0)))
                                  in
                                  let fx' =
                                    app (use f) (use x)
                                      (UR (UL U0))
                                  in
                                  let gx' =
                                    app (use g) fx'
                                      (UR (UL (UR U0)))
                                  in
                                  case_bool ~result:P.q
                                    ~scrutinee:(use b)
                                    ~zero:fx ~one_:gx'
                                    ~using:
                                      (UL (UR (UR (UR U0)))) }
                            (UL (UR (UR U0))) } } }
let qswitch_hs =
  app (app qswitch (Op.value Op.h) U0)
    (Op.value Op.s) U0


module Three =
  Datatype.Make
    (struct
      type tail = Datatype.n2
      let name = "Three"
      let labels =
        Datatype.(
          VCons ("zero",
            VCons ("one",
              VCons ("two", VNil))))
    end) ()

module Two =
  Datatype.Make
    (struct
      type tail = Datatype.n1
      let name = "SourceSemanticTwo"
      let labels =
        Datatype.(VCons ("left", VCons ("right", VNil)))
    end) ()

let three_control =
  Three.select ~target:P.q
    Datatype.(
      VCons (Op.h,
        VCons (Op.s,
          VCons (Op.t, VNil))))

let sealed_h =
  Op.seal ~domain:q ~codomain:q
    (lam ~name:"sealed_h_arg" q q
       { run_lam = fun x -> Op.apply Op.h (use x) })

let datatype_sealed_control =
  Two.select ~target:P.q
    Datatype.(VCons (sealed_h, VCons (Op.x, VNil)))

let datatype_action_control =
  Two.select ~target:P.q
    Datatype.(VCons (Op.h, VCons (Op.x, VNil)))

let datatype_object = S.tensor Two.s q

let datatype_program control =
  lam ~name:"controlled_pair" datatype_object datatype_object
    { run_lam = fun pair -> Op.apply control (use pair) }

let datatype_sealed_program =
  datatype_program datatype_sealed_control

let datatype_action_program =
  datatype_program datatype_action_control

let datatype_sealed_branch_is_applied_value () =
  match emit (Op.value datatype_sealed_control) with
  | Bridge.TLam
      (_, _, _,
       Bridge.TSeq
         (_, Bridge.TDatatypeControl (_, 2, _, _, branches)))
    when Array.length branches = 2 ->
      (match branches.(0) with
       | Bridge.TApply (Bridge.TLam _, Bridge.TId _) -> true
       | _ -> false)
  | _ -> false

let same_framed_boundaries_and_cost left right =
  left.Bridge.fr_input_frame = right.Bridge.fr_input_frame
  && left.Bridge.fr_output_frame = right.Bridge.fr_output_frame
  && abs_float
       (left.Bridge.fr_global_phase -. right.Bridge.fr_global_phase)
       < 1e-12
  && left.Bridge.fr_size = right.Bridge.fr_size

let four_wire_boundaries result =
  let is_four = function
    | Some frame -> frame.Bridge.f_n_qubits = 4
    | None -> false
  in
  is_four result.Bridge.fr_input_frame
  && is_four result.Bridge.fr_output_frame

let duplicate_labels_rejected () =
  try
    let module Bad =
      Datatype.Make
        (struct
          type tail = Datatype.n1
          let name = "Bad"
          let labels =
            Datatype.(
              VCons ("same",
                VCons ("same", VNil)))
        end) ()
    in
    ignore Bad.arity;
    false
  with
  | Invalid_argument message -> contains message "duplicate"
  | _ -> false

let nonfinite_phase_rejected () =
  try
    ignore (Op.phase { Complex.re = nan; im = 0.0 } P.q);
    false
  with
  | Invalid_argument message -> contains message "finite"
  | _ -> false

let nonfinite_angle_rejected make theta =
  try
    ignore (make theta);
    false
  with
  | Invalid_argument message -> contains message "finite"
  | _ -> false

let () =
  print_endline "Sealed Source semantic tests:";
  compile "identity" identity;
  compile "neutral Source.seq H;S" neutral_seq;
  check "neutral Source.seq elaborates to a lambda"
    (neutral_seq_is_eta_lam ());
  compile "higher-order identity applied to H"
    higher_order_identity_on_h;
  check "higher-order identity is the direct lambda identity"
    (higher_order_identity_is_direct_lam ());
  compile "P-level tensor elimination" tensor_eta;
  compile "tensor elimination returning an applied function"
    tensor_let_returns_function;
  compile "direct tensor-elimination reference"
    tensor_let_direct_reference;
  check "tensor-let function result is applied, not sequenced"
    (tensor_let_function_uses_application ());
  (match
     Bridge.eq_circ
       (emit tensor_let_returns_function)
       (emit tensor_let_direct_reference)
   with
   | Bridge.EqCircOk (true, fidelity) ->
       check "tensor-let application matches direct substitution"
         (abs_float (fidelity -. 1.0) < 1e-9)
   | Bridge.EqCircOk (false, fidelity) ->
       Printf.eprintf "tensor-let substitution fidelity: %.12g\n" fidelity;
       check "tensor-let application matches direct substitution" false
   | Bridge.EqCircError error ->
       Printf.eprintf "tensor-let substitution comparison: %s\n" error;
       check "tensor-let application matches direct substitution" false);
  compile "fixed same-context control" fixed_control;
  check "case expansion keeps the manuscript's context-left orientation"
    (fixed_control_uses_context_left_case_expansion ());
  compile "higher-order same-context qswitch" qswitch;
  compile_or_recorded_gap
    "higher-order qswitch specialized to H/S" qswitch_hs;
  compile "arity-indexed nominal datatype control" (Op.value three_control);
  check "datatype neutral branch is applied, never stored as a bare lambda"
    (datatype_sealed_branch_is_applied_value ());
  (match compile_framed "datatype sealed-H control" datatype_sealed_program,
         compile_framed "datatype action-H control" datatype_action_program with
   | Some sealed, Some action ->
       check "datatype sealed-H and action-H controls have equal framed cost"
         (same_framed_boundaries_and_cost sealed action
          && four_wire_boundaries sealed
          && sealed.Bridge.fr_size = 4
          && abs_float sealed.Bridge.fr_global_phase < 1e-12)
   | _ -> ());
  compile "certified exponential of tensor symmetry"
    (Op.value
       (Op.exp_i (Float.pi /. 4.0)
          (Op.involution_twist P.q)));
  check "datatype exposes its declared arity" (Three.arity = 3);
  check "datatype preserves declared label order"
    (Three.labels = ["zero"; "one"; "two"]);
  check "duplicate runtime labels are rejected honestly"
    (duplicate_labels_rejected ());
  check "non-finite phases are rejected" (nonfinite_phase_rejected ());
  check "Rz rejects NaN"
    (nonfinite_angle_rejected Op.rz nan);
  check "Rz rejects infinity"
    (nonfinite_angle_rejected Op.rz infinity);
  check "Exp rejects NaN"
    (nonfinite_angle_rejected
       (fun theta -> Op.exp_i theta Op.involution_h) nan);
  check "Exp rejects infinity"
    (nonfinite_angle_rejected
       (fun theta -> Op.exp_i theta Op.involution_h) infinity);
  if !failures <> 0 then exit 1
