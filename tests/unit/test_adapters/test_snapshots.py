"""Snapshot regression tests for AgentAdapter rendering.

Captures exact ``render_rule_doc`` and ``hook_files`` output of every
built-in adapter against a canonical :class:`BehaviorConfig` fixture.
The snapshots act as the unbroken-output guarantee across the adapters
refactor (builtins/ subpackage, frozen registry, derived template
names, _render private surface).

Regenerate after an intentional output change:

    AC_GUARD_UPDATE_SNAPSHOTS=1 pytest tests/unit/test_adapters/test_snapshots.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from ac_guard.adapters import AgentAdapter, get_adapter, list_adapters
from ac_guard.config.models import BehaviorConfig, OperationRules, Rule

_SNAPSHOT_DIR = Path(__file__).parent / "_snapshots"
_UPDATE = os.environ.get("AC_GUARD_UPDATE_SNAPSHOTS") == "1"

_BUILTIN_NAMES = ("claude-code", "cursor", "opencode", "copilot", "kilocode")

# Hook templates bake ``sys.executable`` so the rendered hook can
# re-exec into the interpreter that ran ``ac-guard install``. That
# path is machine-dependent (macOS vs. Linux vs. Windows runners), so
# we pin it during snapshot tests to keep the captured output
# reproducible across hosts. Tests in test_hooks.py still cover the
# real-``sys.executable`` baking behaviour dynamically.
_PINNED_PYTHON = "/usr/local/bin/python3"


@pytest.fixture(autouse=True)
def _pin_sys_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "executable", _PINNED_PYTHON)


def _canonical_behavior() -> BehaviorConfig:
    """Build a representative BehaviorConfig covering all rule shapes.

    Each operation has at least one entry in each of forbidden /
    require_approval / allow, with a mix of glob and regex patterns,
    custom messages, custom reasons, and varied source labels — so the
    snapshot exercises every branch a template might take.
    """
    return BehaviorConfig(
        read=OperationRules(
            forbidden=[
                Rule(
                    pattern="file:.env*",
                    reason="environment files contain secrets",
                    source="default",
                )
            ],
            require_approval=[
                Rule(
                    pattern="file:**/credentials.json",
                    message="contains credentials, confirm before reading",
                    source="ruleset:strict",
                )
            ],
            allow=[Rule(pattern="file:**/*.py", source="user")],
        ),
        write=OperationRules(
            forbidden=[
                Rule(
                    pattern="file:.git/**",
                    reason="repo internals must not be edited",
                    source="default",
                )
            ],
            require_approval=[
                Rule(
                    pattern="file:pyproject.toml",
                    message="dependency change — confirm intent",
                    source="user",
                )
            ],
            allow=[],
        ),
        execute=OperationRules(
            forbidden=[
                Rule(
                    pattern=r"^rm\s+-rf\s+/",
                    reason="filesystem destruction",
                    regex=True,
                    source="default",
                )
            ],
            require_approval=[
                Rule(
                    pattern="shell:git push --force*",
                    message="rewrites remote history",
                    source="user",
                )
            ],
            allow=[Rule(pattern="shell:pytest *", source="user")],
        ),
    )


def _normalize_eof(text: str) -> str:
    """Collapse trailing newlines to exactly one ``\\n`` (POSIX text-file form).

    Snapshots are committed alongside source and pass through standard
    pre-commit hooks (``end-of-file-fixer``) that strip extra trailing
    blank lines. Normalising both sides on read/write keeps the
    canonical form stable across local generation, CI checkout, and
    hook fix-ups.
    """
    return text.rstrip("\n") + "\n" if text else text


def _compare_or_write(actual: str, snapshot_path: Path) -> None:
    """Assert *actual* equals snapshot file content, or write under update mode.

    When ``AC_GUARD_UPDATE_SNAPSHOTS=1`` is set the file is (re)created
    and the assertion is skipped. Without the flag, a missing snapshot
    fails the test loudly so CI can never silently accept new output.
    """
    actual = _normalize_eof(actual)
    if _UPDATE:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(actual, encoding="utf-8")
        return
    if not snapshot_path.exists():
        pytest.fail(
            f"Snapshot missing: {snapshot_path}.\n"
            "Regenerate with: AC_GUARD_UPDATE_SNAPSHOTS=1 pytest "
            f"{Path(__file__).name}"
        )
    expected = _normalize_eof(snapshot_path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"Snapshot mismatch: {snapshot_path}\n"
        "If the change is intentional regenerate with "
        "AC_GUARD_UPDATE_SNAPSHOTS=1 pytest"
    )


@pytest.fixture(scope="module")
def behavior() -> BehaviorConfig:
    return _canonical_behavior()


def test_builtin_names_complete() -> None:
    """``list_adapters()`` returns exactly the five expected built-ins."""
    assert list_adapters() == sorted(_BUILTIN_NAMES)


@pytest.mark.parametrize("name", _BUILTIN_NAMES)
def test_rule_doc_snapshot(name: str, behavior: BehaviorConfig) -> None:
    """Each adapter's ``render_rule_doc`` matches its frozen snapshot."""
    adapter: AgentAdapter = get_adapter(name)
    actual = adapter.render_rule_doc(behavior)
    _compare_or_write(actual, _SNAPSHOT_DIR / f"{name}__rule_doc.md")


@pytest.mark.parametrize("name", _BUILTIN_NAMES)
def test_hook_files_snapshot(name: str, behavior: BehaviorConfig) -> None:
    """Each adapter's ``hook_files`` manifest and contents match snapshots."""
    adapter: AgentAdapter = get_adapter(name)
    files = sorted(adapter.hook_files(behavior), key=lambda f: f.path)

    manifest_lines = [f"{f.path}\texecutable={f.executable}" for f in files]
    manifest = "\n".join(manifest_lines) + ("\n" if manifest_lines else "")
    _compare_or_write(manifest, _SNAPSHOT_DIR / f"{name}__hook_manifest.txt")

    for spec in files:
        safe_name = spec.path.replace("/", "__").replace("\\", "__")
        _compare_or_write(
            spec.content,
            _SNAPSHOT_DIR / f"{name}__hook__{safe_name}",
        )
