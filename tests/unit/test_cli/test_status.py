"""Tests for status, doctor, and agents commands (WP1.5c)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ac_guard.cli.main import app
from ac_guard.generator.models import STATE_FILE, GeneratedState

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_guard_yaml(tmp_path: Path, data: dict | None = None) -> Path:
    """Write a guard.yaml and return its path."""
    config = tmp_path / "guard.yaml"
    if data is None:
        data = {"version": 1, "project": {"name": "test", "language": "python"}}
    config.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return config


def _config_hash(path: Path) -> str:
    """Compute config hash matching merger._compute_config_hash."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def _write_state(
    project_root: Path,
    agents: list[str] | None = None,
    config_hash: str = "abcd1234",
    artifacts: list[str] | None = None,
) -> GeneratedState:
    """Write a state.json and return the GeneratedState."""
    state = GeneratedState(
        ac_guard_version="0.1.0",
        installed_agents=agents or ["claude-code"],
        config_hash=config_hash,
        artifacts=artifacts or ["CLAUDE.md", ".ac-guard/runtime.json"],
    )
    state_path = project_root / STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state.to_json(), encoding="utf-8")
    return state


@pytest.fixture
def installed_project(tmp_path: Path) -> Path:
    """Project with guard.yaml, .git, state.json, and artifacts."""
    config = _write_guard_yaml(tmp_path)
    (tmp_path / ".git").mkdir()
    config_hash = _config_hash(config)
    _write_state(
        tmp_path,
        agents=["claude-code"],
        config_hash=config_hash,
        artifacts=["CLAUDE.md", ".ac-guard/runtime.json", ".pre-commit-config.yaml"],
    )
    # Create actual artifact files
    (tmp_path / "CLAUDE.md").write_text("# Rules\n", encoding="utf-8")
    (tmp_path / ".ac-guard" / "runtime.json").write_text(
        json.dumps({"config_hash": config_hash}), encoding="utf-8"
    )
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# TestStatusCommand
# ---------------------------------------------------------------------------


class TestStatusCommand:
    """Tests for guard status command."""

    def test_status_shows_installed_agents(self, installed_project: Path) -> None:
        """status shows which agents are installed."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "claude-code" in result.output

    def test_status_not_installed(self, tmp_path: Path) -> None:
        """status when not installed reports it."""
        _write_guard_yaml(tmp_path)
        config = tmp_path / "guard.yaml"
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_status_detects_drift(self, installed_project: Path) -> None:
        """status detects config drift when guard.yaml changed."""
        config = installed_project / "guard.yaml"
        # Modify config to create drift
        config.write_text(
            yaml.dump(
                {"version": 1, "project": {"name": "changed", "language": "go"}},
                default_flow_style=False,
            ),
            encoding="utf-8",
        )
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "drift" in result.output.lower() or "changed" in result.output.lower()

    def test_status_no_drift_when_synced(self, installed_project: Path) -> None:
        """status shows no drift when config hash matches."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert (
            "up to date" in result.output.lower() or "synced" in result.output.lower()
        )

    def test_status_reports_missing_artifacts(self, installed_project: Path) -> None:
        """status reports artifacts listed in state but missing from disk."""
        config = installed_project / "guard.yaml"
        # Remove an artifact
        (installed_project / "CLAUDE.md").unlink()
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "CLAUDE.md" in result.output

    def test_status_with_rules_flag(self, installed_project: Path) -> None:
        """status --rules shows rule listing."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["status", "--rules", "--config", str(config)])
        assert result.exit_code == 0
        # Should show rules section (system protection rules at minimum)
        assert "rule" in result.output.lower()

    def test_status_version_mismatch(self, installed_project: Path) -> None:
        """status detects tool version mismatch."""
        config = installed_project / "guard.yaml"
        # Set state version to something different
        state_path = installed_project / STATE_FILE
        state = GeneratedState.from_json(state_path.read_text(encoding="utf-8"))
        state.ac_guard_version = "99.99.99"
        state_path.write_text(state.to_json(), encoding="utf-8")
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "version" in result.output.lower()


# ---------------------------------------------------------------------------
# TestDoctorCommand
# ---------------------------------------------------------------------------


class TestDoctorCommand:
    """Tests for guard doctor command."""

    def test_doctor_checks_python(self, installed_project: Path) -> None:
        """doctor checks Python version."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert "python" in result.output.lower()

    def test_doctor_checks_git(self, installed_project: Path) -> None:
        """doctor checks git availability."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert "git" in result.output.lower()

    def test_doctor_checks_config(self, installed_project: Path) -> None:
        """doctor validates guard.yaml."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert (
            "guard.yaml" in result.output.lower() or "config" in result.output.lower()
        )

    def test_doctor_not_initialized(self, tmp_path: Path) -> None:
        """doctor reports when not initialized — missing config is FAIL."""
        config = tmp_path / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        # Missing guard.yaml is a failure (can't diagnose without it).
        assert result.exit_code == 1
        assert "guard.yaml" in result.output.lower()

    def test_doctor_checks_artifacts(self, installed_project: Path) -> None:
        """doctor checks artifact integrity."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        # Should mention artifacts or files check
        assert "artifact" in result.output.lower() or "file" in result.output.lower()

    def test_doctor_checks_pre_commit(self, installed_project: Path) -> None:
        """doctor checks pre-commit availability."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert "pre-commit" in result.output.lower()


