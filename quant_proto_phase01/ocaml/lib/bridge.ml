(** Bridge: Call the Python Phase 0-4C compiler from OCaml.

    This module provides a subprocess-based bridge to the Python compiler.
    Terms are serialized to JSON, passed to bridge.py, and results parsed.
*)

(** Wire permutation result from Python *)
type wire_perm = {
  n : int;
  new_to_old : int list;
}

(** A logical type as reconstructed from the bridge payload.

    Parsing the type back into a tree is what makes the round-trip
    STRUCTURAL: comparing the raw JSON text would pass on a payload that
    merely looks similar, and would break on whitespace. *)
type ty_repr =
  | TUnit
  | TQ
  | TTen of ty_repr * ty_repr
  | TPlus of ty_repr * ty_repr
  | TArrow of ty_repr * ty_repr
  | TDual of ty_repr

(** A symbolic frame expression, reconstructed from the bridge payload. *)
type expr_repr =
  | EIdentity of int
  | EWirePerm of int list
  | ETensor of expr_repr * expr_repr
  | ESum of expr_repr list * int * int      (* parts, tag_bits, payload_bits *)
  | ETagCond of int * int list list         (* tag_bits, per_tag *)
  | ECompose of expr_repr * expr_repr
  | EOpaque of string

(** One summand's placement inside a sum frame. A sector may span SEVERAL
    tag words, so [sec_tag_values] is a list, not a single tag. *)
type sector = {
  sec_index : int;
  sec_logical : ty_repr option;
  sec_codes : int list;
  sec_tag_values : int list;
}

(** A sub-interface's placement. [prt_by_sector] is non-empty exactly when the
    placement is sector-conditioned (the port sits on different wires in
    different sectors), in which case [prt_wires] is empty. *)
type port = {
  prt_name : string;
  prt_logical : ty_repr option;
  prt_wires : int list;
  prt_role : string;
  prt_by_sector : (int * int list) list;
}

(** A boundary frame: the exact embedding of a semantic basis into the
    physical register. [f_codes] at position [i] is the physical basis index
    of the i-th valid semantic label. Authoritative -- [wire_perm] is an
    optimisation.

    The judgment type fixes the semantic space; the FRAME fixes the physical
    embedding. Both must survive the bridge intact -- codes and width alone
    do not determine the interface, so the logical type, the symbolic
    expression, the sectors and the ports all round-trip too. *)
type frame = {
  f_n_qubits : int;
  f_codes : int list;
  f_label : string;
  f_logical : ty_repr option;
  f_expr : expr_repr option;
  f_sectors : sector list;
  f_ports : port list;
}

(** Compilation result.

    Carries both boundary frames and the global phase, because a judgment
    type fixes the semantic space but not its physical embedding, and the
    backend circuit representation may discard phase. *)
type compile_result =
  | CompileOk of wire_perm * int  (* perm, circuit_size *)
  | CompileError of string

type framed_result = {
  fr_perm : wire_perm;
  fr_size : int;
  fr_input_frame : frame option;
  fr_output_frame : frame option;
  fr_global_phase : float;
}

type framed_compile_result =
  | FramedOk of framed_result
  | FramedError of string

(** Involution check result *)
type involution_result =
  | InvolutionOk of bool * wire_perm  (* is_invol, perm *)
  | InvolutionError of string

