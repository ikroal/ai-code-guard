"""Integration test: generated hooks work without ac-guard on $PATH.

This is the core regression for the install-time path-baking fix.
Generated git/agent hooks must continue to fire when callers (Claude
Code, generic CI runners, IDEs that don't auto-source the venv) launch
them from a shell whose ``$PATH`` lacks the project venv. The hooks
achieve this by exec-ing absolute paths that the generator bakes into
the rendered files at install time.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from ac_guard.cli.main import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# Minimum PATH that still gives the hook access to standard shell
# utilities (sh, cat, jq if needed) while excluding any venv where
# ac-guard might live. This is the worst-case caller environment we
# need to support.
_MINIMAL_PATH = "/usr/bin:/bin"


def _scaffold_project(tmp_path: Path, agent: str) -> Path:
    """Init a project with .git and run install for the requested agent."""
    config = tmp_path / "guard.yaml"
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    runner.invoke(app, ["init", "--language", "python", "--output", str(config)])
    # Some default git stages need to be active for git_hooks to render;
    # the python preset already declares them.
    result = runner.invoke(app, ["install", "--agent", agent, "--config", str(config)])
    assert result.exit_code == 0, result.output
    return config


class TestGitHooksBakeAbsolutePath:
    """Generated git hooks embed an absolute ac-guard path."""

    def test_pre_commit_uses_absolute_path(self, tmp_path: Path) -> None:
        _scaffold_project(tmp_path, agent="claude-code")
        hook_path = tmp_path / ".git" / "hooks" / "pre-commit"
        assert hook_path.is_file()
        content = hook_path.read_text(encoding="utf-8")
        # Pre-fix shape: `ac-guard run --stage pre-commit` (relies on PATH).
        # Post-fix shape: `exec "/abs/path/ac-guard" run --stage pre-commit`.
        assert 'exec "/' in content
        assert content.rstrip().endswith("run --stage pre-commit")

    def test_pre_push_uses_absolute_path(self, tmp_path: Path) -> None:
        _scaffold_project(tmp_path, agent="claude-code")
        hook_path = tmp_path / ".git" / "hooks" / "pre-push"
        if not hook_path.is_file():
            # pre-push is optional based on active stages; skip if absent.
            return
        content = hook_path.read_text(encoding="utf-8")
        assert 'exec "/' in content
        assert content.rstrip().endswith("run --stage pre-push")

    def test_pre_commit_runs_with_minimal_path(self, tmp_path: Path) -> None:
        """Hook executes successfully with PATH stripped of any venv.

        This is the contract: a tool that doesn't activate the venv
        (e.g. Claude Code's PreToolUse hook) must still be able to fire
        the gate.
        """
        _scaffold_project(tmp_path, agent="claude-code")
        hook_path = tmp_path / ".git" / "hooks" / "pre-commit"

        # Make sure the hook is executable as `ac-guard install` would
        # have set the +x bit; CliRunner runs in-process and the
        # write_artifacts step does set the mode.
        assert hook_path.stat().st_mode & 0o100, "hook must be executable"

        result = subprocess.run(
            [str(hook_path)],
            cwd=tmp_path,
            env={"PATH": _MINIMAL_PATH, "HOME": str(tmp_path)},
            capture_output=True,
            text=True,
            check=False,
        )
        # The hook may succeed (no checks configured) or report a
        # configured failure, but must NOT crash with `command not
        # found` (exit 127) — that would mean PATH dependence resurfaced.
        assert result.returncode != 127, (
            f"hook fell back to PATH lookup of ac-guard; stderr={result.stderr!r}"
        )


class TestCursorHookBakesPython:
    """Cursor hook embeds an absolute python interpreter path."""

    def test_check_sh_uses_absolute_python(self, tmp_path: Path) -> None:
        _scaffold_project(tmp_path, agent="cursor")
        hook_path = tmp_path / ".cursor" / "hooks" / "check.sh"
        assert hook_path.is_file()
        content = hook_path.read_text(encoding="utf-8")
        # Pre-fix shape: `... | python3 -m ac_guard.action_guard ...`.
        # Post-fix shape: `... | "/abs/python3" -m ac_guard.action_guard ...`.
        assert "-m ac_guard.action_guard" in content
        assert "| python3 -m" not in content
        assert '| "/' in content

    def test_check_sh_runs_with_minimal_path(self, tmp_path: Path) -> None:
        """Cursor hook fires under a stripped PATH."""
        _scaffold_project(tmp_path, agent="cursor")
        hook_path = tmp_path / ".cursor" / "hooks" / "check.sh"

        # Cursor hook reads stdin JSON and prints a JSON decision.
        result = subprocess.run(
            [str(hook_path)],
            input='{"tool":"Read","args":{}}',
            cwd=tmp_path,
            env={"PATH": _MINIMAL_PATH, "HOME": str(tmp_path)},
            capture_output=True,
            text=True,
            check=False,
        )
        # 127 = "command not found" — would mean the bake failed and
        # the hook fell back to PATH lookup of `python3`.
        assert result.returncode != 127, (
            f"cursor hook fell back to PATH lookup; stderr={result.stderr!r}"
        )


class TestOpenCodePluginBakesPython:
    """OpenCode TS plugin source embeds an absolute python path constant."""

    def test_ts_source_has_absolute_python_constant(self, tmp_path: Path) -> None:
        _scaffold_project(tmp_path, agent="opencode")
        plugin_path = tmp_path / ".opencode" / "plugins" / "ac-guard.ts"
        assert plugin_path.is_file()
        content = plugin_path.read_text(encoding="utf-8")
        # Constant must hold an absolute path so `execSync` does not
        # depend on the surrounding `$PATH`.
        assert 'const PYTHON_EXECUTABLE = "/' in content
        assert "python3 -m ac_guard.action_guard" not in content