# ---------------------------------------------------------------------------
# TestDoctorLocalHookEntries (Phase 2 PR A)
# ---------------------------------------------------------------------------


def _yaml_with_local_hook(
    tmp_path: Path, *, entry: str, language: str = "system"
) -> Path:
    """Write guard.yaml with one repo: local hook using the given entry."""
    data = {
        "version": 1,
        "project": {"name": "t", "language": "python"},
        "code": {
            "pre-commit": {
                "hooks": [
                    {
                        "repo": "local",
                        "hooks": [
                            {
                                "id": "custom-hook",
                                "name": "Custom",
                                "entry": entry,
                                "language": language,
                            }
                        ],
                    }
                ],
            }
        },
    }
    return _write_guard_yaml(tmp_path, data)


class TestDoctorLocalHookEntries:
    """Phase 2 PR A — verify doctor catches missing local hook entries."""

    def test_entry_in_path_is_ok(self, tmp_path: Path) -> None:
        """A system-language entry resolvable in PATH is reported ok."""
        # ``python3`` is guaranteed present on every dev/CI box.
        config = _yaml_with_local_hook(tmp_path, entry="python3 -c 'pass'")
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert "[ok] custom-hook: python3 (PATH)" in result.output

    def test_entry_project_relative_is_ok(self, tmp_path: Path) -> None:
        """An entry that resolves to a file under project_root is ok."""
        script = tmp_path / "scripts" / "custom.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        config = _yaml_with_local_hook(tmp_path, entry="scripts/custom.sh")
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert "[ok] custom-hook: scripts/custom.sh (project-relative)" in result.output

    def test_missing_entry_is_fail(self, tmp_path: Path) -> None:
        """An entry absent from PATH and project yields FAIL + exit 1."""
        config = _yaml_with_local_hook(tmp_path, entry="definitely-not-a-real-tool-xyz")
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 1
        assert "[FAIL]" in result.output
        assert "definitely-not-a-real-tool-xyz" in result.output

    def test_non_system_language_is_skipped(self, tmp_path: Path) -> None:
        """language: python (not system) bypasses the PATH check entirely."""
        config = _yaml_with_local_hook(
            tmp_path, entry="mypy-but-its-pre-commit-managed", language="python"
        )
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        # Without system-language local hooks, doctor reports the "nothing
        # to verify" variant and does not FAIL even though entry is bogus.
        assert "[ok] No system-language local hooks to verify" in result.output


# ---------------------------------------------------------------------------
# TestDoctorLanguageCoverage (Phase 2 PR A)
# ---------------------------------------------------------------------------


def _init_git_with_files(tmp_path: Path, files: dict[str, str]) -> None:
    """Initialize a git repo at tmp_path and stage each (relpath → content)."""
    import subprocess

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


