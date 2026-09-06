#!/usr/bin/env bash
# Full reproduction driver for Granthi v1.0.0.
#
# Covers the complete verification surface:
#   1. dune build
#   2. dune runtest --force  (all OCaml suites: unit/property tests, the
#      frontend compile-pass/reject harness, the 34-row Source counterpart
#      coverage harness, datatype invariants, compiled doc examples)
#   3. EVERY demo listed in ocaml/demos/manifest.tsv:
#        - a `golden` demo must run AND byte-match its committed
#          ocaml/demos/<name>.output  → GOLDEN-PASS
#        - a `none` demo (intentional no-fixture dump) must run cleanly
#          → NO-FIXTURE-OK
#        - a `golden` demo whose .output file is MISSING is a FAILURE
#          (missing goldens must not pass silently)
#   4. The full Python regression suite.
#
# Exit code: 0 only if every category above succeeds; otherwise the
# number of failures (min 1).

set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
RESULTS="$ROOT/artifact/results"
mkdir -p "$RESULTS"

if command -v opam >/dev/null 2>&1; then
    eval "$(opam env)"
fi

export PYTHONPATH="${PYTHONPATH:-$ROOT/python/src}"

MANIFEST="$ROOT/ocaml/demos/manifest.tsv"

pass_golden=0
pass_nofixture=0
fail=0

hr() { printf '%s\n' "----------------------------------------------------------------"; }

echo "=========================================================="
echo "  Granthi v1.0.0 — full reproduction"
echo "=========================================================="
echo "Working directory: $ROOT"
echo "Results directory: $RESULTS"
echo ""

# --- 1. build ---------------------------------------------------------------
echo "[1] dune build"
if ! (cd ocaml && dune build) 2>&1 | tee "$RESULTS/_dune_build.log" >/dev/null; then
    echo "  dune build FAILED. Aborting; see $RESULTS/_dune_build.log"
    exit 99
fi
echo "  ok"
echo ""

# --- 2. complete OCaml test surface ----------------------------------------
echo "[2] dune runtest --force  (unit suites + frontend harness + counterparts)"
if ! (cd ocaml && dune runtest --force) 2>&1 | tee "$RESULTS/_dune_test.log" >/dev/null; then
    printf '  %-34s  %s\n' "dune runtest" "FAIL"
    echo "  see $RESULTS/_dune_test.log"
    fail=$((fail + 1))
else
    printf '  %-34s  %s\n' "dune runtest" "PASS"
fi
echo ""

# --- 3. every demo in the manifest ------------------------------------------
if [ ! -f "$MANIFEST" ]; then
    echo "manifest missing: $MANIFEST"
    exit 99
fi

echo "[3] demo battery (all rows of ocaml/demos/manifest.tsv)"
printf '  %-32s  %s\n' "DEMO" "OUTCOME"
hr

# Skip the header line; fields are tab-separated: executable, classification,
# fixture, note.
while IFS=$'\t' read -r demo _classification fixture _note; do
    [ "$demo" = "executable" ] && continue
    [ -z "$demo" ] && continue

    committed="ocaml/demos/${demo}.output"
    fresh="$RESULTS/${demo}.out"

    if ! (cd ocaml && dune exec "demos/${demo}.exe") >"$fresh" 2>&1; then
        printf '  %-32s  %s\n' "$demo" "RUNTIME-ERROR"
        fail=$((fail + 1))
        continue
    fi

    case "$fixture" in
        golden)
            if [ ! -f "$committed" ]; then
                printf '  %-32s  %s\n' "$demo" "MISSING-GOLDEN (FAIL)"
                fail=$((fail + 1))
            elif diff -q "$committed" "$fresh" >/dev/null 2>&1; then
                printf '  %-32s  %s\n' "$demo" "GOLDEN-PASS"
                pass_golden=$((pass_golden + 1))
            else
                printf '  %-32s  %s\n' "$demo" "DIFF (FAIL)"
                fail=$((fail + 1))
            fi
            ;;
        none)
            printf '  %-32s  %s\n' "$demo" "NO-FIXTURE-OK"
            pass_nofixture=$((pass_nofixture + 1))
            ;;
        *)
            printf '  %-32s  %s\n' "$demo" "UNKNOWN-FIXTURE-KIND '$fixture' (FAIL)"
            fail=$((fail + 1))
            ;;
    esac
done < "$MANIFEST"

hr
echo ""

# --- 4. Python regression suite ---------------------------------------------
echo "[4] pytest -q python/tests"
if pytest -q python/tests >"$RESULTS/_pytest.log" 2>&1; then
    printf '  %-34s  %s\n' "pytest suite" "PASS"
else
    printf '  %-34s  %s\n' "pytest suite" "FAIL"
    echo "  see $RESULTS/_pytest.log"
    fail=$((fail + 1))
fi
echo ""

# --- Summary -----------------------------------------------------------------
echo "=========================================================="
printf 'Summary: %d golden demos byte-identical, %d intentional no-fixture dumps ran, %d failures\n' \
    "$pass_golden" "$pass_nofixture" "$fail"
echo "Expected at v1.0.0: 32 golden, 2 no-fixture, 0 failures."
echo "=========================================================="

if [ "$fail" -eq 0 ] && [ "$pass_golden" -eq 32 ] && [ "$pass_nofixture" -eq 2 ]; then
    echo "Full reproduction succeeded."
    exit 0
fi
if [ "$fail" -eq 0 ]; then
    # Everything ran, but the category counts moved (e.g., a demo was added).
    # Surface it rather than silently passing.
    echo "Category counts differ from the recorded v1.0.0 baseline; inspect above."
    exit 1
fi
echo "See $RESULTS/ for per-demo output."
exit "$fail"
