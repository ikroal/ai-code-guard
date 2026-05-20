#!/usr/bin/env bash
# Validate syntax of generated artifacts after ac-guard install.
# Covers: #84 (script syntax) + #85 (pre-commit config structure)
#
# Expects the smoke test to have run first, leaving artifacts in E2E_WORKSPACE.
set -euo pipefail

WORKSPACE="${E2E_WORKSPACE:-/tmp/e2e-workspace}"
cd "$WORKSPACE"

ERRORS=0

# --- Python hook scripts (#84) ---
echo "=== Validating Python hook scripts ==="
for py_file in $(find . -name "*.py" -path "*/.claude/*" -o -name "*.py" -path "*/.opencode/*" -o -name "*.py" -path "*/.codex/*" 2>/dev/null || true); do
  if python3 -m py_compile "$py_file" 2>/dev/null; then
    echo "  $py_file: OK"
  else
    echo "  $py_file: FAIL"
    ERRORS=$((ERRORS + 1))
  fi
done

# --- Shell git hooks (#84) ---
echo "=== Validating shell git hooks ==="
for hook in .git/hooks/pre-commit .git/hooks/pre-push .git/hooks/commit-msg .git/hooks/pre-merge-commit .git/hooks/pre-rebase; do
  if [ -f "$hook" ]; then
    if bash -n "$hook" 2>/dev/null; then
      echo "  $hook: OK"
    else
      echo "  $hook: FAIL"
      ERRORS=$((ERRORS + 1))
    fi
  fi
done

# --- Pre-commit config YAML structure (#85) ---
echo "=== Validating pre-commit config structure ==="
if [ -f .pre-commit-config.yaml ]; then
  # Use yaml.safe_load if pyyaml available, otherwise fall back to basic checks
  python3 -c "
import sys
try:
    import yaml
    with open('.pre-commit-config.yaml') as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), 'Top-level must be a mapping'
    assert 'repos' in data, 'Missing repos key'
    assert isinstance(data['repos'], list), 'repos must be a list'
    for repo in data['repos']:
        assert 'repo' in repo, f'Repo entry missing repo key: {repo}'
        assert 'hooks' in repo, f'Repo {repo.get(\"repo\", \"?\")} missing hooks'
        assert isinstance(repo['hooks'], list), 'hooks must be a list'
        for hook in repo['hooks']:
            assert 'id' in hook, f'Hook missing id: {hook}'
    print('pre-commit config structure: OK')
except ImportError:
    # pyyaml not available — validate YAML syntax only
    import json, pathlib
    text = pathlib.Path('.pre-commit-config.yaml').read_text()
    assert 'repos:' in text, 'Missing repos key'
    assert 'id:' in text, 'Missing hook id fields'
    print('pre-commit config structure: OK (basic check, pyyaml not installed)')
"
  if [ $? -ne 0 ]; then
    ERRORS=$((ERRORS + 1))
  fi
else
  echo "  .pre-commit-config.yaml: NOT FOUND (skipped)"
fi

# --- Runtime policy cache (#84) ---
echo "=== Validating runtime.json ==="
if [ -f .ac-guard/runtime.json ]; then
  python3 -c "import json; json.load(open('.ac-guard/runtime.json')); print('runtime.json: OK')"
else
  echo "  .ac-guard/runtime.json: NOT FOUND (skipped)"
fi

echo ""
if [ "$ERRORS" -gt 0 ]; then
  echo "=== Syntax validation FAILED ($ERRORS error(s)) ==="
  exit 1
fi

echo "=== Syntax validation PASSED ==="
