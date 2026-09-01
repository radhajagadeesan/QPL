(** Committed OCaml-side test of the framed bridge round-trip.

    The Python compiler is authoritative about boundary frames; this checks
    that they survive transport rather than being reconstructed on the OCaml
    side. Previously the bridge sent frames one way and OCaml parsed only
    (perm, circuit_size), and the only "serialization test" was a hand-built
    Python dictionary that never crossed the boundary. *)

open Qpl_surface
open Linear

let pass = ref 0
let fail = ref 0

let check name cond =
  if cond then (incr pass; Printf.printf "  PASS %s\n" name)
  else (incr fail; Printf.printf "  FAIL %s\n" name)

let framed name t =
  match Bridge.compile_framed (emit t) with
  | Bridge.FramedOk r -> Some r
  | Bridge.FramedError e ->
      incr fail; Printf.printf "  FAIL %s: %s\n" name e; None

let codes_of = function
  | None -> []
  | Some f -> f.Bridge.f_codes

let frame_of name = function
  | Some f -> Some f
  | None -> incr fail; Printf.printf "  FAIL %s: frame absent\n" name; None

(* Shorthands for building the EXPECTED type tree on the OCaml side. The
   round-trip is structural: OCaml reconstructs the type from the payload and
   compares trees, so neither whitespace nor a merely similar-looking payload
   can pass. *)
let tq = Bridge.TQ
let tu = Bridge.TUnit
let ( *. ) a b = Bridge.TTen (a, b)
let ( +. ) a b = Bridge.TPlus (a, b)
let tbool = tu +. tu

let sector_summary f =
  List.map
    (fun s -> (s.Bridge.sec_index, s.Bridge.sec_codes, s.Bridge.sec_tag_values))
    f.Bridge.f_sectors

let port_named f n =
  List.find_opt (fun p -> p.Bridge.prt_name = n) f.Bridge.f_ports

