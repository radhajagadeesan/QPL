(** Bridge: Call the Python Phase 0-4C compiler from OCaml.

    This module provides a subprocess-based bridge to the Python compiler.
    Terms are serialized to JSON, passed to bridge.py, and results parsed.
*)

(** Wire permutation result from Python *)
type wire_perm = {
  n : int;
  new_to_old : int list;
}

(** Compilation result *)
type compile_result =
  | CompileOk of wire_perm * int  (* perm, circuit_size *)
  | CompileError of string

(** Involution check result *)
type involution_result =
  | InvolutionOk of bool * wire_perm  (* is_invol, perm *)
  | InvolutionError of string

(** Path to bridge.py (relative to surface/) *)
let bridge_path = "bridge.py"

(** Path to Python interpreter *)
let python_path = "python3"

(** Path to project root (for activating venv) *)
let project_root = ref ""

(** Set the project root path *)
let set_project_root path = project_root := path

(** Convert a Rep.t to JSON type representation *)
let rec type_to_json = function
  | Rep.Var _ -> {|{"node": "Q"}|}  (* Variables become Q for now *)
  | Rep.Unit -> {|{"node": "Q"}|}   (* Unit becomes Q for now *)
  | Rep.Tensor (a, b) ->
    Printf.sprintf {|{"node": "Ten", "left": %s, "right": %s}|}
      (type_to_json a) (type_to_json b)
  | Rep.Plus (a, b) ->
    Printf.sprintf {|{"node": "Plus", "left": %s, "right": %s}|}
      (type_to_json a) (type_to_json b)

(** Term representation for JSON serialization *)
type term =
  (* Structural combinators *)
  | TId of Rep.t
  | TSeq of term * term
  | TTenTerm of term * term
  | TTwistTen of Rep.t * Rep.t
  | TAssocTenL of Rep.t * Rep.t * Rep.t
  | TAssocTenR of Rep.t * Rep.t * Rep.t
  | TTwistPlus of Rep.t * Rep.t
  | TAssocPlusL of Rep.t * Rep.t * Rep.t
  | TAssocPlusR of Rep.t * Rep.t * Rep.t
  (* Distributivity (unitary-level) *)
  | TDistL of Rep.t * Rep.t * Rep.t
  | TDistR of Rep.t * Rep.t * Rep.t
  (* Single-qubit gates *)
  | TH of int
  | TS of int
  | TSdg of int
  | TT of int
  | TTdg of int
  | TX of int
  | TY of int
  | TZ of int
  | TRx of float * int
  | TRy of float * int
  | TRz of float * int
  | TPhase of float * int
  (* Two-qubit gates *)
  | TCX of int * int
  | TCZ of int * int
  | TCRz of float * int * int
  (* Three-qubit gate *)
  | TCCX of int * int * int
  (* Controlled single-qubit gates for quantum case expressions *)
  | TCH of int * int
  | TCS of int * int
  | TCSdg of int * int

