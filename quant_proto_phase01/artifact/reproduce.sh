#!/usr/bin/env bash
# Full reproduction driver for SPLASH 2026 AE.
#
# For each demo listed in DEMOS below:
#   1. Run the OCaml demo end-to-end (dune exec).
#   2. Save its stdout to results/<name>.out
#   3. diff against the committed ocaml/demos/<name>.output
#
# Then run the Python test suite as a regression check.
#
# Exit code = total number of failures.

set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
RESULTS="$ROOT/artifact/results"
mkdir -p "$RESULTS"

# Load opam env if we're not in the Docker image (which bakes it in).
if command -v opam >/dev/null 2>&1; then
    eval "$(opam env)"
fi

export PYTHONPATH="${PYTHONPATH:-$ROOT/python/src}"

# Claims table: each row is "paper-section demo-name short-claim".
# The demo name maps to ocaml/demos/<name>.ml, ocaml/demos/<name>.output, and
# `dune exec demos/<name>.exe`.
DEMOS=(
    "S10        algorithms_e2e                  Standard algorithms (Deutsch-Jozsa, HSP, Simon, Bell, GHZ)"
    "S4-S8      abstract_qswitch_oterm_e2e      Abstract QSwitch: open, four Fredkins"
    "S8-S11     qswitch_instantiated_e2e        Closed qSwitch_{H,S} on two qubits"
    "S4-S5      ctrl_lambda_e2e                 ctrl combinator (higher-order controlled application)"
    "S10        nested_apply_e2e                Nested application"
    "S10        verify_nested_ctrl_e2e          Verify nested ctrl composes correctly"
    "S4-S5      short_circuit_e2e               Phase-marked short-circuit AND (routeW^q, -1 phase)"
    "S5         exp_twist_e2e                   Fractional-swap exp(i theta twist), theta = pi/4, pi/2"
    "S5         exp_swap_T3_e2e                 Branch-swap exponentials on Q + (Q + Q)"
    "S4-S9      zn_controlled_phase_e2e         Z_n coherent controlled phase (kick_n)"
    "S4         zn_group_ops_e2e                Z_5 datatype: add, neg"
    "S10        abstract_select_2_e2e           SELECT combinator, n = 2"
    "S10        curried_select_3_e2e            SELECT curried, n = 3"
    "S10        curried_select_3_ndist_e2e      SELECT curried, n-distributed variant"
    "S10        nested_select_e2e               Nested SELECT"
    "S8         n_plusmap_e2e                   n-ary sum compilation walkthrough"
    "S4         datatype_demo                   Finite datatype registration and use"
)

pass=0
fail=0
missing_output=0

hr() { printf '%s\n' "----------------------------------------------------------------"; }

echo "=========================================================="
echo "  Granthi / QPL — full reproduction (SPLASH 2026 AE)"
echo "=========================================================="
echo "Working directory: $ROOT"
echo "Results directory: $RESULTS"
echo ""

# Ensure the OCaml toolchain compiles before we spend time on demos.
echo "[preflight] dune build"
if ! (cd ocaml && dune build) 2>&1 | tee "$RESULTS/_dune_build.log" >/dev/null; then
    echo "  dune build FAILED. Aborting; see $RESULTS/_dune_build.log"
    exit 99
fi
echo "  ok"
echo ""

# One row per demo.
printf '  %-4s  %-32s  %s\n' "SEC" "DEMO" "OUTCOME"
hr

for row in "${DEMOS[@]}"; do
    # Split into three fields: paper section, demo name, description.
    sec="$(echo "$row" | awk '{print $1}')"
    demo="$(echo "$row" | awk '{print $2}')"

    committed="ocaml/demos/${demo}.output"
    fresh="$RESULTS/${demo}.out"

    # Run the demo. Capture stdout+stderr so a runtime error is visible.
    if (cd ocaml && dune exec "demos/${demo}.exe") >"$fresh" 2>&1; then
        if [ ! -f "$committed" ]; then
            printf '  %-4s  %-32s  %s\n' "$sec" "$demo" "NO-COMMITTED-OUTPUT"
            missing_output=$((missing_output + 1))
        elif diff -q "$committed" "$fresh" >/dev/null 2>&1; then
            printf '  %-4s  %-32s  %s\n' "$sec" "$demo" "PASS"
            pass=$((pass + 1))
        else
            printf '  %-4s  %-32s  %s\n' "$sec" "$demo" "DIFF"
            fail=$((fail + 1))
        fi
    else
        printf '  %-4s  %-32s  %s\n' "$sec" "$demo" "RUNTIME-ERROR"
        fail=$((fail + 1))
    fi
done

hr
echo ""

# --- Python regression tests ----------------------------------------------
echo "[python regression] pytest -q python/tests"
if pytest -q python/tests >"$RESULTS/_pytest.log" 2>&1; then
    printf '  %-4s  %-32s  %s\n' "-"  "pytest suite"  "PASS"
    pass=$((pass + 1))
else
    printf '  %-4s  %-32s  %s\n' "-"  "pytest suite"  "FAIL"
    echo "  see $RESULTS/_pytest.log for details"
    fail=$((fail + 1))
fi
echo ""

# --- Summary ---------------------------------------------------------------
echo "=========================================================="
printf 'Summary: %d passed, %d failed, %d without committed output\n' \
    "$pass" "$fail" "$missing_output"
echo "=========================================================="

if [ "$fail" -eq 0 ] && [ "$missing_output" -eq 0 ]; then
    echo "All claims reproduced."
    exit 0
else
    echo "See $RESULTS/ for per-demo output."
    # Exit code = number of failures (matches artifact-evaluation convention).
    exit "$fail"
fi
