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

(** Extract the underlying Rep.t from a type witness *)
val ty_to_rep : 'a ty -> Rep.t

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

(** Lambda abstraction: [lam dom cod body]
    where [body : Prog(x:A, Γ, B)].
    [lam : Prog(x:A, Γ, B) -> Prog(Γ, A ⊸ B)]
    The bound variable x is at the top of the body's context.
    Both domain and codomain types are required for correct emission. *)
val lam : 'a ty -> 'b ty -> ('a * 'g, 'b) prog -> ('g, [`Lolli of 'a * 'b]) prog

(** Application: [app f e : Prog(Γ1 ⊎ Γ2, B)]
    Context is split between function and argument. *)
val app : ('g1, [`Lolli of 'a * 'b]) prog -> ('g2, 'a) prog -> ('g1 * 'g2, 'b) prog

(** {2 Sum (Monoidal ⊕)} *)

(** Bifunctorial action on sums: [omap ty_left ty_right f g : Prog(Γ1 ⊎ Γ2, (A⊕B) ⊸ (C⊕D))]
    where [f : Prog(Γ1, A ⊸ C)] and [g : Prog(Γ2, B ⊸ D)].
    Type witnesses are required for correct PlusMap emission. *)
val omap : 'a ty -> 'b ty
        -> ('g1, [`Lolli of 'a * 'c]) prog
        -> ('g2, [`Lolli of 'b * 'd]) prog
        -> ('g1 * 'g2, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) prog

(** Case elimination (monoidal): [case_ ty_left ty_right scrut left right]
    Context is split: Γ0 for scrutinee, Γ1 for left branch, Γ2 for right.
    ty_left and ty_right are type witnesses for A and B (needed for emission).
    Returns a sum type C ⊕ D. *)
val case_ : 'a ty -> 'b ty
         -> ('g0, [`Plus of 'a * 'b]) prog
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

val assoc_plus_l : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Plus of [`Plus of 'a * 'b] * 'c] * [`Plus of 'a * [`Plus of 'b * 'c]]]) prog
val assoc_plus_r : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Plus of 'a * [`Plus of 'b * 'c]] * [`Plus of [`Plus of 'a * 'b] * 'c]]) prog

val dist_l : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Tensor of [`Plus of 'a * 'b] * 'c] * [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'c]]]) prog
val dist_r : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Tensor of 'a * [`Plus of 'b * 'c]] * [`Plus of [`Tensor of 'a * 'b] * [`Tensor of 'a * 'c]]]) prog

val undist_l : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'c]] * [`Tensor of [`Plus of 'a * 'b] * 'c]]) prog
val undist_r : 'a ty -> 'b ty -> 'c ty ->
  (unit, [`Lolli of [`Plus of [`Tensor of 'a * 'b] * [`Tensor of 'a * 'c]] * [`Tensor of 'a * [`Plus of 'b * 'c]]]) prog

(** n-ary distributivity: Z_n ⊗ A ⊸ ⊕^n (b ⊗ A).

    Takes the summand input types [|s_1; ...; s_n|] and the data type b.
    Returns a closed morphism from [(Plus s_1 (Plus s_2 ...)) ⊗ b] to
    [Plus (s_1 ⊗ b) (Plus (s_2 ⊗ b) ...)].

    At the wire level this is identity (both forms share the flat n-ary
    encoding); compiles to zero gates. Use this for n-ary case analysis
    where you want to write [n_dist ; n-ary plusmap ; n_factor] explicitly
    (e.g., matching the user's curried select formula). *)
val n_dist : 'a ty array -> 'b ty
          -> (unit, [`Lolli of 'in_ty * 'out_ty]) prog

(** n-ary inverse distributivity (factor): ⊕^n (b ⊗ A) ⊸ Z_n ⊗ A.
    Inverse of [n_dist]; also identity at the wire level. *)
val n_factor : 'a ty array -> 'b ty
            -> (unit, [`Lolli of 'in_ty * 'out_ty]) prog

(** Wire-level basis-state permutation on a fixed-width type [ty].
    Maps |i⟩ → |perm.(i)⟩ for i < len(perm); identity on unused states.
    Compiled via pytket ToffoliBox.

    This is a primitive (like [twist_plus] or [assoc_plus_l/r]) generalized
    to arbitrary basis-state permutations. Use for group operations like
    [neg_z_n] whose structural decomposition is verbose. *)
val tag_perm : int array -> 'a ty -> (unit, [`Lolli of 'a * 'a]) prog

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

(** {2 Scalar Phase} *)

(** Scalar multiplication by a unit complex number.

    [phase z ty] multiplies the state by z where |z| = 1.

    - On a qubit (Q), this is Rz(arg(z)) up to global phase
    - On unit type (I), this is a pure scalar (becomes controlled phase in omap)
    - On compound types, this is the scalar applied uniformly

    Raises [Invalid_argument] if |z| ≠ 1 (within tolerance 1e-10).

    Common phases:
    - phase Complex.one ty      = identity
    - phase (Complex.neg Complex.one) ty = multiply by -1
    - phase Complex.i ty        = multiply by i
*)
val phase : Complex.t -> 'a ty -> (unit, [`Lolli of 'a * 'a]) prog

(** Exponential of a structural involution: [exp_i theta body]
    where body is a closed endomorphism satisfying body^2 = id.
    Computes exp(i*theta*body) = cos(theta)*I + i*sin(theta)*body.
    Involution property is verified at compile time by the Python backend. *)
val exp_i : float -> (unit, [`Lolli of 'a * 'a]) prog
         -> (unit, [`Lolli of 'a * 'a]) prog

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

(** Closed omap for sum types: [omap0 ty_left ty_right f g : Prog(∅, (A⊕B) ⊸ (C⊕D))]
    Both f and g must be closed. Type witnesses needed for emission. *)
val omap0 : 'a ty -> 'b ty
         -> (unit, [`Lolli of 'a * 'c]) prog
         -> (unit, [`Lolli of 'b * 'd]) prog
         -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) prog

(** N-ary omap for n-ary sums: [omapn summand_types branches]
    where summand_types has n types and branches has n morphisms.

    NPlusMap(\[A₁,...,Aₙ\], \[f₁,...,fₙ\]) : (A₁+...+Aₙ) → (B₁+...+Bₙ)

    Compiles directly against flat ⌈log₂(n)⌉ tag encoding using
    per-branch X-flip + multi-controlled gates + X-unflip.

    Requires at least 2 summand types. *)
val omapn : _ ty array
         -> (unit, [`Lolli of 'a * 'b]) prog array
         -> (unit, [`Lolli of 'c * 'd]) prog

(** Phase-weighted omap: [phased_omap0 z ty_left ty_right f g]

    Like [omap0], but applies phase weight [z] to the left branch.
    This is the phase-weighted bifunctor omap_z(f, g) from the spec.

    For sum type A ⊕ B with tag qubit(s):
    - Left branch (tag encodes inl): apply f, then multiply by phase z
    - Right branch (tag encodes inr): apply g (no phase)

    The phase z must be a unit complex number (|z| = 1).
    Raises [Invalid_argument] if |z| ≠ 1.

    Example: Apply -1 phase to short-circuit branch of W = I + Bool:
    {[
      let neg_one = Complex.neg Complex.one
      let phase_w = phased_omap0 neg_one one bool_ty (id one) (id bool_ty)
    ]}

    Implementation: emits controlled-phase gates on tag qubits after the
    regular omap compilation. For binary sum (1 tag qubit), this is
    X; P(θ); X where θ = arg(z). For larger sums, uses multi-controlled phase.
*)
val phased_omap0 : Complex.t -> 'a ty -> 'b ty
               -> (unit, [`Lolli of 'a * 'c]) prog
               -> (unit, [`Lolli of 'b * 'd]) prog
               -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) prog

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

(** {1 Case Sugar}

    Combinators for pattern-matching on [A⊕B] with shared context,
    eliminating manual dist/omap/undist plumbing and split witnesses.

    All combinators work at the [prog] level (closed, unit context).
    No new GADT constructors — these desugar to existing structural ops.

    {b Homogeneous} ([case_hom], [case_hom0]): both branches produce the same
    result type C, so the output can be [undist]'d back to [(A⊕B) ⊗ C].

    {b Heterogeneous} ([case_het], [case_het0]): branches produce different types
    C and D, so the output is [(A⊗C) ⊕ (B⊗D)].
*)

(** Branch helper: build [G⊗A → A⊗C] from [body : G → C].

    Useful when the branch ignores the tag arm A (e.g., A=I for Bool)
    and just processes context G into result C, re-pairing with the tag.

    Desugars to: [twist(G,A) ; (id_A ⊗ body)] *)
val make_branch : 'g ty -> 'a ty
               -> (unit, [`Lolli of 'g * 'c]) prog
               -> (unit, [`Lolli of [`Tensor of 'g * 'a] * [`Tensor of 'a * 'c]]) prog

(** Homogeneous case without context.

    Input: [A⊕B], Output: [(A⊕B) ⊗ C].
    Branches [f : A → A⊗C], [g : B → B⊗C].

    Desugars to: [omap0(f, g) ; undist_l(A, B, C)] *)
val case_hom0 : 'a ty -> 'b ty -> 'c ty
             -> (unit, [`Lolli of 'a * [`Tensor of 'a * 'c]]) prog
             -> (unit, [`Lolli of 'b * [`Tensor of 'b * 'c]]) prog
             -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Tensor of [`Plus of 'a * 'b] * 'c]]) prog

(** Homogeneous case with shared context.

    Input: [G ⊗ (A⊕B)], Output: [(A⊕B) ⊗ C].
    Branches [f : G⊗A → A⊗C], [g : G⊗B → B⊗C].

    Desugars to: [dist_r(G,A,B) ; omap0(f,g) ; undist_l(A,B,C)] *)
val case_hom : 'a ty -> 'b ty -> 'g ty -> 'c ty
            -> (unit, [`Lolli of [`Tensor of 'g * 'a] * [`Tensor of 'a * 'c]]) prog
            -> (unit, [`Lolli of [`Tensor of 'g * 'b] * [`Tensor of 'b * 'c]]) prog
            -> (unit, [`Lolli of [`Tensor of 'g * [`Plus of 'a * 'b]]
                                * [`Tensor of [`Plus of 'a * 'b] * 'c]]) prog

(** Heterogeneous case without context.

    Input: [A⊕B], Output: [(A⊗C) ⊕ (B⊗D)].
    Branches [f : A → A⊗C], [g : B → B⊗D].

    Alias for [omap0] — provided for naming consistency with [case_hom0]. *)
val case_het0 : 'a ty -> 'b ty
             -> (unit, [`Lolli of 'a * [`Tensor of 'a * 'c]]) prog
             -> (unit, [`Lolli of 'b * [`Tensor of 'b * 'd]]) prog
             -> (unit, [`Lolli of [`Plus of 'a * 'b]
                                * [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'd]]]) prog

(** Heterogeneous case with shared context.

    Input: [G ⊗ (A⊕B)], Output: [(A⊗C) ⊕ (B⊗D)].
    Branches [f : G⊗A → A⊗C], [g : G⊗B → B⊗D].

    Desugars to: [dist_r(G,A,B) ; omap0(f,g)] *)
val case_het : 'a ty -> 'b ty -> 'g ty
            -> (unit, [`Lolli of [`Tensor of 'g * 'a] * [`Tensor of 'a * 'c]]) prog
            -> (unit, [`Lolli of [`Tensor of 'g * 'b] * [`Tensor of 'b * 'd]]) prog
            -> (unit, [`Lolli of [`Tensor of 'g * [`Plus of 'a * 'b]]
                                * [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'd]]]) prog

(** {1 Emission} *)

(** Emit a closed program to Bridge term for compilation. *)
val emit : (unit, 'a) prog -> Bridge.term

(** Emit with type witness for debugging. *)
val emit_typed : (unit, 'a) prog -> 'a ty -> Bridge.term

(** {1 Context Split Witnesses}

    Split witnesses prove that a context 'g can be partitioned into
    'g1 and 'g2, with each element assigned to one side.
*)

type (_, _, _) split =
  | SNil   : (unit, unit, unit) split
  | SLeft  : ('g1, 'g2, 'g) split -> ('a * 'g1, 'g2, 'a * 'g) split
  | SRight : ('g1, 'g2, 'g) split -> ('g1, 'a * 'g2, 'a * 'g) split

(** {1 Open Terms (Full Source Language)}

    Open terms track both context ('g) and output type ('a) via GADTs.
    This enables the full source language (nested LetPair, variable references)
    with compile-time linearity enforcement through context splitting.

    Binary constructors carry split witnesses to partition the context.
    Closed [prog] values can be embedded via [oembed].
*)

type (_, _) oterm

(** {2 General constructors (explicit split witness)} *)

(** Variable reference at position 0 in a singleton context *)
val ovar : string -> 'a ty -> ('a * unit, 'a) oterm

(** Context weakening: add an unused variable to the front *)
val oshift : 'b ty -> ('g, 'a) oterm -> ('b * 'g, 'a) oterm

(** Tensor introduction (pairing) *)
val opair : ('g1, 'a) oterm -> ('g2, 'b) oterm -> ('g1, 'g2, 'g) split
         -> ('g, [`Tensor of 'a * 'b]) oterm

(** Tensor elimination (destructuring) *)
val oletpair : string -> string -> 'a ty -> 'b ty
            -> ('g1, [`Tensor of 'a * 'b]) oterm
            -> ('a * ('b * 'g2), 'c) oterm
            -> ('g1, 'g2, 'g) split
            -> ('g, 'c) oterm

(** Lambda abstraction *)
val olam : string -> 'a ty -> 'b ty -> ('a * 'g, 'b) oterm
        -> ('g, [`Lolli of 'a * 'b]) oterm

(** Application *)
val oapp : ('g1, [`Lolli of 'a * 'b]) oterm -> ('g2, 'a) oterm
        -> ('g1, 'g2, 'g) split -> ('g, 'b) oterm

(** ⊕-Map: bifunctorial action on sums.
    Branches are bare morphism terms, not function values.
    The branch oterm types 'c and 'd become the output summand types. *)
val oplusmap : 'a ty -> 'b ty
            -> ('g1, 'c) oterm -> ('g2, 'd) oterm
            -> ('g1, 'g2, 'g) split
            -> ('g, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) oterm

(** n-ary ⊕-Map (open). All branches share context 'g and produce homogeneous
    output type 'c. The summand input types are given as an array.

    For n=2 this is semantically equivalent to [oplusmap] with summand_types
    [| 'a; 'b |]. Use this directly when you have n>2 summands to avoid the
    asymmetric-binary nesting issues.

    Result type uses existential sum types (pragmatic loose typing mirroring
    prog-level [omapn]/[NMap]) — the n-ary sum is tracked at Bridge/Python
    level via the [summand_types] array. *)
val o_n_plusmap : 'a ty array -> 'c ty -> ('g, 'c) oterm array
              -> ('g, [`Lolli of 'sum_in * 'sum_out]) oterm

(** Identity morphism *)
val oid : 'a ty -> (unit, 'a) oterm

(** Embed a closed prog into an open term *)
val oembed : (unit, 'a) prog -> (unit, 'a) oterm

(** Sequential composition of morphisms *)
val oseq : ('g1, [`Lolli of 'a * 'b]) oterm
        -> ('g2, [`Lolli of 'b * 'c]) oterm
        -> ('g1, 'g2, 'g) split
        -> ('g, [`Lolli of 'a * 'c]) oterm

(** {2 Closed convenience constructors (both sides unit, split = SNil)} *)

val opair0 : (unit, 'a) oterm -> (unit, 'b) oterm
          -> (unit, [`Tensor of 'a * 'b]) oterm
val oletpair0 : string -> string -> 'a ty -> 'b ty
             -> (unit, [`Tensor of 'a * 'b]) oterm
             -> ('a * ('b * unit), 'c) oterm
             -> (unit, 'c) oterm
val oapp0 : (unit, [`Lolli of 'a * 'b]) oterm -> (unit, 'a) oterm
         -> (unit, 'b) oterm

(** Closed ⊕-Map at oterm level. *)
val oplusmap0 : 'a ty -> 'b ty
             -> (unit, 'c) oterm -> (unit, 'd) oterm
             -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) oterm
val oseq0 : (unit, [`Lolli of 'a * 'b]) oterm
          -> (unit, [`Lolli of 'b * 'c]) oterm
          -> (unit, [`Lolli of 'a * 'c]) oterm

(** {2 Oterm Case Sugar}

    Mirror of the prog-level case sugar at the oterm level.
    All are closed oterm combinators (unit context) that wrap
    structural progs via [oembed] and use [oplusmap0] for branches.

    {b Important:} At the oterm level, [oplusmap0] branches are {i bare terms}
    whose output type becomes the output summand type — they are NOT morphisms
    (unlike prog-level [omap0] branches which are Lolli-typed).

    For homogeneous case, branches produce [A⊗C] and [B⊗C] values.
    For [omake_branch], which produces Lolli-typed oterms, use
    [oembed (case_hom ...)] instead of [ocase_hom].
*)

(** Homogeneous case without context (oterm level).

    Input: [A⊕B], Output: [(A⊕B) ⊗ C].
    Branches are bare tensor oterms producing [A⊗C] and [B⊗C].

    Desugars to: [oplusmap0(f, g) ; undist_l(A, B, C)] *)
val ocase_hom0 : 'a ty -> 'b ty -> 'c ty
              -> (unit, [`Tensor of 'a * 'c]) oterm
              -> (unit, [`Tensor of 'b * 'c]) oterm
              -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Tensor of [`Plus of 'a * 'b] * 'c]]) oterm

(** Homogeneous case with shared context (oterm level).

    Input: [G ⊗ (A⊕B)], Output: [(A⊕B) ⊗ C].
    Branches are bare tensor oterms producing [A⊗C] and [B⊗C].

    Desugars to: [dist_r(G,A,B) ; oplusmap0(f,g) ; undist_l(A,B,C)] *)
val ocase_hom : 'a ty -> 'b ty -> 'g ty -> 'c ty
             -> (unit, [`Tensor of 'a * 'c]) oterm
             -> (unit, [`Tensor of 'b * 'c]) oterm
             -> (unit, [`Lolli of [`Tensor of 'g * [`Plus of 'a * 'b]]
                                 * [`Tensor of [`Plus of 'a * 'b] * 'c]]) oterm

(** Heterogeneous case without context (oterm level).

    Input: [A⊕B], Output: [(A⊗C) ⊕ (B⊗D)].
    Alias for [oplusmap0]. *)
val ocase_het0 : 'a ty -> 'b ty
              -> (unit, 'c) oterm -> (unit, 'd) oterm
              -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) oterm

(** Heterogeneous case with context G (oterm level).

    Input: [G ⊗ (A⊕B)], Output: [(A⊗C) ⊕ (B⊗D)].
    Branches are bare oterms producing output summand values.

    Desugars to: [dist_r(G,A,B) ; oplusmap0(f,g)] *)
val ocase_het : 'a ty -> 'b ty -> 'g ty
             -> (unit, 'c) oterm -> (unit, 'd) oterm
             -> (unit, [`Lolli of [`Tensor of 'g * [`Plus of 'a * 'b]]
                                 * [`Plus of 'c * 'd]]) oterm

(** Embed prog-level [make_branch] into oterm.

    [omake_branch ty_g ty_a body] wraps a closed prog branch as an oterm.
    Only works when [body] is a closed prog (unit context).
    Returns a Lolli-typed oterm — for use with [oembed (case_hom ...)],
    not directly with [ocase_hom]. *)
val omake_branch : 'g ty -> 'a ty
                -> (unit, [`Lolli of 'g * 'c]) prog
                -> (unit, [`Lolli of [`Tensor of 'g * 'a] * [`Tensor of 'a * 'c]]) oterm

(** {2 Context representation} *)

(** Compute the Rep.t representation of an oterm's context 'g *)
val context_rep : ('g, 'a) oterm -> Rep.t

(** Emit an open term to Bridge.term for compilation *)
val emit_oterm : ('g, 'a) oterm -> Bridge.term

(** {1 Datatype Declarations}

    Surface-level datatype declarations following the spec:
    - Datatypes are finite with compile-time fixed arity k
    - No constructors, case analysis, or observation
    - Operations are primitive constants at translated types
    - Elaborates to I^{⊕k} (k-ary monoidal sum of unit)
*)

(** {2 Operation Type Signatures}

    Types for declaring operations, with [self] for self-reference.
*)

type op_ty

(** Self-reference (the datatype being declared) *)
val self : op_ty

(** Unit type I *)
val ty_one : op_ty

(** Qubit type Q *)
val ty_q : op_ty

(** Tensor product *)
val ( **. ) : op_ty -> op_ty -> op_ty

(** Sum *)
val ( ++. ) : op_ty -> op_ty -> op_ty

(** Linear arrow A ⊸ B *)
val lolli : op_ty -> op_ty -> op_ty

(** Embed an existing type witness *)
val of_ty : 'a ty -> op_ty

(** {2 Datatype Descriptor} *)

(** Datatype descriptor record *)
type datatype_desc = {
  name : string;
  arity : int;
  labels : string list;
  rep : Rep.t;
  ops : op_info list;
}

and op_info = {
  op_name : string;
  op_dom : Rep.t;
  op_cod : Rep.t;
}

(** Construct a datatype.

    {[
      let bool = datatype
        ~name:"Bool"
        ~arity:2
        ~labels:["false"; "true"]
        ~ops:[("H", lolli self self); ("X", lolli self self)]
    ]}

    Elaborates [Bool] to [I ⊕ I] and creates operations [H], [X]
    as primitive constants.
*)
val datatype :
  name:string ->
  arity:int ->
  labels:string list ->
  ops:(string * op_ty) list ->
  datatype_desc

(** Get the type witness for a datatype's representation (I^{⊕k}) *)
val rep_ty : datatype_desc -> 'a ty

(** Look up an operation by name *)
val op : datatype_desc -> string -> (unit, [`Lolli of 'a * 'b]) prog

(** Coherent control combinator.

    Given datatype D with arity k and branches [f0; ...; f_{k-1}]
    each of type A ⊸ A, produces:

      control : D ⊗ A ⊸ D ⊗ A

    which applies f_i when the control is in branch i, coherently.
*)
val control :
  datatype_desc ->
  'a ty ->
  (unit, [`Lolli of 'a * 'a]) prog array ->
  (unit, [`Lolli of [`Tensor of 'b * 'a] * [`Tensor of 'b * 'a]]) prog

(** Phase-weighted coherent control combinator.

    Given datatype D with arity k, phases [z₀; ...; z_{k-1}],
    and branches [f₀; ...; f_{k-1}] each of type A ⊸ A, produces:

      phased_control : D ⊗ A ⊸ D ⊗ A

    which applies fᵢ followed by phase zᵢ when control is in branch i.

    Each phase zᵢ must be a unit complex number (|zᵢ| = 1).

    Implementation uses efficient log₂(k) tag encoding:
    - For tag value i (binary pattern b₀b₁...b_{n-1})
    - Apply X to bits that are 0 in the pattern
    - Apply multi-controlled U1(θᵢ) where θᵢ = arg(zᵢ)
    - Apply X to restore

    Example with Trit (k=3, 2 tag qubits):
      Tag 00: X[0]; X[1]; CU1(θ₀); X[1]; X[0]
      Tag 01: X[0]; CU1(θ₁); X[0]
      Tag 10: X[1]; CU1(θ₂); X[1]
*)
val phased_control :
  datatype_desc ->
  Complex.t array ->
  'a ty ->
  (unit, [`Lolli of 'a * 'a]) prog array ->
  (unit, [`Lolli of [`Tensor of 'b * 'a] * [`Tensor of 'b * 'a]]) prog

(** Generate I^{⊕k} from arity k *)
val i_sum : int -> Rep.t
