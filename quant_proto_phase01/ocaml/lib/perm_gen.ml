(** Perm_gen: Generate structural terms for constructor permutations.

    For n-constructor datatypes, we represent the type as a left-associated
    (+) tree:
      2 constructors: A + B
      3 constructors: (A + B) + C
      4 constructors: ((A + B) + C) + D

    Any permutation of constructors can be achieved by composing:
    - TwistPlus: swap two summands
    - AssocPlusL/R: restructure the tree
    - TenTerm with Id: apply operation to subtree

    This module generates the minimal sequence of structural operations.
*)

(** A structural term to emit *)
type term =
  | TId of int                     (* Identity on n wires *)
  | TTwist of int * int            (* TwistPlus with left/right sizes *)
  | TAssocL of int * int * int     (* AssocPlusL with sizes a, b, c *)
  | TAssocR of int * int * int     (* AssocPlusR with sizes a, b, c *)
  | TSeq of term * term            (* Sequential composition *)
  | TTenLeft of term * int         (* Apply term to left of TenTerm, right is id of size *)
  | TTenRight of int * term        (* Apply term to right of TenTerm, left is id of size *)

(** Build type expression for n elements (left-associated) *)
let rec type_expr n start =
  if n = 1 then
    Printf.sprintf "ty_vars[%d]" start
  else
    Printf.sprintf "Plus(%s, ty_vars[%d])" (type_expr (n-1) start) (start + n - 1)

(** Convert term to Python code *)
let rec term_to_python = function
  | TId _ -> "Id(...)"  (* Will be simplified away *)
  | TTwist (left, right) ->
    Printf.sprintf "TwistPlus(%s, %s)"
      (type_expr left 0)
      (type_expr right left)
  | TAssocL (a, b, c) ->
    Printf.sprintf "AssocPlusL(%s, %s, %s)"
      (type_expr a 0)
      (type_expr b a)
      (type_expr c (a + b))
  | TAssocR (a, b, c) ->
    Printf.sprintf "AssocPlusR(%s, %s, %s)"
      (type_expr a 0)
      (type_expr b a)
      (type_expr c (a + b))
  | TSeq (f, g) ->
    Printf.sprintf "Seq(%s, %s)" (term_to_python f) (term_to_python g)
  | TTenLeft (f, _right_size) ->
    Printf.sprintf "TenTerm(%s, Id(...))" (term_to_python f)
  | TTenRight (_left_size, g) ->
    Printf.sprintf "TenTerm(Id(...), %s)" (term_to_python g)

(** Generate term to swap positions i and i+1 in left-associated tree of n elements.

    For a tree like ((A+B)+C)+D (positions 0,1,2,3):
    - swap(3, 2,3): twist at top = TwistPlus(((A+B)+C), D)
    - swap(3, 1,2): need to work inside left subtree
    - swap(3, 0,1): need to work deep inside

    Strategy: For swap at position i in tree of n:
    - If i = n-2: swap at top level
    - Otherwise: apply swap recursively to left subtree of size n-1
*)
let rec swap_at n i =
  if n < 2 then invalid_arg "swap_at: n must be >= 2";
  if i < 0 || i >= n - 1 then invalid_arg "swap_at: i out of range";

  if n = 2 then
    (* Base case: just twist *)
    TTwist (1, 1)
  else if i = n - 2 then
    (* Swap last two: twist at top level *)
    TTwist (n - 1, 1)
  else
    (* Need to swap within left subtree of size n-1 *)
    (* The tree is: (left_subtree) + last_element
       We apply the swap to left_subtree using TenTerm *)
    let inner = swap_at (n - 1) i in
    TTenLeft (inner, 1)

(** Simplify a term by removing identities and flattening sequences *)
let rec simplify = function
  | TId n -> TId n
  | TTwist (l, r) -> TTwist (l, r)
  | TAssocL (a, b, c) -> TAssocL (a, b, c)
  | TAssocR (a, b, c) -> TAssocR (a, b, c)
  | TSeq (TId _, g) -> simplify g
  | TSeq (f, TId _) -> simplify f
  | TSeq (f, g) ->
    let f' = simplify f in
    let g' = simplify g in
    (match f', g' with
     | TId _, _ -> g'
     | _, TId _ -> f'
     | TSeq (a, b), _ -> simplify (TSeq (a, TSeq (b, g')))
     | _ -> TSeq (f', g'))
  | TTenLeft (TId _, _) -> TId 0
  | TTenLeft (f, r) -> TTenLeft (simplify f, r)
  | TTenRight (_, TId _) -> TId 0
  | TTenRight (l, g) -> TTenRight (l, simplify g)

(** Decompose a permutation into adjacent transpositions using bubble sort *)
let decompose_permutation perm =
  let n = Array.length perm in
  let arr = Array.copy perm in
  let swaps = ref [] in

  for i = 0 to n - 2 do
    for j = 0 to n - 2 - i do
      if arr.(j) > arr.(j + 1) then begin
        let tmp = arr.(j) in
        arr.(j) <- arr.(j + 1);
        arr.(j + 1) <- tmp;
        swaps := j :: !swaps
      end
    done
  done;

  List.rev !swaps

(** Generate Python code for a complete permutation *)
let permutation_to_python ~n perm =
  if Array.length perm <> n then
    invalid_arg "permutation_to_python: perm length mismatch";

  (* Check if identity *)
  let is_identity = ref true in
  for i = 0 to n - 1 do
    if perm.(i) <> i then is_identity := false
  done;

  if !is_identity then
    Printf.sprintf "Id(make_type(*ty_vars))"
  else if n = 2 then
    "TwistPlus(ty_vars[0], ty_vars[1])"
  else begin
    (* Decompose into adjacent swaps *)
    let swaps = decompose_permutation perm in
    if swaps = [] then
      Printf.sprintf "Id(make_type(*ty_vars))"
    else begin
      (* Generate term for each swap and compose *)
      let terms = List.map (swap_at n) swaps in
      let combined = List.fold_left (fun acc t -> TSeq (acc, t)) (List.hd terms) (List.tl terms) in
      let simplified = simplify combined in
      term_to_python simplified
    end
  end

(** Build canonical left-associated representation for n constructors *)
let canonical_rep n =
  if n <= 0 then invalid_arg "canonical_rep: n must be positive";
  let rec build i =
    if i = 0 then Rep.var 0
    else Rep.plus (build (i - 1)) (Rep.var i)
  in
  build (n - 1)

(** Pretty-print the canonical representation *)
let canonical_rep_string n =
  Rep.to_string (canonical_rep n)
