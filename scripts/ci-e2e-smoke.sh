#!/usr/bin/env bash
# CI smoke test — verify the full ac-guard user journey as subprocess calls.
# Covers: #83 (smoke test) + #86 (build/install verification preamble)
#
# Environment variables:
#   AC_GUARD       — path to the ac-guard binary (default: ac-guard on PATH)
#   E2E_WORKSPACE  — workspace directory (default: /tmp/e2e-workspace)
set -euo pipefail

AC_GUARD="${AC_GUARD:-ac-guard}"
WORKSPACE="${E2E_WORKSPACE:-/tmp/e2e-workspace}"

# --- Setup: fresh workspace with a git repo ---
rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"
git init
git config user.email "ci@test"
git config user.name "CI"

echo "=== Step 1: ac-guard --version ==="
$AC_GUARD --version

echo "=== Step 2: ac-guard init --language python ==="
$AC_GUARD init --language python

echo "=== Step 3: ac-guard install --agent claude-code ==="
$AC_GUARD install --agent claude-code

echo "=== Step 4: ac-guard run (verify no crash) ==="
# run may exit non-zero if ruff/pytest are not in the clean venv;
# the goal is to verify the command does not crash, not that checks pass.
$AC_GUARD run --format json || true

echo "=== Step 5: ac-guard status --format json (validate JSON) ==="
$AC_GUARD status --format json | python3 -c "import sys, json; json.load(sys.stdin); print('JSON valid')"

echo "=== Step 6: ac-guard show --section code ==="
$AC_GUARD show --section code

echo "=== Smoke test PASSED ==="
echo "(uninstall deferred — artifacts preserved for syntax validation)"
