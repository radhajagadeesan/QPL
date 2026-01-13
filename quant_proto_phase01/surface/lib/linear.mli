(** Linear: Sealed staging DSL with GADT-enforced linear contexts.

    This module provides the [Prog(Γ, A)] abstraction where:
    - Γ is a linear context (type-level, tracked by OCaml's type system)
    - A is the object-language type

    Linearity is enforced by OCaml's type checker through context splitting.
    Every combinator corresponds to exactly one object-language typing rule.
*)

(** {1 Contexts}

    Contexts are represented as nested tuples at the type level:
    - [unit] represents the empty context ∅
    - ['a * 'g] represents context extension (x:A, Γ)

    Context splitting is enforced by the type signatures of combinators.
*)

(** {1 Types}

    Object-language type witnesses. Abstract to prevent forgery.
*)

type 'a ty

(** Qubit *)
val q : [`Q] ty

(** Unit type 1 *)
val one : [`One] ty

(** Tensor A ⊗ B *)
val ( ** ) : 'a ty -> 'b ty -> [`Tensor of 'a * 'b] ty

(** Sum A ⊕ B *)
val ( ++ ) : 'a ty -> 'b ty -> [`Plus of 'a * 'b] ty

(** Linear arrow A ⊸ B *)
val ( -@ ) : 'a ty -> 'b ty -> [`Lolli of 'a * 'b] ty

(** {1 Programs}

    [('g, 'a) prog] represents an object-language term of type ['a]
    with free linear variables described by context ['g].

    The representation is sealed - only the combinators below can construct values.
*)

type ('g, 'a) prog

(** {2 Variables} *)

(** The variable at the top of the context.
    [var : Prog(x:A, A)] *)
val var : ('a * unit, 'a) prog

(** Weaken: use a term in an extended context.
    If [p : Prog(Γ, A)] then [weaken p : Prog(x:B, Γ, A)].
    The new variable x is unused (but must be consumed elsewhere). *)
val weaken : ('g, 'a) prog -> ('b * 'g, 'a) prog

(** {2 Unit} *)

(** Unit introduction: [unit : Prog(∅, 1)] *)
val unit : (unit, [`One]) prog

(** Unit elimination: [letunit e1 e2 : Prog(Γ1 ⊎ Γ2, C)]
    where [e1 : Prog(Γ1, 1)] and [e2 : Prog(Γ2, C)] *)
val letunit : ('g1, [`One]) prog -> ('g2, 'c) prog -> ('g1 * 'g2, 'c) prog

(** {2 Tensor} *)

(** Tensor introduction: [pair e1 e2 : Prog(Γ1 ⊎ Γ2, A ⊗ B)]
    Context is split between the two components. *)
