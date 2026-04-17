"""CLI command implementations for ruleset management."""

from __future__ import annotations

from pathlib import Path

import yaml

from ac_guard.ruleset.cache import clear_cache, get_cache_dir, list_cached, read_meta
from ac_guard.ruleset.exceptions import (
    RulesetError,
)
from ac_guard.ruleset.fetcher import fetch_ruleset
from ac_guard.ruleset.models import CACHE_DIR
from ac_guard.ruleset.parser import parse_ruleset_url


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

    Lists cached rulesets with name, version, and cache path.

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
        meta = read_meta(root, name)
        version = (meta.get("version") if meta else None) or "(default branch)"
        cache_path = f"{CACHE_DIR}/{name}"
        print(f"  {name:<25} {version:<20} {cache_path}")


def ruleset_show_command(
    name: str,
    project_root: Path | None = None,
) -> None:
    """Execute ``guard ruleset show <name>``.

    Displays ruleset metadata, behavior rules, files, and checks.

    Args:
        name: Ruleset name (cache directory name).
        project_root: Project root directory. Defaults to cwd.
    """
    root = project_root or Path.cwd()
    ruleset_dir = root / CACHE_DIR / name

    if not ruleset_dir.is_dir():
        print(f"Error: Ruleset '{name}' not found in cache.")
        print("Run 'ac-guard ruleset fetch <url>' to download it.")
        raise SystemExit(1)

    _print_meta(root, name)
    _print_behavior_rules(ruleset_dir)
    _print_dir_listing(ruleset_dir / "files", "Files")
    _print_dir_listing(ruleset_dir / "checks", "Checks")


def _print_meta(root: Path, name: str) -> None:
    """Print ruleset metadata header."""
    meta = read_meta(root, name)
    print(f"Ruleset: {name}")
    if meta:
        version = meta.get("version") or "(default branch)"
        print(f"  URL:     {meta.get('url', 'unknown')}")
        print(f"  Version: {version}")
        print(f"  Fetched: {meta.get('fetched_at', 'unknown')}")
    print()


def _print_behavior_rules(ruleset_dir: Path) -> None:
    """Print behavior rules from the ruleset's guard.yaml."""
    guard_yaml = ruleset_dir / "guard.yaml"
    if not guard_yaml.is_file():
        return

    data = yaml.safe_load(guard_yaml.read_text(encoding="utf-8"))
    behavior = data.get("behavior", {}) if isinstance(data, dict) else {}
    if not behavior:
        return

    print("Behavior rules:")
    for operation, tiers in sorted(behavior.items()):
        if not isinstance(tiers, dict):
            continue
        for tier, rules in sorted(tiers.items()):
            if not isinstance(rules, list):
                continue
            for rule in rules:
                pattern = rule.get("pattern", "") if isinstance(rule, dict) else ""
                if pattern:
                    print(f"  {operation}.{tier}: {pattern}")
    print()


def _print_dir_listing(directory: Path, label: str) -> None:
    """Print a directory's file listing."""
    if not directory.is_dir():
        return
    items = sorted(f.name for f in directory.iterdir() if f.is_file())
    if not items:
        return
    print(f"{label} ({len(items)}):")
    for item in items:
        print(f"  {item}")
