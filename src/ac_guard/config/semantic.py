"""Semantic config validation — L2 (raw) and L3 (resolved), zero-IO.

L1 ``validator.py`` checks structural shape (types, required fields,
enum values). This module checks **semantic** correctness that schema
shape can't express:

L2 (raw dict, after ``validate_raw_config``):
    * ``format-lint-stage-scope`` — ``format``/``lint`` toggles only
      apply on file-scoped stages (``pre-commit``/``pre-push``).
    * ``command-syntax`` — user-supplied command strings must be
      ``shlex.split``-parseable (balanced quotes, etc.).

L3 (ResolvedConfig, after merge / system-rule injection):
    * ``tier-consistency`` — same pattern must not appear in both
      ``forbidden`` and ``allow`` under one operation.
    * ``pattern-uniqueness`` — within a tier list, no pattern should
      appear twice (system-injected rules excluded — they may
      legitimately overlap user patterns).

Each rule is a small function ``(data, issues) -> None``; the
``_SemanticRule`` struct binds it to a stable ``code``. The driver
runs all rules, post-injects ``rule_code`` on every issue produced,
and raises ``ConfigValidationError`` once at the end so the user sees
every problem in a single pass.

Adding a new rule is mechanical: write ``_verify_xxx``, append a
``_SemanticRule(code=..., apply=_verify_xxx)`` to the relevant tuple,
and add a ``rule_code``-asserting test in ``test_semantic.py``.

Internal submodule — import the public surface via
:mod:`ac_guard.config` rather than reaching in here directly.
"""

from __future__ import annotations

import shlex
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ac_guard.config.exceptions import ConfigValidationError, ValidationIssue

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from ac_guard.config.models import OperationRules, ResolvedConfig

__all__ = ["validate_semantic_resolved", "validate_semantic_static"]


# Stages whose pre-commit ``types:`` filter matches source files. Only
# these accept ``format`` / ``lint`` toggle shortcuts; on other stages
# (commit-msg / pre-rebase / pre-merge-commit) the per-language hooks
# would silently never run because the input is a message file or a
# branch ref, not a source file. This is the rule's private decision
# criterion — deliberately not in domain.stages, since whether a stage
# is file-scoped is a property of pre-commit's filtering behavior, not
# of ac-guard's stage registry.
_FILE_SCOPED: frozenset[str] = frozenset({"pre-commit", "pre-push"})


# ---------------------------------------------------------------------------
# Rule struct and driver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SemanticRule:
    """Stable rule code + the function that implements the rule.

    Attributes:
        code: Stable identifier surfaced on every ``ValidationIssue``
            this rule produces (so users / docs / tests can refer to a
            specific rule without coupling to error wording).
        apply: Pure function that appends ``ValidationIssue`` entries
            for every problem found. Should not raise.
    """

    code: str
    apply: Callable[[Any, list[ValidationIssue]], None]


def _run_rules(rules: tuple[_SemanticRule, ...], data: Any) -> list[ValidationIssue]:
    """Run every rule against ``data``, post-inject ``rule_code``."""
    issues: list[ValidationIssue] = []
    for rule in rules:
        before = len(issues)
        rule.apply(data, issues)
        for issue in issues[before:]:
            issue.rule_code = rule.code
    return issues


# ---------------------------------------------------------------------------
# L2 rules (raw dict)
# ---------------------------------------------------------------------------


def _verify_format_lint_scope(raw: Any, issues: list[ValidationIssue]) -> None:
    """``format`` / ``lint`` only apply on file-scoped stages.

    On non-file-scoped stages (commit-msg / pre-merge-commit /
    pre-rebase) the per-language hooks ac-guard generates carry a
    ``types:`` filter that pre-commit will never match, so ``format:
    true`` would silently no-op. That's worse than the current schema
    rejecting the toggle outright.
    """
    code = (raw or {}).get("code") or {}
    if not isinstance(code, dict):
        return
    issues.extend(
        ValidationIssue(
            path=f"code.{stage_name}.{toggle}",
            message=(
                "only applies on file-scoped stages "
                "(pre-commit / pre-push); on "
                f"'{stage_name}' pre-commit's types: "
                "filter never matches and the generated "
                "per-language hooks silently never run"
            ),
            value=True,
        )
        for stage_name, bucket in code.items()
        if isinstance(bucket, dict) and stage_name not in _FILE_SCOPED
        for toggle in ("format", "lint")
        if bucket.get(toggle) is True
    )


def _verify_command_syntax(raw: Any, issues: list[ValidationIssue]) -> None:
    """User-supplied command strings must be ``shlex.split``-parseable.

    Catches unbalanced quotes / dangling backslashes early. Empty
    strings are L1's job (``non_empty``); we skip them here to avoid
    double-reporting.
    """
    for path, command in _iter_user_commands(raw):
        _check_shlex(path, command, issues)


def _check_shlex(path: str, command: Any, issues: list[ValidationIssue]) -> None:
    """Append a ``command-syntax`` issue if ``command`` fails shlex parsing.

    Empty strings and non-strings are silently skipped — L1 already
    handles those.
    """
    if not isinstance(command, str) or not command:
        return
    try:
        shlex.split(command)
    except ValueError as exc:
        issues.append(
            ValidationIssue(
                path=path,
                message=f"command is not shell-parseable: {exc}",
                value=command,
            )
        )


