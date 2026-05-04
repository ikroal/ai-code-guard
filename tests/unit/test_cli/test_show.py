"""Tests for ``ac-guard show`` command.

Covers the (section, format) matrix:

- section ∈ {behavior, code, rulesets, all}
- format ∈ {text, table, json}
- error paths: bad section / bad format / missing config

Replaces the previous ``test_validation.py`` (which only exercised the
``code`` section in ``text`` and ``table`` shapes).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from ac_guard.cli.main import app

runner = CliRunner()


def _write_config(tmp_path: Path, data: dict) -> Path:
    config_path = tmp_path / "guard.yaml"
    config_path.write_text(yaml.dump(data), encoding="utf-8")
    return config_path


def _basic_config() -> dict:
    """A guard.yaml dict that exercises behavior + code + rulesets."""
    return {
        "version": 1,
        "project": {"name": "demo", "language": "python"},
        "rulesets": ["org-defaults"],
        "behavior": {
            "read": {"forbidden": [{"pattern": "file:secret/**"}]},
            "execute": {"forbidden": [{"pattern": "shell:rm -rf*"}]},
        },
        "code": {
            "pre-commit": {
                "format": True,
                "lint": True,
                "checks": {
                    "mypy": {
                        "command": "mypy src/",
                        "timeout": 60,
                        "types": ["python"],
                    },
                },
            },
            "pre-push": {
                "checks": {
                    "pytest": {"command": "pytest -q"},
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Section: code
# ---------------------------------------------------------------------------


class TestSectionCode:
    """code section across all three formats."""

    def test_text_lists_checks_per_stage(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app, ["show", "--section", "code", "--config", str(config)]
        )
        assert result.exit_code == 0, result.output
        assert "Code gates" in result.output
        assert "pre-commit stage:" in result.output
        assert "format" in result.output
        assert "mypy" in result.output
        assert "pre-push stage:" in result.output
        assert "pytest" in result.output

    def test_table_renders_columns(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app,
            ["show", "--section", "code", "--format", "table", "--config", str(config)],
        )
        assert result.exit_code == 0, result.output
        assert "Name" in result.output
        assert "Stage" in result.output
        assert "Type" in result.output
        assert "mypy" in result.output
        assert "60s" in result.output  # timeout column

    def test_json_emits_per_stage_dict(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app,
            ["show", "--section", "code", "--format", "json", "--config", str(config)],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "code" in payload
        assert "pre-commit" in payload["code"]
        assert payload["code"]["pre-commit"]["format"] is True
        assert "mypy" in payload["code"]["pre-commit"]["checks"]


# ---------------------------------------------------------------------------
# Section: behavior
# ---------------------------------------------------------------------------


class TestSectionBehavior:
    """behavior section across all three formats."""

    def test_text_lists_rules(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app, ["show", "--section", "behavior", "--config", str(config)]
        )
        assert result.exit_code == 0, result.output
        assert "Behavior rules" in result.output
        assert "read.forbidden" in result.output
        assert "file:secret/**" in result.output
        assert "execute.forbidden" in result.output
        assert "shell:rm -rf*" in result.output

    def test_table_renders_columns(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app,
            [
                "show",
                "--section",
                "behavior",
                "--format",
                "table",
                "--config",
                str(config),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Operation" in result.output
        assert "Tier" in result.output
        assert "Pattern" in result.output

    def test_json_groups_by_op_then_tier(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app,
            [
                "show",
                "--section",
                "behavior",
                "--format",
                "json",
                "--config",
                str(config),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "behavior" in payload
        assert "read" in payload["behavior"]
        assert any(
            entry["pattern"] == "file:secret/**"
            for entry in payload["behavior"]["read"]["forbidden"]
        )

    def test_no_user_behavior_still_renders_baseline(self, tmp_path: Path) -> None:
        # The system injects baseline rules (e.g. forbid `git commit
        # --no-verify`). Even with an empty user-defined ``behavior:``
        # block, the renderer must still complete cleanly and report
        # those baseline rules with source ``[system]``.
        cfg = _basic_config()
        cfg.pop("behavior")
        config = _write_config(tmp_path, cfg)
        result = runner.invoke(
            app, ["show", "--section", "behavior", "--config", str(config)]
        )
        assert result.exit_code == 0, result.output
        assert "Behavior rules" in result.output
        assert "[system]" in result.output


# ---------------------------------------------------------------------------
# Section: rulesets
# ---------------------------------------------------------------------------


class TestSectionRulesets:
    def test_text_lists_referenced_bundles(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app, ["show", "--section", "rulesets", "--config", str(config)]
        )
        assert result.exit_code == 0, result.output
        assert "Rulesets" in result.output
        assert "org-defaults" in result.output

    def test_json_emits_list(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app,
            [
                "show",
                "--section",
                "rulesets",
                "--format",
                "json",
                "--config",
                str(config),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["rulesets"] == ["org-defaults"]

    def test_empty_rulesets_prints_placeholder(self, tmp_path: Path) -> None:
        cfg = _basic_config()
        cfg.pop("rulesets")
        config = _write_config(tmp_path, cfg)
        result = runner.invoke(
            app, ["show", "--section", "rulesets", "--config", str(config)]
        )
        assert result.exit_code == 0, result.output
        assert "no rulesets referenced" in result.output


# ---------------------------------------------------------------------------
# Section: all
# ---------------------------------------------------------------------------


class TestSectionAll:
    def test_text_emits_all_three_sections(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(app, ["show", "--config", str(config)])
        assert result.exit_code == 0, result.output
        assert "Behavior rules" in result.output
        assert "Code gates" in result.output
        assert "Rulesets" in result.output

    def test_json_includes_all_three_keys(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app, ["show", "--format", "json", "--config", str(config)]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert set(payload.keys()) == {"behavior", "code", "rulesets"}


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_unknown_section_exits_1(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app, ["show", "--section", "bogus", "--config", str(config)]
        )
        assert result.exit_code == 1
        assert "Unknown section" in result.output

    def test_unknown_format_exits_1(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _basic_config())
        result = runner.invoke(
            app, ["show", "--format", "yaml", "--config", str(config)]
        )
        assert result.exit_code == 1
        assert "Unknown format" in result.output

    def test_missing_config_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["show", "--config", str(tmp_path / "nope.yaml")])
        assert result.exit_code == 1
        assert "Error" in result.output
