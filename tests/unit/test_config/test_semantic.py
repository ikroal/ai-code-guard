"""Tests for ac_guard.config.semantic — zero-IO semantic rules.

Four named rules cover the cross-field semantics that L1 schema can't
express. Tests group them by rule (one ``Test*Rule`` class per code)
and dispatch through the single ``validate_semantic(payload, rules)``
driver. Each issue carries a ``rule_code`` so tests can assert which
rule fired without coupling to error wording.

Two of the rules judge yaml content (``_FORMAT_LINT_SCOPE`` /
``_COMMAND_SYNTAX``) and run from ``loader.py``; the other two judge
the merged tree (``_TIER_CONSISTENCY`` / ``_PATTERN_UNIQUENESS``) and
run from ``merger.py``. The split is caller-side strategy, not a
property of the rules themselves.
"""

from __future__ import annotations

import pytest

from ac_guard.config.exceptions import ConfigValidationError, ValidationIssue
from ac_guard.config.models import (
    BehaviorConfig,
    CodeConfig,
    OperationRules,
    OutputConfig,
    ResolvedConfig,
    Rule,
)
from ac_guard.config.semantic import (
    _COMMAND_SYNTAX,
    _FORMAT_LINT_SCOPE,
    _PATTERN_UNIQUENESS,
    _TIER_CONSISTENCY,
    validate_semantic,
)

# Rule groupings used by the package-internal callers (loader / merger).
# Tests reuse them so behavior matches what loader / merger actually run.
_YAML_RULES = (_FORMAT_LINT_SCOPE, _COMMAND_SYNTAX)
_TREE_RULES = (_TIER_CONSISTENCY, _PATTERN_UNIQUENESS)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolved(behavior: BehaviorConfig | None = None) -> ResolvedConfig:
    """Minimal ResolvedConfig with optional custom behavior block."""
    return ResolvedConfig(
        version=1,
        project_name="x",
        project_language="python",
        behavior=behavior or BehaviorConfig.empty(),
        code=CodeConfig(),
        languages={},
        output=OutputConfig(),
    )


# ---------------------------------------------------------------------------
# Yaml-content rules: dispatched via validate_semantic(_YAML_RULES)
# ---------------------------------------------------------------------------