(** Convert a term to JSON *)
let rec term_to_json = function
  (* Structural combinators *)
  | TId ty ->
    Printf.sprintf {|{"node": "Id", "ty": %s}|} (type_to_json ty)
  | TSeq (f, g) ->
    Printf.sprintf {|{"node": "Seq", "f": %s, "g": %s}|}
      (term_to_json f) (term_to_json g)
  | TTenTerm (f, g) ->
    Printf.sprintf {|{"node": "TenTerm", "f": %s, "g": %s}|}
      (term_to_json f) (term_to_json g)
  | TTwistTen (a, b) ->
    Printf.sprintf {|{"node": "TwistTen", "a": %s, "b": %s}|}
      (type_to_json a) (type_to_json b)
  | TAssocTenL (a, b, c) ->
    Printf.sprintf {|{"node": "AssocTenL", "a": %s, "b": %s, "c": %s}|}
      (type_to_json a) (type_to_json b) (type_to_json c)
  | TAssocTenR (a, b, c) ->
    Printf.sprintf {|{"node": "AssocTenR", "a": %s, "b": %s, "c": %s}|}
      (type_to_json a) (type_to_json b) (type_to_json c)
  | TTwistPlus (a, b) ->
    Printf.sprintf {|{"node": "TwistPlus", "a": %s, "b": %s}|}
      (type_to_json a) (type_to_json b)
  | TAssocPlusL (a, b, c) ->
    Printf.sprintf {|{"node": "AssocPlusL", "a": %s, "b": %s, "c": %s}|}
      (type_to_json a) (type_to_json b) (type_to_json c)
  | TAssocPlusR (a, b, c) ->
    Printf.sprintf {|{"node": "AssocPlusR", "a": %s, "b": %s, "c": %s}|}
      (type_to_json a) (type_to_json b) (type_to_json c)
  (* Distributivity *)
  | TDistL (a, b, c) ->
    Printf.sprintf {|{"node": "DistL", "a": %s, "b": %s, "c": %s}|}
      (type_to_json a) (type_to_json b) (type_to_json c)
  | TDistR (a, b, c) ->
    Printf.sprintf {|{"node": "DistR", "a": %s, "b": %s, "c": %s}|}
      (type_to_json a) (type_to_json b) (type_to_json c)
  (* Single-qubit gates *)
  | TH i -> Printf.sprintf {|{"node": "H", "i": %d}|} i
  | TS i -> Printf.sprintf {|{"node": "S", "i": %d}|} i
  | TSdg i -> Printf.sprintf {|{"node": "Sdg", "i": %d}|} i
  | TT i -> Printf.sprintf {|{"node": "T", "i": %d}|} i
  | TTdg i -> Printf.sprintf {|{"node": "Tdg", "i": %d}|} i
  | TX i -> Printf.sprintf {|{"node": "X", "i": %d}|} i
  | TY i -> Printf.sprintf {|{"node": "Y", "i": %d}|} i
  | TZ i -> Printf.sprintf {|{"node": "Z", "i": %d}|} i
  | TRx (theta, i) -> Printf.sprintf {|{"node": "Rx", "theta": %f, "i": %d}|} theta i
  | TRy (theta, i) -> Printf.sprintf {|{"node": "Ry", "theta": %f, "i": %d}|} theta i
  | TRz (theta, i) -> Printf.sprintf {|{"node": "Rz", "theta": %f, "i": %d}|} theta i
  | TPhase (theta, i) -> Printf.sprintf {|{"node": "Phase", "theta": %f, "i": %d}|} theta i
  (* Two-qubit gates *)
  | TCX (i, j) -> Printf.sprintf {|{"node": "CX", "i": %d, "j": %d}|} i j
  | TCZ (i, j) -> Printf.sprintf {|{"node": "CZ", "i": %d, "j": %d}|} i j
  | TCRz (theta, i, j) -> Printf.sprintf {|{"node": "CRz", "theta": %f, "i": %d, "j": %d}|} theta i j
  (* Three-qubit gate *)
  | TCCX (i, j, k) -> Printf.sprintf {|{"node": "CCX", "i": %d, "j": %d, "k": %d}|} i j k
  (* Controlled single-qubit gates for quantum case expressions *)
  | TCH (i, j) -> Printf.sprintf {|{"node": "CH", "i": %d, "j": %d}|} i j
  | TCS (i, j) -> Printf.sprintf {|{"node": "CS", "i": %d, "j": %d}|} i j
  | TCSdg (i, j) -> Printf.sprintf {|{"node": "CSdg", "i": %d, "j": %d}|} i j

(** Simple JSON parsing helpers *)
let find_string key json =
  let pattern = Printf.sprintf {|"%s": "|} key in
  try
    let start = String.index json '"' in
    let json_from_key = String.sub json (String.index json (String.get pattern 0)) (String.length json - String.index json (String.get pattern 0)) in
    let _ = (start, json_from_key) in
    (* Simplified: look for "key": "value" or "key": value *)
    let re = Str.regexp (Printf.sprintf {|"%s": *"\([^"]*\)"|} key) in
    if Str.string_match re json 0 then
      Some (Str.matched_group 1 json)
    else
      let re2 = Str.regexp (Printf.sprintf {|"%s": *\([^,}]*\)|} key) in
      if Str.string_match re2 json 0 then
        Some (String.trim (Str.matched_group 1 json))
      else
        None
  with _ -> None

