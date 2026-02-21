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

(** Path to bridge.py (relative to ocaml/) *)
let bridge_path = "bridge.py"

(** Path to Python interpreter *)
let python_path = "python3"

(** Path to project root (for activating venv) *)
let project_root = ref ""

(** Set the project root path *)
let set_project_root path = project_root := path

(** Auto-detect project root by searching upward for ocaml/bridge.py *)
let find_project_root () =
  let rec search dir =
    let candidate = Filename.concat (Filename.concat dir "ocaml") "bridge.py" in
    if Sys.file_exists candidate then dir
    else
      let parent = Filename.dirname dir in
      if parent = dir then ""  (* reached filesystem root, give up *)
      else search parent
  in
  search (Sys.getcwd ())

(** Get the project root, auto-detecting if not explicitly set *)
let get_project_root () =
  if !project_root = "" then begin
    let detected = find_project_root () in
    if detected <> "" then project_root := detected
  end;
  !project_root

(** Convert a Rep.t to JSON type representation *)
let rec type_to_json = function
  | Rep.Var _ -> {|{"node": "Q"}|}  (* Variables become Q for now *)
  | Rep.Unit -> {|{"node": "Unit"}|}
  | Rep.Tensor (a, b) ->
    Printf.sprintf {|{"node": "Ten", "left": %s, "right": %s}|}
      (type_to_json a) (type_to_json b)
  | Rep.Plus (a, b) ->
    Printf.sprintf {|{"node": "Plus", "left": %s, "right": %s}|}
      (type_to_json a) (type_to_json b)
  | Rep.Lolli (a, b) ->
    Printf.sprintf {|{"node": "Arrow", "dom": %s, "cod": %s}|}
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
  (* Inverse distributivity *)
  | TUndistL of Rep.t * Rep.t * Rep.t
  | TUndistR of Rep.t * Rep.t * Rep.t
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
  (* General multi-controlled gate (for nested cases) *)
  | TGate of string * int list * int list  (* gate_name, targets, controls *)
  (* Exponentials of structural involutions *)
  | TExpSwap of float * int * int  (* exp(iθ·SWAP) on wires i and j *)
  | TExpInvolution of float * term  (* exp(iθ·P) where P is involution *)
  (* Higher-order constructs (GOI apply) *)
  | TFunVar of string * Rep.t * Rep.t  (* function variable: x : A → B *)
  | TLam of string * Rep.t * Rep.t * term  (* lambda: λx:A→B. body *)
  | TApply of term * term  (* application: f arg, compiled via GOI *)
  (* Bifunctorial action on sums (⊕-Map) *)
  | TPlusMap of Rep.t * Rep.t * term * term  (* f ⊕ g : (A + B) → (C + D) *)
  (* Phase-weighted bifunctorial action: applies phase z to left branch *)
  | TPhasedPlusMap of float * Rep.t * Rep.t * term * term  (* phase θ, ty_left, ty_right, f, g *)
  (* Phase-weighted n-ary control: applies phase zᵢ to branch i *)
  | TPhasedControl of string * int * float list * Rep.t * Rep.t  (* name, arity, phases, dt_rep, a_ty *)
  (* N-ary bifunctorial action on sums *)
  | TNPlusMap of Rep.t array * term array  (* summand_types, branches *)
  (* Pattern-matching case on sums *)
  | TCase of Rep.t * Rep.t * term * term * term
  (* Full source language: variables, pairs, let-pair *)
  | TVar of string * Rep.t               (* variable reference *)
  | TPair of term * term                  (* tensor introduction *)
  | TLetPair of string * string * Rep.t * Rep.t * term * term  (* let (x,y) = t in u *)  (* case scrut of Left => left | Right => right *)

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
  (* Inverse distributivity *)
  | TUndistL (a, b, c) ->
    Printf.sprintf {|{"node": "UndistL", "a": %s, "b": %s, "c": %s}|}
      (type_to_json a) (type_to_json b) (type_to_json c)
  | TUndistR (a, b, c) ->
    Printf.sprintf {|{"node": "UndistR", "a": %s, "b": %s, "c": %s}|}
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
  (* General multi-controlled gate for nested cases *)
  | TGate (name, targets, controls) ->
    let targets_json = Printf.sprintf "[%s]" (String.concat ", " (List.map string_of_int targets)) in
    let controls_json = Printf.sprintf "[%s]" (String.concat ", " (List.map string_of_int controls)) in
    Printf.sprintf {|{"node": "Gate", "name": "%s", "targets": %s, "controls": %s}|}
      name targets_json controls_json
  (* Exponentials of structural involutions *)
  | TExpSwap (theta, i, j) ->
    Printf.sprintf {|{"node": "ExpSwap", "theta": %f, "i": %d, "j": %d}|} theta i j
  | TExpInvolution (theta, body) ->
    Printf.sprintf {|{"node": "ExpInvolution", "theta": %f, "body": %s}|}
      theta (term_to_json body)
  (* Higher-order constructs (GOI apply) *)
  | TFunVar (name, dom, cod) ->
    Printf.sprintf {|{"node": "FunVar", "name": "%s", "dom": %s, "cod": %s}|}
      name (type_to_json dom) (type_to_json cod)
  | TLam (name, dom, cod, body) ->
    Printf.sprintf {|{"node": "Lam", "name": "%s", "dom": %s, "cod": %s, "body": %s}|}
      name (type_to_json dom) (type_to_json cod) (term_to_json body)
  | TApply (f, arg) ->
    Printf.sprintf {|{"node": "Apply", "f": %s, "arg": %s}|}
      (term_to_json f) (term_to_json arg)
  (* Bifunctorial action on sums (⊕-Map) *)
  | TPlusMap (ty_left, ty_right, left, right) ->
    Printf.sprintf {|{"node": "PlusMap", "ty_left": %s, "ty_right": %s, "left": %s, "right": %s}|}
      (type_to_json ty_left) (type_to_json ty_right) (term_to_json left) (term_to_json right)
  (* Phase-weighted bifunctorial action *)
  | TPhasedPlusMap (theta, ty_left, ty_right, left, right) ->
    Printf.sprintf {|{"node": "PhasedPlusMap", "theta": %f, "ty_left": %s, "ty_right": %s, "left": %s, "right": %s}|}
      theta (type_to_json ty_left) (type_to_json ty_right) (term_to_json left) (term_to_json right)
  (* N-ary bifunctorial action on sums *)
  | TNPlusMap (summand_types, branches) ->
    let types_json = Printf.sprintf "[%s]"
      (String.concat ", " (Array.to_list (Array.map type_to_json summand_types))) in
    let branches_json = Printf.sprintf "[%s]"
      (String.concat ", " (Array.to_list (Array.map term_to_json branches))) in
    Printf.sprintf {|{"node": "NPlusMap", "summand_types": %s, "branches": %s}|}
      types_json branches_json
  (* Phase-weighted n-ary control *)
  | TPhasedControl (name, arity, phases, dt_rep, a_ty) ->
    let phases_json = Printf.sprintf "[%s]"
      (String.concat ", " (List.map (Printf.sprintf "%f") phases)) in
    Printf.sprintf {|{"node": "PhasedControl", "name": "%s", "arity": %d, "phases": %s, "dt_rep": %s, "a_ty": %s}|}
      name arity phases_json (type_to_json dt_rep) (type_to_json a_ty)
  (* Pattern-matching case on sums *)
  | TCase (ty_left, ty_right, scrut, left, right) ->
    Printf.sprintf {|{"node": "CaseExpr", "ty_left": %s, "ty_right": %s, "scrut": %s, "left": %s, "right": %s}|}
      (type_to_json ty_left) (type_to_json ty_right) (term_to_json scrut) (term_to_json left) (term_to_json right)
  (* Full source language *)
  | TVar (name, ty) ->
    Printf.sprintf {|{"node": "Var", "name": "%s", "ty": %s}|} name (type_to_json ty)
  | TPair (fst, snd) ->
    Printf.sprintf {|{"node": "Pair", "fst": %s, "snd": %s}|}
      (term_to_json fst) (term_to_json snd)
  | TLetPair (x, y, ty_x, ty_y, pair, body) ->
    Printf.sprintf {|{"node": "LetPair", "x": "%s", "y": "%s", "ty_x": %s, "ty_y": %s, "pair": %s, "body": %s}|}
      x y (type_to_json ty_x) (type_to_json ty_y) (term_to_json pair) (term_to_json body)