(** Path to bridge.py (relative to ocaml/) *)
let bridge_path = "bridge.py"

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
  (* Scalar phase: multiply amplitudes by z = e^{iθ}, semantics is z · I on ty.
     NOT to be confused with TRz / TPhase (per-wire relative phase gates). *)
  | TGlobalPhase of float * Rep.t
  (* Coherent control over an n-ary datatype: D (x) A -> D (x) A, tensor frame *)
  | TDatatypeControl of string * int * Rep.t * Rep.t * term array
  (* Coherent sum introduction: Block^sum_{alpha,beta}(R1, R2).
     Angles carry arg(alpha), arg(beta); |alpha| = |beta| = 1 is enforced at
     the smart constructor. NOT amplitude preparation. *)
  | TSum of float * float * term * term
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
  (* Wire-level identity between two types of equal width (n_dist/n_factor) *)
  | TWireIdentity of Rep.t * Rep.t
  (* Wire-level basis-state permutation (compiled via ToffoliBox) *)
  | TTagPerm of int list * Rep.t
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
  | TSum (alpha_theta, beta_theta, r1, r2) ->
    Printf.sprintf {|{"node": "Sum", "alpha_theta": %.17g, "beta_theta": %.17g, "left": %s, "right": %s}|}
      alpha_theta beta_theta (term_to_json r1) (term_to_json r2)
  | TDatatypeControl (name, arity, dt_rep, a_ty, branches) ->
    let branches_json = Printf.sprintf "[%s]"
      (String.concat ", " (Array.to_list (Array.map term_to_json branches))) in
    Printf.sprintf {|{"node": "DatatypeControl", "name": "%s", "arity": %d, "dt_rep": %s, "a_ty": %s, "branches": %s}|}
      name arity (type_to_json dt_rep) (type_to_json a_ty) branches_json
  | TGlobalPhase (theta, ty) ->
    Printf.sprintf {|{"node": "GlobalPhase", "theta": %.17g, "ty": %s}|}
      theta (type_to_json ty)
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
  | TWireIdentity (dom, cod) ->
    Printf.sprintf {|{"node": "WireIdentity", "dom": %s, "cod": %s}|}
      (type_to_json dom) (type_to_json cod)
  | TTagPerm (perm, ty) ->
    let perm_str = String.concat ", " (List.map string_of_int perm) in
    Printf.sprintf {|{"node": "TagPerm", "perm": [%s], "ty": %s}|}
      perm_str (type_to_json ty)
  (* Single-qubit gates *)
  | TH i -> Printf.sprintf {|{"node": "H", "i": %d}|} i
  | TS i -> Printf.sprintf {|{"node": "S", "i": %d}|} i
  | TSdg i -> Printf.sprintf {|{"node": "Sdg", "i": %d}|} i
  | TT i -> Printf.sprintf {|{"node": "T", "i": %d}|} i
  | TTdg i -> Printf.sprintf {|{"node": "Tdg", "i": %d}|} i
  | TX i -> Printf.sprintf {|{"node": "X", "i": %d}|} i
  | TY i -> Printf.sprintf {|{"node": "Y", "i": %d}|} i
  | TZ i -> Printf.sprintf {|{"node": "Z", "i": %d}|} i
  | TRx (theta, i) -> Printf.sprintf {|{"node": "Rx", "theta": %.17g, "i": %d}|} theta i
  | TRy (theta, i) -> Printf.sprintf {|{"node": "Ry", "theta": %.17g, "i": %d}|} theta i
  | TRz (theta, i) -> Printf.sprintf {|{"node": "Rz", "theta": %.17g, "i": %d}|} theta i
  | TPhase (theta, i) -> Printf.sprintf {|{"node": "Phase", "theta": %.17g, "i": %d}|} theta i
  (* Two-qubit gates *)
  | TCX (i, j) -> Printf.sprintf {|{"node": "CX", "i": %d, "j": %d}|} i j
  | TCZ (i, j) -> Printf.sprintf {|{"node": "CZ", "i": %d, "j": %d}|} i j
  | TCRz (theta, i, j) -> Printf.sprintf {|{"node": "CRz", "theta": %.17g, "i": %d, "j": %d}|} theta i j
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
    Printf.sprintf {|{"node": "ExpSwap", "theta": %.17g, "i": %d, "j": %d}|} theta i j
  | TExpInvolution (theta, body) ->
    Printf.sprintf {|{"node": "ExpInvolution", "theta": %.17g, "body": %s}|}
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
    Printf.sprintf {|{"node": "PhasedPlusMap", "theta": %.17g, "ty_left": %s, "ty_right": %s, "left": %s, "right": %s}|}
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
      (String.concat ", " (List.map (Printf.sprintf "%.17g") phases)) in
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

  Fun.protect ~finally:(fun () ->
    (try Sys.remove tmp_in with Sys_error _ -> ());
    (try Sys.remove tmp_out with Sys_error _ -> ())
  ) (fun () ->
    let oc = open_out tmp_in in
    output_string oc request_json;
    close_out oc;

    (* Run python with temp file I/O *)
    let cmd = Printf.sprintf "PYTHONPATH=%s/python/src %s %s < %s > %s 2>&1"
      root python bridge_script tmp_in tmp_out in
    let exit_code = Sys.command cmd in
    if exit_code <> 0 then
      failwith (Printf.sprintf "Bridge process failed with exit code %d" exit_code);

    (* Read response *)
    let ic = open_in tmp_out in
    let len = in_channel_length ic in
    let output = really_input_string ic len in
    close_in ic;

    String.trim output
  )