val pair : ('g1, 'a) prog -> ('g2, 'b) prog -> ('g1 * 'g2, [`Tensor of 'a * 'b]) prog

(** Tensor elimination: [letpair e1 (fun (x, y) -> e2)]
    Binds x:A and y:B in e2. *)
val letpair : ('g1, [`Tensor of 'a * 'b]) prog
           -> ('a * ('b * 'g2), 'c) prog
           -> ('g1 * 'g2, 'c) prog

(** {2 Linear Implication} *)

(** Lambda abstraction: [lam ty body]
    where [body : Prog(x:A, Γ, B)].
    [lam : Prog(x:A, Γ, B) -> Prog(Γ, A ⊸ B)]
    The bound variable x is at the top of the body's context. *)
val lam : 'a ty -> ('a * 'g, 'b) prog -> ('g, [`Lolli of 'a * 'b]) prog

(** Application: [app f e : Prog(Γ1 ⊎ Γ2, B)]
    Context is split between function and argument. *)
val app : ('g1, [`Lolli of 'a * 'b]) prog -> ('g2, 'a) prog -> ('g1 * 'g2, 'b) prog

(** {2 Sum (Monoidal ⊕)} *)

(** Bifunctorial action on sums: [omap f g : Prog(Γ1 ⊎ Γ2, (A⊕B) ⊸ (C⊕D))]
    where [f : Prog(Γ1, A ⊸ C)] and [g : Prog(Γ2, B ⊸ D)] *)
val omap : ('g1, [`Lolli of 'a * 'c]) prog
        -> ('g2, [`Lolli of 'b * 'd]) prog
        -> ('g1 * 'g2, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) prog

(** Case elimination (monoidal): [case scrut left right]
    Context is split: Γ0 for scrutinee, Γ1 for left branch, Γ2 for right.
    Returns a sum type C ⊕ D. *)
val case_ : ('g0, [`Plus of 'a * 'b]) prog
         -> ('a * 'g1, 'c) prog
         -> ('b * 'g2, 'd) prog
         -> ('g0 * ('g1 * 'g2), [`Plus of 'c * 'd]) prog

(** {2 Structural Isomorphisms (Closed)} *)

(** All structural isos are closed: [Prog(∅, A ⊸ A)] *)

val twist_tensor : 'a ty -> 'b ty -> (unit, [`Lolli of [`Tensor of 'a * 'b] * [`Tensor of 'b * 'a]]) prog
val twist_plus   : 'a ty -> 'b ty -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'b * 'a]]) prog

val assoc_tensor_l : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Tensor of [`Tensor of 'a * 'b] * 'c] * [`Tensor of 'a * [`Tensor of 'b * 'c]]]) prog
val assoc_tensor_r : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Tensor of 'a * [`Tensor of 'b * 'c]] * [`Tensor of [`Tensor of 'a * 'b] * 'c]]) prog

val dist_l : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Tensor of [`Plus of 'a * 'b] * 'c] * [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'c]]]) prog
val dist_r : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Tensor of 'a * [`Plus of 'b * 'c]] * [`Plus of [`Tensor of 'a * 'b] * [`Tensor of 'a * 'c]]]) prog

(** {2 Unitary Constants (Closed Endomorphisms)} *)

(** Primitive gates are closed endomorphisms: [Prog(∅, A ⊸ A)] *)

val gate_h : (unit, [`Lolli of [`Q] * [`Q]]) prog
val gate_s : (unit, [`Lolli of [`Q] * [`Q]]) prog
val gate_x : (unit, [`Lolli of [`Q] * [`Q]]) prog
val gate_y : (unit, [`Lolli of [`Q] * [`Q]]) prog
val gate_z : (unit, [`Lolli of [`Q] * [`Q]]) prog
val gate_t : (unit, [`Lolli of [`Q] * [`Q]]) prog

val gate_cx : (unit, [`Lolli of [`Tensor of [`Q] * [`Q]] * [`Tensor of [`Q] * [`Q]]]) prog

val gate_rz : float -> (unit, [`Lolli of [`Q] * [`Q]]) prog

(** {2 Composition (Derived)} *)

(** Identity on a type: [id ty : Prog(∅, A ⊸ A)] *)
val id : 'a ty -> (unit, [`Lolli of 'a * 'a]) prog

(** Sequential composition: [seq f g : Prog(Γ1 ⊎ Γ2, A ⊸ C)]
    where [f : Prog(Γ1, A ⊸ B)] and [g : Prog(Γ2, B ⊸ C)] *)
val seq : ('g1, [`Lolli of 'a * 'b]) prog
       -> ('g2, [`Lolli of 'b * 'c]) prog
       -> ('g1 * 'g2, [`Lolli of 'a * 'c]) prog

(** Closed sequential composition: [seq0 f g : Prog(∅, A ⊸ C)]
    Both f and g must be closed. *)
val seq0 : (unit, [`Lolli of 'a * 'b]) prog
        -> (unit, [`Lolli of 'b * 'c]) prog
        -> (unit, [`Lolli of 'a * 'c]) prog

(** Closed parallel composition: [par0 f g : Prog(∅, (A⊗C) ⊸ (B⊗D))]
    Both f and g must be closed. *)
val par0 : (unit, [`Lolli of 'a * 'b]) prog
        -> (unit, [`Lolli of 'c * 'd]) prog
        -> (unit, [`Lolli of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'd]]) prog

(** {1 Meta-level Combinators}

    These combinators use OCaml's recursion at the meta-level to generate
    object-level programs. All inputs and outputs are closed (context = unit).
*)

(** [iterate n ty f] generates f^n = f ; f ; ... ; f (n times).
    Returns [id ty] when n <= 0. *)
val iterate : int -> 'a ty
           -> (unit, [`Lolli of 'a * 'a]) prog
           -> (unit, [`Lolli of 'a * 'a]) prog

(** [fold ty fs] generates f₁ ; f₂ ; ... ; fₙ.
    Returns [id ty] when list is empty. *)
val fold : 'a ty
        -> (unit, [`Lolli of 'a * 'a]) prog list
        -> (unit, [`Lolli of 'a * 'a]) prog

(** [pow2 n ty f] generates f^(2^n) using repeated squaring.
    More efficient than [iterate (1 lsl n) ty f] for large n. *)
val pow2 : int -> 'a ty
        -> (unit, [`Lolli of 'a * 'a]) prog
        -> (unit, [`Lolli of 'a * 'a]) prog

(** [indexed_fold n ty gen] generates gen(0) ; gen(1) ; ... ; gen(n-1).
    Useful for parameterized gate sequences. *)
val indexed_fold : int -> 'a ty
                -> (int -> (unit, [`Lolli of 'a * 'a]) prog)
                -> (unit, [`Lolli of 'a * 'a]) prog

(** {1 Emission} *)

(** Emit a closed program to Bridge term for compilation. *)
val emit : (unit, 'a) prog -> Bridge.term

(** Emit with type witness for debugging. *)
val emit_typed : (unit, 'a) prog -> 'a ty -> Bridge.term
