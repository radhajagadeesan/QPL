(** Sealed programmer-facing presentation of Granthi's Source calculus.

    [Linear] remains the Raw implementation language.  This interface has no
    Raw injection, sum introduction, branchwise sum map, or unclassified
    operation constructor.  Every public sum is witnessed by [P.t], hence is
    wholly first-order. *)

type q
type qbool
type (!'a, !'b) tensor
type (!'a, !'b) plus
type (!'a, !'b) lolli

module P : sig
  type _ t

  val q : q t
  val qbool : qbool t
  val tensor : 'a t -> 'b t -> ('a, 'b) tensor t
  val plus : 'a t -> 'b t -> ('a, 'b) plus t

  val ( ** ) : 'a t -> 'b t -> ('a, 'b) tensor t
  val ( ++ ) : 'a t -> 'b t -> ('a, 'b) plus t
end

module S : sig
  type _ t

  val data : 'a P.t -> 'a t
  val tensor : 'a t -> 'b t -> ('a, 'b) tensor t
  val lolli : 'a t -> 'b t -> ('a, 'b) lolli t

  val ( ** ) : 'a t -> 'b t -> ('a, 'b) tensor t
  val ( -@ ) : 'a t -> 'b t -> ('a, 'b) lolli t
end

val q : q S.t
val qbool : qbool S.t