(** Parse an int list out of a JSON array field, e.g. "codes": [0, 2, 4] *)
let parse_int_list key json =
  try
    let re = Str.regexp (Printf.sprintf {|"%s": *\[\([^]]*\)\]|} key) in
    let _ = Str.search_forward re json 0 in
    let body = Str.matched_group 1 json in
    if String.trim body = "" then Some []
    else
      Some (List.map (fun s -> int_of_string (String.trim s))
              (String.split_on_char ',' body))
  with Not_found | Failure _ -> None

(** Raw text of the value of a TOP-LEVEL key of a JSON object.

    A flat regexp search is wrong here: in [Ten(Plus(..), Plus(..))] the first
    textual occurrence of ["right"] belongs to the nested LEFT subtree, so a
    flat search silently returns the wrong subterm. This walks the object at
    depth one and returns the value of the key at that level only. *)
let field key raw =
  let n = String.length raw in
  if n < 2 || raw.[0] <> '{' then None
  else begin
    let want = "\"" ^ key ^ "\"" in
    let wl = String.length want in
    let result = ref None in
    let depth = ref 0 and in_str = ref false and esc = ref false and i = ref 1 in
    while !result = None && !i < n - 1 do
      let ch = raw.[!i] in
      if !in_str then begin
        if !esc then esc := false
        else if ch = '\\' then esc := true
        else if ch = '"' then in_str := false
      end else if ch = '"' then begin
        if !depth = 0 && !i + wl <= n && String.sub raw !i wl = want then begin
          (* skip the key, then whitespace and the colon *)
          let j = ref (!i + wl) in
          while !j < n && (raw.[!j] = ' ' || raw.[!j] = ':') do incr j done;
          if !j < n then begin
            let c = raw.[!j] in
            if c = '{' || c = '[' then begin
              let closing = if c = '{' then '}' else ']' in
              let d = ref 0 and k = ref !j
              and s2 = ref false and e2 = ref false and stop = ref (-1) in
              while !stop < 0 && !k < n do
                let ck = raw.[!k] in
                if !s2 then begin
                  if !e2 then e2 := false
                  else if ck = '\\' then e2 := true
                  else if ck = '"' then s2 := false
                end
                else if ck = '"' then s2 := true
                else if ck = c then incr d
                else if ck = closing then
                  (decr d; if !d = 0 then stop := !k + 1);
                incr k
              done;
              if !stop > 0 then result := Some (String.sub raw !j (!stop - !j))
            end else begin
              (* scalar: up to the next top-level comma or the closing brace *)
              let k = ref !j and s2 = ref false and e2 = ref false
              and stop = ref (-1) in
              while !stop < 0 && !k < n do
                let ck = raw.[!k] in
                if !s2 then begin
                  if !e2 then e2 := false
                  else if ck = '\\' then e2 := true
                  else if ck = '"' then s2 := false
                end
                else if ck = '"' then s2 := true
                else if ck = ',' || ck = '}' then stop := !k;
                incr k
              done;
              let stop = if !stop < 0 then n - 1 else !stop in
              result := Some (String.trim (String.sub raw !j (stop - !j)))
            end
          end;
          (* consumed as a key; continue past it if unmatched *)
          i := !j - 1
        end else in_str := true
      end
      else if ch = '{' || ch = '[' then incr depth
      else if ch = '}' || ch = ']' then decr depth;
      incr i
    done;
    !result
  end

(** A top-level string field, unquoted. *)
let field_string key raw =
  match field key raw with
  | Some v when String.length v >= 2 && v.[0] = '"' ->
    Some (String.sub v 1 (String.length v - 2))
  | _ -> None

(** A top-level integer field. *)
let field_int key raw =
  match field key raw with
  | Some v -> int_of_string_opt (String.trim v)
  | None -> None

(** A top-level array of integers. *)
let field_int_list key raw =
  match field key raw with
  | None -> None
  | Some v ->
    let body = String.sub v 1 (String.length v - 2) in
    if String.trim body = "" then Some []
    else
      (try Some (List.map (fun x -> int_of_string (String.trim x))
                   (String.split_on_char ',' body))
       with Failure _ -> None)

