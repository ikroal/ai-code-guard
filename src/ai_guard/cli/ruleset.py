"""CLI command implementations for ruleset management."""

from __future__ import annotations

from pathlib import Path

from ai_guard.ruleset.cache import clear_cache, get_cache_dir, list_cached
from ai_guard.ruleset.exceptions import (
    RulesetError,
)
from ai_guard.ruleset.fetcher import fetch_ruleset
from ai_guard.ruleset.parser import parse_ruleset_url


def ruleset_fetch_command(url: str, project_root: Path | None = None) -> None:
    """Execute ``guard ruleset fetch <url>``.

    Parses the URL, clones the ruleset into the local cache,
    validates its structure, and prints a summary.

    Args:
        url: Git URL of the ruleset, optionally with ``#version``.
        project_root: Project root directory. Defaults to cwd.
    """
    root = project_root or Path.cwd()

    try:
        ref = parse_ruleset_url(url)
    except RulesetError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None

    cache_root = get_cache_dir(root)
    version_info = f" @ {ref.version}" if ref.version else ""
    print(f"Fetching ruleset '{ref.name}'{version_info} ...")

    try:
        result_dir = fetch_ruleset(ref, cache_root)
    except RulesetError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None

    # Summarize contents
    files_count = (
        sum(1 for _ in (result_dir / "files").iterdir())
        if (result_dir / "files").is_dir()
        else 0
    )
    checks_count = (
        sum(1 for _ in (result_dir / "checks").iterdir())
        if (result_dir / "checks").is_dir()
        else 0
    )

    print(f"Cached to {result_dir.relative_to(root)}")
    print("  guard.yaml: found")
    print(f"  files/: {files_count} file(s)")
    print(f"  checks/: {checks_count} script(s)")


def ruleset_cache_clear_command(project_root: Path | None = None) -> None:
    """Execute ``guard ruleset cache clear``.

    Removes all cached rulesets and prints the count.

    Args:
        project_root: Project root directory. Defaults to cwd.
    """
    root = project_root or Path.cwd()
    count = clear_cache(root)

    if count == 0:
        print("No cached rulesets to remove.")
    else:
        print(f"Cleared {count} cached ruleset(s).")


def ruleset_list_command(project_root: Path | None = None) -> None:
    """Execute ``guard ruleset list``.

    Lists cached rulesets with basic info.

    Args:
        project_root: Project root directory. Defaults to cwd.
    """
    root = project_root or Path.cwd()
    names = list_cached(root)

    if not names:
        print("No cached rulesets.")
        return

    print(f"Cached rulesets ({len(names)}):")
    for name in names:
        print(f"  - {name}")
