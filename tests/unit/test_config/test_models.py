"""Tests for ac_guard.config.models — Config data model definitions."""

from __future__ import annotations

import pytest

from ac_guard.config.models import (
    AuditConfig,
    BehaviorConfig,
    CheckItem,
    CodeConfig,
    LanguageTools,
    OperationRules,
    OutputConfig,
    PrReportConfig,
    ResolvedConfig,
    Rule,
)

# ---------------------------------------------------------------------------
# A. Rule
# ---------------------------------------------------------------------------


class TestRule:
    def test_required_pattern(self):
        rule = Rule(pattern="file:*.py")
        assert rule.pattern == "file:*.py"

    def test_defaults(self):
        rule = Rule(pattern="file:*.py")
        assert rule.reason is None
        assert rule.message is None
        assert rule.regex is False
        assert rule.source == "user"

    def test_all_fields(self):
        rule = Rule(
            pattern="shell:rm -rf*",
            reason="dangerous",
            message="blocked",
            regex=True,
            source="system",
        )
        assert rule.pattern == "shell:rm -rf*"
        assert rule.reason == "dangerous"
        assert rule.message == "blocked"
        assert rule.regex is True
        assert rule.source == "system"

    def test_regex_flag(self):
        rule = Rule(pattern=r"shell:git\s+push.*", regex=True)
        assert rule.regex is True

    def test_source_variants(self):
        for src in ("default", "ruleset:security", "user", "system"):
            rule = Rule(pattern="file:x", source=src)
            assert rule.source == src

    def test_missing_pattern_raises(self):
        with pytest.raises(TypeError):
            Rule()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# B. OperationRules
# ---------------------------------------------------------------------------


class TestOperationRules:
    def test_construction(self):
        rules = OperationRules(
            forbidden=[Rule(pattern="file:.env")],
            require_approval=[Rule(pattern="file:.github/**")],
            allow=[Rule(pattern="file:src/**")],
        )
        assert len(rules.forbidden) == 1
        assert len(rules.require_approval) == 1
        assert len(rules.allow) == 1

    def test_empty_lists(self):
        rules = OperationRules(forbidden=[], require_approval=[], allow=[])
        assert rules.forbidden == []
        assert rules.require_approval == []
        assert rules.allow == []

    def test_missing_field_raises(self):
        with pytest.raises(TypeError):
            OperationRules(forbidden=[])  # type: ignore[call-arg]

    def test_empty_factory(self):
        rules = OperationRules.empty()
        assert rules.forbidden == []
        assert rules.require_approval == []
        assert rules.allow == []


# ---------------------------------------------------------------------------
# C. BehaviorConfig
# ---------------------------------------------------------------------------


class TestBehaviorConfig:
    def test_construction(self):
        ops = OperationRules.empty()
        cfg = BehaviorConfig(read=ops, write=ops, execute=ops)
        assert cfg.read is ops

    def test_missing_field_raises(self):
        with pytest.raises(TypeError):
            BehaviorConfig(read=OperationRules.empty())  # type: ignore[call-arg]

    def test_empty_factory(self):
        cfg = BehaviorConfig.empty()
        assert cfg.read.forbidden == []
        assert cfg.write.forbidden == []
        assert cfg.execute.forbidden == []


# ---------------------------------------------------------------------------
# D. CheckItem
# ---------------------------------------------------------------------------


class TestCheckItem:
    def test_required_command(self):
        item = CheckItem(command="ruff check")
        assert item.command == "ruff check"

    def test_defaults(self):
        item = CheckItem(command="ruff check")
        assert item.timeout == 300
        assert item.enabled is True
        assert item.types is None
        assert item.pass_filenames is True

    def test_all_fields(self):
        item = CheckItem(
            command="pytest",
            timeout=600,
            enabled=False,
            types=["python"],
            pass_filenames=False,
        )
        assert item.command == "pytest"
        assert item.timeout == 600
        assert item.enabled is False
        assert item.types == ["python"]
        assert item.pass_filenames is False

    def test_missing_command_raises(self):
        with pytest.raises(TypeError):
            CheckItem()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# E. CodeConfig
