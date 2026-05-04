"""Semantic config validation — zero-IO rules over yaml or merged config.

L1 ``validator.py`` checks structural shape (types, required fields,
enum values). This module checks **semantic** correctness that schema
shape can't express. All rules are zero-IO; the IO-bearing
configuration-vs-environment diagnostics live in ``diagnose.py``.

The four rules currently implemented:

* ``format-lint-stage-scope`` — ``format``/``lint`` toggles only apply
  on file-scoped stages (``pre-commit`` / ``pre-push``); judged from a
  parsed yaml.
* ``command-syntax`` — user-supplied command strings must be
  ``shlex.split``-parseable (balanced quotes, etc.); judged from a
  parsed yaml.
* ``tier-consistency`` — same pattern must not appear in both
  ``forbidden`` and ``allow`` under one operation; judged from the
  merged tree.
* ``pattern-uniqueness`` — within a tier list, no pattern should
  appear twice (system-injected rules excluded — they may legitimately
  overlap user patterns); judged from the merged tree.

Public surface (within the ``ac_guard.config`` package only — this
module's ``__all__`` is empty):

* ``validate_semantic(payload, rules)`` — single driver. Runs the
  given rules against ``payload``, aggregates ``ValidationIssue``
  entries (each tagged with ``rule.code``), and raises
  ``ConfigValidationError`` once if any rule fired. Caller decides
  which rules apply to its payload.
* ``_FORMAT_LINT_SCOPE`` / ``_COMMAND_SYNTAX`` / ``_TIER_CONSISTENCY``
  / ``_PATTERN_UNIQUENESS`` — named rule constants. ``loader.py`` and
  ``merger.py`` each import the rules that match the data they have
  on hand (parsed yaml for loader, merged tree for merger).

Adding a new rule is mechanical: write ``_verify_xxx``, define a
module-level ``_SemanticRule(code=..., apply=_verify_xxx)`` constant, and
have the relevant caller import it into its rule list. Add a
``rule_code``-asserting test in ``test_semantic.py``.

Internal submodule — never imported across packages.
"""

from __future__ import annotations

import shlex
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ac_guard.config.exceptions import ConfigValidationError, ValidationIssue

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from ac_guard.config.models import OperationRules, ResolvedConfig

__all__: list[str] = []  # package-internal — accessed via submodule path


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


def _run_rules(rules: Iterable[_SemanticRule], data: Any) -> list[ValidationIssue]:
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
# Named rule constants — caller imports the ones it cares about.
# ---------------------------------------------------------------------------


_FORMAT_LINT_SCOPE = _SemanticRule(
    code="format-lint-stage-scope",
    apply=_verify_format_lint_scope,
)
_COMMAND_SYNTAX = _SemanticRule(
    code="command-syntax",
    apply=_verify_command_syntax,
)
_TIER_CONSISTENCY = _SemanticRule(
    code="tier-consistency",
    apply=_verify_tier_consistency,
)
_PATTERN_UNIQUENESS = _SemanticRule(
    code="pattern-uniqueness",
    apply=_verify_pattern_uniqueness,
)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def validate_semantic(payload: Any, rules: Iterable[_SemanticRule]) -> None:
    """Run the given semantic rules over *payload*; raise on any issue.

    Callers (loader.py / merger.py) decide which rules apply to their
    payload by passing the rule constants they want to enforce. The
    driver itself stays oblivious to "phase" / "stage" / "raw vs
    resolved" concepts — those are caller-side strategy.

    Args:
        payload: The data each rule will inspect. For rules judging
            yaml content, pass the parsed dict (post-L1). For rules
            judging the merged tree, pass the ``ResolvedConfig``.
        rules: Iterable of rule constants to run. Issues from each
            rule are tagged with that rule's ``code`` automatically.

    Raises:
        ConfigValidationError: If any rule produces issues.
    """
    issues = _run_rules(rules, payload)
    if issues:
        raise ConfigValidationError(issues)