(** Split a raw JSON array into the raw text of its elements. *)
let split_array raw =
  let n = String.length raw in
  if n < 2 then []
  else begin
    let body_start = 1 and body_stop = n - 1 in
    let out = ref [] and buf = Buffer.create 64 in
    let depth = ref 0 and in_str = ref false and esc = ref false in
    for i = body_start to body_stop - 1 do
      let ch = raw.[i] in
      let boundary =
        if !in_str then begin
          (if !esc then esc := false
           else if ch = '\\' then esc := true
           else if ch = '"' then in_str := false);
          false
        end else if ch = '"' then (in_str := true; false)
        else if ch = '{' || ch = '[' then (incr depth; false)
        else if ch = '}' || ch = ']' then (decr depth; false)
        else ch = ',' && !depth = 0
      in
      if boundary then begin
        out := Buffer.contents buf :: !out; Buffer.clear buf
      end else Buffer.add_char buf ch
    done;
    let last = String.trim (Buffer.contents buf) in
    let all = if last = "" then !out else last :: !out in
    List.rev_map String.trim all |> List.rev |> List.rev
  end

(** Reconstruct a logical type from its serialized form. *)
let rec parse_ty raw =
  match field_string "node" raw with
  | None -> None
  | Some "Unit" -> Some TUnit
  | Some "Q" -> Some TQ
  | Some (("Ten" | "Plus") as node) ->
    (match field "left" raw, field "right" raw with
     | Some l, Some r ->
       (match parse_ty l, parse_ty r with
        | Some l', Some r' ->
          Some (if node = "Ten" then TTen (l', r') else TPlus (l', r'))
        | _ -> None)
     | _ -> None)
  | Some "Arrow" ->
    (match field "dom" raw, field "cod" raw with
     | Some d, Some c ->
       (match parse_ty d, parse_ty c with
        | Some d', Some c' -> Some (TArrow (d', c'))
        | _ -> None)
     | _ -> None)
  | Some "Dual" ->
    (match field "ty" raw with
     | Some t -> (match parse_ty t with Some t' -> Some (TDual t') | None -> None)
     | None -> None)
  | Some _ -> None

(** Reconstruct a symbolic frame expression from its serialized form. *)
let rec parse_expr raw =
  match field_string "k" raw with
  | None -> None
  | Some "identity" ->
    (match field_int "n" raw with Some n -> Some (EIdentity n) | None -> None)
  | Some "wireperm" ->
    (match field_int_list "new_to_old" raw with
     | Some p -> Some (EWirePerm p) | None -> None)
  | Some "tensor" ->
    (match field "left" raw, field "right" raw with
     | Some l, Some r ->
       (match parse_expr l, parse_expr r with
        | Some l', Some r' -> Some (ETensor (l', r'))
        | _ -> None)
     | _ -> None)
  | Some "compose" ->
    (match field "first" raw, field "second" raw with
     | Some a, Some b ->
       (match parse_expr a, parse_expr b with
        | Some a', Some b' -> Some (ECompose (a', b'))
        | _ -> None)
     | _ -> None)
  | Some "sum" ->
    (match field "parts" raw, field_int "tag_bits" raw,
           field_int "payload_bits" raw with
     | Some arr, Some tb, Some pb ->
       let parts = List.map parse_expr (split_array arr) in
       if List.exists (fun x -> x = None) parts then None
       else Some (ESum (List.filter_map (fun x -> x) parts, tb, pb))
     | _ -> None)
  | Some "tagcond" ->
    (match field "per_tag" raw, field_int "tag_bits" raw with
     | Some arr, Some tb ->
       Some (ETagCond (tb,
                       List.map
                         (fun e ->
                            List.filter_map
                              (fun x -> int_of_string_opt (String.trim x))
                              (split_array e))
                         (split_array arr)))
     | _ -> None)
  | Some "opaque" ->
    Some (EOpaque (match field_string "note" raw with Some n -> n | None -> ""))
  | Some _ -> None

let parse_sector raw =
  { sec_index = (match field_int "index" raw with Some v -> v | None -> -1);
    sec_logical = (match field "logical" raw with
                   | Some v -> parse_ty v | None -> None);
    sec_codes = (match field_int_list "codes" raw with Some c -> c | None -> []);
    sec_tag_values =
      (match field_int_list "tag_values" raw with Some t -> t | None -> []) }

let parse_port raw =
  let by_sector =
    match field "by_sector" raw with
    | None -> []
    | Some arr ->
      List.filter_map
        (fun elt ->
           (* each element is [tag, [wires...]] *)
           match split_array elt with
           | tag :: rest ->
             (try
                let t = int_of_string (String.trim tag) in
                let ws = match rest with
                  | [w] ->
                    List.filter_map
                      (fun x -> int_of_string_opt (String.trim x))
                      (split_array (String.trim w))
                  | _ -> []
                in
                Some (t, ws)
              with Failure _ -> None)
           | [] -> None)
        (split_array arr)
  in
  { prt_name = (match field_string "name" raw with Some v -> v | None -> "");
    prt_logical = (match field "logical" raw with
                   | Some v -> parse_ty v | None -> None);
    prt_wires = (match field_int_list "wires" raw with Some w -> w | None -> []);
    prt_role = (match field_string "role" raw with Some v -> v | None -> "");
    prt_by_sector = by_sector }

