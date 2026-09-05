(* Standalone driver for the Source frontend rewriter.

   Used by the compile-reject harness as  ocamlc -ppx "<exe> --as-ppx"  and
   available for read-only expansion display.  It never writes files of its
   own. *)
let () = Ppxlib.Driver.standalone ()
