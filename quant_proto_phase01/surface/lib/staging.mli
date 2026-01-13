(** Staging: OCaml as a meta-language for generating linear λ-calculus programs.

    This module provides a "tagless-final" style interface for constructing
    well-typed object-language terms. OCaml serves as the staging/host language
    where we can freely copy, iterate, and use recursion - all at the meta-level.

    The generated terms form a higher-order linear λ-calculus with:
    - Tensor (⊗), monoidal sum (+), linear function (⊸)
    - Quantum primitives (gates, exponentials of involutions)

    Key insight: OCaml combinators like [iterate], [fold], [pow2] generate
    object-language terms. The "copying" happens at the meta-level (OCaml),
    not in the object language where linearity is enforced.
*)

(** {1 Type Witnesses} *)

(** Abstract type witness for object-language types.
    Prevents fabrication of ill-formed types. *)
type 'a ty

(** Qubit type witness *)
val q : [`Q] ty

(** Unit type witness *)
val unit : [`Unit] ty

(** Tensor product type witness *)
val tensor : 'a ty -> 'b ty -> [`Tensor of 'a * 'b] ty

(** Sum type witness (monoidal, one-hot encoded) *)
val plus : 'a ty -> 'b ty -> [`Plus of 'a * 'b] ty

(** Linear function type witness *)
val lolli : 'a ty -> 'b ty -> [`Lolli of 'a * 'b] ty

(** {1 Object Language Terms} *)

(** Abstract term representation.
    Terms are well-typed by construction. *)
type 'a tm

(** {2 Structural Combinators} *)

(** Identity morphism *)
val id : 'a ty -> ('a -> 'a) tm

(** Sequential composition *)
val seq : ('a -> 'b) tm -> ('b -> 'c) tm -> ('a -> 'c) tm

(** Parallel composition (tensor of morphisms) *)
val par : ('a -> 'b) tm -> ('c -> 'd) tm -> ([`Tensor of 'a * 'c] -> [`Tensor of 'b * 'd]) tm

(** Tensor twist: A ⊗ B → B ⊗ A *)
val twist_ten : 'a ty -> 'b ty -> ([`Tensor of 'a * 'b] -> [`Tensor of 'b * 'a]) tm

(** Sum twist: A + B → B + A *)
val twist_plus : 'a ty -> 'b ty -> ([`Plus of 'a * 'b] -> [`Plus of 'b * 'a]) tm

(** Left tensor associativity: (A ⊗ B) ⊗ C → A ⊗ (B ⊗ C) *)
val assoc_ten_l : 'a ty -> 'b ty -> 'c ty ->
  ([`Tensor of [`Tensor of 'a * 'b] * 'c] -> [`Tensor of 'a * [`Tensor of 'b * 'c]]) tm

(** Right tensor associativity: A ⊗ (B ⊗ C) → (A ⊗ B) ⊗ C *)
val assoc_ten_r : 'a ty -> 'b ty -> 'c ty ->
  ([`Tensor of 'a * [`Tensor of 'b * 'c]] -> [`Tensor of [`Tensor of 'a * 'b] * 'c]) tm

(** Left sum associativity: (A + B) + C → A + (B + C) *)
val assoc_plus_l : 'a ty -> 'b ty -> 'c ty ->
  ([`Plus of [`Plus of 'a * 'b] * 'c] -> [`Plus of 'a * [`Plus of 'b * 'c]]) tm

(** Right sum associativity: A + (B + C) → (A + B) + C *)
val assoc_plus_r : 'a ty -> 'b ty -> 'c ty ->
  ([`Plus of 'a * [`Plus of 'b * 'c]] -> [`Plus of [`Plus of 'a * 'b] * 'c]) tm

(** Left distributivity: (A + B) ⊗ C → (A ⊗ C) + (B ⊗ C) *)
val dist_l : 'a ty -> 'b ty -> 'c ty ->
  ([`Tensor of [`Plus of 'a * 'b] * 'c] -> [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'c]]) tm

(** Right distributivity: A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C) *)
val dist_r : 'a ty -> 'b ty -> 'c ty ->
  ([`Tensor of 'a * [`Plus of 'b * 'c]] -> [`Plus of [`Tensor of 'a * 'b] * [`Tensor of 'a * 'c]]) tm

(** {2 Quantum Gates} *)

(** Hadamard gate on wire i *)
val h : int -> 'a ty -> ('a -> 'a) tm

(** Pauli-X gate on wire i *)
val x : int -> 'a ty -> ('a -> 'a) tm

(** Pauli-Y gate on wire i *)
val y : int -> 'a ty -> ('a -> 'a) tm

(** Pauli-Z gate on wire i *)
val z : int -> 'a ty -> ('a -> 'a) tm

(** S gate on wire i *)
val s : int -> 'a ty -> ('a -> 'a) tm

(** T gate on wire i *)
val t : int -> 'a ty -> ('a -> 'a) tm

(** Rz rotation on wire i *)
val rz : float -> int -> 'a ty -> ('a -> 'a) tm

(** CNOT gate (control i, target j) *)
val cx : int -> int -> 'a ty -> ('a -> 'a) tm

(** CZ gate (control i, target j) *)
val cz : int -> int -> 'a ty -> ('a -> 'a) tm

(** Toffoli gate (controls i,j, target k) *)
val ccx : int -> int -> int -> 'a ty -> ('a -> 'a) tm

(** {2 Exponentials of Involutions} *)

(** Involution witness - certifies P : A → A with P² = id *)
type 'a invol

(** Certify a term as an involution.
    Raises Failure if P² ≠ id. *)
val certify_invol : ('a -> 'a) tm -> 'a invol

(** Tensor twist as involution *)
val invol_twist_ten : 'a ty -> 'b ty -> [`Tensor of 'a * 'b] invol

(** Sum twist as involution *)
val invol_twist_plus : 'a ty -> 'b ty -> [`Plus of 'a * 'b] invol

(** Exponential of involution: exp(iθP) where P² = id *)
val exp_i : float -> 'a invol -> ('a -> 'a) tm

(** {1 Meta-Level Combinators (Staging)} *)

(** These are OCaml functions that GENERATE object-language terms.
    The iteration/recursion happens at the meta-level, producing
    well-typed object terms. *)

(** [iterate n ty f] generates f^n = f ; f ; ... ; f (n times).
    Returns identity on ty if n = 0. *)
val iterate : int -> 'a ty -> ('a -> 'a) tm -> ('a -> 'a) tm

(** [fold fs] generates f₁ ; f₂ ; ... ; fₙ.
    Returns identity if list is empty. *)
val fold : 'a ty -> ('a -> 'a) tm list -> ('a -> 'a) tm

(** [pow2 f] generates f² = f ; f (efficient for power-of-2 iteration). *)
val pow2 : ('a -> 'a) tm -> ('a -> 'a) tm

(** [power_of_2 n f] generates f^(2^n) using repeated squaring.
    More efficient than [iterate (1 lsl n) f] for large n. *)
val power_of_2 : int -> ('a -> 'a) tm -> ('a -> 'a) tm

(** [indexed_fold n gen] generates gen(0) ; gen(1) ; ... ; gen(n-1).
    The generator [gen] is called at the meta-level to produce each stage. *)
val indexed_fold : int -> 'a ty -> (int -> ('a -> 'a) tm) -> ('a -> 'a) tm

(** {1 Term Extraction} *)

(** Extract the underlying Bridge term for compilation *)
val to_bridge : 'a tm -> Bridge.term

(** Compile a term to a circuit *)
val compile : 'a tm -> Bridge.compile_result