def _yaml_with_languages(
    tmp_path: Path, langs: dict[str, dict[str, str]] | None = None
) -> Path:
    """Write guard.yaml declaring the given languages (empty default = python)."""
    data: dict = {
        "version": 1,
        "project": {"name": "t", "language": "python"},
    }
    if langs is not None:
        data["languages"] = {
            name: {
                "tools": {
                    "format": tools.get("format", "echo fmt"),
                    "lint": tools.get("lint", "echo lint"),
                }
            }
            for name, tools in langs.items()
        }
    return _write_guard_yaml(tmp_path, data)


class TestDoctorLanguageCoverage:
    """Phase 2 PR A — language coverage (D9) detects drift between repo and config."""

    def test_declared_with_files_is_ok(self, tmp_path: Path) -> None:
        """Declared python + tracked .py files → [ok] with count."""
        _init_git_with_files(tmp_path, {f"src/a{i}.py": "" for i in range(5)})
        config = _yaml_with_languages(tmp_path, {"python": {}})
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert "[ok] python: 5 files" in result.output

    def test_declared_without_files_is_warn(self, tmp_path: Path) -> None:
        """Declared rust + zero .rs files → [WARN]."""
        _init_git_with_files(tmp_path, {"README.md": ""})
        config = _yaml_with_languages(tmp_path, {"rust": {}})
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert "[WARN] rust" in result.output
        assert "no source files found" in result.output

    def test_undeclared_above_threshold_is_warn(self, tmp_path: Path) -> None:
        """Undeclared typescript + >=3 .ts files → [WARN]."""
        _init_git_with_files(tmp_path, {f"web/b{i}.ts": "" for i in range(4)})
        config = _yaml_with_languages(tmp_path, {"python": {}})
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert "[WARN] typescript" in result.output
        assert "4 files" in result.output

    def test_undeclared_below_threshold_is_silent(self, tmp_path: Path) -> None:
        """Undeclared language with <3 files is suppressed."""
        _init_git_with_files(tmp_path, {"x.go": "", "scripts/setup.go": ""})
        config = _yaml_with_languages(tmp_path, {"python": {}})
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        # Go files below threshold → no warn line mentioning go.
        # Section 5 is the only section that reports language coverage now.
        section = result.output.lower().split("\n5.")[1]
        assert "go: " not in section, section

    def test_not_a_git_repo_does_not_crash(self, tmp_path: Path) -> None:
        """When git ls-files fails, doctor stays sane and continues.

        The git diagnostic check (Step 1) already calls out git issues,
        so the language-coverage check here just reports the empty repo
        as ``WARN`` for declared-but-missing files — that's an
        acceptable downstream signal.
        """
        config = _yaml_with_languages(tmp_path, {"python": {}})
        # No .git dir in tmp_path → git ls-files returns non-zero
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert "5. Configuration Diagnosis" in result.output


# ---------------------------------------------------------------------------
# TestDoctorStageSemanticFitMigrated
# ---------------------------------------------------------------------------
#
# Format/lint placement on non-file-scoped stages was previously a doctor
# WARN. It moved to L2 of config validation (rule code
# ``format-lint-stage-scope`` in ``test_semantic.py``), so doctor now fails
# at config-load time instead of soft-warning. The doctor side just needs
# to confirm config-load failures are surfaced via exit 1 and the rule
# message reaches the user.


def _yaml_with_stage(tmp_path: Path, stage: str, field: str, value: bool) -> Path:
    """Write a guard.yaml toggling one stage bucket field."""
    data = {
        "version": 1,
        "project": {"name": "t", "language": "python"},
        "code": {stage: {field: value}},
    }
    return _write_guard_yaml(tmp_path, data)


