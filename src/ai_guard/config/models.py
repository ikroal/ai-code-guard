"""Configuration data models for AI Guard."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
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
]


@dataclass
class Rule:
    """A single behavior constraint rule."""

    pattern: str
    reason: str | None = None
    message: str | None = None
    regex: bool = False
    source: str = "user"


@dataclass
class OperationRules:
    """Three-tier rules for a single operation type (read/write/execute)."""

    forbidden: list[Rule]
    require_approval: list[Rule]
    allow: list[Rule]

    @classmethod
    def empty(cls) -> OperationRules:
        """Create an instance with empty rule lists."""
        return cls(forbidden=[], require_approval=[], allow=[])


@dataclass
class BehaviorConfig:
    """Behavior constraints across read, write, and execute dimensions."""

    read: OperationRules
    write: OperationRules
    execute: OperationRules

    @classmethod
    def empty(cls) -> BehaviorConfig:
        """Create an instance with empty operation rules."""
        return cls(
            read=OperationRules.empty(),
            write=OperationRules.empty(),
            execute=OperationRules.empty(),
        )


@dataclass
class CheckItem:
    """A single code check definition."""

    command: str
    timeout: int = 300
    enabled: bool = True
    types: list[str] | None = None
    pass_filenames: bool = True


@dataclass
class CodeConfig:
    """Code quality check configuration for commit and push stages."""

    commit_format: bool = True
    commit_naming: bool = True
    commit_checks: dict[str, CheckItem] = field(default_factory=dict)
    push_lint: bool = True
    push_checks: dict[str, CheckItem] = field(default_factory=dict)


@dataclass
class LanguageTools:
    """Format and lint tool mapping for a programming language."""

    format: str
    lint: str


@dataclass
class AuditConfig:
    """Audit logging configuration."""

    enabled: bool = True
    path: str = ".ai-guard/audit.jsonl"
    retention: int = 30


@dataclass
class PrReportConfig:
    """Pull request report configuration."""

    enabled: bool = False
    platform: str = "github"
    api_url: str | None = None
    token_env: str = "GITHUB_TOKEN"


@dataclass
class OutputConfig:
    """Output and reporting configuration."""

    verbosity: str = "normal"
    locale: str = "en"
    audit: AuditConfig = field(default_factory=AuditConfig)
    pr_report: PrReportConfig = field(default_factory=PrReportConfig)


@dataclass
class ResolvedConfig:
    """Final merged configuration consumed by all AI Guard modules."""

    version: int
    project_name: str
    project_language: str
    behavior: BehaviorConfig
    code: CodeConfig
    languages: dict[str, LanguageTools]
    output: OutputConfig
    build_command: str | None = None
    config_hash: str = ""