# ---------------------------------------------------------------------------


class TestCodeConfig:
    """CodeConfig is keyed by pre-commit gating stage (schema v2, #123)."""

    def test_all_defaults(self):
        cfg = CodeConfig()
        assert cfg is not None

    def test_defaults_values(self):
        cfg = CodeConfig()
        # Dataclass defaults: every bucket empty. The merger applies
        # project-level defaults (pre-commit.format=True, pre-push.lint=
        # True) via _DEFAULT_CONFIG — not this constructor.
        assert cfg.pre_commit.format is False
        assert cfg.pre_commit.lint is False
        assert cfg.pre_commit.checks == {}
        assert cfg.pre_commit.hooks == []
        assert cfg.pre_push.lint is False
        assert cfg.pre_push.hooks == []
        assert cfg.extra_repos == []
        # Legacy shim: commit_naming is always False (D8, dead flag).
        assert cfg.commit_naming is False

    def test_with_check_items(self):
        from ac_guard.config.models import StageBucket

        cfg = CodeConfig(
            pre_commit=StageBucket(
                checks={"license": CheckItem(command="check-license")}
            ),
            pre_push=StageBucket(
                checks={"test": CheckItem(command="pytest", timeout=600)}
            ),
        )
        assert "license" in cfg.pre_commit.checks
        assert cfg.pre_push.checks["test"].timeout == 600
        # Legacy shim access
        assert "license" in cfg.commit_checks
        assert cfg.push_checks["test"].timeout == 600

    def test_default_factory_independence(self):
        a = CodeConfig()
        b = CodeConfig()
        a.pre_commit.checks["x"] = CheckItem(command="x")
        assert "x" not in b.pre_commit.checks

    def test_buckets_helper_returns_all_five(self):
        cfg = CodeConfig()
        names = [name for name, _ in cfg.buckets()]
        assert names == [
            "pre-commit",
            "commit-msg",
            "pre-merge-commit",
            "pre-push",
            "pre-rebase",
        ]

    def test_active_stages_empty_when_all_buckets_empty(self):
        cfg = CodeConfig()
        assert cfg.active_stages() == []

    def test_active_stages_reports_non_empty(self):
        from ac_guard.config.models import StageBucket

        cfg = CodeConfig(
            pre_commit=StageBucket(format=True),
            pre_push=StageBucket(checks={"test": CheckItem(command="pytest")}),
        )
        assert cfg.active_stages() == ["pre-commit", "pre-push"]


# ---------------------------------------------------------------------------
# F. LanguageTools
# ---------------------------------------------------------------------------


class TestLanguageTools:
    def test_construction(self):
        tools = LanguageTools(format="black", lint="ruff")
        assert tools.format == "black"
        assert tools.lint == "ruff"

    def test_missing_field_raises(self):
        with pytest.raises(TypeError):
            LanguageTools(format="black")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# G. AuditConfig
# ---------------------------------------------------------------------------


class TestAuditConfig:
    def test_all_defaults(self):
        cfg = AuditConfig()
        assert cfg is not None

    def test_defaults_values(self):
        cfg = AuditConfig()
        assert cfg.enabled is True
        assert cfg.path == ".ac-guard/audit.jsonl"
        assert cfg.retention == 30

    def test_custom_values(self):
        cfg = AuditConfig(enabled=False, path="/tmp/audit.jsonl", retention=0)
        assert cfg.enabled is False
        assert cfg.path == "/tmp/audit.jsonl"
        assert cfg.retention == 0


# ---------------------------------------------------------------------------
# H. PrReportConfig
# ---------------------------------------------------------------------------


class TestPrReportConfig:
    def test_all_defaults(self):
        cfg = PrReportConfig()
        assert cfg is not None

    def test_defaults_values(self):
        cfg = PrReportConfig()
        assert cfg.enabled is False
        assert cfg.platform == "github"
        assert cfg.api_url is None
        assert cfg.token_env == "GITHUB_TOKEN"


