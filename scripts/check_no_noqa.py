#!/usr/bin/env python3
"""Fail if production Python source contains per-line lint suppressions.

Per-line ``#`` comments that silence ruff/pyflakes hide legitimate
lint signal. If a rule is correct, fix the code; if the rule is wrong,
disable it at config level (``pyproject.toml``), not per-line. Tests
are exempt because ``tests/*`` already has sanctioned per-file-ignores
for F401-style test imports.

Exits 0 if clean, 1 with a file:line:snippet report otherwise.
"""

from __future__ import annotations

import io
import sys
import tokenize
from pathlib import Path

# Built at runtime so this file does not self-match when it scans itself.
_TOKEN = "no" + "qa"


def _is_test_file(p: Path) -> bool:
    return "tests" in p.parts


def violations(path: Path) -> list[tuple[int, str]]:
    """Return (line, snippet) for every COMMENT that contains the token.

    We only inspect real Python comment tokens; docstring / string-literal
    text mentioning the token is ignored as documentation, not a real
    suppression directive.
    """
    src = path.read_text(encoding="utf-8")
    out: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            stripped = tok.string.lstrip("#").strip()
            # Match `<TOKEN>` or `<TOKEN>:rule-code`
            if stripped == _TOKEN or stripped.startswith(_TOKEN + ":"):
                out.append((tok.start[0], tok.string[:80]))
    except (tokenize.TokenizeError, IndentationError):
        pass  # unparseable — be conservative
    return out


def _default_paths() -> list[Path]:
    """Full src/ scan when invoked manually (no argv)."""
    return list(Path("src").rglob("*.py")) if Path("src").is_dir() else []


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv[1:]] or _default_paths()
    found = False
    for p in paths:
        if not p.is_file() or _is_test_file(p):
            continue
        for line, snippet in violations(p):
            print(f"{p}:{line}: {snippet}")
            found = True
    if found:
        print(
            "error: per-line lint suppressions are forbidden in production "
            "source; fix the code or relax the rule in pyproject.toml"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