type empty
type (!'id, !'a, !'tail) cons
type (!'id, !'a) var
type (_, _) term

(** A total, disjoint partition of one ordered nominal context. *)
type (_, _, _) uses =
  | U0 : (empty, empty, empty) uses
  | UL : ('l, 'r, 'all) uses ->
      (('id, 'a, 'l) cons, 'r, ('id, 'a, 'all) cons) uses
  | UR : ('l, 'r, 'all) uses ->
      ('l, ('id, 'a, 'r) cons, ('id, 'a, 'all) cons) uses

val use : ('id, 'a) var -> (('id, 'a, empty) cons, 'a) term

val pair :
  ('g1, 'a) term ->
  ('g2, 'b) term ->
  ('g1, 'g2, 'g) uses ->
  ('g, ('a, 'b) tensor) term

(** Apply a Source function value.  Certified closed operations use
    [Op.apply], which retains their certification. *)
val app :
  ('g1, ('a, 'b) lolli) term ->
  ('g2, 'a) term ->
  ('g1, 'g2, 'g) uses ->
  ('g, 'b) term

val seq :
  ('g1, ('a, 'b) lolli) term ->
  ('g2, ('b, 'c) lolli) term ->
  ('g1, 'g2, 'g) uses ->
  ('g, ('a, 'c) lolli) term

(** Rank-2 binders give every lexical variable a fresh nominal identity. *)
type ('a, 'g, 'b) abstraction = {
  run_lam : 'id. ('id, 'a) var -> (('id, 'a, 'g) cons, 'b) term;
}

val lam :
  ?name:string ->
  'a S.t ->
  'b S.t ->
  ('a, 'g, 'b) abstraction ->
  ('g, ('a, 'b) lolli) term

(** Source tensor elimination: [let (x,y) = pair in body]. *)
type ('a, 'b, 'g, 'c) tensor_body = {
  run_split :
    'x 'y.
    ('x, 'a) var ->
    ('y, 'b) var ->
    (('x, 'a, ('y, 'b, 'g) cons) cons, 'c) term;
}

val let_tensor :
  ?left_name:string ->
  ?right_name:string ->
  'a S.t ->
  'b S.t ->
  ('g1, ('a, 'b) tensor) term ->
  ('a, 'b, 'g2, 'c) tensor_body ->
  ('g1, 'g2, 'g) uses ->
  ('g, 'c) term

val split :
  ?left_name:string ->
  ?right_name:string ->
  'a S.t ->
  'b S.t ->
  ('g1, ('a, 'b) tensor) term ->
  ('a, 'b, 'g2, 'c) tensor_body ->
  ('g1, 'g2, 'g) uses ->
  ('g, 'c) term

val let_pair :
  ?left_name:string ->
  ?right_name:string ->
  'a S.t ->
  'b S.t ->
  ('g1, ('a, 'b) tensor) term ->
  ('a, 'b, 'g2, 'c) tensor_body ->
  ('g1, 'g2, 'g) uses ->
  ('g, 'c) term

type ('a, 'b) op

module Op : sig
  val seal :
    domain:'a S.t ->
    codomain:'b S.t ->
    (empty, ('a, 'b) lolli) term ->
    ('a, 'b) op

  val value : ('a, 'b) op -> (empty, ('a, 'b) lolli) term
  val apply : ('a, 'b) op -> ('g, 'a) term -> ('g, 'b) term
  val id : 'a S.t -> ('a, 'a) op
  val compose : ('a, 'b) op -> ('b, 'c) op -> ('a, 'c) op
  val tensor : ('a, 'b) op -> ('c, 'd) op ->
    (('a, 'c) tensor, ('b, 'd) tensor) op

  (** Tensor coherence is definable at arbitrary Source types. *)
  val twist : 'a S.t -> 'b S.t ->
    (('a, 'b) tensor, ('b, 'a) tensor) op
  val assoc_left : 'a S.t -> 'b S.t -> 'c S.t ->
    ((('a, 'b) tensor, 'c) tensor, ('a, ('b, 'c) tensor) tensor) op
  val assoc_right : 'a S.t -> 'b S.t -> 'c S.t ->
    (('a, ('b, 'c) tensor) tensor, (('a, 'b) tensor, 'c) tensor) op

  (** Additive coherence and distributors are confined to [P] witnesses. *)
  val twist_plus : 'a P.t -> 'b P.t ->
    (('a, 'b) plus, ('b, 'a) plus) op
  val assoc_plus_left : 'a P.t -> 'b P.t -> 'c P.t ->
    ((('a, 'b) plus, 'c) plus, ('a, ('b, 'c) plus) plus) op
  val assoc_plus_right : 'a P.t -> 'b P.t -> 'c P.t ->
    (('a, ('b, 'c) plus) plus, (('a, 'b) plus, 'c) plus) op
  val dist_left : 'a P.t -> 'b P.t -> 'c P.t ->
    ((('a, 'b) plus, 'c) tensor,
     (('a, 'c) tensor, ('b, 'c) tensor) plus) op
  val dist_right : 'a P.t -> 'b P.t -> 'c P.t ->
    (('a, ('b, 'c) plus) tensor,
     (('a, 'b) tensor, ('a, 'c) tensor) plus) op
  val undist_left : 'a P.t -> 'b P.t -> 'c P.t ->
    ((('a, 'c) tensor, ('b, 'c) tensor) plus,
     (('a, 'b) plus, 'c) tensor) op
  val undist_right : 'a P.t -> 'b P.t -> 'c P.t ->
    ((('a, 'b) tensor, ('a, 'c) tensor) plus,
     ('a, ('b, 'c) plus) tensor) op

  val h : (q, q) op
  val s : (q, q) op
  val t : (q, q) op
  val x : (q, q) op
  val y : (q, q) op
  val z : (q, q) op
  val not_bool : (qbool, qbool) op
  val cx : ((q, q) tensor, (q, q) tensor) op
  val rz : float -> (q, q) op
  val phase : Complex.t -> 'a P.t -> ('a, 'a) op

  type 'a involution
  val involution_id : 'a P.t -> 'a involution
  val involution_h : q involution
  val involution_x : q involution
  val involution_y : q involution
  val involution_z : q involution
  val involution_cx : (q, q) tensor involution
  val involution_twist : 'a P.t -> ('a, 'a) tensor involution
  val involution_tensor : 'a involution -> 'b involution ->
    ('a, 'b) tensor involution
  val involution_plus : 'a involution -> 'b involution ->
    ('a, 'b) plus involution
  val exp_i : float -> 'a involution -> ('a, 'a) op
end

(** Nominal first-order control datatypes.  The constructor vector is the
    single arity authority: a declared five-way selector accepts exactly five
    certified endomorphisms.  Applications of [Make] are generative, even
    when their declarations have identical names and labels.  No injection,
    observation, or Raw representation is exposed. *)
module Datatype : sig
  type zero
  type !'n succ

  type (!'n, !'a) vector =
    | VNil : (zero, 'a) vector
    | VCons : 'a * ('n, 'a) vector -> ('n succ, 'a) vector

  val ( @: ) : 'a -> ('n, 'a) vector -> ('n succ, 'a) vector

  type n1 = zero succ
  type n2 = n1 succ
  type n3 = n2 succ
  type n4 = n3 succ
  type n5 = n4 succ
  type n6 = n5 succ
  type n7 = n6 succ
  type n8 = n7 succ

  module type SPEC = sig
    type tail
    val name : string
    val labels : (tail succ, string) vector
  end

  module Make (D : SPEC) () : sig
    type t
    type arity = D.tail succ

    val p : t P.t
    val s : t S.t
    val name : string
    val labels : string list
    val arity : int

    val select :
      target:'a P.t ->
      (arity, ('a, 'a) op) vector ->
      ((t, 'a) tensor, (t, 'a) tensor) op

    (** Exhaustive tag-preserving datatype case.  Branch order is
        declaration order; the tag survives in the result; every branch
        returns the same first-order type and consumes the identical
        complete nominal linear context.  The hidden representation is
        the canonical LEFT-associated expansion fixed by the clean
        calculus (bigplus_{i<=n} A_i := (bigplus_{i<n} A_i) ⊕ A_n), and
        dispatch is a single flat n-ary map over its leaf order. *)
    val cases :
      result:'c P.t ->
      scrutinee:('g1, t) term ->
      branches:(arity, (('id, 'x, 'tail) cons, 'c) term) vector ->
      using:('g1, ('id, 'x, 'tail) cons, 'g) uses ->
      ('g, (t, 'c) tensor) term

    (** Empty shared context is a separate clause, as with [case0]. *)
    val cases0 :
      result:'c P.t ->
      scrutinee:('g, t) term ->
      branches:(arity, (empty, 'c) term) vector ->
      ('g, (t, 'c) tensor) term

    (** Certified label permutation.  Position [i] carries the destination
        of constructor [i]: the forward convention |i⟩ ↦ |p(i)⟩.  Length is
        fixed by [arity]; range and bijectivity are validated eagerly; the
        padding states of a non-power-of-two arity are untouched.  Lowers
        through the existing trusted tag-permutation machinery; no
        injection, observation, or representation is exposed. *)
    val permute : (arity, int) vector -> (t, t) op

    (** [permute]'s checks plus the proof p(p(i)) = i.  A valid
        non-involutive permutation (a 3-cycle, say) is rejected here even
        though [permute] accepts it. *)
    val involution_permute : (arity, int) vector -> t Op.involution
  end
end

(** Tag-preserving Source case.  The branch types share the *same* context
    index [gamma], whose entries include fresh binder identities.  The routed
    summand binders are deliberately absent: the elaborator pairs the selected
    summand back automatically.  The context is packaged exactly once. *)
val case :
  left:'a P.t ->
  right:'b P.t ->
  result:'c P.t ->
  scrutinee:('g1, ('a, 'b) plus) term ->
  left_branch:(('id, 'x, 'tail) cons, 'c) term ->
  right_branch:(('id, 'x, 'tail) cons, 'c) term ->
  using:('g1, ('id, 'x, 'tail) cons, 'g) uses ->
  ('g, (('a, 'b) plus, 'c) tensor) term

(** Empty shared context is a separate clause; no public Source unit is used. *)
val case0 :
  left:'a P.t ->
  right:'b P.t ->
  result:'c P.t ->
  scrutinee:('g, ('a, 'b) plus) term ->
  left_branch:(empty, 'c) term ->
  right_branch:(empty, 'c) term ->
  ('g, (('a, 'b) plus, 'c) tensor) term

val case_bool :
  result:'c P.t ->
  scrutinee:('g1, qbool) term ->
  zero:(('id, 'x, 'tail) cons, 'c) term ->
  one_:(('id, 'x, 'tail) cons, 'c) term ->
  using:('g1, ('id, 'x, 'tail) cons, 'g) uses ->
  ('g, (qbool, 'c) tensor) term

val case_bool0 :
  result:'c P.t ->
  scrutinee:('g, qbool) term ->
  zero:(empty, 'c) term ->
  one_:(empty, 'c) term ->
  ('g, (qbool, 'c) tensor) term

(** The one-way, total Source-to-Raw expansion.  There is no inverse Raw
    coercion and no constructor accepting [Bridge.term]. *)
val emit : (empty, 'a) term -> Bridge.term
