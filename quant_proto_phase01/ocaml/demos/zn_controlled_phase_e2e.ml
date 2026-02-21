(** Zn Controlled Phase Rotation E2E Demo

    Full pipeline: OCaml Surface -> Bridge -> Python compile -> Circuit

    Demonstrates coherent control over cyclic groups:
    - Z2 (Bool): Case with CZ gate
    - Z4: Binary decomposition with CS, CZ
    - Z5: CRz binary decomposition with 5th roots of unity

    The control value remains in superposition throughout.
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

let pi = Float.pi

(** Calculate tag width (number of qubits for flat encoding) *)
let tag_width n =
  if n <= 1 then 0
  else
    let rec log2_ceil k acc =
      if k <= 1 then acc
      else log2_ceil ((k + 1) / 2) (acc + 1)
    in
    log2_ceil n 0

let () =
  (* Set project root for bridge.py *)
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  banner "Zn CONTROLLED PHASE ROTATION E2E DEMO";
  print_endline "\nCoherent control over cyclic groups Zn\n";

  (* =========================================================================
     PART 1: Datatype Declarations
     ========================================================================= *)
  banner "PART 1: Datatype Declaration for Cyclic Groups";

  print_endline "
DATATYPE SPECIFICATION
----------------------
    datatype Z_n where
        labels  0 | 1 | ... | n-1
        ops     add : Zn ⊗ Zn ⊸ Zn ⊗ Zn,  neg : Zn ⊸ Zn

COHERENT CONTROL COMBINATOR
---------------------------
    control_Zn : (Zn ⊸ (A ⊸ A)) ⊸ (A ⊗ Zn ⊸ A ⊗ Zn)

This applies a family of programs indexed by group elements,
WITHOUT observing the index. The control value is preserved.
";

  (* Define Z2, Z4, Z5 using the datatype facility *)
  let z2 = datatype
    ~name:"Z2"
    ~arity:2
    ~labels:["0"; "1"]
    ~ops:[("add", lolli (self **. self) (self **. self));
          ("neg", lolli self self)]
  in

  let z4 = datatype
    ~name:"Z4"
    ~arity:4
    ~labels:["0"; "1"; "2"; "3"]
    ~ops:[("add", lolli (self **. self) (self **. self));
          ("neg", lolli self self)]
  in

  let z5 = datatype
    ~name:"Z5"
    ~arity:5
    ~labels:["0"; "1"; "2"; "3"; "4"]
    ~ops:[("add", lolli (self **. self) (self **. self));
          ("neg", lolli self self)]
  in

  Printf.printf "\nDatatypes defined:\n";
  Printf.printf "  Z2: arity=%d, rep width=%d tag qubits\n" z2.arity (tag_width z2.arity);
  Printf.printf "  Z4: arity=%d, rep width=%d tag qubits\n" z4.arity (tag_width z4.arity);
  Printf.printf "  Z5: arity=%d, rep width=%d tag qubits\n" z5.arity (tag_width z5.arity);

  (* =========================================================================
     PART 2: Z2 (Bool) Controlled Phase
     ========================================================================= *)
  banner "PART 2: Z2 (Bool) Controlled Phase";

  print_endline "
TYPE STRUCTURE
--------------
    Z2 = I + I    (Bool: False | True)
    A  = Q ⊗ Q    (two qubits)

PHASE SELECTOR
--------------
    P_0 = I ⊗ I     (identity, phase 1)
    P_1 = Z ⊗ I     (Z gate on first qubit, phase -1)

    Wire layout: [tag | q0 | q1]
";

  (* For Z2, we use dist_l and omap.
     But for the controlled phase with CZ, we need to emit Bridge terms directly. *)

  (* Z2 ⊗ Q with 3 qubits: tag (wire 0), q0 (wire 1), q1 (wire 2)
     Controlled-Z on (tag, q0) = CZ(0, 1) *)
  let z2_phase = Bridge.TCZ (0, 1) in

  Printf.printf "\nZ2 controlled phase circuit:\n";
  Printf.printf "  Term: CZ(tag, q0)\n";
  Printf.printf "  Bridge: %s\n" (Bridge.term_to_json z2_phase);

  (match Bridge.compile_show z2_phase with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err ->
       Printf.printf "  FAILED: %s\n" err);

  (* =========================================================================
     PART 3: Z4 Controlled Phase
     ========================================================================= *)
  banner "PART 3: Z4 Controlled Phase";

  print_endline "
TYPE STRUCTURE
--------------
    Z4 = I + (I + (I + I))    (4 elements: 0, 1, 2, 3)
    A  = Q ⊗ Q

    Tag width: 2 qubits (flat log2 encoding)
    Wire layout: [t0 | t1 | q0 | q1]

PHASE SELECTOR (4th roots of unity)
-----------------------------------
    P_0 = I    (phase 1)      k=0: t0=0, t1=0
    P_1 = S    (phase i)      k=1: t0=1, t1=0
    P_2 = Z    (phase -1)     k=2: t0=0, t1=1
    P_3 = Sdg  (phase -i)     k=3: t0=1, t1=1

CLEVER DECOMPOSITION
--------------------
    Key insight: S * Z = Sdg (up to global phase)!

    Circuit: CS(t0, q0) ; CZ(t1, q0)

    When k=0: neither fires -> I (phase 1)
    When k=1: CS fires     -> S (phase i)
    When k=2: CZ fires     -> Z (phase -1)
    When k=3: both fire    -> S*Z = Sdg (-i)
";

  (* Z4 ⊗ (Q⊗Q) with 4 qubits: t0, t1, q0, q1
     CS(t0, q0) ; CZ(t1, q0) = CS(0, 2) ; CZ(1, 2) *)
  let z4_phase = Bridge.TSeq (
    Bridge.TCS (0, 2),   (* CS(t0, q0) *)
    Bridge.TCZ (1, 2)    (* CZ(t1, q0) *)
  ) in

  Printf.printf "\nZ4 controlled phase circuit:\n";
  Printf.printf "  Term: CS(t0, q0) ; CZ(t1, q0)\n";
  Printf.printf "  Bridge: %s\n" (Bridge.term_to_json z4_phase);

  (match Bridge.compile_show z4_phase with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err ->
       Printf.printf "  FAILED: %s\n" err);

  (* =========================================================================
     PART 4: Z5 Controlled Phase
     ========================================================================= *)
  banner "PART 4: Z5 Controlled Phase";

  print_endline "
TYPE STRUCTURE
--------------
    Z5 = I + (I + (I + (I + I)))    (5 elements: 0, 1, 2, 3, 4)
    A  = Q ⊗ Q

    Tag width: 3 qubits (flat log2 encoding)
    Wire layout: [t0 | t1 | t2 | q0 | q1]

PHASE SELECTOR (5th roots of unity)
-----------------------------------
    P_k = Rz(2*pi*k/5)

    k = 0: Rz(0)       (phase 1)
    k = 1: Rz(2pi/5)   (phase e^{2pi*i/5})
    k = 2: Rz(4pi/5)   (phase e^{4pi*i/5})
    k = 3: Rz(6pi/5)   (phase e^{6pi*i/5})
    k = 4: Rz(8pi/5)   (phase e^{8pi*i/5})

BINARY DECOMPOSITION
--------------------
    With flat binary encoding [t0, t1, t2] where k = 4*t2 + 2*t1 + t0:

    Phase(k) = k * (2pi/5)
             = t0*(2pi/5) + t1*(4pi/5) + t2*(8pi/5)

    Since phases are ADDITIVE:
      CRz(2pi/5, t0, q0) ; CRz(4pi/5, t1, q0) ; CRz(8pi/5, t2, q0)

    Total: 3 gates (O(log n) for general Zn)
";

  (* Z5 ⊗ (Q⊗Q) with 5 qubits: t0, t1, t2, q0, q1
     CRz(2pi/5, t0, q0) ; CRz(4pi/5, t1, q0) ; CRz(8pi/5, t2, q0)
     Wire indices: t0=0, t1=1, t2=2, q0=3, q1=4 *)
  let theta1 = 2.0 *. pi /. 5.0 in  (* 2pi/5 *)
  let theta2 = 4.0 *. pi /. 5.0 in  (* 4pi/5 *)
  let theta4 = 8.0 *. pi /. 5.0 in  (* 8pi/5 *)

  let z5_phase = Bridge.TSeq (
    Bridge.TCRz (theta1, 0, 3),  (* CRz(2pi/5, t0, q0) *)
    Bridge.TSeq (
      Bridge.TCRz (theta2, 1, 3),  (* CRz(4pi/5, t1, q0) *)
      Bridge.TCRz (theta4, 2, 3)   (* CRz(8pi/5, t2, q0) *)
    )
  ) in

  Printf.printf "\nZ5 controlled phase circuit:\n";
  Printf.printf "  Term: CRz(2pi/5, t0, q0) ; CRz(4pi/5, t1, q0) ; CRz(8pi/5, t2, q0)\n";
  Printf.printf "  Angles: theta1=%.4f, theta2=%.4f, theta4=%.4f\n" theta1 theta2 theta4;
  Printf.printf "  Bridge: %s\n" (Bridge.term_to_json z5_phase);

  (match Bridge.compile_show z5_phase with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err ->
       Printf.printf "  FAILED: %s\n" err);

  (* =========================================================================
     PART 5: General Zn Formula
     ========================================================================= *)
  banner "PART 5: General Zn Formula";

  print_endline "
GENERAL BINARY DECOMPOSITION
----------------------------
For Zn controlled phase rotation (n-th roots of unity):

    Phase(k) = k * (2*pi/n) = sum_{j} t_j * (2^j * 2*pi/n)

    where k = sum_{j} t_j * 2^j (binary expansion)

    Circuit: sequence of CRz(2^j * 2*pi/n, t_j, target) for j = 0..ceil(log2(n))-1

    Gate count: ceil(log2(n)) = O(log n)

This is EXPONENTIALLY better than naive O(n) approaches!


KEY INSIGHTS
------------
1. REVERSIBILITY
   The `add` operation returns inputs alongside sum:
     add : Zn ⊗ Zn ⊸ Zn ⊗ Zn
   Discarding would lose information.

2. NO OBSERVATION
   Unlike classical pattern matching, control_Zn does NOT observe
   which branch the control value is in. The control passes through
   unchanged and can remain in superposition.

3. PHASE ADDITIVITY
   Phases combine multiplicatively, which translates to
   additive angles. Binary decomposition exploits this.
";

  (* =========================================================================
     PART 6: Using Linear DSL Datatype
     ========================================================================= *)
  banner "PART 6: Linear DSL Datatype Integration";

  Printf.printf "\nDatatype descriptors created via Linear.datatype:\n\n";

  let print_datatype dt =
    Printf.printf "  %s:\n" dt.name;
    Printf.printf "    arity: %d\n" dt.arity;
    Printf.printf "    labels: [%s]\n" (String.concat ", " dt.labels);
    Printf.printf "    operations:\n";
    List.iter (fun op ->
      Printf.printf "      %s\n" op.op_name
    ) dt.ops;
    print_endline ""
  in

  print_datatype z2;
  print_datatype z4;
  print_datatype z5;

  Printf.printf "  (Z8 declared in PART 7 using NPlusMap)\n";

  (* =========================================================================
     PART 7: Z8 Coherent Action via NPlusMap
     ========================================================================= *)
  banner "PART 7: Z8 Coherent Action via NPlusMap";

  print_endline "
TYPE STRUCTURE
--------------
    Z8 = I + (I + (I + (I + (I + (I + (I + I))))))  (8 elements)
    A  = Q

    Tag width: 3 qubits (flat log2 encoding)

NPlusMap APPROACH
-----------------
    Instead of manual binary decomposition, NPlusMap dispatches
    one morphism per summand. The compiler handles the tag encoding.

    Branch m: Rz(m * 0.25) half-turns
    m=0: Rz(0.00)  m=1: Rz(0.25)  m=2: Rz(0.50)  m=3: Rz(0.75)
    m=4: Rz(1.00)  m=5: Rz(1.25)  m=6: Rz(1.50)  m=7: Rz(1.75)
";

  let z8 = datatype
    ~name:"Z8"
    ~arity:8
    ~labels:["0";"1";"2";"3";"4";"5";"6";"7"]
    ~ops:[("add", lolli (self **. self) (self **. self));
          ("neg", lolli self self)]
  in

  Printf.printf "  Z8: arity=%d, rep width=%d tag qubits\n" z8.arity (tag_width z8.arity);

  (* Build NPlusMap: 8 branches, each Rz(m * 0.25) half-turns *)
  let summand_types = Array.make 8 q in
  let branches = Array.init 8 (fun m ->
    gate_rz (float_of_int m *. 0.25)
  ) in
  let z8_action = omapn summand_types branches in
  let z8_term = emit z8_action in

  Printf.printf "  Z8 NPlusMap term emitted\n";
  Printf.printf "  Bridge JSON: %s\n" (Bridge.term_to_json z8_term);

  (match Bridge.compile_show z8_term with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err ->
       Printf.printf "  FAILED: %s\n" err;
       exit 1);

  (* =========================================================================
     PART 8: Summary
     ========================================================================= *)
  banner "SUMMARY";

  Printf.printf "
Zn CONTROLLED PHASE ROTATION
----------------------------

Demonstrated: Coherent control over cyclic groups

    Z2 (Bool):     1 tag qubit,  1 gate  (CZ)
    Z4:            2 tag qubits, 2 gates (CS ; CZ)
    Z5:            3 tag qubits, 3 gates (CRz ; CRz ; CRz)
    Z8 (NPlusMap): 3 tag qubits, compiled via NPlusMap (8 branches)

Key formula:
    control_Zn : (Zn ⊸ (A ⊸ A)) ⊸ (Zn ⊗ A ⊸ Zn ⊗ A)

NPlusMap: n-ary coherent sum eliminator.
  No manual binary decomposition needed!
  Compiles directly against flat tag encoding.

This is the quantum analogue of \"case\" that:
  - Applies operations indexed by group elements
  - Preserves the index in superposition
  - Never observes/collapses the control
";

  banner "DEMO COMPLETE"