class TestFormatLintStageScopeRule:
    """``format`` / ``lint`` toggles only apply on file-scoped stages.

    Schema-level key validation already restricts ``code.<stage>`` to
    ``KNOWN_STAGES``, so this rule is purely about the toggle/stage
    semantic mismatch (``format: true`` on ``commit-msg`` would silently
    no-op because pre-commit's ``types:`` filter never matches commit
    message files).
    """

    def test_format_on_commit_msg_rejected(self) -> None:
        raw = {"code": {"commit-msg": {"format": True}}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(raw, _YAML_RULES)
        issues = [
            e for e in exc_info.value.errors if e.rule_code == "format-lint-stage-scope"
        ]
        assert len(issues) == 1
        assert issues[0].path == "code.commit-msg.format"

    def test_lint_on_pre_rebase_rejected(self) -> None:
        raw = {"code": {"pre-rebase": {"lint": True}}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(raw, _YAML_RULES)
        issues = [
            e for e in exc_info.value.errors if e.rule_code == "format-lint-stage-scope"
        ]
        assert len(issues) == 1
        assert issues[0].path == "code.pre-rebase.lint"

    def test_format_on_pre_commit_passes(self) -> None:
        raw = {"code": {"pre-commit": {"format": True}}}
        validate_semantic(raw, _YAML_RULES)  # no raise

    def test_format_on_pre_push_passes(self) -> None:
        raw = {"code": {"pre-push": {"format": True}}}
        validate_semantic(raw, _YAML_RULES)  # no raise

    def test_format_false_on_commit_msg_passes(self) -> None:
        """Rule fires only on True; explicit False is benign."""
        raw = {"code": {"commit-msg": {"format": False, "lint": False}}}
        validate_semantic(raw, _YAML_RULES)  # no raise

    def test_both_format_and_lint_misplaced_each_reported(self) -> None:
        """Both toggles produce separate issues so the user sees both."""
        raw = {"code": {"commit-msg": {"format": True, "lint": True}}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(raw, _YAML_RULES)
        paths = sorted(e.path for e in exc_info.value.errors)
        assert paths == ["code.commit-msg.format", "code.commit-msg.lint"]

    def test_non_dict_bucket_skipped(self) -> None:
        """Schema (L1) catches non-dict buckets; L2 defends against
        being run independently with a malformed input."""
        raw = {"code": {"pre-commit": "not-a-dict"}}
        validate_semantic(raw, _YAML_RULES)  # no raise


class TestCommandSyntaxRule:
    """User-supplied command strings must be shlex-parseable."""

    def test_tool_format_unbalanced_quote_rejected(self) -> None:
        raw = {
            "languages": {
                "python": {"tools": {"format": "ruff 'unclosed", "lint": "ruff check"}}
            }
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(raw, _YAML_RULES)
        issues = [e for e in exc_info.value.errors if e.rule_code == "command-syntax"]
        assert len(issues) == 1
        assert issues[0].path == "languages.python.tools.format"

    def test_tool_lint_unbalanced_quote_rejected(self) -> None:
        raw = {
            "languages": {"python": {"tools": {"format": "black", "lint": 'ruff "x'}}}
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(raw, _YAML_RULES)
        issues = [e for e in exc_info.value.errors if e.rule_code == "command-syntax"]
        assert len(issues) == 1
        assert issues[0].path == "languages.python.tools.lint"

    def test_check_command_unbalanced_quote_rejected(self) -> None:
        raw = {
            "code": {
                "pre-commit": {"checks": {"my-check": {"command": "echo 'broken"}}}
            }
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(raw, _YAML_RULES)
        issues = [e for e in exc_info.value.errors if e.rule_code == "command-syntax"]
        assert len(issues) == 1
        assert issues[0].path == "code.pre-commit.checks.my-check.command"

    def test_well_formed_commands_pass(self) -> None:
        raw = {
            "languages": {
                "python": {"tools": {"format": "black .", "lint": "ruff check"}},
            },
            "code": {
                "pre-commit": {
                    "checks": {
                        "lint-extra": {"command": "echo 'all good'"},
                    },
                },
            },
        }
        validate_semantic(raw, _YAML_RULES)  # no raise

    def test_empty_command_skipped(self) -> None:
        """Empty strings are an L1 concern (non_empty); L2 must not double-report."""
        raw = {"languages": {"python": {"tools": {"format": "", "lint": ""}}}}
        validate_semantic(raw, _YAML_RULES)  # no raise


# ---------------------------------------------------------------------------
# Merged-tree rules: dispatched via validate_semantic(_TREE_RULES)
# ---------------------------------------------------------------------------


class TestTierConsistencyRule:
    """Same pattern must not appear in both forbidden and allow under one op."""

    def test_same_pattern_in_forbidden_and_allow_rejected(self) -> None:
        rules = OperationRules(
            forbidden=[Rule(pattern="file:secrets/**")],
            require_approval=[],
            allow=[Rule(pattern="file:secrets/**")],
        )
        cfg = _resolved(
            BehaviorConfig(
                read=rules, write=OperationRules.empty(), execute=OperationRules.empty()
            )
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(cfg, _TREE_RULES)
        issues = [e for e in exc_info.value.errors if e.rule_code == "tier-consistency"]
        assert len(issues) == 1
        assert "behavior.read" in issues[0].path

    def test_separate_patterns_in_each_tier_pass(self) -> None:
        rules = OperationRules(
            forbidden=[Rule(pattern="file:a")],
            require_approval=[],
            allow=[Rule(pattern="file:b")],
        )
        cfg = _resolved(
            BehaviorConfig(
                read=rules, write=OperationRules.empty(), execute=OperationRules.empty()
            )
        )
        validate_semantic(cfg, _TREE_RULES)  # no raise

    def test_same_pattern_in_different_ops_does_not_conflict(self) -> None:
        """forbidden:X under read does not conflict with allow:X under write."""
        cfg = _resolved(
            BehaviorConfig(
                read=OperationRules(
                    forbidden=[Rule(pattern="file:x")],
                    require_approval=[],
                    allow=[],
                ),
                write=OperationRules(
                    forbidden=[],
                    require_approval=[],
                    allow=[Rule(pattern="file:x")],
                ),
                execute=OperationRules.empty(),
            )
        )
        validate_semantic(cfg, _TREE_RULES)  # no raise

    def test_each_op_checked_independently(self) -> None:
        """All three operations (read/write/execute) get their own check."""
        conflict = OperationRules(
            forbidden=[Rule(pattern="x")],
            require_approval=[],
            allow=[Rule(pattern="x")],
        )
        cfg = _resolved(BehaviorConfig(read=conflict, write=conflict, execute=conflict))
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(cfg, _TREE_RULES)
        paths = {
            e.path for e in exc_info.value.errors if e.rule_code == "tier-consistency"
        }
        assert paths == {"behavior.read", "behavior.write", "behavior.execute"}


class TestPatternUniquenessRule:
    """No pattern should appear twice in the same tier list."""

    def test_duplicate_in_forbidden_rejected(self) -> None:
        cfg = _resolved(
            BehaviorConfig(
                read=OperationRules(
                    forbidden=[
                        Rule(pattern="file:a"),
                        Rule(pattern="file:a"),
                    ],
                    require_approval=[],
                    allow=[],
                ),
                write=OperationRules.empty(),
                execute=OperationRules.empty(),
            )
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(cfg, _TREE_RULES)
        issues = [
            e for e in exc_info.value.errors if e.rule_code == "pattern-uniqueness"
        ]
        assert len(issues) == 1
        assert "behavior.read.forbidden" in issues[0].path

    def test_system_injected_duplicates_skipped(self) -> None:
        """System-injected protection rules may legitimately overlap user patterns."""
        cfg = _resolved(
            BehaviorConfig(
                read=OperationRules(
                    forbidden=[
                        Rule(pattern="file:a", source="user"),
                        Rule(pattern="file:a", source="system"),
                    ],
                    require_approval=[],
                    allow=[],
                ),
                write=OperationRules.empty(),
                execute=OperationRules.empty(),
            )
        )
        validate_semantic(cfg, _TREE_RULES)  # no raise

    def test_two_user_duplicates_rejected_even_with_system_third(self) -> None:
        """System rule does not save user duplicates from being reported."""
        cfg = _resolved(
            BehaviorConfig(
                read=OperationRules(
                    forbidden=[
                        Rule(pattern="file:a", source="user"),
                        Rule(pattern="file:a", source="user"),
                        Rule(pattern="file:a", source="system"),
                    ],
                    require_approval=[],
                    allow=[],
                ),
                write=OperationRules.empty(),
                execute=OperationRules.empty(),
            )
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(cfg, _TREE_RULES)
        issues = [
            e for e in exc_info.value.errors if e.rule_code == "pattern-uniqueness"
        ]
        assert len(issues) == 1

    def test_clean_tiers_pass(self) -> None:
        cfg = _resolved(
            BehaviorConfig(
                read=OperationRules(
                    forbidden=[
                        Rule(pattern="file:a"),
                        Rule(pattern="file:b"),
                    ],
                    require_approval=[Rule(pattern="file:c")],
                    allow=[Rule(pattern="file:d")],
                ),
                write=OperationRules.empty(),
                execute=OperationRules.empty(),
            )
        )
        validate_semantic(cfg, _TREE_RULES)  # no raise

    def test_duplicates_in_each_tier_reported(self) -> None:
        cfg = _resolved(
            BehaviorConfig(
                read=OperationRules(
                    forbidden=[Rule(pattern="x"), Rule(pattern="x")],
                    require_approval=[Rule(pattern="y"), Rule(pattern="y")],
                    allow=[Rule(pattern="z"), Rule(pattern="z")],
                ),
                write=OperationRules.empty(),
                execute=OperationRules.empty(),
            )
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(cfg, _TREE_RULES)
        paths = {
            e.path for e in exc_info.value.errors if e.rule_code == "pattern-uniqueness"
        }
        assert paths == {
            "behavior.read.forbidden",
            "behavior.read.require_approval",
            "behavior.read.allow",
        }


# ---------------------------------------------------------------------------
# Driver behavior: rule_code injection, multi-rule aggregation
# ---------------------------------------------------------------------------


class TestDriverInjection:
    """The driver post-injects rule_code on every issue from a rule."""

    def test_rule_code_set_on_all_issues_from_rule(self) -> None:
        raw = {"code": {"commit-msg": {"format": True, "lint": True}}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(raw, _YAML_RULES)
        # Both issues from format-lint-stage-scope must carry the same rule_code.
        for issue in exc_info.value.errors:
            assert issue.rule_code == "format-lint-stage-scope"

    def test_multiple_rules_run_and_aggregate(self) -> None:
        """A single bad config can fire multiple rules; all issues surface together."""
        raw = {
            "code": {
                "commit-msg": {"format": True},  # → format-lint-stage-scope
            },
            "languages": {
                "python": {
                    "tools": {"format": "ruff 'broken", "lint": "x"}
                },  # → command-syntax
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(raw, _YAML_RULES)
        codes = {e.rule_code for e in exc_info.value.errors}
        assert codes == {"format-lint-stage-scope", "command-syntax"}


class TestEmptyConfigsPass:
    """Empty / minimal configs should not trigger any rule."""

    def test_static_passes_on_empty(self) -> None:
        validate_semantic({}, _YAML_RULES)

    def test_static_passes_on_minimal(self) -> None:
        validate_semantic(
            {"version": 1, "project": {"language": "python"}},
            _YAML_RULES,
        )

    def test_resolved_passes_on_empty_behavior(self) -> None:
        validate_semantic(_resolved(), _TREE_RULES)


class TestIssueIsValidationIssueInstance:
    """Driver returns standard ValidationIssue with rule_code populated."""

    def test_issue_class(self) -> None:
        raw = {"code": {"commit-msg": {"format": True}}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_semantic(raw, _YAML_RULES)
        for issue in exc_info.value.errors:
            assert isinstance(issue, ValidationIssue)
