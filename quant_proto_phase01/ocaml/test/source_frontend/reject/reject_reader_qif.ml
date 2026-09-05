(* The reader's higher-order qif in concise syntax:
      qif x then X else I  : qbit ⊗ (qbit ⊸ qbit)
   The coherent selection of a function value is a case whose branches
   have type q ⊸ q — rejected by the first-order restriction, at the
   case itself. *)

open Qpl_surface.Source

let%source bad (x : qbool) (xg : (q, q) lolli) (idg : (q, q) lolli) =
  case x
    ~zero:idg
    ~one_:xg

let _ = bad
