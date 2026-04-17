"""Configuration data models for AI Code Guard.

All config-related dataclasses that represent the parsed and merged
guard.yaml configuration. These are pure data containers with no
validation logic — schema validation belongs in the config loader.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "AuditConfig",
    "BehaviorConfig",
    "CheckItem",
    "CodeConfig",
    "LanguageTools",
    "OperationRules",
    "OutputConfig",
    "PrReportConfig",
    "ResolvedConfig",
    "Rule",
]


@dataclass
class Rule:
    """A single behavior constraint rule.

    Attributes:
        pattern: Resource pattern with scheme prefix
            (file:/shell:/mcp:/web:). Supports glob by default.
        reason: Human-readable reason shown when a violation
            is denied.
        message: Custom message shown when asking for user
            approval (require_approval rules).
        regex: If True, pattern uses regex matching instead
            of glob.
        source: Origin of this rule. One of "default",
            "ruleset:<name>", "user", or "system".
    """

    pattern: str
    reason: str | None = None
    message: str | None = None
    regex: bool = False
    source: str = "user"


@dataclass
class OperationRules:
    """Three-tier rules for a single operation type.

    Attributes:
        forbidden: Rules that unconditionally block the
            operation.
        require_approval: Rules that pause and ask the user
            for confirmation.
        allow: Rules that explicitly permit the operation,
            overriding default-deny in strict mode.
    """

    forbidden: list[Rule]
    require_approval: list[Rule]
    allow: list[Rule]

    @classmethod
    def empty(cls) -> OperationRules:
        """Create an instance with empty rule lists.

        Returns:
            OperationRules with empty forbidden,
            require_approval, and allow lists.
        """
        return cls(forbidden=[], require_approval=[], allow=[])


@dataclass
class BehaviorConfig:
    """Behavior constraints across three operation dimensions.

    Attributes:
        read: Rules for file/resource read operations.
        write: Rules for file/resource write operations.
        execute: Rules for shell command and MCP tool
            execution.
    """

    read: OperationRules
    write: OperationRules
    execute: OperationRules

    @classmethod
    def empty(cls) -> BehaviorConfig:
        """Create an instance with empty operation rules.

        Returns:
            BehaviorConfig with empty read, write, and execute
            OperationRules.
        """
        return cls(
            read=OperationRules.empty(),
            write=OperationRules.empty(),
            execute=OperationRules.empty(),
        )


@dataclass
class CheckItem:
    """A single code check definition.

    Attributes:
        command: Shell command to execute for this check.
        timeout: Maximum execution time in seconds.
        enabled: Whether this check is active.
        types: File type filter (e.g. ["python"]). None
            means all files.
        pass_filenames: Whether to append changed filenames
            to the command.
    """

    command: str
    timeout: int = 300
    enabled: bool = True
    types: list[str] | None = None
    pass_filenames: bool = True


@dataclass
class CodeConfig:
    """Code quality check configuration.

    Attributes:
        commit_format: Enable format checking at commit stage.
        commit_naming: Enable naming convention checking at
            commit stage.
        commit_checks: Custom check items run at commit stage,
            keyed by check name.
        push_lint: Enable semantic lint at push stage.
        push_checks: Custom check items run at push stage,
            keyed by check name.
    """

    commit_format: bool = True
    commit_naming: bool = False
    commit_checks: dict[str, CheckItem] = field(default_factory=dict)
    push_lint: bool = True
    push_checks: dict[str, CheckItem] = field(default_factory=dict)


@dataclass
class LanguageTools:
    """Format and lint tool mapping for a programming language.

    Attributes:
        format: Formatter tool name (e.g. "black", "prettier").
        lint: Linter tool name (e.g. "ruff", "eslint").
    """

    format: str
    lint: str


@dataclass
class AuditConfig:
    """Audit logging configuration.

    Attributes:
        enabled: Whether audit logging is active.
        path: File path for the audit log (JSON Lines).
        retention: Number of days to retain audit records.
            0 means permanent.
    """

    enabled: bool = True
    path: str = ".ac-guard/audit.jsonl"
    retention: int = 30


@dataclass
class PrReportConfig:
    """Pull request report configuration.

    Attributes:
        enabled: Whether PR report posting is active.
        platform: Code hosting platform. One of "github",
            "gitlab", "gitea", or "bitbucket".
        api_url: Custom API endpoint for self-hosted
            instances. None uses the platform default.
        token_env: Environment variable name that holds
            the platform access token.
    """

    enabled: bool = False
    platform: str = "github"
    api_url: str | None = None
    token_env: str = "GITHUB_TOKEN"


@dataclass
class OutputConfig:
    """Output and reporting configuration.

    Attributes:
        verbosity: Output detail level. One of "quiet",
            "normal", or "verbose".
        locale: Report language code ("en" or "zh-CN").
        audit: Audit logging settings.
        pr_report: PR report posting settings.
    """

    verbosity: str = "normal"
    locale: str = "en"
    audit: AuditConfig = field(default_factory=AuditConfig)
    pr_report: PrReportConfig = field(default_factory=PrReportConfig)


@dataclass
class ResolvedConfig:
    """Final merged configuration consumed by all modules.

    Produced by the config loader after merging defaults,
    rulesets, and the project guard.yaml. This is the single
    configuration object passed to Generator, Enforcer, and
    other modules.

    Attributes:
        version: Configuration schema version number.
        project_name: Project display name, defaults to
            the directory name.
        project_language: Primary programming language
            (e.g. "python", "typescript").
        behavior: Behavior constraint rules across read,
            write, and execute dimensions.
        code: Code quality check configuration for commit
            and push stages.
        languages: Per-language tool mappings, keyed by
            language name.
        output: Output and reporting settings.
        build_command: Optional build command run before
            push-stage checks.
        config_hash: SHA hash of the source guard.yaml,
            used for drift detection.
    """

    version: int
    project_name: str
    project_language: str
    behavior: BehaviorConfig
    code: CodeConfig
    languages: dict[str, LanguageTools]
    output: OutputConfig
    build_command: str | None = None
    config_hash: str = ""
    rulesets: list[str] = field(default_factory=list)
