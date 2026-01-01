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
  | TId of Rep.t
  | TSeq of term * term
  | TTenTerm of term * term
  | TTwistTen of Rep.t * Rep.t
  | TAssocTenL of Rep.t * Rep.t * Rep.t
  | TAssocTenR of Rep.t * Rep.t * Rep.t
  | TTwistPlus of Rep.t * Rep.t
  | TAssocPlusL of Rep.t * Rep.t * Rep.t
  | TAssocPlusR of Rep.t * Rep.t * Rep.t

(** Convert a term to JSON *)
let rec term_to_json = function
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
