"""Validation list and report command implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_guard.config.exceptions import ConfigError
from ai_guard.config.merger import resolve_config

if TYPE_CHECKING:
    from pathlib import Path

    from ai_guard.config.models import CheckItem

__all__ = ["validation_list_command", "validation_report_command"]


def validation_list_command(config_path: Path) -> None:
    """Execute ``guard validation list``.

    Lists all configured checks grouped by stage (commit/push),
    showing builtin checks and custom check commands.

    Args:
        config_path: Path to guard.yaml.
    """
    code = _load_code_config(config_path)

    print("Commit stage:")
    _print_builtin("format", code.commit_format)
    _print_builtin("naming", code.commit_naming)
    for name, item in sorted(code.commit_checks.items()):
        _print_custom(name, item)

    print("\nPush stage:")
    _print_builtin("lint", code.push_lint)
    for name, item in sorted(code.push_checks.items()):
        _print_custom(name, item)


def validation_report_command(config_path: Path) -> None:
    """Execute ``guard validation report``.

    Generates a formatted table showing all check configurations
    with name, stage, type, command, timeout, and file types.

    Args:
        config_path: Path to guard.yaml.
    """
    code = _load_code_config(config_path)

    rows: list[tuple[str, str, str, str, str, str]] = []

    # Commit stage
    if code.commit_format:
        rows.append(("format", "commit", "builtin", "-", "-", "-"))
    if code.commit_naming:
        rows.append(("naming", "commit", "builtin", "-", "-", "-"))
    for name, item in sorted(code.commit_checks.items()):
        rows.append(_check_row(name, "commit", item))

    # Push stage
    if code.push_lint:
        rows.append(("lint", "push", "builtin", "-", "-", "-"))
    for name, item in sorted(code.push_checks.items()):
        rows.append(_check_row(name, "push", item))

    # Print table
    header = ("Name", "Stage", "Type", "Command", "Timeout", "Types")
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


def _load_code_config(config_path: Path):
    """Load and return the CodeConfig from guard.yaml.

    Args:
        config_path: Path to guard.yaml.

    Returns:
        CodeConfig instance.
    """
    try:
        resolved = resolve_config(config_path)
        return resolved.code
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None


def _print_builtin(name: str, enabled: bool) -> None:
    """Print a builtin check entry for list output."""
    status = "enabled" if enabled else "disabled"
    print(f"  [builtin] {name:<15} ({status})")


def _print_custom(name: str, item: CheckItem) -> None:
    """Print a custom check entry for list output."""
    print(f"  [custom]  {name:<15} {item.command}")


def _check_row(
    name: str, stage: str, item: CheckItem
) -> tuple[str, str, str, str, str, str]:
    """Build a table row for a custom check item."""
    timeout = f"{item.timeout}s" if item.timeout else "-"
    types = ", ".join(item.types) if item.types else "-"
    return (name, stage, "custom", item.command, timeout, types)
