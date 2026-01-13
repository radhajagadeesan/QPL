(** Staging: OCaml as a meta-language for generating linear λ-calculus programs.

    Implementation of the sealed staging API.
    See staging.mli for the interface and documentation.
*)

(** Internal representation using Bridge terms.
    The phantom types provide compile-time type safety while the
    underlying representation is uniform Bridge.term values. *)
type _ ty = Rep.t
type _ tm = Bridge.term
type _ invol = Bridge.term

(* Type constructors *)
let q = Rep.var 0
let unit = Rep.Unit
let tensor a b = Rep.Tensor (a, b)
let plus a b = Rep.Plus (a, b)
let lolli a b = Rep.Tensor (a, b)  (* Int representation: A ⊸ B = A ⊗ B *)

(* Structural combinators *)
let id ty = Bridge.TId ty
let seq f g = Bridge.TSeq (f, g)
let par f g = Bridge.TTenTerm (f, g)
let twist_ten a b = Bridge.TTwistTen (a, b)
let twist_plus a b = Bridge.TTwistPlus (a, b)
let assoc_ten_l a b c = Bridge.TAssocTenL (a, b, c)
let assoc_ten_r a b c = Bridge.TAssocTenR (a, b, c)
let assoc_plus_l a b c = Bridge.TAssocPlusL (a, b, c)
let assoc_plus_r a b c = Bridge.TAssocPlusR (a, b, c)
let dist_l a b c = Bridge.TDistL (a, b, c)
let dist_r a b c = Bridge.TDistR (a, b, c)

(* Gates *)
let h i _ = Bridge.TH i
let x i _ = Bridge.TX i
let y i _ = Bridge.TY i
let z i _ = Bridge.TZ i
let s i _ = Bridge.TS i
let t i _ = Bridge.TT i
let rz theta i _ = Bridge.TRz (theta, i)
let cx i j _ = Bridge.TCX (i, j)
let cz i j _ = Bridge.TCZ (i, j)
let ccx i j k _ = Bridge.TCCX (i, j, k)

(* Involutions *)
let certify_invol term =
  match Bridge.check_involution term with
  | Bridge.InvolutionOk (true, _) -> term
  | Bridge.InvolutionOk (false, _) -> failwith "Term is not involutive: P² ≠ id"
  | Bridge.InvolutionError msg -> failwith ("Involution check failed: " ^ msg)

let invol_twist_ten a b = Bridge.TTwistTen (a, b)
let invol_twist_plus a b = Bridge.TTwistPlus (a, b)

let exp_i theta invol = Bridge.TExpInvolution (theta, invol)

(* Meta-level combinators *)
let rec iterate n f =
  if n <= 0 then
    (* Need type for identity - extract from term if possible *)
    Bridge.TId (Rep.var 0)  (* Placeholder - works for Q *)
  else if n = 1 then
    f
  else
    seq f (iterate (n - 1) f)

let fold ty fs =
  match fs with
  | [] -> Bridge.TId ty
  | [f] -> f
  | f :: rest -> List.fold_left seq f rest

let pow2 f = seq f f

let rec power_of_2 n f =
  if n <= 0 then f
  else power_of_2 (n - 1) (pow2 f)

let indexed_fold n ty gen =
  let stages = List.init n gen in
  fold ty stages

(* Extraction *)
let to_bridge tm = tm

let compile tm = Bridge.compile tm
