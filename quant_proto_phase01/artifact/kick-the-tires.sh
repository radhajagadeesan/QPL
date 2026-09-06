#!/usr/bin/env bash
# Kick-the-tires smoke test for SPLASH 2026 AE.
# Target wall-clock: under a minute on a laptop.
#
# Checks:
#   1. OCaml toolchain works: `dune build` succeeds.
#   2. OCaml -> Bridge -> Python pipeline works: run one small demo end-to-end.
#   3. Python test suite works: run one focused pytest module.
#   4. Byte-identical reproducibility: diff the demo's stdout against the
#      committed .output file.
#
# Exit code: 0 iff all four checks pass.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "=========================================================="
echo "  Granthi / QPL — kick-the-tires"
echo "=========================================================="
echo "Working directory: $ROOT"
echo ""

# Load opam env if we're not in the Docker image (which bakes it in).
if command -v opam >/dev/null 2>&1; then
    eval "$(opam env)"
fi

# Ensure Python sees the source tree.
export PYTHONPATH="$ROOT/python/src${PYTHONPATH:+:$PYTHONPATH}"

pass=0
fail=0

report() {
    local label="$1" status="$2"
    if [ "$status" = "PASS" ]; then
        printf "  [ %s ] %s\n" "PASS" "$label"
        pass=$((pass + 1))
    else
        printf "  [ %s ] %s\n" "FAIL" "$label"
        fail=$((fail + 1))
    fi
}

# ---------------------------------------------------------------- 1: dune build
echo "[1/4] dune build"
if (cd ocaml && dune build) >/dev/null 2>&1; then
    report "OCaml compiles cleanly" PASS
else
    report "OCaml compiles cleanly" FAIL
fi
echo ""

# ---------------------------------------------------------------- 2: one demo
echo "[2/4] Run one small demo end-to-end (test_first_order)"
tmp="$(mktemp)"
if (cd ocaml && dune exec demos/test_first_order.exe) >"$tmp" 2>&1; then
    report "Demo runs to completion (exit 0)" PASS
    if grep -q "OK:" "$tmp"; then
        report "Demo prints expected OK marker" PASS
    else
        report "Demo prints expected OK marker" FAIL
        echo "----- demo output -----"
        cat "$tmp"
        echo "-----------------------"
    fi
else
    report "Demo runs to completion (exit 0)" FAIL
    echo "----- demo output -----"
    cat "$tmp"
    echo "-----------------------"
fi
rm -f "$tmp"
echo ""

# ---------------------------------------------------------------- 3: one pytest
echo "[3/4] Python test suite (test_exp_involution)"
if pytest -q python/tests/test_exp_involution.py >/dev/null 2>&1; then
    report "pytest module passes" PASS
else
    report "pytest module passes" FAIL
fi
echo ""

# ---------------------------------------------------------------- 4: diff
echo "[4/4] Deterministic output: diff algorithms_e2e against committed .output"
committed="ocaml/demos/algorithms_e2e.output"
fresh="$(mktemp)"
if (cd ocaml && dune exec demos/algorithms_e2e.exe) >"$fresh" 2>&1; then
    if diff -q "$committed" "$fresh" >/dev/null; then
        report "Fresh output matches committed .output byte-for-byte" PASS
    else
        report "Fresh output matches committed .output byte-for-byte" FAIL
        echo "----- diff (first 40 lines) -----"
        diff "$committed" "$fresh" | head -40
        echo "---------------------------------"
    fi
else
    report "algorithms_e2e demo runs" FAIL
fi
rm -f "$fresh"
echo ""

echo "=========================================================="
printf "Kick-the-tires: %d passed, %d failed\n" "$pass" "$fail"
echo "=========================================================="

if [ "$fail" -eq 0 ]; then
    exit 0
else
    exit 1
fi