(** Parse one frame object out of the response, keyed by its field name. *)
let parse_frame key json =
  try
    let re = Str.regexp (Printf.sprintf {|"%s": *{|} key) in
    let start = Str.search_forward re json 0 in
    (* take the balanced object following the key *)
    let rec scan i depth =
      if i >= String.length json then None
      else match json.[i] with
        | '{' -> scan (i + 1) (depth + 1)
        | '}' -> if depth = 1 then Some (i + 1) else scan (i + 1) (depth - 1)
        | _ -> scan (i + 1) depth
    in
    let obj_start = Str.search_forward (Str.regexp "{") json start in
    match scan obj_start 0 with
    | None -> None
    | Some obj_end ->
      let obj = String.sub json obj_start (obj_end - obj_start) in
      let n = match field_int "n_qubits" obj with Some v -> v | None -> 0 in
      let codes = match field_int_list "codes" obj with Some c -> c | None -> [] in
      let label = match field_string "label" obj with Some l -> l | None -> "" in
      let logical = match field "logical" obj with
        | Some v -> parse_ty v | None -> None in
      let expr = match field "expr" obj with
        | Some v -> parse_expr v | None -> None in
      let sectors = match field "sectors" obj with
        | None -> []
        | Some arr -> List.map parse_sector (split_array arr) in
      let ports = match field "ports" obj with
        | None -> []
        | Some arr -> List.map parse_port (split_array arr) in
      Some { f_n_qubits = n; f_codes = codes; f_label = label;
             f_logical = logical; f_expr = expr;
             f_sectors = sectors; f_ports = ports }
  with Not_found -> None

(** Compile a term and return the full framed artifact: both boundary frames
    and the global phase, not only the perm. *)
let compile_framed term =
  let term_json = term_to_json term in
  let request = Printf.sprintf {|{"type": "compile", "term": %s}|} term_json in
  let response = call_bridge request in
  match find_bool "success" response with
  | Some true ->
    (match parse_perm response, find_int "circuit_size" response with
     | Some perm, Some size ->
       let phase = match find_float "global_phase" response with
         | Some f -> f | None -> 0.0 in
       (* A successful framed response must carry BOTH frames and the phase;
          a missing field is an error, not a silent default. *)
       (match parse_frame "input_frame" response,
              parse_frame "output_frame" response,
              find_float "global_phase" response with
        | Some fi, Some fo, Some _ ->
          FramedOk { fr_perm = perm; fr_size = size;
                     fr_input_frame = Some fi; fr_output_frame = Some fo;
                     fr_global_phase = phase }
        | _ ->
          FramedError "framed response is missing a frame or the global phase")
     | _ -> FramedError "Failed to parse framed response")
  | Some false ->
    (match find_string "error" response with
     | Some err -> FramedError err
     | None -> FramedError "Unknown error")
  | None -> FramedError "Invalid response"

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

(** Compile a term with materialize=True, print the circuit gates, and return the result.
    materialize=True forces structural isomorphisms (twists, etc.) to emit real SWAP gates
    rather than accumulate as symbolic wire permutations. Useful for backend-level testing. *)
let compile_show_materialized term =
  let term_json = term_to_json term in
  let request = Printf.sprintf
    {|{"type": "compile", "term": %s, "show_gates": true, "materialize": true}|}
    term_json in

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

(** Compare circuits on a subspace (auto-detect visible wires).

    term1 is a larger circuit (n qubits), term2 is a reference (m qubits).
    Tries all C(n,m) wire combinations to find which m wires of term1
    act like term2 (with remaining wires initialized to |0⟩).
    Returns EqCircOk(equal, fidelity) or EqCircError. *)
let eq_circ_partial term1 term2 =
  let term1_json = term_to_json term1 in
  let term2_json = term_to_json term2 in
  let request = Printf.sprintf
    {|{"type": "eq_circ_partial", "term1": %s, "term2": %s, "visible_wires": "auto"}|}
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
     | None -> EqCircError ("Unknown error"))
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
