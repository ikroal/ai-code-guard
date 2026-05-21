"""Tests for config multi-source merger (WP1.2c)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ac_guard.config.exceptions import (
    ConfigFileNotFoundError,
    ConfigSyntaxError,
    ConfigWarning,
)
from ac_guard.config.merger import (
    _SYSTEM_EXECUTE_FORBIDDEN,
    _SYSTEM_PROTECTION_PATTERNS,
    resolve_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, data: dict, filename: str = "guard.yaml") -> Path:
    """Dump *data* as YAML into a temporary file and return its path."""
    p = tmp_path / filename
    p.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return p


def _minimal_guard(**overrides: object) -> dict:
    """Return a minimal valid guard.yaml dict with optional overrides."""
    base: dict = {"version": 1, "project": {"language": "python"}}
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TestResolveConfigMinimal
# ---------------------------------------------------------------------------


class TestResolveConfigMinimal:
    """Minimal guard.yaml produces valid ResolvedConfig with defaults."""

    def test_returns_resolved_config(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        assert result.version == 1
        assert result.project_language == "python"

    def test_project_name_defaults_to_dir_name(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        assert result.project_name == tmp_path.name

    def test_explicit_project_name(self, tmp_path: Path) -> None:
        data = _minimal_guard()
        data["project"]["name"] = "my-project"
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.project_name == "my-project"

    def test_config_hash_non_empty(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        assert result.config_hash
        assert len(result.config_hash) == 8

    def test_default_code_config(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        # Defaults from _DEFAULT_CONFIG: pre-commit.format=True,
        # pre-push.lint=True.
        assert result.code.pre_commit.format is True
        assert result.code.pre_push.lint is True
        assert result.code.pre_commit.checks == {}
        assert result.code.pre_push.checks == {}

    def test_default_output_config(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        assert result.output.verbosity == "normal"
        assert result.output.locale == "en"
        assert result.output.audit.enabled is True
        assert result.output.audit.retention == 30
        assert result.output.pr_report.enabled is False

    def test_default_behavior_empty(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        # read should be empty; execute.forbidden holds system rules only
        assert result.behavior.read.forbidden == []
        user_execute = [
            r for r in result.behavior.execute.forbidden if r.source != "system"
        ]
        assert user_execute == []

    def test_build_command_none_by_default(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        assert result.build_command is None

    def test_no_rulesets(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        # Should work fine with no rulesets
        assert result.version == 1
        assert result.rulesets == []

    def test_rulesets_passthrough(self, tmp_path: Path) -> None:
        """Rulesets from guard.yaml are passed through to ResolvedConfig."""
        data = _minimal_guard(rulesets=["security-rules", "team-conventions"])
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.rulesets == ["security-rules", "team-conventions"]


# ---------------------------------------------------------------------------
# TestScalarOverride
# ---------------------------------------------------------------------------


class TestScalarOverride:
    """User guard.yaml overrides built-in default scalars."""

    def test_override_verbosity(self, tmp_path: Path) -> None:
        data = _minimal_guard(output={"verbosity": "verbose"})
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.output.verbosity == "verbose"

    def test_override_locale(self, tmp_path: Path) -> None:
        data = _minimal_guard(output={"locale": "zh-CN"})
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.output.locale == "zh-CN"

    def test_override_commit_format(self, tmp_path: Path) -> None:
        data = _minimal_guard(code={"pre-commit": {"format": False}})
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.code.pre_commit.format is False

    def test_override_push_lint(self, tmp_path: Path) -> None:
        data = _minimal_guard(code={"pre-push": {"lint": False}})
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.code.pre_push.lint is False

    def test_build_command(self, tmp_path: Path) -> None:
        data = _minimal_guard(build={"command": "make build"})
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.build_command == "make build"

    def test_audit_retention_override(self, tmp_path: Path) -> None:
        data = _minimal_guard(output={"audit": {"retention": 90}})
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.output.audit.retention == 90
        # Other audit fields should keep defaults
        assert result.output.audit.enabled is True
        assert result.output.audit.path == ".ac-guard/audit.jsonl"


# ---------------------------------------------------------------------------
# TestRuleListAppend
# ---------------------------------------------------------------------------


class TestRuleListAppend:
    """Rules from multiple sources are appended, not replaced."""

    def test_user_rules_appended(self, tmp_path: Path) -> None:
        data = _minimal_guard(
            behavior={
                "read": {
                    "forbidden": [
                        {"pattern": "file:**/secret.*", "reason": "no secrets"}
                    ],
                },
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        patterns = [r.pattern for r in result.behavior.read.forbidden]
        assert "file:**/secret.*" in patterns

    def test_ruleset_then_user_rules_ordered(self, tmp_path: Path) -> None:
        ruleset_raw: dict = {
            "behavior": {
                "read": {
                    "forbidden": [{"pattern": "file:*.key"}],
                },
            },
        }
        data = _minimal_guard(
            behavior={
                "read": {
                    "forbidden": [{"pattern": "file:*.pem"}],
                },
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("company", ruleset_raw)])
        patterns = [r.pattern for r in result.behavior.read.forbidden]
        # Ruleset rule comes before user rule
        assert patterns.index("file:*.key") < patterns.index("file:*.pem")

    def test_multiple_rulesets_append_in_order(self, tmp_path: Path) -> None:
        rs1: dict = {
            "behavior": {"execute": {"forbidden": [{"pattern": "shell:rm -rf *"}]}},
        }
        rs2: dict = {
            "behavior": {
                "execute": {"forbidden": [{"pattern": "shell:drop database"}]}
            },
        }
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path, rulesets=[("rs1", rs1), ("rs2", rs2)])
        patterns = [r.pattern for r in result.behavior.execute.forbidden]
        assert patterns.index("shell:rm -rf *") < patterns.index("shell:drop database")


# ---------------------------------------------------------------------------
# TestRuleSourceTracking
# ---------------------------------------------------------------------------


class TestRuleSourceTracking:
    """Each rule is tagged with its origin source."""

    def test_user_rule_source(self, tmp_path: Path) -> None:
        data = _minimal_guard(
            behavior={
                "read": {"forbidden": [{"pattern": "file:*.env"}]},
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        rule = next(
            r for r in result.behavior.read.forbidden if r.pattern == "file:*.env"
        )
        assert rule.source == "user"

    def test_ruleset_rule_source(self, tmp_path: Path) -> None:
        rs: dict = {
            "behavior": {"read": {"forbidden": [{"pattern": "file:*.key"}]}},
        }
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path, rulesets=[("company", rs)])
        rule = next(
            r for r in result.behavior.read.forbidden if r.pattern == "file:*.key"
        )
        assert rule.source == "ruleset:company"

    def test_system_rule_source(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        system_rules = [
            r for r in result.behavior.write.require_approval if r.source == "system"
        ]
        assert len(system_rules) == len(_SYSTEM_PROTECTION_PATTERNS)


# ---------------------------------------------------------------------------
# TestSystemProtectionRules
# ---------------------------------------------------------------------------


class TestSystemProtectionRules:
    """System protection rules are injected and immutable."""

    def test_system_rules_present(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        patterns = [r.pattern for r in result.behavior.write.require_approval]
        for expected in _SYSTEM_PROTECTION_PATTERNS:
            assert expected in patterns

    def test_system_rules_count(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        system_rules = [
            r for r in result.behavior.write.require_approval if r.source == "system"
        ]
        assert len(system_rules) == 4

    def test_system_rules_have_correct_source(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        for rule in result.behavior.write.require_approval:
            if rule.pattern in _SYSTEM_PROTECTION_PATTERNS:
                assert rule.source == "system"

    def test_user_rules_coexist_with_system_rules(self, tmp_path: Path) -> None:
        data = _minimal_guard(
            behavior={
                "write": {
                    "require_approval": [{"pattern": "file:deploy/**"}],
                },
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        patterns = [r.pattern for r in result.behavior.write.require_approval]
        assert "file:deploy/**" in patterns
        for expected in _SYSTEM_PROTECTION_PATTERNS:
            assert expected in patterns


# ---------------------------------------------------------------------------
# TestSystemExecuteRules
# ---------------------------------------------------------------------------


class TestSystemExecuteRules:
    """System execute.forbidden rules (anti-bypass) are injected."""

    def test_execute_forbidden_includes_no_verify_patterns(
        self, tmp_path: Path
    ) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        patterns = [r.pattern for r in result.behavior.execute.forbidden]
        for entry in _SYSTEM_EXECUTE_FORBIDDEN:
            assert entry["pattern"] in patterns

    def test_execute_forbidden_source_is_system(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        system_patterns = {e["pattern"] for e in _SYSTEM_EXECUTE_FORBIDDEN}
        for rule in result.behavior.execute.forbidden:
            if rule.pattern in system_patterns:
                assert rule.source == "system"

    def test_execute_forbidden_regex_flag_preserved(self, tmp_path: Path) -> None:
        """Regex entries retain ``regex=True`` after resolution."""
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        by_pattern = {r.pattern: r for r in result.behavior.execute.forbidden}
        for entry in _SYSTEM_EXECUTE_FORBIDDEN:
            rule = by_pattern[entry["pattern"]]
            assert rule.regex is entry.get("regex", False)

    def test_execute_forbidden_has_bypass_patterns(self, tmp_path: Path) -> None:
        """Regression for #104 — 4 bypass patterns on top of --no-verify."""
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        patterns = [r.pattern for r in result.behavior.execute.forbidden]
        assert any("SKIP=" in p for p in patterns)
        assert any("-c" in p and "hooks" in p for p in patterns)
        assert any("config" in p and "hookspath" in p.lower() for p in patterns)
        assert any("rebase" in p and "exec" in p for p in patterns)

    def test_execute_forbidden_has_ci_env_pattern(self, tmp_path: Path) -> None:
        """Regression: CI= env-var bypass is denied by default."""
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        patterns = [r.pattern for r in result.behavior.execute.forbidden]
        assert any("CI=" in p and "git" in p for p in patterns)

    def test_execute_forbidden_has_force_push_patterns(self, tmp_path: Path) -> None:
        """Regression: force push is blocked for all branches."""
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        patterns = [r.pattern for r in result.behavior.execute.forbidden]
        # --force / --force-with-lease
        assert any("git" in p and "push" in p and "--force" in p for p in patterns)
        # -f short form
        assert any("git" in p and "push" in p and "-f" in p for p in patterns)
        # `git push <remote> +<branch>` shorthand
        assert any("git" in p and "push" in p and "+" in p for p in patterns)

    def test_user_execute_rules_coexist_with_system_rules(self, tmp_path: Path) -> None:
        data = _minimal_guard(
            behavior={
                "execute": {
                    "forbidden": [{"pattern": "shell:rm -rf /*"}],
                },
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        patterns = [r.pattern for r in result.behavior.execute.forbidden]
        assert "shell:rm -rf /*" in patterns
        for entry in _SYSTEM_EXECUTE_FORBIDDEN:
            assert entry["pattern"] in patterns


# ---------------------------------------------------------------------------
# TestLanguagesAutoPopulate
# ---------------------------------------------------------------------------


class TestLanguagesAutoPopulate:
    """Empty languages gets auto-filled from project.language + defaults."""

    def test_empty_languages_filled_from_project_language(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())  # language=python, no languages
        result = resolve_config(path)
        assert "python" in result.languages
        assert result.languages["python"].format == "black"
        assert result.languages["python"].lint == "ruff"

    def test_explicit_languages_not_overridden(self, tmp_path: Path) -> None:
        data = _minimal_guard(
            languages={
                "python": {"tools": {"format": "ruff format", "lint": "ruff"}},
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.languages["python"].format == "ruff format"

    def test_unknown_project_language_rejected_by_schema(self, tmp_path: Path) -> None:
        """Unknown project.language fails schema validation early.

        Before the language enum was added to the schema, an unregistered
        language flowed through merger and just left ``languages`` empty.
        Now the schema rejects it before resolve_config can ever populate
        anything, so the user gets a clear typo-style error up front.
        """
        from ac_guard.config.exceptions import ConfigValidationError

        data = {"version": 1, "project": {"language": "brainfuck"}}
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ConfigValidationError) as exc_info:
            resolve_config(path)
        assert any(e.path == "project.language" for e in exc_info.value.errors)


# ---------------------------------------------------------------------------
# TestRemoveProcessing
# ---------------------------------------------------------------------------


class TestRemoveProcessing:
    """Remove entries remove matching rules; warnings for edge cases."""

    def test_remove_matching_rule(self, tmp_path: Path) -> None:
        rs: dict = {
            "behavior": {
                "read": {"forbidden": [{"pattern": "file:*.log"}]},
            },
        }
        data = _minimal_guard(
            behavior={
                "read": {"remove": [{"pattern": "file:*.log"}]},
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        patterns = [r.pattern for r in result.behavior.read.forbidden]
        assert "file:*.log" not in patterns

    def test_remove_nonexistent_warns(self, tmp_path: Path) -> None:
        data = _minimal_guard(
            behavior={
                "read": {"remove": [{"pattern": "file:nonexistent"}]},
            }
        )
        path = _write_yaml(tmp_path, data)
        with pytest.warns(ConfigWarning, match="not found"):
            resolve_config(path)

    def test_remove_system_rule_warns(self, tmp_path: Path) -> None:
        data = _minimal_guard(
            behavior={
                "write": {"remove": [{"pattern": "file:guard.yaml"}]},
            }
        )
        path = _write_yaml(tmp_path, data)
        with pytest.warns(ConfigWarning, match="system-protected"):
            result = resolve_config(path)
        # System rule should still be present
        patterns = [r.pattern for r in result.behavior.write.require_approval]
        assert "file:guard.yaml" in patterns

    def test_remove_from_require_approval_tier(self, tmp_path: Path) -> None:
        rs: dict = {
            "behavior": {
                "execute": {
                    "require_approval": [{"pattern": "shell:docker *"}],
                },
            },
        }
        data = _minimal_guard(
            behavior={
                "execute": {"remove": [{"pattern": "shell:docker *"}]},
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        patterns = [r.pattern for r in result.behavior.execute.require_approval]
        assert "shell:docker *" not in patterns

    def test_remove_from_allow_tier(self, tmp_path: Path) -> None:
        rs: dict = {
            "behavior": {
                "write": {"allow": [{"pattern": "file:tmp/**"}]},
            },
        }
        data = _minimal_guard(
            behavior={
                "write": {"remove": [{"pattern": "file:tmp/**"}]},
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        patterns = [r.pattern for r in result.behavior.write.allow]
        assert "file:tmp/**" not in patterns

    def test_multiple_removes(self, tmp_path: Path) -> None:
        rs: dict = {
            "behavior": {
                "read": {
                    "forbidden": [
                        {"pattern": "file:*.key"},
                        {"pattern": "file:*.pem"},
                        {"pattern": "file:*.env"},
                    ],
                },
            },
        }
        data = _minimal_guard(
            behavior={
                "read": {
                    "remove": [
                        {"pattern": "file:*.key"},
                        {"pattern": "file:*.pem"},
                    ],
                },
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        patterns = [r.pattern for r in result.behavior.read.forbidden]
        assert "file:*.key" not in patterns
        assert "file:*.pem" not in patterns
        assert "file:*.env" in patterns


# ---------------------------------------------------------------------------
# TestDeepMergeChecks
# ---------------------------------------------------------------------------


class TestDeepMergeChecks:
    """checks dicts are deep-merged at the field level."""

    def test_override_check_field(self, tmp_path: Path) -> None:
        rs: dict = {
            "code": {
                "pre-commit": {
                    "checks": {
                        "mytest": {"command": "pytest", "timeout": 300},
                    },
                },
            },
        }
        data = _minimal_guard(
            code={
                "pre-commit": {
                    "checks": {
                        "mytest": {"command": "pytest -x", "timeout": 600},
                    },
                },
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        check = result.code.pre_commit.checks["mytest"]
        assert check.command == "pytest -x"
        assert check.timeout == 600

    def test_add_new_check(self, tmp_path: Path) -> None:
        rs: dict = {
            "code": {
                "pre-push": {
                    "checks": {
                        "lint": {"command": "ruff check ."},
                    },
                },
            },
        }
        data = _minimal_guard(
            code={
                "pre-push": {
                    "checks": {
                        "typecheck": {"command": "mypy src/"},
                    },
                },
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        assert "lint" in result.code.pre_push.checks
        assert "typecheck" in result.code.pre_push.checks

    def test_preserve_unmentioned_check(self, tmp_path: Path) -> None:
        rs: dict = {
            "code": {
                "pre-commit": {
                    "checks": {
                        "existing": {"command": "echo ok"},
                    },
                },
            },
        }
        data = _minimal_guard(
            code={
                "pre-commit": {
                    "checks": {
                        "new": {"command": "echo new"},
                    },
                },
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        assert "existing" in result.code.pre_commit.checks
        assert "new" in result.code.pre_commit.checks

    def test_partial_field_override(self, tmp_path: Path) -> None:
        """Overlay changes only timeout; command preserved from base."""
        rs: dict = {
            "code": {
                "pre-commit": {
                    "checks": {
                        "test": {"command": "pytest", "timeout": 300},
                    },
                },
            },
        }
        rs2: dict = {
            "code": {
                "pre-commit": {
                    "checks": {
                        "test": {"command": "pytest", "timeout": 600},
                    },
                },
            },
        }
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path, rulesets=[("rs1", rs), ("rs2", rs2)])
        check = result.code.pre_commit.checks["test"]
        assert check.command == "pytest"
        assert check.timeout == 600


# ---------------------------------------------------------------------------
# TestLanguageMerge
# ---------------------------------------------------------------------------


class TestLanguageMerge:
    """Language tool mappings are deep-merged."""

    def test_add_new_language(self, tmp_path: Path) -> None:
        data = _minimal_guard(
            languages={
                "python": {"tools": {"format": "black", "lint": "ruff"}},
                "go": {"tools": {"format": "gofmt", "lint": "golangci-lint"}},
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert "python" in result.languages
        assert "go" in result.languages

    def test_override_existing_tool(self, tmp_path: Path) -> None:
        rs: dict = {
            "languages": {
                "python": {"tools": {"format": "black", "lint": "ruff"}},
            },
        }
        # User guard.yaml must have both format+lint (validator requirement),
        # but the merge should still override per-field from rulesets.
        data = _minimal_guard(
            languages={
                "python": {"tools": {"format": "ruff format", "lint": "ruff"}},
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        assert result.languages["python"].format == "ruff format"
        assert result.languages["python"].lint == "ruff"

    def test_ruleset_override_between_rulesets(self, tmp_path: Path) -> None:
        """Rulesets (not validated) can do partial tool override."""
        rs1: dict = {
            "languages": {
                "python": {"tools": {"format": "black", "lint": "ruff"}},
            },
        }
        rs2: dict = {
            "languages": {
                "python": {"tools": {"format": "ruff format"}},
            },
        }
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path, rulesets=[("rs1", rs1), ("rs2", rs2)])
        assert result.languages["python"].format == "ruff format"
        # lint preserved from rs1
        assert result.languages["python"].lint == "ruff"

    def test_preserve_base_language(self, tmp_path: Path) -> None:
        rs: dict = {
            "languages": {
                "python": {"tools": {"format": "black", "lint": "ruff"}},
                "go": {"tools": {"format": "gofmt", "lint": "golangci-lint"}},
            },
        }
        data = _minimal_guard(
            languages={
                "python": {"tools": {"format": "ruff format", "lint": "ruff"}},
            }
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        assert "go" in result.languages
        assert result.languages["go"].format == "gofmt"


# ---------------------------------------------------------------------------
# TestOutputMerge
# ---------------------------------------------------------------------------


class TestOutputMerge:
    """Output config nested dicts are field-level merged."""

    def test_audit_partial_override(self, tmp_path: Path) -> None:
        data = _minimal_guard(output={"audit": {"retention": 90}})
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.output.audit.retention == 90
        assert result.output.audit.enabled is True  # default preserved

    def test_pr_report_partial_override(self, tmp_path: Path) -> None:
        data = _minimal_guard(
            output={"pr_report": {"enabled": True, "platform": "gitlab"}}
        )
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.output.pr_report.enabled is True
        assert result.output.pr_report.platform == "gitlab"
        assert result.output.pr_report.token_env == "GITHUB_TOKEN"  # default

    def test_scalar_override(self, tmp_path: Path) -> None:
        data = _minimal_guard(output={"verbosity": "quiet", "locale": "zh-CN"})
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path)
        assert result.output.verbosity == "quiet"
        assert result.output.locale == "zh-CN"

    def test_ruleset_output_then_user_override(self, tmp_path: Path) -> None:
        rs: dict = {
            "output": {"verbosity": "verbose", "audit": {"retention": 60}},
        }
        data = _minimal_guard(output={"audit": {"retention": 90}})
        path = _write_yaml(tmp_path, data)
        result = resolve_config(path, rulesets=[("rs", rs)])
        # User overrides ruleset
        assert result.output.audit.retention == 90
        # Ruleset overrides default
        assert result.output.verbosity == "verbose"


# ---------------------------------------------------------------------------
# TestConfigHash
# ---------------------------------------------------------------------------


class TestConfigHash:
    """config_hash is a deterministic 8-char hex fingerprint."""

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        data = _minimal_guard()
        sub1 = tmp_path / "a"
        sub2 = tmp_path / "b"
        sub1.mkdir()
        sub2.mkdir()
        p1 = _write_yaml(sub1, data)
        p2 = _write_yaml(sub2, data)
        r1 = resolve_config(p1)
        r2 = resolve_config(p2)
        assert r1.config_hash == r2.config_hash

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        d1 = _minimal_guard()
        d2 = _minimal_guard(output={"verbosity": "verbose"})
        sub1 = tmp_path / "a"
        sub2 = tmp_path / "b"
        sub1.mkdir()
        sub2.mkdir()
        p1 = _write_yaml(sub1, d1)
        p2 = _write_yaml(sub2, d2)
        r1 = resolve_config(p1)
        r2 = resolve_config(p2)
        assert r1.config_hash != r2.config_hash

    def test_hash_is_hex_string(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        assert len(result.config_hash) == 8
        int(result.config_hash, 16)  # Should not raise


# ---------------------------------------------------------------------------
# TestErrorPropagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    """Errors from loader are propagated through resolve_config."""

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileNotFoundError):
            resolve_config(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "guard.yaml"
        p.write_text(":\n  :\n    - [invalid", encoding="utf-8")
        with pytest.raises(ConfigSyntaxError):
            resolve_config(p)


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_rulesets_list(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path, rulesets=[])
        assert result.version == 1

    def test_none_rulesets(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path, rulesets=None)
        assert result.version == 1

    def test_guard_yaml_with_only_project(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        assert result.behavior.read.forbidden == []
        assert result.code.pre_commit.format is True

    def test_no_mutation_of_input(self, tmp_path: Path) -> None:
        """resolve_config must not mutate the ruleset RawConfig dicts."""
        rs: dict = {
            "behavior": {
                "read": {"forbidden": [{"pattern": "file:*.key"}]},
            },
        }
        import copy

        original = copy.deepcopy(rs)
        path = _write_yaml(tmp_path, _minimal_guard())
        resolve_config(path, rulesets=[("rs", rs)])
        # The _source key should not leak into the original
        assert "_source" not in rs["behavior"]["read"]["forbidden"][0]
        assert rs == original

    def test_languages_auto_populated_from_project_language(
        self, tmp_path: Path
    ) -> None:
        # _minimal_guard sets project.language = python and no languages
        # block. The merger should auto-populate from defaults/languages.yaml.
        path = _write_yaml(tmp_path, _minimal_guard())
        result = resolve_config(path)
        assert "python" in result.languages

    def test_languages_empty_when_project_language_unknown(
        self, tmp_path: Path
    ) -> None:
        """Unregistered project.language is now a schema error.

        Was: the merger left ``languages`` empty when given an unknown
        language. Now: schema rejects it up front so the user gets a
        clear typo-style error rather than silently broken format/lint.
        """
        from ac_guard.config.exceptions import ConfigValidationError

        data = {"version": 1, "project": {"language": "brainfuck"}}
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ConfigValidationError):
            resolve_config(path)