let find_bool key json =
  let re = Str.regexp (Printf.sprintf {|"%s": *\(true\|false\)|} key) in
  try
    let _ = Str.search_forward re json 0 in
    Some (Str.matched_group 1 json = "true")
  with Not_found -> None

let find_int key json =
  let re = Str.regexp (Printf.sprintf {|"%s": *\([0-9]+\)|} key) in
  try
    let _ = Str.search_forward re json 0 in
    Some (int_of_string (Str.matched_group 1 json))
  with Not_found -> None

let find_int_list key json =
  let re = Str.regexp (Printf.sprintf {|"%s": *\[\([0-9, ]*\)\]|} key) in
  try
    let _ = Str.search_forward re json 0 in
    let list_str = Str.matched_group 1 json in
    let parts = String.split_on_char ',' list_str in
    Some (List.map (fun s -> int_of_string (String.trim s)) parts)
  with _ -> None

(** Parse a wire_perm from JSON *)
let parse_perm json =
  match find_int "n" json, find_int_list "new_to_old" json with
  | Some n, Some new_to_old -> Some { n; new_to_old }
  | _ -> None

(** Call the Python bridge with a JSON request *)
let call_bridge request_json =
  let bridge_script = Filename.concat !project_root "surface/bridge.py" in
  let venv_python = Filename.concat !project_root "../venv/bin/python" in

  (* Write request to temp file *)
  let tmp_in = Filename.temp_file "qpl_bridge_" ".json" in
  let tmp_out = Filename.temp_file "qpl_bridge_" ".out" in

  let oc = open_out tmp_in in
  output_string oc request_json;
  close_out oc;

  (* Run python with temp file I/O *)
  let cmd = Printf.sprintf "%s %s < %s > %s 2>&1"
    venv_python bridge_script tmp_in tmp_out in
  let _ = Sys.command cmd in

  (* Read response *)
  let ic = open_in tmp_out in
  let len = in_channel_length ic in
  let output = really_input_string ic len in
  close_in ic;

  (* Cleanup *)
  Sys.remove tmp_in;
  Sys.remove tmp_out;

  String.trim output

(** Compile a term and return the wire permutation *)
let compile term =
  let term_json = term_to_json term in
  let request = Printf.sprintf {|{"type": "compile", "term": %s}|} term_json in

  let response = call_bridge request in

  match find_bool "success" response with
  | Some true ->
    (match parse_perm response, find_int "circuit_size" response with
     | Some perm, Some size -> CompileOk (perm, size)
     | _ -> CompileError "Failed to parse response")
  | Some false ->
    (match find_string "error" response with
     | Some err -> CompileError err
     | None -> CompileError "Unknown error")
  | None ->
    CompileError ("Invalid response: " ^ response)

(** Check if a term compiles to an involutive permutation *)
let check_involution term =
  let term_json = term_to_json term in
  let request = Printf.sprintf {|{"type": "check_involution", "term": %s}|} term_json in

  let response = call_bridge request in

  match find_bool "success" response with
  | Some true ->
    (match find_bool "is_involution" response, parse_perm response with
     | Some is_invol, Some perm -> InvolutionOk (is_invol, perm)
     | _ -> InvolutionError "Failed to parse response")
  | Some false ->
    (match find_string "error" response with
     | Some err -> InvolutionError err
     | None -> InvolutionError "Unknown error")
  | None ->
    InvolutionError ("Invalid response: " ^ response)

(** Helper: create a TwistPlus term for a 2-constructor datatype swap *)
let twist_plus_for_bool () =
  TTwistPlus (Rep.var 0, Rep.var 1)
