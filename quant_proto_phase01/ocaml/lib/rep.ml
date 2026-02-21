(** Rep: Canonical representations for monoidal types.

    Types are built from:
    - Var i     : type variable (0-indexed)
    - Unit      : monoidal unit
    - Tensor    : tensor product (⊗)
    - Plus      : monoidal sum (+) -- NOT a coproduct

    These elaborate to the Phase 0-4C core IR.
*)

(** Type representation *)
type t =
  | Var of int
  | Unit
  | Tensor of t * t
  | Plus of t * t
  | Lolli of t * t   (* linear implication A ⊸ B *)

(** Smart constructors *)
let var i = Var i
let unit = Unit
let tensor a b = Tensor (a, b)
let plus a b = Plus (a, b)
let lolli a b = Lolli (a, b)

(** Infix operators for readability *)
let ( *@ ) = tensor
let ( +@ ) = plus

(** Count the number of wires (leaves) in a representation *)
let rec wire_count = function
  | Var _ -> 1
  | Unit -> 0
  | Tensor (a, b) -> (wire_count a) + (wire_count b)
  | Plus (a, b) -> (wire_count a) + (wire_count b)
  | Lolli (a, b) -> (wire_count a) + (wire_count b)

(** Collect all variable indices used *)
let rec vars = function
  | Var i -> [i]
  | Unit -> []
  | Tensor (a, b) | Plus (a, b) | Lolli (a, b) -> vars a @ vars b

(** Substitute variables according to a mapping *)
let rec subst mapping = function
  | Var i -> (try List.assoc i mapping with Not_found -> Var i)
  | Unit -> Unit
  | Tensor (a, b) -> Tensor (subst mapping a, subst mapping b)
  | Plus (a, b) -> Plus (subst mapping a, subst mapping b)
  | Lolli (a, b) -> Lolli (subst mapping a, subst mapping b)

(** Pretty-print a representation *)
let rec to_string = function
  | Var i -> Printf.sprintf "V%d" i
  | Unit -> "I"
  | Tensor (a, b) -> Printf.sprintf "(%s ⊗ %s)" (to_string a) (to_string b)
  | Plus (a, b) -> Printf.sprintf "(%s + %s)" (to_string a) (to_string b)
  | Lolli (a, b) -> Printf.sprintf "(%s ⊸ %s)" (to_string a) (to_string b)

(** Compute the canonical wire indices for each position in a rep.
    Returns a list of (path, wire_index) pairs where path encodes L/R choices. *)
type path = L | R

let rec wire_positions ?(prefix=[]) ?(offset=0) = function
  | Var _ -> [(List.rev prefix, offset)], offset + 1
  | Unit -> [], offset
  | Tensor (a, b) ->
    let pos_a, next = wire_positions ~prefix:(L :: prefix) ~offset a in
    let pos_b, final = wire_positions ~prefix:(R :: prefix) ~offset:next b in
    pos_a @ pos_b, final
  | Plus (a, b) ->
    let pos_a, next = wire_positions ~prefix:(L :: prefix) ~offset a in
    let pos_b, final = wire_positions ~prefix:(R :: prefix) ~offset:next b in
    pos_a @ pos_b, final
  | Lolli (a, b) ->
    let pos_a, next = wire_positions ~prefix:(L :: prefix) ~offset a in
    let pos_b, final = wire_positions ~prefix:(R :: prefix) ~offset:next b in
    pos_a @ pos_b, final

(** Equality check *)
let rec equal a b = match a, b with
  | Var i, Var j -> i = j
  | Unit, Unit -> true
  | Tensor (a1, a2), Tensor (b1, b2) -> equal a1 b1 && equal a2 b2
  | Plus (a1, a2), Plus (b1, b2) -> equal a1 b1 && equal a2 b2
  | Lolli (a1, a2), Lolli (b1, b2) -> equal a1 b1 && equal a2 b2
  | _ -> false