let () =
  print_endline "";
  print_endline "=== framed bridge round-trip (OCaml side) ===";

  (* Both frames and the phase must be present in a successful response. *)
  (match framed "id q" (id q) with
   | None -> ()
   | Some r ->
     check "id q: input frame present"  (r.Bridge.fr_input_frame <> None);
     check "id q: output frame present" (r.Bridge.fr_output_frame <> None);
     check "id q: codes are [0;1]" (codes_of r.Bridge.fr_input_frame = [0; 1]));

  (* A pending permutation must be visible in the transported output frame:
     asymmetric, so an inverse-direction error cannot hide. *)
  (match framed "twist_tensor q (one++one)" (twist_tensor q (one ++ one)) with
   | None -> ()
   | Some r ->
     let i = codes_of r.Bridge.fr_input_frame in
     let o = codes_of r.Bridge.fr_output_frame in
     check "twist: input is canonical" (i = [0; 1; 2; 3]);
     check "twist: output carries the pending perm" (o <> i));

  (* dist_l: the derivation-selected shared four-qubit layout. *)
  let qb = one ++ one in
  (match framed "dist_l" (dist_l qb (qb ** qb) qb) with
   | None -> ()
   | Some r ->
     let i = codes_of r.Bridge.fr_input_frame in
     let o = codes_of r.Bridge.fr_output_frame in
     check "dist_l: four qubits"
       ((match r.Bridge.fr_input_frame with Some f -> f.Bridge.f_n_qubits | None -> 0) = 4);
     check "dist_l: gate-free" (r.Bridge.fr_size = 0);
     check "dist_l: input and output codes identical" (i = o);
     check "dist_l: shared layout codes"
       (o = [0; 1; 4; 5; 8; 9; 10; 11; 12; 13; 14; 15]));

  (* ---------------------------------------------------------------------
     Structural round-trip: a frame is an EXACT embedding, so codes and width
     alone do not determine it. The logical type, the symbolic expression,
     the sectors and the port placements must all survive transport.
     --------------------------------------------------------------------- *)

  (* Logical types, reconstructed as trees and compared structurally. *)
  (match framed "id q logical" (id q) with
   | None -> ()
   | Some r ->
     (match frame_of "id q" r.Bridge.fr_input_frame with
      | None -> ()
      | Some f ->
        check "id q: logical type round-trips as Q"
          (f.Bridge.f_logical = Some tq);
        check "id q: expression round-trips structurally"
          (f.Bridge.f_expr = Some (Bridge.EIdentity 1))));

  (* The symbolic expression must survive as a TREE, not as a note. This one
     exercises every constructor at once: compose(tensor(sum, identity),
     wireperm), including the pending permutation at the exit. *)
  (match framed "twist expr" (twist_tensor q (one ++ one)) with
   | None -> ()
   | Some r ->
     (match frame_of "twist in" r.Bridge.fr_input_frame,
            frame_of "twist out" r.Bridge.fr_output_frame with
      | Some fi, Some fo ->
        let bits = Bridge.ESum ([Bridge.EIdentity 0; Bridge.EIdentity 0], 1, 0) in
        check "twist: input expression is tensor(identity, sum)"
          (fi.Bridge.f_expr = Some (Bridge.ETensor (Bridge.EIdentity 1, bits)));
        check "twist: output expression carries the exit permutation"
          (fo.Bridge.f_expr
           = Some (Bridge.ECompose
                     (Bridge.ETensor (bits, Bridge.EIdentity 1),
                      Bridge.EWirePerm [1; 0])))
      | _ -> ()));

  (* An opaque note must arrive as an opaque note, with its text intact. *)
  (match framed "dist_l expr" (dist_l (one ++ one) ((one ++ one) ** (one ++ one)) (one ++ one)) with
   | None -> ()
   | Some r ->
     (match frame_of "dist_l in" r.Bridge.fr_input_frame with
      | None -> ()
      | Some f ->
        check "dist_l: opaque expression text round-trips"
          (f.Bridge.f_expr
           = Some (Bridge.EOpaque "dist_l shared layout [tag | payload | C]"))));

  (match framed "id (q ** (one++one)) logical" (id (q ** (one ++ one))) with
   | None -> ()
   | Some r ->
     (match frame_of "ten logical" r.Bridge.fr_input_frame with
      | None -> ()
      | Some f ->
        check "Ten(Q, I+I): logical tree round-trips structurally"
          (f.Bridge.f_logical = Some (tq *. tbool))));

  (* Sectors: index, codes and the FULL tag-word set, plus each summand's own
     logical type. A sector may span several tag words, so a single tag value
     would misdescribe it. *)
  let qb = one ++ one in
  (match framed "dist_l sectors" (dist_l qb (qb ** qb) qb) with
   | None -> ()
   | Some r ->
     (match frame_of "dist_l out" r.Bridge.fr_output_frame with
      | None -> ()
      | Some f ->
        check "dist_l: two sectors round-trip"
          (List.length f.Bridge.f_sectors = 2);
        check "dist_l: sector indices, codes and tag words"
          (sector_summary f
           = [ (0, [0; 1; 4; 5], [0]);
               (1, [8; 9; 10; 11; 12; 13; 14; 15], [1]) ]);
        check "dist_l: sector logical types round-trip structurally"
          (List.map (fun s -> s.Bridge.sec_logical) f.Bridge.f_sectors
           = [ Some (tbool *. tbool); Some ((tbool *. tbool) *. tbool) ])));

  (* Ports, including a SECTOR-CONDITIONED placement: the summand payload
     sits on one wire in sector 0 and two wires in sector 1, which a fixed
     wire tuple cannot express. *)
  (match framed "dist_l ports" (dist_l qb (qb ** qb) qb) with
   | None -> ()
   | Some r ->
     (match frame_of "dist_l out" r.Bridge.fr_output_frame with
      | None -> ()
      | Some f ->
        check "dist_l: three ports round-trip" (List.length f.Bridge.f_ports = 3);
        (match port_named f "tag" with
         | None -> check "dist_l: tag port present" false
         | Some p ->
           check "dist_l: tag port placement and role"
             (p.Bridge.prt_wires = [0] && p.Bridge.prt_role = "tag"));
        (match port_named f "C" with
         | None -> check "dist_l: C port present" false
         | Some p ->
           check "dist_l: C port placement, role and logical type"
             (p.Bridge.prt_wires = [3] && p.Bridge.prt_role = "payload"
              && p.Bridge.prt_logical = Some tbool));
        (match port_named f "summand" with
         | None -> check "dist_l: summand port present" false
         | Some p ->
           check "dist_l: summand placement is sector-conditioned"
             (p.Bridge.prt_wires = []
              && p.Bridge.prt_by_sector = [ (0, [1]); (1, [1; 2]) ]);
           check "dist_l: summand port logical type round-trips"
             (p.Bridge.prt_logical = Some (tbool +. (tbool *. tbool))))));

  (* Exact phase transport: %f truncated pi to 1.0000001102657934. *)
  (match framed "phase pi" (phase (Complex.neg Complex.one) q) with
   | None -> ()
   | Some r ->
     let ph = r.Bridge.fr_global_phase in
     check (Printf.sprintf "phase pi survives exactly (got %.17g)" ph)
       (abs_float (ph -. 1.0) < 1e-12));

  Printf.printf "\n  framed bridge: %d passed, %d failed\n" !pass !fail;
  if !fail > 0 then exit 1
