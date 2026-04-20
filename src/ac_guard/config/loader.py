"""Configuration file loader for AI Code Guard.

Reads a single guard.yaml file from disk, parses YAML, validates
the schema, and returns a raw config dict (RawConfig). This dict
preserves the original YAML structure for downstream merging by
the config merger (WP1.2c).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

import yaml

from ac_guard.config.exceptions import (
    ConfigFileNotFoundError,
    ConfigSyntaxError,
    ConfigValidationError,
    ValidationIssue,
)
from ac_guard.config.validator import validate_raw_config

__all__ = ["RawConfig", "load_config"]


# --- RawConfig TypedDicts ---
# Mirror the guard.yaml schema (§5.2). All fields optional (total=False)
# because a single source file may contain only a subset of fields.


class RawRuleDict(TypedDict, total=False):
    """Raw rule entry from YAML."""

    pattern: str
    reason: str
    message: str
    regex: bool


class RawOperationRulesDict(TypedDict, total=False):
    """Raw operation rules (forbidden/require_approval/allow/remove)."""

    forbidden: list[RawRuleDict]
    require_approval: list[RawRuleDict]
    allow: list[RawRuleDict]
    remove: list[RawRuleDict]


class RawBehaviorDict(TypedDict, total=False):
    """Raw behavior config across three operation types."""

    read: RawOperationRulesDict
    write: RawOperationRulesDict
    execute: RawOperationRulesDict


class RawCheckItemDict(TypedDict, total=False):
    """Raw check item definition."""

    command: str
    timeout: int
    enabled: bool
    types: list[str]
    pass_filenames: bool


class RawPreCommitHookDict(TypedDict, total=False):
    """Raw pre-commit hook entry. Only ``id`` is required; all other
    pre-commit fields pass through verbatim."""

    id: str


class RawPreCommitRepoDict(TypedDict, total=False):
    """Raw pre-commit repo entry."""

    repo: str
    rev: str
    hooks: list[RawPreCommitHookDict]


class RawStageBucketDict(TypedDict, total=False):
    """Raw per-stage bucket under ``code.<stage>``."""

    format: bool
    lint: bool
    checks: dict[str, RawCheckItemDict]
    hooks: list[RawPreCommitRepoDict]


class RawExtraDict(TypedDict, total=False):
    """Raw ``code._extra`` block (passthrough for non-gating stages)."""

    repos: list[RawPreCommitRepoDict]


class RawCodeDict(TypedDict, total=False):
    """Raw ``code:`` config, keyed by pre-commit gating stage names."""

    # YAML keys use hyphens: pre-commit, commit-msg, pre-merge-commit,
    # pre-push, pre-rebase. We cannot declare hyphenated identifiers as
    # TypedDict attributes; the loader uses dict lookups with the yaml
    # string keys directly.
    _extra: RawExtraDict


class RawPreCommitMetaDict(TypedDict, total=False):
    """Raw ``_pre_commit:`` top-level block."""

    minimum_version: str
    default_install_hook_types: list[str]
    default_language_version: dict[str, str]


class RawLanguageToolsDict(TypedDict, total=False):
    """Raw language tools mapping."""

    format: str
    lint: str


class RawLanguageEntryDict(TypedDict, total=False):
    """Raw entry for a single language."""

    tools: RawLanguageToolsDict


class RawBuildDict(TypedDict, total=False):
    """Raw build config."""

    command: str


class RawAuditDict(TypedDict, total=False):
    """Raw audit logging config."""

    enabled: bool
    path: str
    retention: int


class RawPrReportDict(TypedDict, total=False):
    """Raw PR report config."""

    enabled: bool
    platform: str
    api_url: str
    token_env: str


class RawOutputDict(TypedDict, total=False):
    """Raw output config."""

    verbosity: str
    locale: str
    audit: RawAuditDict
    pr_report: RawPrReportDict


class RawProjectConfig(TypedDict, total=False):
    """Raw project section."""

    name: str
    language: str


class RawConfig(TypedDict, total=False):
    """Raw parsed guard.yaml structure.

    All fields are optional because a single source file (defaults,
    ruleset, or user config) may contain only a subset. The merger
    (WP1.2c) combines multiple RawConfig dicts into a ResolvedConfig.
    """

    version: int
    project: RawProjectConfig
    rulesets: list[str]
    languages: dict[str, RawLanguageEntryDict]
    behavior: RawBehaviorDict
    code: RawCodeDict
    build: RawBuildDict
    output: RawOutputDict
    _pre_commit: RawPreCommitMetaDict


# --- Public API ---


def load_config(path: str | Path) -> RawConfig:
    """Load and validate a single guard.yaml file.

    Reads the file, parses YAML, validates schema and semantics,
    and returns the raw config dict.

    Args:
        path: Path to a guard.yaml file.

    Returns:
        RawConfig dict representing the parsed, validated config.

    Raises:
        ConfigFileNotFoundError: File does not exist.
        ConfigSyntaxError: YAML syntax error with line/column info.
        ConfigValidationError: Schema or semantic validation failures.
    """
    resolved = Path(path)
    _check_file_exists(resolved)
    data = _read_yaml(resolved)
    _check_is_dict(data, resolved)
    validate_raw_config(data, source=str(resolved))
    return data  # type: ignore[return-value]


# --- Internal helpers ---


def _check_file_exists(path: Path) -> None:
    if not path.is_file():
        raise ConfigFileNotFoundError(path)


def _read_yaml(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        line: int | None = None
        column: int | None = None
        detail = str(exc)
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            line = mark.line + 1  # PyYAML uses 0-based
            column = mark.column + 1
        raise ConfigSyntaxError(
            path,
            line=line,
            column=column,
            detail=detail,
        ) from exc


def _check_is_dict(data: Any, path: Path) -> None:
    if data is None:
        raise ConfigValidationError(
            [
                ValidationIssue("", "file is empty or contains only comments"),
            ]
        )
    if not isinstance(data, dict):
        raise ConfigValidationError(
            [
                ValidationIssue(
                    "",
                    f"expected a YAML mapping at top level, got {type(data).__name__}",
                    data,
                ),
            ]
        )
