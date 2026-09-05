(* Reading B of the reader's qif (rule (⋆⋆)): select a FUNCTION VALUE
   coherently, then destructure the resulting pair and apply the function
   half to the qubit half.  The case result would be a sum payload
   carrying q ⊸ q; the first-order restriction rejects the case. *)

open Qpl_surface.Source

let%source bad (b : qbool) (f0 : (q, q) lolli) (f1 : (q, q) lolli) =
  let (b2, sel) = split (case b ~zero:f0 ~one_:f1) in
  (b2, sel)

let _ = bad
