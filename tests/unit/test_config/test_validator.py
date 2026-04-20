"""Tests for config schema validator."""

from __future__ import annotations

import pytest

from ac_guard.config.exceptions import ConfigValidationError, ValidationIssue
from ac_guard.config.validator import validate_raw_config


def _minimal_config(**overrides: object) -> dict:
    """Build a minimal valid config dict for testing."""
    base: dict = {"version": 1, "project": {"language": "python"}}
    base.update(overrides)
    return base


# --- Structural validation ---


class TestValidMinimalConfig:
    def test_minimal_config_passes(self) -> None:
        validate_raw_config({"version": 1, "project": {"language": "python"}})

    def test_full_config_passes(self) -> None:
        data = {
            "version": 1,
            "project": {"name": "my-project", "language": "python"},
            "rulesets": [
                "git@github.com:company/base-rules.git",
            ],
            "languages": {
                "python": {"tools": {"format": "black", "lint": "ruff"}},
            },
            "behavior": {
                "read": {
                    "forbidden": [
                        {"pattern": "file:**/token.*", "reason": "tokens"},
                    ],
                },
                "write": {
                    "require_approval": [
                        {
                            "pattern": "file:.github/workflows/**",
                            "message": "CI config",
                        },
                    ],
                    "allow": [{"pattern": "file:scripts/**"}],
                    "remove": [{"pattern": "file:build/**"}],
                },
                "execute": {
                    "forbidden": [
                        {
                            "pattern": "shell:git commit\\s+--no-verify",
                            "reason": "no skip hooks",
                            "regex": True,
                        },
                    ],
                },
            },
            "code": {
                "pre-commit": {
                    "format": True,
                    "checks": {
                        "license_header": {
                            "command": "./scripts/check-license.sh",
                            "types": ["python"],
                        },
                    },
                },
                "pre-push": {
                    "lint": True,
                    "checks": {
                        "test": {"command": "pytest", "timeout": 300},
                        "coverage": {
                            "command": "pytest --cov --cov-fail-under=80",
                        },
                        "asan": {
                            "command": "./build.sh test --asan",
                            "enabled": False,
                        },
                    },
                },
            },
            "build": {"command": "make build"},
            "output": {
                "verbosity": "normal",
                "locale": "zh-CN",
                "audit": {
                    "enabled": True,
                    "path": ".ac-guard/audit.jsonl",
                    "retention": 30,
                },
                "pr_report": {
                    "enabled": False,
                    "platform": "github",
                    "api_url": "https://github.company.com/api/v3",
                    "token_env": "GITHUB_TOKEN",
                },
            },
        }
        validate_raw_config(data)


class TestTopLevelStructure:
    def test_unknown_top_level_key(self) -> None:
        data = _minimal_config(foo=1)
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("foo" in e.path for e in exc_info.value.errors)

    def test_empty_dict_reports_missing_required(self) -> None:
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config({})
        paths = [e.path for e in exc_info.value.errors]
        assert "version" in paths
        assert "project" in paths