(** Simple JSON parsing helpers *)
let find_string key json =
  try
    let re = Str.regexp (Printf.sprintf {|"%s": *"\([^"]*\)"|} key) in
    let _ = Str.search_forward re json 0 in
    Some (Str.matched_group 1 json)
  with Not_found -> None

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

let find_float key json =
  let re = Str.regexp (Printf.sprintf {|"%s": *\([0-9.eE+-]+\)|} key) in
  try
    let _ = Str.search_forward re json 0 in
    Some (float_of_string (Str.matched_group 1 json))
  with _ -> None

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
  let root = get_project_root () in
  let bridge_script = Filename.concat root "ocaml/bridge.py" in
  let venv_python = Filename.concat root "../venv/bin/python" in
  let python =
    if Sys.file_exists venv_python then venv_python
    else "python3"
  in

  (* Write request to temp file *)
  let tmp_in = Filename.temp_file "qpl_bridge_" ".json" in
  let tmp_out = Filename.temp_file "qpl_bridge_" ".out" in

  let oc = open_out tmp_in in
  output_string oc request_json;
  close_out oc;

  (* Run python with temp file I/O *)
  let cmd = Printf.sprintf "PYTHONPATH=%s/src %s %s < %s > %s 2>&1"
    root python bridge_script tmp_in tmp_out in
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
     | None -> CompileError ("Unknown error in: " ^ String.sub response 0 (min 300 (String.length response))))
  | None ->
    CompileError ("Invalid response: " ^ String.sub response 0 (min 300 (String.length response)))

