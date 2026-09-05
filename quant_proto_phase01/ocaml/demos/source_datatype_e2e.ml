open Qpl_surface
open Source

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

let controlled_gate =
  Three.select ~target:P.q
    Datatype.(
      VCons (Op.h,
        VCons (Op.s,
          VCons (Op.t, VNil))))

let tagged_qubit = S.tensor Three.s q

let program =
  lam ~name:"tagged_qubit" tagged_qubit tagged_qubit
    { run_lam =
        fun input ->
          Op.apply controlled_gate (use input) }

let () =
  Printf.printf
    "Source datatype: %s has %d constructors [%s]\n"
    Three.name Three.arity (String.concat ", " Three.labels);
  match Bridge.compile_show (emit program) with
  | Bridge.CompileOk (permutation, gates) ->
      Printf.printf
        "Source datatype: OK gates=%d wires=%d\n"
        gates permutation.n
  | Bridge.CompileError error ->
      Printf.eprintf "Source datatype: FAIL: %s\n" error;
      exit 1