class TestVersionField:
    def test_version_wrong_type(self) -> None:
        data = {"version": "1", "project": {"language": "python"}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("version" in e.path for e in exc_info.value.errors)

    def test_version_unsupported(self) -> None:
        data = {"version": 99, "project": {"language": "python"}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("version" in e.path for e in exc_info.value.errors)


class TestProjectField:
    def test_missing_project_language(self) -> None:
        data = {"version": 1, "project": {"name": "x"}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("project.language" in e.path for e in exc_info.value.errors)

    def test_project_not_dict(self) -> None:
        data = {"version": 1, "project": "python"}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("project" in e.path for e in exc_info.value.errors)

    def test_project_language_empty_string(self) -> None:
        data = {"version": 1, "project": {"language": ""}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("project.language" in e.path for e in exc_info.value.errors)

    def test_project_unknown_field(self) -> None:
        data = _minimal_config()
        data["project"]["extra"] = True
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("project.extra" in e.path for e in exc_info.value.errors)


class TestRulesetsField:
    def test_rulesets_not_list(self) -> None:
        data = _minimal_config(rulesets="single")
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("rulesets" in e.path for e in exc_info.value.errors)

    def test_rulesets_item_not_string(self) -> None:
        data = _minimal_config(rulesets=[123])
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("rulesets[0]" in e.path for e in exc_info.value.errors)


class TestBehaviorField:
    def test_unknown_behavior_operation(self) -> None:
        data = _minimal_config(behavior={"delete": {}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("behavior.delete" in e.path for e in exc_info.value.errors)

    def test_unknown_rule_tier(self) -> None:
        data = _minimal_config(behavior={"read": {"deny": []}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("behavior.read.deny" in e.path for e in exc_info.value.errors)

    def test_rule_missing_pattern(self) -> None:
        data = _minimal_config(behavior={"read": {"forbidden": [{"reason": "x"}]}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("pattern" in e.path for e in exc_info.value.errors)

    def test_unknown_rule_field(self) -> None:
        data = _minimal_config(
            behavior={
                "read": {
                    "forbidden": [
                        {"pattern": "file:*.py", "priority": 1},
                    ],
                },
            }
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("priority" in e.path for e in exc_info.value.errors)

    def test_rule_source_in_yaml_is_unknown(self) -> None:
        """source is runtime-assigned, not allowed in YAML."""
        data = _minimal_config(
            behavior={
                "read": {
                    "forbidden": [
                        {"pattern": "file:*.py", "source": "default"},
                    ],
                },
            }
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("source" in e.path for e in exc_info.value.errors)

    def test_rule_tier_not_list(self) -> None:
        data = _minimal_config(behavior={"read": {"forbidden": "not-a-list"}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("behavior.read.forbidden" in e.path for e in exc_info.value.errors)

    def test_rule_not_dict(self) -> None:
        data = _minimal_config(behavior={"read": {"forbidden": ["not-a-dict"]}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any(
            "behavior.read.forbidden[0]" in e.path for e in exc_info.value.errors
        )

    def test_behavior_not_dict(self) -> None:
        data = _minimal_config(behavior="bad")
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("behavior" in e.path for e in exc_info.value.errors)


class TestCodeField:
    def test_check_missing_command(self) -> None:
        data = _minimal_config(
            code={"pre-commit": {"checks": {"my_check": {"timeout": 30}}}}
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("command" in e.path for e in exc_info.value.errors)

    def test_timeout_negative(self) -> None:
        data = _minimal_config(
            code={
                "pre-commit": {
                    "checks": {
                        "my_check": {"command": "echo", "timeout": -1},
                    },
                },
            }
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("timeout" in e.path for e in exc_info.value.errors)

    def test_timeout_zero(self) -> None:
        data = _minimal_config(
            code={
                "pre-commit": {
                    "checks": {
                        "my_check": {"command": "echo", "timeout": 0},
                    },
                },
            }
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("timeout" in e.path for e in exc_info.value.errors)

    def test_code_not_dict(self) -> None:
        data = _minimal_config(code="bad")
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("code" in e.path for e in exc_info.value.errors)

    def test_unknown_code_stage(self) -> None:
        data = _minimal_config(code={"deploy": {}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("code.deploy" in e.path for e in exc_info.value.errors)


class TestLanguagesField:
    def test_languages_not_dict(self) -> None:
        data = _minimal_config(languages="python")
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("languages" in e.path for e in exc_info.value.errors)

    def test_language_entry_not_dict(self) -> None:
        data = _minimal_config(languages={"python": "bad"})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("languages.python" in e.path for e in exc_info.value.errors)

    def test_language_missing_tools(self) -> None:
        data = _minimal_config(languages={"python": {}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("languages.python.tools" in e.path for e in exc_info.value.errors)

    def test_language_tools_missing_format(self) -> None:
        data = _minimal_config(languages={"python": {"tools": {"lint": "ruff"}}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("format" in e.path for e in exc_info.value.errors)

    def test_language_tools_missing_lint(self) -> None:
        data = _minimal_config(languages={"python": {"tools": {"format": "black"}}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("lint" in e.path for e in exc_info.value.errors)


class TestBuildField:
    def test_build_not_dict(self) -> None:
        data = _minimal_config(build="make")
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("build" in e.path for e in exc_info.value.errors)

    def test_build_command_not_string(self) -> None:
        data = _minimal_config(build={"command": 123})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("build.command" in e.path for e in exc_info.value.errors)


class TestOutputField:
    def test_output_not_dict(self) -> None:
        data = _minimal_config(output="verbose")
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("output" in e.path for e in exc_info.value.errors)


# --- Semantic validation ---


class TestRegexValidation:
    def test_invalid_regex_pattern(self) -> None:
        data = _minimal_config(
            behavior={
                "execute": {
                    "forbidden": [
                        {"pattern": "[unclosed", "regex": True},
                    ],
                },
            }
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("regex" in e.message.lower() for e in exc_info.value.errors)

    def test_valid_regex_passes(self) -> None:
        data = _minimal_config(
            behavior={
                "execute": {
                    "forbidden": [
                        {
                            "pattern": "shell:git\\s+push",
                            "reason": "no push",
                            "regex": True,
                        },
                    ],
                },
            }
        )
        validate_raw_config(data)


class TestEnumValidation:
    def test_verbosity_invalid(self) -> None:
        data = _minimal_config(output={"verbosity": "debug"})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("verbosity" in e.path for e in exc_info.value.errors)

    def test_verbosity_all_valid_values(self) -> None:
        for val in ("quiet", "normal", "verbose"):
            validate_raw_config(_minimal_config(output={"verbosity": val}))

    def test_locale_invalid(self) -> None:
        data = _minimal_config(output={"locale": "fr"})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("locale" in e.path for e in exc_info.value.errors)

    def test_locale_all_valid_values(self) -> None:
        for val in ("en", "zh-CN"):
            validate_raw_config(_minimal_config(output={"locale": val}))

    def test_platform_invalid(self) -> None:
        data = _minimal_config(output={"pr_report": {"platform": "azure"}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("platform" in e.path for e in exc_info.value.errors)

    def test_platform_all_valid_values(self) -> None:
        for val in ("github", "gitlab", "gitea", "bitbucket"):
            validate_raw_config(
                _minimal_config(output={"pr_report": {"platform": val}})
            )


class TestRetentionValidation:
    def test_retention_negative(self) -> None:
        data = _minimal_config(output={"audit": {"retention": -5}})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert any("retention" in e.path for e in exc_info.value.errors)

    def test_retention_zero_is_valid(self) -> None:
        """0 means permanent retention."""
        validate_raw_config(_minimal_config(output={"audit": {"retention": 0}}))


# --- Error collection ---


class TestErrorCollection:
    def test_multiple_errors_collected(self) -> None:
        """Three distinct errors should all appear in one exception."""
        data = {
            "version": "wrong",  # type error
            "project": {"name": "x"},  # missing language
            "foo": 1,  # unknown key
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        assert len(exc_info.value.errors) >= 3

    def test_validation_issue_structure(self) -> None:
        issue = ValidationIssue(
            path="behavior.read.forbidden[0].pattern",
            message="required field missing",
            value=None,
        )
        assert issue.path == "behavior.read.forbidden[0].pattern"
        assert issue.message == "required field missing"
        assert issue.value is None

    def test_error_message_contains_all_paths(self) -> None:
        data = {"version": "wrong", "project": {"name": "x"}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_raw_config(data)
        msg = str(exc_info.value)
        assert "version" in msg
        assert "project.language" in msg