class TestDoctorStageSemanticFitMigrated:
    """format/lint stage-scope misconfig now fails at config-load time."""

    def test_pre_commit_format_passes_load(self, tmp_path: Path) -> None:
        """Canonical placement — config loads cleanly, doctor proceeds."""
        config = _yaml_with_stage(tmp_path, "pre-commit", "format", True)
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        # Doctor's config step printed [ok], not a load error.
        assert (
            "[FAIL]"
            not in result.output.split("Configuration")[1].split("File Integrity")[0]
        )

    def test_commit_msg_format_fails_at_load(self, tmp_path: Path) -> None:
        """commit-msg.format: true is rejected at L2 (rule format-lint-stage-scope)."""
        config = _yaml_with_stage(tmp_path, "commit-msg", "format", True)
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 1
        assert "code.commit-msg.format" in result.output

    def test_pre_rebase_lint_fails_at_load(self, tmp_path: Path) -> None:
        config = _yaml_with_stage(tmp_path, "pre-rebase", "lint", True)
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 1
        assert "code.pre-rebase.lint" in result.output


# ---------------------------------------------------------------------------
# TestDoctorStrict
# ---------------------------------------------------------------------------


def _yaml_declared_lang_no_files(tmp_path: Path, lang: str) -> Path:
    """Project declares ``lang`` in languages: but commits no source files
    for it — produces a [WARN] from doctor's language-coverage check."""
    _init_git_with_files(tmp_path, {"README.md": ""})  # one tracked non-source
    return _yaml_with_languages(tmp_path, {lang: {}})


class TestDoctorStrict:
    """--strict turns WARNs into exit-1 for CI; FAILs always exit 1."""

    def test_strict_with_warn_exits_one(self, tmp_path: Path) -> None:
        """With --strict, any WARN causes exit 1."""
        config = _yaml_declared_lang_no_files(tmp_path, "rust")
        result = runner.invoke(app, ["doctor", "--config", str(config), "--strict"])
        assert result.exit_code == 1
        assert "[WARN]" in result.output

    def test_non_strict_with_warn_exits_zero(self, tmp_path: Path) -> None:
        """Without --strict, WARN is informational and doctor still exits 0."""
        config = _yaml_declared_lang_no_files(tmp_path, "rust")
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert "[WARN]" in result.output

    def test_fail_always_exits_one(self, tmp_path: Path) -> None:
        """FAIL unconditionally exits 1, regardless of --strict."""
        config = _yaml_with_local_hook(tmp_path, entry="definitely-not-a-real-tool-xyz")
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# TestAgentsCommand
# ---------------------------------------------------------------------------


class TestAgentsCommand:
    """Tests for guard agents command."""

    def test_agents_lists_all(self) -> None:
        """agents shows all supported agents."""
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        assert "claude-code" in result.output.lower()
        assert "cursor" in result.output.lower()
        assert "opencode" in result.output.lower()
        assert "copilot" in result.output.lower()
        assert "kilocode" in result.output.lower()

    def test_agents_shows_capabilities(self) -> None:
        """agents shows capability information."""
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        assert "block" in result.output.lower()

    def test_agents_shows_installed_status(
        self, installed_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """agents marks installed agents."""
        monkeypatch.chdir(installed_project)
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        # claude-code should be marked as installed
        output_lower = result.output.lower()
        assert "claude-code" in output_lower
        assert "installed" in output_lower

    def test_agents_no_installation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """agents works when nothing is installed."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        # Should still list all agents
        assert "claude-code" in result.output.lower()

    def test_agents_shows_rule_doc_path(self) -> None:
        """agents shows rule document paths."""
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        assert "claude.md" in result.output.lower()


class TestStatusJsonOutput:
    """Tests for status --format json."""

    def test_status_json_installed(self, installed_project: Path) -> None:
        """JSON output includes installation details."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(
            app, ["status", "--config", str(config), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["installed"] is True
        assert "claude-code" in data["installed_agents"]
        assert "config_hash" in data
        assert "artifacts" in data

    def test_status_json_not_installed(self, tmp_path: Path) -> None:
        """JSON output when not installed."""
        config = tmp_path / "guard.yaml"
        config.write_text("version: 1\n", encoding="utf-8")
        result = runner.invoke(
            app, ["status", "--config", str(config), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["installed"] is False