(** Compile a term, print the circuit gates, and return the result *)
let compile_show term =
  let term_json = term_to_json term in
  let request = Printf.sprintf {|{"type": "compile", "term": %s, "show_gates": true}|} term_json in

  let response = call_bridge request in

  match find_bool "success" response with
  | Some true ->
    (match find_string "circuit_text" response with
     | Some text ->
       let text = Str.global_replace (Str.regexp_string "\\n") "\n" text in
       Printf.printf "%s\n" text
     | None -> ());
    (match parse_perm response, find_int "circuit_size" response with
     | Some perm, Some size -> CompileOk (perm, size)
     | _ -> CompileError "Failed to parse response")
  | Some false ->
    (match find_string "error" response with
     | Some err ->
       Printf.printf "Compile error: %s\n" err;
       CompileError err
     | None ->
       Printf.printf "Unknown error\n";
       CompileError "Unknown error")
  | None ->
    Printf.printf "Invalid response\n";
    CompileError ("Invalid response: " ^ String.sub response 0 (min 300 (String.length response)))

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

(** Circuit equality result *)
type eq_circ_result =
  | EqCircOk of bool * float  (* equal, fidelity *)
  | EqCircError of string

(** Check if two terms compile to equal circuits (up to global phase) *)
let eq_circ term1 term2 =
  let term1_json = term_to_json term1 in
  let term2_json = term_to_json term2 in
  let request = Printf.sprintf {|{"type": "eq_circ", "term1": %s, "term2": %s}|}
    term1_json term2_json in

  let response = call_bridge request in

  match find_bool "success" response with
  | Some true ->
    (match find_bool "equal" response with
     | Some eq ->
       let fidelity = match find_float "fidelity" response with
         | Some f -> f
         | None -> 0.0
       in
       EqCircOk (eq, fidelity)
     | None -> EqCircError "Failed to parse equality result")
  | Some false ->
    (match find_string "error" response with
     | Some err -> EqCircError err
     | None -> EqCircError ("Unknown error in: " ^ String.sub response 0 (min 300 (String.length response))))
  | None ->
    EqCircError ("Invalid response: " ^ String.sub response 0 (min 300 (String.length response)))

(** Verify compiled term matches C^k(G) against mathematical reference.

    gate_re, gate_im: 2×2 real/imaginary parts of the gate matrix.
    n_controls: number of control qubits (k).
    Returns EqCircOk(equal, fidelity) or EqCircError(msg). *)
let verify_ctrl_unitary term gate_re gate_im n_controls =
  let json_row row =
    Printf.sprintf "[%s]"
      (String.concat ", " (List.map (Printf.sprintf "%.17g") row))
  in
  let json_matrix m =
    Printf.sprintf "[%s]"
      (String.concat ", " (List.map json_row m))
  in
  let term_json = term_to_json term in
  let request = Printf.sprintf
    {|{"type": "verify_ctrl_unitary", "term": %s, "gate_re": %s, "gate_im": %s, "n_controls": %d}|}
    term_json (json_matrix gate_re) (json_matrix gate_im) n_controls
  in

  let response = call_bridge request in

  match find_bool "success" response with
  | Some true ->
    (match find_bool "equal" response with
     | Some eq ->
       let fidelity = match find_float "fidelity" response with
         | Some f -> f
         | None -> 0.0
       in
       EqCircOk (eq, fidelity)
     | None -> EqCircError "Failed to parse equality result")
  | Some false ->
    (match find_string "error" response with
     | Some err -> EqCircError err
     | None -> EqCircError ("Unknown error in: " ^ String.sub response 0 (min 300 (String.length response))))
  | None ->
    EqCircError ("Invalid response: " ^ String.sub response 0 (min 300 (String.length response)))

(** Helper: create a TwistPlus term for a 2-constructor datatype swap *)
let twist_plus_for_bool () =
  TTwistPlus (Rep.var 0, Rep.var 1)
