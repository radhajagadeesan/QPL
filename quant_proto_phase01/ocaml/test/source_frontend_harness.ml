(** Compile-pass/compile-fail conformance for the [let%source] frontend.

    Each fixture is copied into a fresh directory and typechecked against the
    installed public library interface with the standalone Source rewriter
    attached via [-ppx].  Rejected fixtures must fail with the located
    diagnostics recorded in their [.diag] files, whose fragments pin both the
    source position (file, line, character span) and the message text.
    Isolation matters: [ocamlc -stop-after typing -c] can still leave a
    [.cmi], and no rejected fixture may influence a later case. *)

type config = {
  ocamlc : string;
  public_cmi : string;
  ppx_driver : string;
  fixtures : string;
}

type output = {
  status : Unix.process_status;
  stdout : string;
  stderr : string;
}

let fail format =
  Printf.ksprintf
    (fun message ->
       prerr_endline message;
       exit 2)
    format

let parse_args () =
  let ocamlc = ref None in
  let public_cmi = ref None in
  let ppx_driver = ref None in
  let fixtures = ref None in
  let set slot flag value =
    match !slot with
    | None -> slot := Some value
    | Some _ -> fail "duplicate %s argument" flag
  in
  let rec loop = function
    | [] -> ()
    | "--ocamlc" :: value :: rest ->
        set ocamlc "--ocamlc" value;
        loop rest
    | "--public-cmi" :: value :: rest ->
        set public_cmi "--public-cmi" value;
        loop rest
    | "--ppx-driver" :: value :: rest ->
        set ppx_driver "--ppx-driver" value;
        loop rest
    | "--fixtures" :: value :: rest ->
        set fixtures "--fixtures" value;
        loop rest
    | flag :: _ -> fail "unknown or incomplete argument: %s" flag
  in
  loop (List.tl (Array.to_list Sys.argv));
  let require flag = function
    | Some value -> value
    | None -> fail "missing %s argument" flag
  in
  {
    ocamlc = require "--ocamlc" !ocamlc;
    public_cmi = require "--public-cmi" !public_cmi;
    ppx_driver = require "--ppx-driver" !ppx_driver;
    fixtures = require "--fixtures" !fixtures;
  }

let read_file path =
  let channel = open_in_bin path in
  Fun.protect
    ~finally:(fun () -> close_in_noerr channel)
    (fun () -> really_input_string channel (in_channel_length channel))

let copy_file source target =
  let input_channel = open_in_bin source in
  Fun.protect
    ~finally:(fun () -> close_in_noerr input_channel)
    (fun () ->
       let output_channel = open_out_bin target in
       Fun.protect
         ~finally:(fun () -> close_out_noerr output_channel)
         (fun () ->
            let buffer = Bytes.create 65536 in
            let rec loop () =
              match input input_channel buffer 0 (Bytes.length buffer) with
              | 0 -> ()
              | count ->
                  output output_channel buffer 0 count;
                  loop ()
            in
            loop ()))

let rec remove_tree path =
  match (Unix.lstat path).Unix.st_kind with
  | Unix.S_DIR ->
      Sys.readdir path
      |> Array.iter (fun name -> remove_tree (Filename.concat path name));
      Unix.rmdir path
  | _ -> Sys.remove path

let with_temp_dir stem action =
  let marker = Filename.temp_file ("qpl-frontend-" ^ stem ^ "-") ".tmp" in
  Sys.remove marker;
  Unix.mkdir marker 0o700;
  Fun.protect ~finally:(fun () -> remove_tree marker)
    (fun () -> action marker)

let starts_with ~prefix value =
  let prefix_length = String.length prefix in
  String.length value >= prefix_length
  && String.sub value 0 prefix_length = prefix

let clean_environment () =
  Unix.environment ()
  |> Array.to_list
  |> List.filter (fun entry ->
         not (starts_with ~prefix:"OCAMLPARAM=" entry)
         && not (starts_with ~prefix:"OCAML_COLOR=" entry))
  |> fun entries ->
  Array.of_list ("OCAML_COLOR=never" :: entries)

let run_process ~cwd executable arguments =
  let stdout_path = Filename.concat cwd "compiler.stdout" in
  let stderr_path = Filename.concat cwd "compiler.stderr" in
  let stdout_fd =
    Unix.openfile stdout_path [Unix.O_WRONLY; Unix.O_CREAT; Unix.O_TRUNC] 0o600
  in
  let stderr_fd =
    Unix.openfile stderr_path [Unix.O_WRONLY; Unix.O_CREAT; Unix.O_TRUNC] 0o600
  in
  let old_cwd = Sys.getcwd () in
  let pid =
    Fun.protect
      ~finally:(fun () ->
          Unix.close stdout_fd;
          Unix.close stderr_fd;
          Unix.chdir old_cwd)
      (fun () ->
         Unix.chdir cwd;
         Unix.create_process_env executable arguments (clean_environment ())
           Unix.stdin stdout_fd stderr_fd)
  in
  let _, status = Unix.waitpid [] pid in
  {
    status;
    stdout = read_file stdout_path;
    stderr = read_file stderr_path;
  }

