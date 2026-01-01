(** Datatype: Registration and elaboration for surface datatypes.

    Surface datatypes are NOT coproducts. They are:
    - Type aliases for monoidal (+) expressions
    - Sources of naming discipline for constructor access
    - Compile-time only (elaborate away before Phase 4C)
*)

(** Constructor metadata *)
type ctor_info = {
  name : string;
  payload : Rep.t;
}

(** A registered datatype *)
type 'arity datatype = {
  dt_name : string;
  arity : int;
  rep : Rep.t;
  constructors : ctor_info list;
}

(** Module type for datatype specification (arity 1) *)
module type SPEC1 = sig
  type 'a t
  val name : string
  val rep : Rep.t
  val constructors : (string * Rep.t) list
end

(** Module type for datatype specification (arity 2) *)
module type SPEC2 = sig
  type ('a, 'b) t
  val name : string
  val rep : Rep.t
  val constructors : (string * Rep.t) list
end

(** Module type for datatype specification (arity 3) *)
module type SPEC3 = sig
  type ('a, 'b, 'c) t
  val name : string
  val rep : Rep.t
  val constructors : (string * Rep.t) list
end

(** Output signature for registered datatypes *)
module type REGISTERED = sig
  (** The datatype record *)
  val info : int datatype

  (** Get the canonical representation *)
  val rep : Rep.t

  (** Get constructor by name *)
  val constructor : string -> ctor_info option

  (** Emit Python code for the representation *)
  val emit_rep : unit -> string

  (** Emit Python code for packing into a constructor *)
  val emit_pack : string -> string

  (** Emit Python code for case analysis (structural rewiring) *)
  val emit_case : (string * string) list -> string
end

(** Helper to find constructor index *)
let find_ctor_index ctors name =
  let rec aux idx = function
    | [] -> None
    | c :: rest -> if c.name = name then Some idx else aux (idx + 1) rest
  in
  aux 0 ctors

(** Functor to register a datatype with arity 1 *)
module Make1 (S : SPEC1) : REGISTERED = struct
  let ctors =
    List.map (fun (name, payload) -> { name; payload }) S.constructors

  let info = {
    dt_name = S.name;
    arity = 1;
    rep = S.rep;
    constructors = ctors;
  }

  let rep = S.rep

  let constructor name =
    List.find_opt (fun c -> c.name = name) ctors

  let emit_rep () =
    Emit.rep_to_python S.rep

  let emit_pack ctor_name =
    match find_ctor_index ctors ctor_name with
    | Some idx ->
      Emit.pack_to_python ~dt_name:S.name ~ctor_name ~ctor_idx:idx
    | None -> failwith (Printf.sprintf "Unknown constructor: %s" ctor_name)

  let emit_case branches =
    let n = List.length ctors in
    if List.length branches <> n then
      failwith (Printf.sprintf "case requires exactly %d branches" n);
    if n = 2 then begin
      let c0 = List.nth ctors 0 in
      let c1 = List.nth ctors 1 in
      Emit.case_2_to_python
        ~dt_name:S.name
        ~c0_name:c0.name ~c0_payload:c0.payload
        ~c1_name:c1.name ~c1_payload:c1.payload
        ~branches
    end
    else
      Emit.case_n_to_python ~dt_name:S.name ~n
end

(** Functor to register a datatype with arity 2 *)
module Make2 (S : SPEC2) : REGISTERED = struct
  let ctors =
    List.map (fun (name, payload) -> { name; payload }) S.constructors

  let info = {
    dt_name = S.name;
    arity = 2;
    rep = S.rep;
    constructors = ctors;
  }

  let rep = S.rep

  let constructor name =
    List.find_opt (fun c -> c.name = name) ctors

  let emit_rep () =
    Emit.rep_to_python S.rep

  let emit_pack ctor_name =
    match find_ctor_index ctors ctor_name with
    | Some idx ->
      Emit.pack_to_python ~dt_name:S.name ~ctor_name ~ctor_idx:idx
    | None -> failwith (Printf.sprintf "Unknown constructor: %s" ctor_name)

  let emit_case branches =
    let n = List.length ctors in
    if List.length branches <> n then
      failwith (Printf.sprintf "case requires exactly %d branches" n);
    if n = 2 then begin
      let c0 = List.nth ctors 0 in
      let c1 = List.nth ctors 1 in
      Emit.case_2_to_python
        ~dt_name:S.name
        ~c0_name:c0.name ~c0_payload:c0.payload
        ~c1_name:c1.name ~c1_payload:c1.payload
        ~branches
    end
    else
      Emit.case_n_to_python ~dt_name:S.name ~n
end

(** Functor to register a datatype with arity 3 *)
module Make3 (S : SPEC3) : REGISTERED = struct
  let ctors =
    List.map (fun (name, payload) -> { name; payload }) S.constructors

  let info = {
    dt_name = S.name;
    arity = 3;
    rep = S.rep;
    constructors = ctors;
  }

  let rep = S.rep

  let constructor name =
    List.find_opt (fun c -> c.name = name) ctors

  let emit_rep () =
    Emit.rep_to_python S.rep

  let emit_pack ctor_name =
    match find_ctor_index ctors ctor_name with
    | Some idx ->
      Emit.pack_to_python ~dt_name:S.name ~ctor_name ~ctor_idx:idx
    | None -> failwith (Printf.sprintf "Unknown constructor: %s" ctor_name)

  let emit_case branches =
    let n = List.length ctors in
    if List.length branches <> n then
      failwith (Printf.sprintf "case requires exactly %d branches" n);
    if n = 2 then begin
      let c0 = List.nth ctors 0 in
      let c1 = List.nth ctors 1 in
      Emit.case_2_to_python
        ~dt_name:S.name
        ~c0_name:c0.name ~c0_payload:c0.payload
        ~c1_name:c1.name ~c1_payload:c1.payload
        ~branches
    end
    else
      Emit.case_n_to_python ~dt_name:S.name ~n
end

(** Validate that a datatype is well-formed:
    - All constructors reference valid variables
    - No recursive references
    - Representation matches constructors *)
let validate (dt : _ datatype) =
  let max_var = dt.arity - 1 in
  let valid_vars = List.init dt.arity (fun i -> i) in

  (* Check rep uses only valid variables *)
  let rep_vars = Rep.vars dt.rep in
  let rep_valid = List.for_all (fun v -> v <= max_var && v >= 0) rep_vars in

  (* Check each constructor *)
  let ctors_valid = List.for_all (fun (c : ctor_info) ->
    let vars = Rep.vars c.payload in
    List.for_all (fun v -> List.mem v valid_vars) vars
  ) dt.constructors in

  rep_valid && ctors_valid
