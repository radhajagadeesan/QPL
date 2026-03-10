(** Zn Controlled Phase Rotation E2E Demo

    Full pipeline: OCaml Linear DSL -> Bridge -> Python compile -> Circuit

    Demonstrates coherent control over cyclic groups Zn using the
    `control` combinator from the Linear DSL. Each Zn is declared as
    a datatype, then `control zn q branches` produces a morphism
    Zn ⊗ Q → Zn ⊗ Q that applies branch k when the control is element k.

    The control value remains in superposition throughout.
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(** Calculate tag width (number of qubits for flat encoding) *)
let tag_width n =
  if n <= 1 then 0
  else
    let rec log2_ceil k acc =
      if k <= 1 then acc
      else log2_ceil ((k + 1) / 2) (acc + 1)
    in
    log2_ceil n 0

let had_failure = ref false
let verifications_run = ref 0
let verifications_passed = ref 0

let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile_show term with
  | Bridge.CompileOk _ -> ()
  | Bridge.CompileError err ->
      Printf.printf "  FAILED: %s\n" err;
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

let () =
  banner "Zn CONTROLLED PHASE ROTATION E2E DEMO";
  print_endline "\nCoherent control over cyclic groups via Linear DSL\n";

  (* =========================================================================
     PART 1: Datatype Declarations
     ========================================================================= *)
  banner "PART 1: Datatype Declarations";

  let z2 = datatype ~name:"Z2" ~arity:2
    ~labels:["0"; "1"]
    ~ops:[("add", lolli (self **. self) (self **. self));
          ("neg", lolli self self)]
  in
  let z4 = datatype ~name:"Z4" ~arity:4
    ~labels:["0"; "1"; "2"; "3"]
    ~ops:[("add", lolli (self **. self) (self **. self));
          ("neg", lolli self self)]
  in
  let z5 = datatype ~name:"Z5" ~arity:5
    ~labels:["0"; "1"; "2"; "3"; "4"]
    ~ops:[("add", lolli (self **. self) (self **. self));
          ("neg", lolli self self)]
  in
  let z8 = datatype ~name:"Z8" ~arity:8
    ~labels:["0";"1";"2";"3";"4";"5";"6";"7"]
    ~ops:[("add", lolli (self **. self) (self **. self));
          ("neg", lolli self self)]
  in

  let print_dt dt =
    Printf.printf "  %s: arity=%d, %d tag qubits\n" dt.name dt.arity (tag_width dt.arity)
  in
  print_dt z2; print_dt z4; print_dt z5; print_dt z8;

  (* =========================================================================
     PART 2: Z2 Controlled Phase (2nd roots of unity)
     ========================================================================= *)
  banner "PART 2: Z2 Controlled Phase";

  print_endline "\n  control z2 q [| id q; gate_z |]";
  print_endline "  Branch 0: identity, Branch 1: Z gate\n";

  let z2_phase = control z2 q [| id q; gate_z |] in
  compile_and_report "Z2 phase: Z2 ⊗ Q → Z2 ⊗ Q" (emit z2_phase);

  (* =========================================================================
     PART 3: Z4 Controlled Phase (4th roots of unity)
     ========================================================================= *)
  banner "PART 3: Z4 Controlled Phase";

  print_endline "\n  control z4 q [| Rz(0); Rz(0.5); Rz(1.0); Rz(1.5) |]  (half-turns)";
  print_endline "  Branch k: Rz(k/2) half-turns = e^{ikπ/2} relative phase\n";

  let z4_phase = control z4 q
    (Array.init 4 (fun m -> gate_rz (float_of_int m *. 0.5))) in
  compile_and_report "Z4 phase: Z4 ⊗ Q → Z4 ⊗ Q" (emit z4_phase);

  (* =========================================================================
     PART 4: Z5 Controlled Phase (5th roots of unity)
     ========================================================================= *)
  banner "PART 4: Z5 Controlled Phase";

  print_endline "\n  control z5 q [| Rz(0); Rz(2/5); Rz(4/5); Rz(6/5); Rz(8/5) |]  (half-turns)";
  print_endline "  Branch k: Rz(2k/5) half-turns = e^{i2πk/5} relative phase\n";

  let z5_phase = control z5 q
    (Array.init 5 (fun m -> gate_rz (2.0 *. float_of_int m /. 5.0))) in
  compile_and_report "Z5 phase: Z5 ⊗ Q → Z5 ⊗ Q" (emit z5_phase);

  (* =========================================================================
     PART 5: Z8 Controlled Phase (8th roots of unity)
     ========================================================================= *)
  banner "PART 5: Z8 Controlled Phase";

  print_endline "\n  control z8 q [| Rz(0); Rz(0.25); ...; Rz(1.75) |]  (half-turns)";
  print_endline "  Branch k: Rz(k/4) half-turns = e^{ikπ/4} relative phase\n";

  let z8_phase = control z8 q
    (Array.init 8 (fun m -> gate_rz (float_of_int m *. 0.25))) in
  compile_and_report "Z8 phase: Z8 ⊗ Q → Z8 ⊗ Q" (emit z8_phase);

  (* =========================================================================
     PART 6: Semantic Verification
     ========================================================================= *)
  banner "PART 6: Semantic Verification";

  print_endline "
Verifying correctness: control with forward phases composed with
inverse phases should give identity (f ; f^{-1} = id).
";

  (* Build inverse rotations and verify f ; f_inv = id *)
  let z2_inv = control z2 q [| id q; gate_z |] in  (* Z is self-inverse *)
  let z2_composed = seq0 z2_phase z2_inv in
  let z2_id = id (rep_ty z2 ** q) in
  verify_eq "Z2: phase ; phase^{-1} = id"
    (emit z2_composed) (emit z2_id);

  let z4_inv = control z4 q
    (Array.init 4 (fun m -> gate_rz (-. (float_of_int m *. 0.5)))) in
  let z4_composed = seq0 z4_phase z4_inv in
  let z4_id = id (rep_ty z4 ** q) in
  verify_eq "Z4: phase ; phase^{-1} = id"
    (emit z4_composed) (emit z4_id);

  let z5_inv = control z5 q
    (Array.init 5 (fun m -> gate_rz (-. (2.0 *. float_of_int m /. 5.0)))) in
  let z5_composed = seq0 z5_phase z5_inv in
  let z5_id = id (rep_ty z5 ** q) in
  verify_eq "Z5: phase ; phase^{-1} = id"
    (emit z5_composed) (emit z5_id);

  let z8_inv = control z8 q
    (Array.init 8 (fun m -> gate_rz (-. (float_of_int m *. 0.25)))) in
  let z8_composed = seq0 z8_phase z8_inv in
  let z8_id = id (rep_ty z8 ** q) in
  verify_eq "Z8: phase ; phase^{-1} = id"
    (emit z8_composed) (emit z8_id);

  (* Also verify: control with all-identity branches = identity *)
  let z4_trivial = control z4 q (Array.make 4 (id q)) in
  verify_eq "Z4: control [id;id;id;id] = id (trivial)"
    (emit z4_trivial) (emit z4_id);

  let z8_trivial = control z8 q (Array.make 8 (id q)) in
  verify_eq "Z8: control [id;...;id] = id (trivial)"
    (emit z8_trivial) (emit z8_id);

  Printf.printf "\nVerification: %d/%d passed\n" !verifications_passed !verifications_run;

  (* =========================================================================
     SUMMARY
     ========================================================================= *)
  banner "SUMMARY";

  Printf.printf "
Compiled Zn controlled phase rotations via Linear DSL:

  Z2: control z2 q [id; Z]           %d tag qubits
  Z4: control z4 q [Rz(k/2)]         %d tag qubits
  Z5: control z5 q [Rz(2k/5)]        %d tag qubits
  Z8: control z8 q [Rz(k/4)]         %d tag qubits

All use the `control` combinator on declared datatypes.
The compiler handles tag encoding and multi-controlled gates.
" (tag_width 2) (tag_width 4) (tag_width 5) (tag_width 8);

  banner "DEMO COMPLETE";
  if !had_failure then exit 1
