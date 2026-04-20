"""Validation list and report command implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.config.exceptions import ConfigError
from ac_guard.config.merger import resolve_config

if TYPE_CHECKING:
    from pathlib import Path

    from ac_guard.config.models import CheckItem, CodeConfig

__all__ = ["validation_list_command", "validation_report_command"]


def validation_list_command(config_path: Path) -> None:
    """Execute ``guard validation list``.

    Lists all configured checks grouped by pre-commit gating stage,
    showing builtin toggles (format / lint) and custom check commands.

    Args:
        config_path: Path to guard.yaml.
    """
    code = _load_code_config(config_path)
    first = True
    for stage_name, bucket in code.buckets():
        if bucket.is_empty():
            continue
        if not first:
            print()
        first = False
        print(f"{stage_name} stage:")
        if bucket.format:
            _print_builtin("format", True)
        if bucket.lint:
            _print_builtin("lint", True)
        for name, item in sorted(bucket.checks.items()):
            _print_custom(name, item)
        for repo in bucket.hooks:
            _print_external(repo)
    if first:
        # No active buckets at all — still tell the user something.
        print("No checks configured.")


def validation_report_command(config_path: Path) -> None:
    """Execute ``guard validation report``.

    Generates a formatted table of every configured check grouped by
    stage (name / stage / type / command / timeout / types).

    Args:
        config_path: Path to guard.yaml.
    """
    code = _load_code_config(config_path)
    rows: list[tuple[str, str, str, str, str, str]] = []

    for stage_name, bucket in code.buckets():
        if bucket.format:
            rows.append(("format", stage_name, "builtin", "-", "-", "-"))
        if bucket.lint:
            rows.append(("lint", stage_name, "builtin", "-", "-", "-"))
        for name, item in sorted(bucket.checks.items()):
            rows.append(_check_row(name, stage_name, item))
        for repo in bucket.hooks:
            rows.extend(
                (
                    hook.id,
                    stage_name,
                    "external",
                    f"{repo.repo}@{repo.rev or 'local'}",
                    "-",
                    "-",
                )
                for hook in repo.hooks
            )

    header = ("Name", "Stage", "Type", "Command", "Timeout", "Types")
    if not rows:
        print("Check Configuration Report")
        print("(no checks configured)")
        return
    widths = [
        max(len(header[i]), *(len(row[i]) for row in rows)) + 2
        for i in range(len(header))
    ]

    print("Check Configuration Report")
    print("-" * sum(widths))
    print("".join(h.ljust(w) for h, w in zip(header, widths, strict=True)))
    print("-" * sum(widths))
    for row in rows:
        print("".join(val.ljust(w) for val, w in zip(row, widths, strict=True)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_code_config(config_path: Path) -> CodeConfig:
    """Load and return the CodeConfig from guard.yaml."""
    try:
        resolved = resolve_config(config_path)
        return resolved.code
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None


def _print_builtin(name: str, enabled: bool) -> None:
    """Print a builtin check entry for list output."""
    status = "enabled" if enabled else "disabled"
    print(f"  [builtin]  {name:<15} ({status})")


def _print_custom(name: str, item: CheckItem) -> None:
    """Print a custom check entry for list output."""
    print(f"  [custom]   {name:<15} {item.command}")


def _print_external(repo) -> None:
    """Print an external pre-commit repo + its hook ids."""
    label = f"{repo.repo}@{repo.rev}" if repo.rev else repo.repo
    for hook in repo.hooks:
        print(f"  [external] {hook.id:<15} ({label})")


def _check_row(
    name: str, stage: str, item: CheckItem
) -> tuple[str, str, str, str, str, str]:
    """Build a table row for a custom check item."""
    timeout = f"{item.timeout}s" if item.timeout else "-"
    types = ", ".join(item.types) if item.types else "-"
    return (name, stage, "custom", item.command, timeout, types)
