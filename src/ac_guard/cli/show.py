"""``ac-guard show`` command implementation.

Read-only inspection of the *configured* content of ``guard.yaml``,
section by section. Subsumes the previous ``validation list`` /
``validation report`` (which only saw the ``code`` section) and the
previous ``status --rules`` (which only saw the ``behavior`` section)
into a single S4-Inspection entry point that mirrors the top-level
keys of ``guard.yaml``.

Sections (``--section``) align 1:1 with ``guard.yaml`` top-level keys
to avoid the ``rules`` / ``ruleset`` lexical confusion:

- ``behavior`` → ``resolved.behavior.{read,write,execute}.{tier}`` rules
  (action_guard subsystem)
- ``code`` → ``resolved.code.<stage>.{format,lint,checks,hooks}`` gates
  (code_gate subsystem)
- ``rulesets`` → external bundle references currently merged into the
  resolved config
- ``all`` (default) → render all three sections in order

Formats (``--format``):

- ``text`` (default) — grouped, human-readable
- ``table`` — ASCII table grids (one per section); concise for code,
  available on every section for symmetry
- ``json`` — machine-readable structured dump
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ac_guard.config import ConfigError, resolve_config

if TYPE_CHECKING:
    from pathlib import Path

    from ac_guard.config import (
        CheckItem,
        OperationRules,
        PreCommitRepo,
        ResolvedConfig,
        Rule,
        StageBucket,
    )

__all__ = ["ShowRequest", "show_command"]

_VALID_SECTIONS = ("behavior", "code", "rulesets", "all")
_VALID_FORMATS = ("text", "table", "json")


@dataclass(frozen=True)
class ShowRequest:
    """Inputs for ``ac-guard show``.

    Attributes:
        section: Which top-level guard.yaml section to render
            (``behavior`` / ``code`` / ``rulesets`` / ``all``).
        config_path: Path to ``guard.yaml``.
        output_format: ``text`` / ``table`` / ``json``.
    """

    section: str
    config_path: Path
    output_format: str = "text"


def show_command(request: ShowRequest) -> None:
    """Render configured content of ``guard.yaml``."""
    if request.section not in _VALID_SECTIONS:
        print(
            f"Error: Unknown section '{request.section}'. "
            f"Available: {', '.join(_VALID_SECTIONS)}"
        )
        raise SystemExit(1)
    if request.output_format not in _VALID_FORMATS:
        print(
            f"Error: Unknown format '{request.output_format}'. "
            f"Available: {', '.join(_VALID_FORMATS)}"
        )
        raise SystemExit(1)

    resolved = _load_config(request.config_path)
    sections = (
        ("behavior", "code", "rulesets")
        if request.section == "all"
        else (request.section,)
    )

    if request.output_format == "json":
        _render_json(resolved, sections)
    else:
        _render_human(resolved, sections, request.output_format)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load_config(config_path: Path) -> ResolvedConfig:
    try:
        return resolve_config(config_path)
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _render_json(resolved: ResolvedConfig, sections: tuple[str, ...]) -> None:
    payload: dict[str, object] = {}
    if "behavior" in sections:
        payload["behavior"] = _behavior_payload(resolved)
    if "code" in sections:
        payload["code"] = _code_payload(resolved)
    if "rulesets" in sections:
        payload["rulesets"] = list(resolved.rulesets)
    print(json.dumps(payload, indent=2))


def _behavior_payload(resolved: ResolvedConfig) -> dict[str, dict[str, list[dict]]]:
    out: dict[str, dict[str, list[dict]]] = {}
    for op_name, op_rules in (
        ("read", resolved.behavior.read),
        ("write", resolved.behavior.write),
        ("execute", resolved.behavior.execute),
    ):
        out[op_name] = {
            tier: [{"pattern": r.pattern, "source": r.source} for r in rules]
            for tier, rules in _iter_tiers(op_rules)
        }
    return out


def _code_payload(resolved: ResolvedConfig) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for stage_name, bucket in resolved.code.buckets():
        if bucket.is_empty():
            continue
        out[stage_name] = {
            "format": bucket.format,
            "lint": bucket.lint,
            "checks": {
                name: {
                    "command": item.command,
                    "timeout": item.timeout,
                    "types": list(item.types) if item.types else [],
                }
                for name, item in sorted(bucket.checks.items())
            },
            "hooks": [
                {
                    "repo": repo.repo,
                    "rev": repo.rev,
                    "hooks": [hook.id for hook in repo.hooks],
                }
                for repo in bucket.hooks
            ],
        }
    return out


# ---------------------------------------------------------------------------
# Text / table (section dispatch)
# ---------------------------------------------------------------------------


def _render_human(
    resolved: ResolvedConfig, sections: tuple[str, ...], output_format: str
) -> None:
    first = True
    for name in sections:
        if not first:
            print()
        first = False
        if name == "behavior":
            _render_behavior(resolved, output_format)
        elif name == "code":
            _render_code(resolved, output_format)
        elif name == "rulesets":
            _render_rulesets(resolved, output_format)


# ---------------------------------------------------------------------------
# Behavior section
# ---------------------------------------------------------------------------


def _render_behavior(resolved: ResolvedConfig, output_format: str) -> None:
    rows: list[tuple[str, str, str, str]] = []
    for op_name, op_rules in (
        ("read", resolved.behavior.read),
        ("write", resolved.behavior.write),
        ("execute", resolved.behavior.execute),
    ):
        for tier, rules in _iter_tiers(op_rules):
            rows.extend((op_name, tier, rule.pattern, rule.source) for rule in rules)

    print("Behavior rules")
    if not rows:
        print("  (no behavior rules configured)")
        return

    if output_format == "table":
        _print_table(("Operation", "Tier", "Pattern", "Source"), rows)
        return

    # text
    for op, tier, pattern, source in rows:
        print(f"  {op}.{tier}: {pattern} [{source}]")


def _iter_tiers(op_rules: OperationRules) -> list[tuple[str, list[Rule]]]:
    return [
        ("forbidden", op_rules.forbidden),
        ("require_approval", op_rules.require_approval),
        ("allow", op_rules.allow),
    ]


# ---------------------------------------------------------------------------
# Code section
# ---------------------------------------------------------------------------


def _render_code(resolved: ResolvedConfig, output_format: str) -> None:
    print("Code gates")
    buckets = [
        (stage_name, bucket)
        for stage_name, bucket in resolved.code.buckets()
        if not bucket.is_empty()
    ]
    if not buckets:
        print("  (no code gates configured)")
        return

    if output_format == "table":
        rows = _flatten_code_rows(buckets)
        _print_table(("Name", "Stage", "Type", "Command", "Timeout", "Types"), rows)
        return

    # text — per-stage grouped (ex-`validation list` shape)
    first = True
    for stage_name, bucket in buckets:
        if not first:
            print()
        first = False
        print(f"  {stage_name} stage:")
        if bucket.format:
            print(f"    [builtin]  {'format':<15} (enabled)")
        if bucket.lint:
            print(f"    [builtin]  {'lint':<15} (enabled)")
        for name, item in sorted(bucket.checks.items()):
            print(f"    [custom]   {name:<15} {item.command}")
        for repo in bucket.hooks:
            label = f"{repo.repo}@{repo.rev}" if repo.rev else repo.repo
            for hook in repo.hooks:
                print(f"    [external] {hook.id:<15} ({label})")


def _flatten_code_rows(
    buckets: list[tuple[str, StageBucket]],
) -> list[tuple[str, str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str, str]] = []
    for stage_name, bucket in buckets:
        if bucket.format:
            rows.append(("format", stage_name, "builtin", "-", "-", "-"))
        if bucket.lint:
            rows.append(("lint", stage_name, "builtin", "-", "-", "-"))
        for name, item in sorted(bucket.checks.items()):
            rows.append(_check_row(name, stage_name, item))
        for repo in bucket.hooks:
            rows.extend(
                _external_row(stage_name, repo, hook_id)
                for hook_id in (h.id for h in repo.hooks)
            )
    return rows


def _check_row(
    name: str, stage: str, item: CheckItem
) -> tuple[str, str, str, str, str, str]:
    timeout = f"{item.timeout}s" if item.timeout else "-"
    types = ", ".join(item.types) if item.types else "-"
    return (name, stage, "custom", item.command, timeout, types)


def _external_row(
    stage: str, repo: PreCommitRepo, hook_id: str
) -> tuple[str, str, str, str, str, str]:
    return (
        hook_id,
        stage,
        "external",
        f"{repo.repo}@{repo.rev or 'local'}",
        "-",
        "-",
    )


# ---------------------------------------------------------------------------
# Rulesets section
# ---------------------------------------------------------------------------


def _render_rulesets(resolved: ResolvedConfig, output_format: str) -> None:
    print("Rulesets")
    rulesets = list(resolved.rulesets)
    if not rulesets:
        print("  (no rulesets referenced)")
        return

    if output_format == "table":
        rows = [(name,) for name in rulesets]
        _print_table(("Name",), rows)
        return

    # text
    for name in rulesets:
        print(f"  {name}")


# ---------------------------------------------------------------------------
# Generic table renderer
# ---------------------------------------------------------------------------


def _print_table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    if not rows:
        return
    widths = [
        max(len(header[i]), *(len(row[i]) for row in rows)) + 2
        for i in range(len(header))
    ]
    print("-" * sum(widths))
    print("".join(h.ljust(w) for h, w in zip(header, widths, strict=True)))
    print("-" * sum(widths))
    for row in rows:
        print("".join(val.ljust(w) for val, w in zip(row, widths, strict=True)))