let contains haystack needle =
  let haystack_length = String.length haystack in
  let needle_length = String.length needle in
  let rec search at =
    if needle_length = 0 then true
    else if at + needle_length > haystack_length then false
    else if String.sub haystack at needle_length = needle then true
    else search (at + 1)
  in
  search 0

let lines text =
  String.split_on_char '\n' text
  |> List.map String.trim
  |> List.filter (fun line ->
         line <> "" && not (starts_with ~prefix:"#" line))

let ml_files directory =
  if not (Sys.file_exists directory && Sys.is_directory directory) then
    fail "missing fixture directory: %s" directory;
  Sys.readdir directory
  |> Array.to_list
  |> List.filter (fun name -> Filename.check_suffix name ".ml")
  |> List.sort String.compare

let canonical path =
  try Unix.realpath path
  with Unix.Unix_error (error, _, _) ->
    fail "cannot resolve %s: %s" path (Unix.error_message error)

let compile_fixture config include_dir directory basename =
  let source = Filename.concat directory basename in
  with_temp_dir (Filename.remove_extension basename)
    (fun temporary ->
       let local_source = Filename.concat temporary basename in
       copy_file source local_source;
       let arguments =
         [|
           config.ocamlc;
           "-color"; "never";
           "-error-style"; "short";
           "-short-paths";
           "-warn-error"; "-A";
           "-I"; include_dir;
           "-ppx"; config.ppx_driver ^ " --as-ppx";
           "-stop-after"; "typing";
           "-c"; basename;
         |]
       in
       run_process ~cwd:temporary config.ocamlc arguments)

let show_status = function
  | Unix.WEXITED code -> Printf.sprintf "exit %d" code
  | Unix.WSIGNALED signal -> Printf.sprintf "signal %d" signal
  | Unix.WSTOPPED signal -> Printf.sprintf "stopped %d" signal

let check_pass config include_dir directory basename =
  let result = compile_fixture config include_dir directory basename in
  match result.status with
  | Unix.WEXITED 0 ->
      Printf.printf "PASS  pass/%s\n%!" basename;
      true
  | status ->
      Printf.eprintf
        "FAIL  pass/%s (%s)\nstdout:\n%s\nstderr:\n%s\n%!"
        basename (show_status status) result.stdout result.stderr;
      false

let diag_path directory basename =
  Filename.concat directory
    (Filename.remove_extension basename ^ ".diag")

let check_reject config include_dir directory basename =
  let expected_path = diag_path directory basename in
  if not (Sys.file_exists expected_path) then
    fail "rejected fixture has no .diag: %s" basename;
  let expected = lines (read_file expected_path) in
  if expected = [] then fail "empty diagnostic expectation: %s" expected_path;
  let result = compile_fixture config include_dir directory basename in
  let missing =
    List.filter (fun fragment -> not (contains result.stderr fragment)) expected
  in
  match result.status, missing with
  | Unix.WEXITED 2, [] ->
      Printf.printf "PASS  reject/%s\n%!" basename;
      true
  | status, _ ->
      Printf.eprintf
        "FAIL  reject/%s (%s)\nmissing fragments: [%s]\nstdout:\n%s\nstderr:\n%s\n%!"
        basename (show_status status) (String.concat "; " missing)
        result.stdout result.stderr;
      false

let reject_diag_files directory =
  Sys.readdir directory
  |> Array.to_list
  |> List.filter (fun name -> Filename.check_suffix name ".diag")
  |> List.sort String.compare

let () =
  let parsed = parse_args () in
  let config =
    {
      ocamlc = canonical parsed.ocamlc;
      public_cmi = canonical parsed.public_cmi;
      ppx_driver = canonical parsed.ppx_driver;
      fixtures = canonical parsed.fixtures;
    }
  in
  let include_dir = Filename.dirname config.public_cmi in
  let pass_dir = Filename.concat config.fixtures "pass" in
  let reject_dir = Filename.concat config.fixtures "reject" in
  let passes = ml_files pass_dir in
  let rejects = ml_files reject_dir in
  if passes = [] || rejects = [] then
    fail "the frontend conformance suite requires both pass and reject fixtures";
  let expected_diags =
    List.map (fun name -> Filename.remove_extension name ^ ".diag") rejects
    |> List.sort String.compare
  in
  let actual_diags = reject_diag_files reject_dir in
  if actual_diags <> expected_diags then
    fail "orphan or missing .diag files in %s" reject_dir;
  let pass_results =
    List.map (check_pass config include_dir pass_dir) passes
  in
  let pass_failures =
    List.fold_left (fun count ok -> if ok then count else count + 1)
      0 pass_results
  in
  if pass_failures <> 0 then begin
    Printf.eprintf
      "Source frontend: %d positive fixture(s) failed; rejected fixtures were not run.\n%!"
      pass_failures;
    exit 1
  end;
  let reject_results =
    List.map (check_reject config include_dir reject_dir) rejects
  in
  let reject_failures =
    List.fold_left (fun count ok -> if ok then count else count + 1)
      0 reject_results
  in
  if reject_failures <> 0 then begin
    Printf.eprintf "Source frontend: %d rejected fixture(s) failed.\n%!"
      reject_failures;
    exit 1
  end;
  Printf.printf
    "Source frontend: %d compile-pass and %d compile-fail fixtures verified.\n%!"
    (List.length passes) (List.length rejects)
