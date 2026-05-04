"""CLI command implementations for ruleset management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import yaml

from ac_guard.ruleset import (
    RulesetError,
    clear_cache,
    fetch_ruleset,
    get_cache_dir,
    get_ruleset_dir,
    list_cached,
    parse_ruleset_url,
    read_meta,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "RulesetCacheClearRequest",
    "RulesetFetchRequest",
    "RulesetListRequest",
    "RulesetShowRequest",
    "ruleset_cache_clear_command",
    "ruleset_fetch_command",
    "ruleset_list_command",
    "ruleset_show_command",
]


@dataclass(frozen=True)
class RulesetFetchRequest:
    """Inputs for ``ac-guard ruleset fetch <url>``."""

    url: str
    project_root: Path


@dataclass(frozen=True)
class RulesetListRequest:
    """Inputs for ``ac-guard ruleset list``."""

    project_root: Path


@dataclass(frozen=True)
class RulesetShowRequest:
    """Inputs for ``ac-guard ruleset show <name>``."""

    name: str
    project_root: Path


@dataclass(frozen=True)
class RulesetCacheClearRequest:
    """Inputs for ``ac-guard ruleset cache clear``."""

    project_root: Path


def ruleset_fetch_command(request: RulesetFetchRequest) -> None:
    """Execute ``guard ruleset fetch <url>``.

    Parses the URL, clones the ruleset into the local cache,
    validates its structure, and prints a summary.
    """
    root = request.project_root

    try:
        ref = parse_ruleset_url(request.url)
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


def ruleset_cache_clear_command(request: RulesetCacheClearRequest) -> None:
    """Execute ``guard ruleset cache clear``.

    Removes all cached rulesets and prints the count.
    """
    count = clear_cache(request.project_root)

    if count == 0:
        print("No cached rulesets to remove.")
    else:
        print(f"Cleared {count} cached ruleset(s).")


def ruleset_list_command(request: RulesetListRequest) -> None:
    """Execute ``guard ruleset list``.

    Lists cached rulesets with name, version, and cache path.
    """
    root = request.project_root
    names = list_cached(root)

    if not names:
        print("No cached rulesets.")
        return

    cache_root = get_cache_dir(root)
    print(f"Cached rulesets ({len(names)}):")
    for name in names:
        meta = read_meta(root, name)
        version = (meta.get("version") if meta else None) or "(default branch)"
        cache_path = (cache_root / name).relative_to(root)
        print(f"  {name:<25} {version:<20} {cache_path}")


def ruleset_show_command(request: RulesetShowRequest) -> None:
    """Execute ``guard ruleset show <name>``.

    Displays ruleset metadata, behavior rules, files, and checks.
    """
    root = request.project_root
    ruleset_dir = get_ruleset_dir(root, request.name)

    if ruleset_dir is None:
        print(f"Error: Ruleset '{request.name}' not found in cache.")
        print("Run 'ac-guard ruleset fetch <url>' to download it.")
        raise SystemExit(1)

    _print_meta(root, request.name)
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