# ---------------------------------------------------------------------------
# I. OutputConfig
# ---------------------------------------------------------------------------


class TestOutputConfig:
    def test_all_defaults(self):
        cfg = OutputConfig()
        assert cfg is not None

    def test_defaults_values(self):
        cfg = OutputConfig()
        assert cfg.verbosity == "normal"
        assert cfg.locale == "en"
        assert isinstance(cfg.audit, AuditConfig)
        assert isinstance(cfg.pr_report, PrReportConfig)

    def test_nested_custom(self):
        cfg = OutputConfig(
            audit=AuditConfig(retention=7),
            pr_report=PrReportConfig(enabled=True, platform="gitlab"),
        )
        assert cfg.audit.retention == 7
        assert cfg.pr_report.platform == "gitlab"

    def test_default_factory_independence(self):
        a = OutputConfig()
        b = OutputConfig()
        a.audit.retention = 999
        assert b.audit.retention == 30


# ---------------------------------------------------------------------------
# J. ResolvedConfig
# ---------------------------------------------------------------------------


def _make_resolved_config(**overrides) -> ResolvedConfig:
    """Build a minimal valid ResolvedConfig for testing."""
    defaults = dict(
        version=1,
        project_name="test-project",
        project_language="python",
        behavior=BehaviorConfig.empty(),
        code=CodeConfig(),
        languages={"python": LanguageTools(format="black", lint="ruff")},
        output=OutputConfig(),
    )
    defaults.update(overrides)
    return ResolvedConfig(**defaults)


class TestResolvedConfig:
    def test_construction(self):
        cfg = _make_resolved_config()
        assert cfg.version == 1
        assert cfg.project_name == "test-project"

    def test_required_fields(self):
        with pytest.raises(TypeError):
            ResolvedConfig(version=1, project_name="x")  # type: ignore[call-arg]

    def test_optional_defaults(self):
        cfg = _make_resolved_config()
        assert cfg.build_command is None
        assert cfg.config_hash == ""

    def test_full_nested_access(self):
        cfg = _make_resolved_config(
            behavior=BehaviorConfig(
                read=OperationRules.empty(),
                write=OperationRules(
                    forbidden=[
                        Rule(pattern="file:vendor/**", reason="no vendor edits"),
                    ],
                    require_approval=[],
                    allow=[Rule(pattern="file:src/**")],
                ),
                execute=OperationRules.empty(),
            ),
            languages={
                "python": LanguageTools(format="black", lint="ruff"),
                "typescript": LanguageTools(format="prettier", lint="eslint"),
            },
        )
        assert cfg.behavior.write.forbidden[0].pattern == "file:vendor/**"
        assert cfg.behavior.write.forbidden[0].reason == "no vendor edits"
        assert cfg.behavior.write.allow[0].pattern == "file:src/**"
        assert cfg.languages["typescript"].lint == "eslint"


# ---------------------------------------------------------------------------
# K. Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_config_package_exports(self):
        from ac_guard.config import (  # noqa: F401
            AuditConfig,
            BehaviorConfig,
            CheckItem,
            CodeConfig,
            LanguageTools,
            OperationRules,
            OutputConfig,
            PrReportConfig,
            ResolvedConfig,
            Rule,
        )

    def test_config_all_list(self):
        import ac_guard.config as config_mod

        expected = {
            # Exceptions
            "ConfigError",
            "ConfigFileNotFoundError",
            "ConfigSyntaxError",
            "ConfigValidationError",
            "ConfigWarning",
            "ValidationIssue",
            # Loader
            "load_config",
            "RawConfig",
            # Merger
            "resolve_config",
            # Validator
            "validate_raw_config",
            # Models
            "Rule",
            "OperationRules",
            "BehaviorConfig",
            "CheckItem",
            "CodeConfig",
            "LanguageTools",
            "AuditConfig",
            "PrReportConfig",
            "OutputConfig",
            "ResolvedConfig",
        }
        assert set(config_mod.__all__) == expected
