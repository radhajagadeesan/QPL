(* Handwritten sealed-API oracles, copied verbatim from the sealed demos
   (rows 27–31).  These deliberately spell out the context routing the
   frontend synthesizes, so the concise counterparts are compared against
   an INDEPENDENT construction.  Excluded from the anti-vacuity scan. *)

open Qpl_surface
open Source

(* closed application helper for instantiating polymorphic counterparts *)
let apply0 f x = app f x U0

(* row 30: source_quickstart_e2e.ml *)
let quickstart =
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

(* row 29: source_fixed_control_e2e.ml *)
let fixed_control =
  lam ~name:"input" (S.tensor qbool q) (S.tensor qbool q)
    { run_lam =
        fun input ->
          let_tensor ~left_name:"control" ~right_name:"target"
            qbool q (use input)
            { run_split =
                fun control target ->
                  case_bool ~result:P.q
                    ~scrutinee:(use control)
                    ~zero:(Op.apply Op.h (use target))
                    ~one_:(Op.apply Op.s (use target))
                    ~using:(UL (UR U0)) }
            (UL U0) }

(* row 27: source_datatype_e2e.ml *)
module Three =
  Datatype.Make
    (struct
      type tail = Datatype.n2
      let name = "Three"
      let labels =
        Datatype.(VCons ("zero", VCons ("one", VCons ("two", VNil))))
    end) ()

let three_controlled =
  Three.select ~target:P.q
    Datatype.(VCons (Op.h, VCons (Op.s, VCons (Op.t, VNil))))

let three_program =
  lam ~name:"tagged_qubit" (S.tensor Three.s q) (S.tensor Three.s q)
    { run_lam = fun input -> Op.apply three_controlled (use input) }

(* row 28: source_exp_twist_e2e.ml *)
let exp_twist_value =
  Op.value (Op.exp_i (Float.pi /. 4.0) (Op.involution_twist P.q))

(* row 31: test_first_order.ml *)
let exp_x_value =
  Op.value (Op.exp_i (Float.pi /. 4.0) Op.involution_x)
