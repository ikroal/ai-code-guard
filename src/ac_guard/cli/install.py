"""install, update, and uninstall command implementations for AI Code Guard CLI.

Orchestrates config loading, adapter resolution, generator pipeline (G1-G7),
and state management to manage AI Code Guard artifact lifecycle.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import yaml

from ac_guard.adapters.registry import AdapterNotFoundError, get_adapter, list_adapters
from ac_guard.audit import prune_by_age
from ac_guard.config import (
    ConfigError,
    RawConfig,
    load_config,
    resolve_config,
)
from ac_guard.generator.core import (
    create_state,
    delete_artifacts,
    generate_check_scripts,
    generate_git_hooks,
    generate_hook_files,
    generate_policy_cache,
    generate_precommit_config,
    generate_rule_docs,
    generate_tool_configs,
    read_state,
    write_artifacts,
    write_state,
)
from ac_guard.generator.exceptions import ArtifactWriteError
from ac_guard.generator.models import STATE_FILE
from ac_guard.ruleset.cache import get_cache_dir

_LEGACY_RUNTIME_CACHE = ".ac-guard/policy.json"

if TYPE_CHECKING:
    from pathlib import Path

    from ac_guard.adapters.base import AgentAdapter
    from ac_guard.config import ResolvedConfig
    from ac_guard.domain import FileSpec

__all__ = ["install_command", "update_command", "uninstall_command"]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_adapters(agent_names: list[str]) -> list[AgentAdapter]:
    """Resolve agent names to adapter instances.

    Args:
        agent_names: List of agent identifiers.

    Returns:
        List of AgentAdapter instances.

    Raises:
        AdapterNotFoundError: If any name is not registered.
    """
    return [get_adapter(name) for name in agent_names]


def _run_generator_pipeline(
    resolved_config: ResolvedConfig,
    adapters: list[AgentAdapter],
    project_root: Path,
    rulesets: list[str],
    *,
    force: bool = False,
) -> list[str]:
    """Run G1-G7 generator primitives and write artifacts.

    Args:
        resolved_config: Fully resolved configuration.
        adapters: List of agent adapters to generate for.
        project_root: Path to project root directory.
        rulesets: List of ruleset names for tool config generation.
        force: If True, overwrite existing tool config files.

    Returns:
        List of written artifact paths (relative to project root).

    Raises:
        ArtifactWriteError: If file writes fail.
    """

    artifacts: list[FileSpec] = []

    # G1: Rule documents
    artifacts.extend(generate_rule_docs(adapters, resolved_config.behavior))

    # G2: Hook files
    artifacts.extend(generate_hook_files(adapters, resolved_config.behavior))

    # G3: Tool configs from rulesets (skip existing unless --force)
    artifacts.extend(generate_tool_configs(project_root, rulesets, force=force))

    # G3b: Check scripts from rulesets (always overwrite)
    artifacts.extend(generate_check_scripts(project_root, rulesets))

    # G4: Pre-commit config
    artifacts.append(
        generate_precommit_config(
            resolved_config.code,
            resolved_config.languages,
            resolved_config.pre_commit_meta,
        )
    )

    # G5: Policy cache (runtime.json — behavior + audit config)
    artifacts.append(
        generate_policy_cache(
            resolved_config.behavior,
            resolved_config.config_hash,
            audit=resolved_config.output.audit,
        )
    )

    # G6: Git hooks
    git_hooks = generate_git_hooks(project_root, resolved_config.code)
    if not git_hooks:
        print("Warning: .git directory not found. Git hooks were not installed.")
    artifacts.extend(git_hooks)

    # G7: Write all artifacts to disk
    return write_artifacts(project_root, artifacts)


def _print_available_agents() -> None:
    """Print list of available agents with capabilities."""
    print("Available agents:")
    for name in list_adapters():
        adapter = get_adapter(name)
        caps = adapter.capabilities
        cap_desc = []
        if caps.can_block:
            cap_desc.append("can block")
        if caps.can_ask:
            cap_desc.append("can ask")
        if not cap_desc:
            cap_desc.append("rule docs only")
        print(f"  {name:<15} ({' + '.join(cap_desc)})")
    print("\nUsage: ac-guard install --agent <name>[,<name>,...]")


def _print_install_summary(
    written_paths: list[str],
    agents: list[str],
) -> None:
    """Print installation summary.

    Args:
        written_paths: List of artifact paths written.
        agents: List of installed agent names.
    """
    print(f"\nAI Code Guard installed for: {', '.join(agents)}")
    print(f"\nGenerated {len(written_paths)} artifact(s):")
    for path in sorted(written_paths):
        print(f"  {path}")


def _merge_agents(existing: list[str], new: list[str]) -> list[str]:
    """Merge new agents into existing list, preserving order and deduplicating.

    Args:
        existing: Previously installed agent names.
        new: New agent names to add.

    Returns:
        Merged list with no duplicates.
    """
    seen = set(existing)
    merged = list(existing)
    for name in new:
        if name not in seen:
            merged.append(name)
            seen.add(name)
    return merged


def _load_ruleset_configs(
    project_root: Path,
    rulesets: list[str],
) -> list[tuple[str, RawConfig]]:
    """Load guard.yaml from each cached ruleset.

    For each ruleset name listed in the project config, looks for
    a cached copy under ``.ac-guard/cache/<name>/guard.yaml``.
    Warns (but does not fail) if a ruleset is not cached.

    Ruleset guard.yaml files are config fragments (they may lack
    ``version`` and ``project`` fields), so they are loaded without
    schema validation — the merger handles partial configs.

    Args:
        project_root: Path to the project root.
        rulesets: List of ruleset names from the project config.

    Returns:
        List of ``(name, raw_config)`` pairs for rulesets that
        have a cached ``guard.yaml``.
    """
    if not rulesets:
        return []

    cache_dir = get_cache_dir(project_root)
    pairs: list[tuple[str, RawConfig]] = []

    for name in rulesets:
        rs_config_path = cache_dir / name / "guard.yaml"
        if rs_config_path.is_file():
            with open(rs_config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                pairs.append((name, data))  # type: ignore[arg-type]
        else:
            print(
                f"Warning: Ruleset '{name}' not cached. Run: ac-guard ruleset fetch <url>"
            )

    return pairs


# ---------------------------------------------------------------------------
# Public command functions
# ---------------------------------------------------------------------------


def _run_post_install_audit_maintenance(
    project_root: Path, resolved: ResolvedConfig
) -> None:
    """Clean up legacy artifacts and apply audit retention.

    Idempotent; safe to call at the end of both install and update.
    Silent on I/O failure so it never blocks the pipeline.
    """
    # One-time removal of the legacy `.ac-guard/policy.json` (renamed to
    # runtime.json in v0.1.0). No-op once the file is gone.
    legacy = project_root / _LEGACY_RUNTIME_CACHE
    with contextlib.suppress(OSError):
        if legacy.is_file():
            legacy.unlink()

    audit_cfg = resolved.output.audit
    if audit_cfg.enabled and audit_cfg.retention > 0:
        prune_by_age(
            project_root,
            audit_cfg.path,
            max_age_days=audit_cfg.retention,
        )


def install_command(
    agents: list[str],
    project_root: Path,
    config_path: Path,
    *,
    force: bool = False,
) -> None:
    """Execute the install command.

    Without agents, lists available agents. With agents, generates
    all artifacts and updates installation state.

    Args:
        agents: Agent names to install (empty to list available).
        project_root: Path to project root directory.
        config_path: Path to guard.yaml.
        force: If True, overwrite existing tool config files.
    """
    if not agents:
        _print_available_agents()
        return

    # Normalize agent names
    agents = [a.strip().lower() for a in agents if a.strip()]

    # Validate all agent names first
    available = list_adapters()
    unknown = [name for name in agents if name not in available]
    if unknown:
        print(
            f"Error: Unknown agent(s): {', '.join(unknown)}. "
            f"Available: {', '.join(available)}"
        )
        raise SystemExit(1)

    # Load and resolve config (with ruleset configs from cache)
    try:
        raw_config = load_config(config_path)
        rulesets: list[str] = raw_config.get("rulesets", [])
        ruleset_pairs = _load_ruleset_configs(project_root, rulesets)
        resolved = resolve_config(config_path, rulesets=ruleset_pairs)
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None

    # Read existing state for incremental install
    existing_state = read_state(project_root)
    existing_agents = existing_state.installed_agents if existing_state else []
    all_agents = _merge_agents(existing_agents, agents)

    # Resolve all adapters
    adapters = _resolve_adapters(all_agents)

    # Run generator pipeline
    try:
        written_paths = _run_generator_pipeline(
            resolved, adapters, project_root, rulesets, force=force
        )
    except ArtifactWriteError as e:
        print(f"Error: Failed to write artifacts: {', '.join(e.failed_paths)}")
        raise SystemExit(1) from None

    # Update state
    state = create_state(all_agents, resolved.config_hash, written_paths)
    write_state(project_root, state)

    _run_post_install_audit_maintenance(project_root, resolved)

    _print_install_summary(written_paths, all_agents)


def update_command(
    project_root: Path,
    config_path: Path,
    *,
    force: bool = False,
) -> None:
    """Execute the update command.

    Re-generates all artifacts for previously installed agents.

    Args:
        project_root: Path to project root directory.
        config_path: Path to guard.yaml.
        force: If True, overwrite existing tool config files.
    """
    existing_state = read_state(project_root)
    if existing_state is None:
        print("Error: AI Code Guard is not installed. Run 'ac-guard install' first.")
        raise SystemExit(1)

    # Load and resolve config (with ruleset configs from cache)
    try:
        raw_config = load_config(config_path)
        rulesets: list[str] = raw_config.get("rulesets", [])
        ruleset_pairs = _load_ruleset_configs(project_root, rulesets)
        resolved = resolve_config(config_path, rulesets=ruleset_pairs)
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None

    # Resolve adapters for installed agents
    try:
        adapters = _resolve_adapters(existing_state.installed_agents)
    except AdapterNotFoundError as e:
        print(f"Error: {e}")
        print("Consider reinstalling with 'ac-guard install --agent <agents>'.")
        raise SystemExit(1) from None

    # Run generator pipeline
    try:
        written_paths = _run_generator_pipeline(
            resolved, adapters, project_root, rulesets, force=force
        )
    except ArtifactWriteError as e:
        print(f"Error: Failed to write artifacts: {', '.join(e.failed_paths)}")
        raise SystemExit(1) from None

    # Update state
    state = create_state(
        existing_state.installed_agents, resolved.config_hash, written_paths
    )
    write_state(project_root, state)

    _run_post_install_audit_maintenance(project_root, resolved)

    agents_str = ", ".join(existing_state.installed_agents)
    print(f"Updated {len(written_paths)} artifact(s) for agents: {agents_str}")


def uninstall_command(
    project_root: Path,
    keep_config: bool,
) -> None:
    """Execute the uninstall command.

    Deletes all generated artifacts and state file.

    Args:
        project_root: Path to project root directory.
        keep_config: If True, preserves guard.yaml.
    """
    existing_state = read_state(project_root)
    if existing_state is None:
        print("Nothing to uninstall.")
        return

    # Delete artifacts tracked in state
    deleted = delete_artifacts(project_root, existing_state.artifacts)

    # Delete state.json
    state_path = project_root / STATE_FILE
    if state_path.is_file():
        state_path.unlink()
        deleted.append(STATE_FILE)

    # Clean up .ac-guard directory if empty
    ac_guard_dir = project_root / ".ac-guard"
    if ac_guard_dir.is_dir():
        with contextlib.suppress(OSError):
            ac_guard_dir.rmdir()  # Only removes if empty

    # Delete guard.yaml unless --keep-config
    if not keep_config:
        config_path = project_root / "guard.yaml"
        if config_path.is_file():
            config_path.unlink()
            deleted.append("guard.yaml")

    not_deleted = set(existing_state.artifacts) - set(deleted)

    print(f"Uninstalled. Removed {len(deleted)} file(s).")
    if not_deleted:
        print("Warning: Could not delete:")
        for path in sorted(not_deleted):
            print(f"  {path}")
