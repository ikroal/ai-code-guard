"""Configuration data models for AI Code Guard.

All config-related dataclasses that represent the parsed and merged
guard.yaml configuration. These are pure data containers with no
validation logic — schema validation belongs in the config loader.

Schema v2 (#123): ``code:`` is keyed by pre-commit gating stage names
(pre-commit / commit-msg / pre-merge-commit / pre-push / pre-rebase).
Each stage bucket holds the same five fields
(``format`` / ``lint`` / ``checks`` / ``hooks`` / plus ruff N-rules via
``lint``). ``_pre_commit`` carries top-level pre-commit meta, ``_extra``
carries passthrough hooks for non-gating stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AuditConfig",
    "BehaviorConfig",
    "CheckItem",
    "CodeConfig",
    "LanguageTools",
    "OperationRules",
    "OutputConfig",
    "PrReportConfig",
    "PreCommitHook",
    "PreCommitMeta",
    "PreCommitRepo",
    "ResolvedConfig",
    "Rule",
    "StageBucket",
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
    """A single code check definition (short-hand for local hooks).

    A ``CheckItem`` is rendered into the generated
    ``.pre-commit-config.yaml`` as a ``custom-<name>`` entry under the
    stage bucket's ``repo: local`` block.

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
class PreCommitHook:
    """Passthrough wrapper for a single pre-commit hook entry.

    ``id`` is required; all other pre-commit fields (``name`` / ``entry`` /
    ``args`` / ``language`` / ``types`` / ``pass_filenames`` /
    ``additional_dependencies`` / ``stages`` / ``always_run`` / ``files`` /
    ``exclude`` / ...) are carried verbatim in ``extra`` so new
    pre-commit fields work without schema changes.

    Attributes:
        id: Hook identifier (required).
        extra: Any additional pre-commit hook fields passed through
            to the generated yaml as-is.
    """

    id: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreCommitRepo:
    """Passthrough wrapper for a pre-commit ``repos[]`` entry.

    Attributes:
        repo: Repository URL or the literal ``"local"``.
        rev: Repository revision tag/branch. ``None`` for local repos.
        hooks: List of hook entries under this repo.
    """

    repo: str
    rev: str | None = None
    hooks: list[PreCommitHook] = field(default_factory=list)


@dataclass
class StageBucket:
    """Per-stage configuration bucket under ``code.<stage>``.

    Each bucket produces exactly one local ac-guard repo entry (built
    from ``format`` / ``lint`` / ``checks``) plus ``hooks`` passed
    through verbatim in the generated ``.pre-commit-config.yaml``. All
    resulting hooks carry the bucket's stage as their default
    ``stages:`` field (user-provided ``stages`` on passthrough hooks
    overrides).

    Attributes:
        format: Inject per-language format hooks (``format-<lang>``)
            from ``languages[*].tools.format``.
        lint: Inject per-language lint hooks (``lint-<lang>``) from
            ``languages[*].tools.lint``.
        checks: Short-hand local hooks rendered as ``custom-<name>``.
        hooks: Full pre-commit repo/hook declarations. Community repos
            or project-specific local hooks that need the full
            passthrough surface live here.
    """

    format: bool = False
    lint: bool = False
    checks: dict[str, CheckItem] = field(default_factory=dict)
    hooks: list[PreCommitRepo] = field(default_factory=list)

    def is_empty(self) -> bool:
        """True when no ac-guard semantic or external hooks are declared."""
        return not self.format and not self.lint and not self.checks and not self.hooks


@dataclass
class CodeConfig:
    """Code quality configuration, keyed by pre-commit gating stage.

    The five gating stage buckets mirror pre-commit's native stage
    taxonomy. Non-gating stages (post-* / prepare-commit-msg / manual)
    live in ``extra_repos`` as passthrough — ac-guard does not gate
    them but renders them into the generated yaml so pre-commit still
    executes them.

    Attributes:
        pre_commit: pre-commit stage (most project hooks land here).
        commit_msg: commit-msg stage (e.g. conventional-pre-commit).
        pre_merge_commit: pre-merge-commit stage (rare).
        pre_push: pre-push stage (heavy checks, test/coverage).
        pre_rebase: pre-rebase stage (rare).
        extra_repos: Passthrough repos for non-gating stages
            (populated from ``code._extra.repos`` in yaml).
    """

    pre_commit: StageBucket = field(default_factory=StageBucket)
    commit_msg: StageBucket = field(default_factory=StageBucket)
    pre_merge_commit: StageBucket = field(default_factory=StageBucket)
    pre_push: StageBucket = field(default_factory=StageBucket)
    pre_rebase: StageBucket = field(default_factory=StageBucket)
    extra_repos: list[PreCommitRepo] = field(default_factory=list)

    GATING_STAGES = (
        "pre_commit",
        "commit_msg",
        "pre_merge_commit",
        "pre_push",
        "pre_rebase",
    )

    def buckets(self) -> list[tuple[str, StageBucket]]:
        """Return (yaml_stage_name, bucket) pairs for all gating stages."""
        return [
            ("pre-commit", self.pre_commit),
            ("commit-msg", self.commit_msg),
            ("pre-merge-commit", self.pre_merge_commit),
            ("pre-push", self.pre_push),
            ("pre-rebase", self.pre_rebase),
        ]

    def active_stages(self) -> list[str]:
        """Return yaml stage names for buckets that have any content.

        Used by ``generate_git_hooks`` to only emit wrappers for
        stages the project actually uses.
        """
        return [name for name, bucket in self.buckets() if not bucket.is_empty()]

    # ---- Legacy read-only shims (Phase 1a, drop in Phase 1c) -----------
    # These let checker / generator / CLI continue to read ``commit_*`` /
    # ``push_*`` attributes during the transition to the new bucket API.
    # Write-paths (merger, test constructors) must use the new fields
    # directly; shims are read-only.

    @property
    def commit_format(self) -> bool:
        return self.pre_commit.format

    @property
    def commit_naming(self) -> bool:
        # D8: commit_naming is a dead flag; shim always returns False so
        # the old checker branch becomes a no-op without removal yet.
        return False

    @property
    def commit_checks(self) -> dict[str, CheckItem]:
        return self.pre_commit.checks

    @property
    def push_lint(self) -> bool:
        return self.pre_push.lint

    @property
    def push_checks(self) -> dict[str, CheckItem]:
        return self.pre_push.checks


@dataclass
class PreCommitMeta:
    """Top-level pre-commit yaml fields.

    Populated from guard.yaml's ``_pre_commit:`` block. All fields
    optional; generator substitutes sensible defaults when absent.

    Attributes:
        minimum_version: Value for ``minimum_pre_commit_version``
            in the generated yaml.
        default_install_hook_types: List for
            ``default_install_hook_types`` (defaults to the active
            stages detected from guard.yaml).
        default_language_version: Map for
            ``default_language_version`` (e.g. ``{python: python3}``).
    """

    minimum_version: str | None = None
    default_install_hook_types: list[str] | None = None
    default_language_version: dict[str, str] = field(default_factory=dict)


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
        code: Code quality configuration keyed by pre-commit
            gating stage (schema v2).
        languages: Per-language tool mappings, keyed by
            language name.
        output: Output and reporting settings.
        pre_commit_meta: Top-level pre-commit yaml fields
            (minimum_version, default_language_version, ...).
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
    pre_commit_meta: PreCommitMeta = field(default_factory=PreCommitMeta)
    build_command: str | None = None
    config_hash: str = ""
    rulesets: list[str] = field(default_factory=list)