def _iter_user_commands(raw: Any) -> Iterator[tuple[str, Any]]:
    """Yield ``(path, command)`` for every user-supplied command string.

    Sources:
    * ``languages.<lang>.tools.format``
    * ``languages.<lang>.tools.lint``
    * ``code.<stage>.checks.<name>.command``
    """
    languages = (raw or {}).get("languages") or {}
    if isinstance(languages, dict):
        for lang, entry in languages.items():
            tools = (entry or {}).get("tools") if isinstance(entry, dict) else None
            if isinstance(tools, dict):
                yield f"languages.{lang}.tools.format", tools.get("format")
                yield f"languages.{lang}.tools.lint", tools.get("lint")

    code = (raw or {}).get("code") or {}
    if isinstance(code, dict):
        for stage_name, bucket in code.items():
            if not isinstance(bucket, dict):
                continue
            checks = bucket.get("checks") or {}
            if not isinstance(checks, dict):
                continue
            for check_name, item in checks.items():
                if isinstance(item, dict):
                    yield (
                        f"code.{stage_name}.checks.{check_name}.command",
                        item.get("command"),
                    )


# ---------------------------------------------------------------------------
# L3 rules (ResolvedConfig)
# ---------------------------------------------------------------------------


_OPERATIONS = ("read", "write", "execute")
_TIER_FIELDS = ("forbidden", "require_approval", "allow")


def _verify_tier_consistency(
    resolved: ResolvedConfig, issues: list[ValidationIssue]
) -> None:
    """Same pattern in ``forbidden`` and ``allow`` under one op is contradictory.

    Each operation (read/write/execute) is checked independently — it
    is fine to forbid pattern X for read while allowing it for write.
    """
    for op in _OPERATIONS:
        rules: OperationRules = getattr(resolved.behavior, op)
        forbidden = {r.pattern for r in rules.forbidden}
        allow = {r.pattern for r in rules.allow}
        issues.extend(
            ValidationIssue(
                path=f"behavior.{op}",
                message=(
                    f"pattern '{pattern}' appears in both "
                    "'forbidden' and 'allow'; remove one tier or "
                    "use 'remove' to override"
                ),
                value=pattern,
            )
            for pattern in sorted(forbidden & allow)
        )


def _verify_pattern_uniqueness(
    resolved: ResolvedConfig, issues: list[ValidationIssue]
) -> None:
    """Within a single tier list, the same pattern should not appear twice.

    System-injected rules (``source="system"``) may legitimately
    overlap user patterns and are excluded from the duplicate count;
    duplicates among user/ruleset/default rules are still reported
    even when a system rule shares the pattern.
    """
    for op in _OPERATIONS:
        rules: OperationRules = getattr(resolved.behavior, op)
        for tier_field in _TIER_FIELDS:
            tier = getattr(rules, tier_field)
            patterns = [r.pattern for r in tier if r.source != "system"]
            for pattern, count in Counter(patterns).items():
                if count > 1:
                    issues.append(
                        ValidationIssue(
                            path=f"behavior.{op}.{tier_field}",
                            message=(
                                f"pattern '{pattern}' appears "
                                f"{count} times in this tier; merge "
                                "or remove the duplicates"
                            ),
                            value=pattern,
                        )
                    )


# ---------------------------------------------------------------------------
# Rule registries — adding a new rule means appending a line here.
# ---------------------------------------------------------------------------


_STATIC_RULES: tuple[_SemanticRule, ...] = (
    _SemanticRule(code="format-lint-stage-scope", apply=_verify_format_lint_scope),
    _SemanticRule(code="command-syntax", apply=_verify_command_syntax),
)


_RESOLVED_RULES: tuple[_SemanticRule, ...] = (
    _SemanticRule(code="tier-consistency", apply=_verify_tier_consistency),
    _SemanticRule(code="pattern-uniqueness", apply=_verify_pattern_uniqueness),
)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def validate_semantic_static(raw: dict[str, Any], *, source: str) -> None:
    """Run L2 semantic rules over a raw config dict.

    Args:
        raw: Parsed YAML dict, post-L1 schema validation.
        source: Label kept for parity with ``validate_raw_config``;
            currently unused by the rules but reserved for future
            error context (e.g. yaml line numbers).

    Raises:
        ConfigValidationError: If any L2 rule fires.
    """
    del source  # reserved
    issues = _run_rules(_STATIC_RULES, raw)
    if issues:
        raise ConfigValidationError(issues)


def validate_semantic_resolved(resolved: ResolvedConfig) -> None:
    """Run L3 semantic rules over a fully merged ``ResolvedConfig``.

    Args:
        resolved: ResolvedConfig returned by the merger.

    Raises:
        ConfigValidationError: If any L3 rule fires.
    """
    issues = _run_rules(_RESOLVED_RULES, resolved)
    if issues:
        raise ConfigValidationError(issues)
