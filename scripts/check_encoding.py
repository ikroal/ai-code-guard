#!/usr/bin/env python3
"""Fail if any Python file calls ``read_text`` or ``write_text`` without
explicitly passing an ``encoding`` argument. See issue #108 for context.

Rationale: Windows defaults Path.read_text() / .write_text() to cp1252
until PEP 686 lands in Python 3.15. Requiring encoding="utf-8"
explicitly makes code behave identically across platforms.

Scope: every Python file under src/ and tests/; production code gets
the same scrutiny as tests. Walks balanced parentheses so multi-line
calls are handled correctly. Exits 0 if clean, 1 with a file:line:
snippet report otherwise.
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from pathlib import Path

_CALL_RE = re.compile(r"\.(read_text|write_text)\(")


def _string_regions(src: str) -> list[tuple[int, int]]:
    """Return [(start, end)] byte offsets for every string literal.

    Matches inside these regions are docstring / comment text, not
    actual API calls — must be skipped to avoid false positives.
    """
    regions: list[tuple[int, int]] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(src).readline)
        line_offsets = [0]
        for line in src.splitlines(keepends=True):
            line_offsets.append(line_offsets[-1] + len(line))
        for tok in tokens:
            if tok.type in (tokenize.STRING, tokenize.FSTRING_MIDDLE):
                (r0, c0), (r1, c1) = tok.start, tok.end
                start = line_offsets[r0 - 1] + c0
                end = line_offsets[r1 - 1] + c1
                regions.append((start, end))
    except (tokenize.TokenizeError, IndentationError):
        # Unparseable file — be conservative, return no regions so all
        # matches are considered real. Caller will still get a (noisy)
        # report rather than silent pass.
        pass
    return regions


def _in_string(pos: int, regions: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in regions)


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
    regions = _string_regions(src)
    out: list[tuple[int, str]] = []
    for m in _CALL_RE.finditer(src):
        if _in_string(m.start(), regions):
            # Match sits inside a docstring / string literal — not a real call.
            continue
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


def _default_paths() -> list[Path]:
    """Full project scan when invoked manually (no argv)."""
    out: list[Path] = []
    for root in ("src", "tests"):
        if Path(root).is_dir():
            out.extend(Path(root).rglob("*.py"))
    return out


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv[1:]] or _default_paths()
    found = False
    for p in paths:
        if not p.is_file():
            continue
        for line, snippet in violations(p):
            print(f"{p}:{line}: {snippet}")
            found = True
    if found:
        print(
            'error: pass encoding="utf-8" explicitly to all read_text/'
            "write_text calls (see issue #108)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
