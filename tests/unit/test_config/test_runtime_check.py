"""Tests for ac_guard.config.runtime_check — L4 semantic-runtime checks.

L4 holds the semantic checks that need a runtime context (filesystem,
PATH, git working tree). They live in ``config.runtime_check`` rather
than ``config.semantic`` so the file boundary makes the IO contract
visible: ``semantic.py`` is zero-IO, ``runtime_check.py`` is the only
config-layer module allowed to touch the outside world.

doctor consumes ``runtime_check(resolved, project_root)`` and renders
the returned ``Diagnostic`` list; these tests exercise the helpers in
isolation under a controlled tmp_path.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Importing the submodule populates ``sys.modules`` even though the
# ``__init__.py`` rebinds the ``runtime_check`` *attribute* of the
# config package to the function. Reaching into ``sys.modules`` is the
# only way to get a handle on the actual submodule for ``__all__``
# introspection.
import ac_guard.config.runtime_check  # noqa: F401  (registers in sys.modules)
from ac_guard.config.models import (
    BehaviorConfig,
    CodeConfig,
    LanguageTools,
    OutputConfig,
    PreCommitHook,
    PreCommitRepo,
    ResolvedConfig,
    StageBucket,
)

rc = sys.modules["ac_guard.config.runtime_check"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolved(
    *,
    code: CodeConfig | None = None,
    languages: dict[str, LanguageTools] | None = None,
    rulesets: list[str] | None = None,
) -> ResolvedConfig:
    return ResolvedConfig(
        version=1,
        project_name="t",
        project_language="python",
        behavior=BehaviorConfig.empty(),
        code=code or CodeConfig(),
        languages=languages or {},
        output=OutputConfig(),
        rulesets=rulesets or [],
    )


def _local_system_hook(hook_id: str, entry: str) -> PreCommitRepo:
    """Build a ``repo: local`` + ``language: system`` hook entry."""
    return PreCommitRepo(
        repo="local",
        rev=None,
        hooks=[PreCommitHook(id=hook_id, extra={"language": "system", "entry": entry})],
    )


def _git_init(tmp_path: Path, files: dict[str, str]) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    for relpath, content in files.items():
        full = tmp_path / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        subprocess.run(
            ["git", "add", relpath],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )


# ---------------------------------------------------------------------------
# Diagnostic shape
# ---------------------------------------------------------------------------


class TestDiagnosticShape:
    """Diagnostic is a frozen dataclass with three fields."""

    def test_levels_are_known(self) -> None:
        for level in ("ok", "warn", "fail"):
            d = rc.Diagnostic(level=level, path="x", message="y")
            assert d.level == level

    def test_is_frozen(self) -> None:
        d = rc.Diagnostic(level="ok", path="x", message="y")
        with pytest.raises((AttributeError, TypeError)):
            d.path = "z"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _verify_command_paths
# ---------------------------------------------------------------------------


class TestVerifyCommandPaths:
    """Local-system hook entries' first token must be PATH-resolvable
    or live as a file under project_root."""

    def test_resolvable_via_path_is_ok(self, tmp_path: Path) -> None:
        # ``python3`` is universally on PATH in the test env (.venv was
        # used to launch pytest).
        bucket = StageBucket(hooks=[_local_system_hook("h1", "python3 -c 'pass'")])
        cfg = _resolved(code=CodeConfig(pre_commit=bucket))
        diags = rc._verify_command_paths(cfg, tmp_path)
        assert any(d.level == "ok" for d in diags)
        assert all(d.level != "fail" for d in diags)

    def test_resolvable_via_project_relative_is_ok(self, tmp_path: Path) -> None:
        script = tmp_path / "scripts" / "custom.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        bucket = StageBucket(hooks=[_local_system_hook("h1", "scripts/custom.sh")])
        cfg = _resolved(code=CodeConfig(pre_commit=bucket))
        diags = rc._verify_command_paths(cfg, tmp_path)
        assert any(d.level == "ok" for d in diags)

    def test_unresolvable_is_fail(self, tmp_path: Path) -> None:
        bucket = StageBucket(hooks=[_local_system_hook("h1", "definitely-missing-xyz")])
        cfg = _resolved(code=CodeConfig(pre_commit=bucket))
        diags = rc._verify_command_paths(cfg, tmp_path)
        fails = [d for d in diags if d.level == "fail"]
        assert len(fails) == 1
        assert "definitely-missing-xyz" in fails[0].message

    def test_non_system_language_skipped(self, tmp_path: Path) -> None:
        """Python/node/docker hooks have pre-commit install the entry
        into an isolated env; we can't (and shouldn't) precheck them."""
        bucket = StageBucket(
            hooks=[
                PreCommitRepo(
                    repo="local",
                    rev=None,
                    hooks=[
                        PreCommitHook(
                            id="h1",
                            extra={"language": "python", "entry": "missing-tool"},
                        )
                    ],
                )
            ]
        )
        cfg = _resolved(code=CodeConfig(pre_commit=bucket))
        diags = rc._verify_command_paths(cfg, tmp_path)
        assert all(d.level != "fail" for d in diags)

    def test_no_local_system_hooks_emits_ok_summary(self, tmp_path: Path) -> None:
        cfg = _resolved()
        diags = rc._verify_command_paths(cfg, tmp_path)
        assert len(diags) == 1
        assert diags[0].level == "ok"


# ---------------------------------------------------------------------------
# _verify_language_coverage
# ---------------------------------------------------------------------------


class TestVerifyLanguageCoverage:
    """Compare ``languages:`` declarations to git-tracked source files."""

    def test_declared_with_files_is_ok(self, tmp_path: Path) -> None:
        _git_init(tmp_path, {f"src/a{i}.py": "" for i in range(5)})
        cfg = _resolved(
            languages={"python": LanguageTools(format="black", lint="ruff")}
        )
        diags = rc._verify_language_coverage(cfg, tmp_path)
        assert any(d.level == "ok" and "python" in d.message for d in diags)

    def test_declared_without_files_is_warn(self, tmp_path: Path) -> None:
        _git_init(tmp_path, {"README.md": ""})
        cfg = _resolved(
            languages={"rust": LanguageTools(format="rustfmt", lint="clippy")}
        )
        diags = rc._verify_language_coverage(cfg, tmp_path)
        warns = [d for d in diags if d.level == "warn"]
        assert any("rust" in d.message for d in warns)

    def test_undeclared_above_threshold_is_warn(self, tmp_path: Path) -> None:
        _git_init(tmp_path, {f"web/b{i}.ts": "" for i in range(4)})
        cfg = _resolved(
            languages={"python": LanguageTools(format="black", lint="ruff")}
        )
        diags = rc._verify_language_coverage(cfg, tmp_path)
        warns = [d for d in diags if d.level == "warn"]
        assert any("typescript" in d.message for d in warns)

    def test_undeclared_below_threshold_is_silent(self, tmp_path: Path) -> None:
        _git_init(tmp_path, {"x.go": "", "scripts/setup.go": ""})
        cfg = _resolved(
            languages={"python": LanguageTools(format="black", lint="ruff")}
        )
        diags = rc._verify_language_coverage(cfg, tmp_path)
        assert not any("go" in d.message.lower() for d in diags)

    def test_no_repo_does_not_crash(self, tmp_path: Path) -> None:
        cfg = _resolved(
            languages={"python": LanguageTools(format="black", lint="ruff")}
        )
        # No .git dir → counts come back empty; declared with 0 files = WARN.
        diags = rc._verify_language_coverage(cfg, tmp_path)
        # Should not raise; check output is a list.
        assert isinstance(diags, list)


# ---------------------------------------------------------------------------
# _verify_ruleset_paths
# ---------------------------------------------------------------------------


class TestVerifyRulesetPaths:
    """Local ruleset paths must exist; URLs / git refs are not checked."""

    def test_existing_local_path_is_ok(self, tmp_path: Path) -> None:
        rs = tmp_path / "rules.yaml"
        rs.write_text("version: 1\n", encoding="utf-8")
        cfg = _resolved(rulesets=[str(rs)])
        diags = rc._verify_ruleset_paths(cfg, tmp_path)
        assert all(d.level != "fail" for d in diags)

    def test_missing_local_path_is_fail(self, tmp_path: Path) -> None:
        cfg = _resolved(rulesets=[str(tmp_path / "missing.yaml")])
        diags = rc._verify_ruleset_paths(cfg, tmp_path)
        fails = [d for d in diags if d.level == "fail"]
        assert len(fails) == 1
        assert "missing.yaml" in fails[0].message

    def test_git_url_not_checked(self, tmp_path: Path) -> None:
        """git@... and https://... refer to remote repos; no IO check."""
        cfg = _resolved(
            rulesets=[
                "git@github.com:org/rules.git",
                "https://example.com/rules.git",
            ]
        )
        diags = rc._verify_ruleset_paths(cfg, tmp_path)
        # No FAIL on remote refs.
        assert all(d.level != "fail" for d in diags)

    def test_relative_path_resolved_under_project_root(self, tmp_path: Path) -> None:
        rs = tmp_path / "rules.yaml"
        rs.write_text("version: 1\n", encoding="utf-8")
        cfg = _resolved(rulesets=["rules.yaml"])
        diags = rc._verify_ruleset_paths(cfg, tmp_path)
        assert all(d.level != "fail" for d in diags)


# ---------------------------------------------------------------------------
# runtime_check public entry
# ---------------------------------------------------------------------------


class TestRuntimeCheck:
    """The public entry runs all helpers and concatenates diagnostics."""

    def test_returns_list_of_diagnostics(self, tmp_path: Path) -> None:
        cfg = _resolved()
        diags = rc.runtime_check(cfg, tmp_path)
        assert isinstance(diags, list)
        assert all(isinstance(d, rc.Diagnostic) for d in diags)

    def test_aggregates_failures_from_multiple_helpers(self, tmp_path: Path) -> None:
        cfg = _resolved(
            code=CodeConfig(
                pre_commit=StageBucket(
                    hooks=[_local_system_hook("h1", "missing-bin-xyz")]
                )
            ),
            rulesets=[str(tmp_path / "missing.yaml")],
        )
        diags = rc.runtime_check(cfg, tmp_path)
        fails = [d for d in diags if d.level == "fail"]
        # One from command-paths, one from ruleset-paths.
        assert len(fails) >= 2

    def test_public_module_surface(self) -> None:
        assert "runtime_check" in rc.__all__
        assert "Diagnostic" in rc.__all__
