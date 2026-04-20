#!/usr/bin/env python3
"""Fail if any test file calls ``read_text`` or ``write_text`` without
explicitly passing ``encoding="utf-8"``. See issue #108 for context.

Walks balanced parentheses so multi-line calls are handled correctly.
Exits 0 if clean, 1 with a file:line:snippet report otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_CALL_RE = re.compile(r"\.(read_text|write_text)\(")


def _find_close(src: str, open_paren: int) -> int:
    """Return index of the ``)`` matching ``src[open_paren] == '('``.

    Respects string literals (single, double, triple). Returns -1 on
    unbalanced input.
    """
    depth = 0
    i = open_paren
    in_str: str | None = None
    n = len(src)
    while i < n:
        c = src[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in ("'", '"'):
            triple = src[i : i + 3]
            if triple in ('"""', "'''"):
                end = src.find(triple, i + 3)
                if end == -1:
                    return -1
                i = end + 3
                continue
            in_str = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def violations(path: Path) -> list[tuple[int, str]]:
    src = path.read_text(encoding="utf-8")
    out: list[tuple[int, str]] = []
    for m in _CALL_RE.finditer(src):
        open_paren = m.end() - 1
        close = _find_close(src, open_paren)
        if close == -1:
            continue
        inner = src[open_paren + 1 : close]
        if "encoding=" in inner:
            continue
        line = src[: m.start()].count("\n") + 1
        snippet = src[m.start() : close + 1].replace("\n", " ")[:80]
        out.append((line, snippet))
    return out


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv[1:]] or list(Path("tests").rglob("*.py"))
    found = False
    for p in paths:
        if not p.is_file():
            continue
        for line, snippet in violations(p):
            print(f"{p}:{line}: {snippet}")
            found = True
    if found:
        print(
            'error: add encoding="utf-8" to all read_text/write_text '
            "calls in tests/ (see issue #108)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
