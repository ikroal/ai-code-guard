"""install, update, and uninstall command implementations for AI Guard CLI.

Orchestrates config loading, adapter resolution, generator pipeline (G1-G7),
and state management to manage AI Guard artifact lifecycle.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from ai_guard.adapters.base import AgentAdapter
from ai_guard.adapters.registry import AdapterNotFoundError, get_adapter, list_adapters
from ai_guard.config.exceptions import (
    ConfigError,
)
from ai_guard.config.loader import load_config
from ai_guard.config.merger import resolve_config
from ai_guard.config.models import ResolvedConfig
from ai_guard.generator.core import (
    create_state,
    delete_artifacts,
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
from ai_guard.generator.exceptions import ArtifactWriteError
from ai_guard.generator.models import STATE_FILE

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
) -> list[str]:
    """Run G1-G7 generator primitives and write artifacts.

    Args:
        resolved_config: Fully resolved configuration.
        adapters: List of agent adapters to generate for.
        project_root: Path to project root directory.
        rulesets: List of ruleset names for tool config generation.

    Returns:
        List of written artifact paths (relative to project root).

    Raises:
        ArtifactWriteError: If file writes fail.
    """
    from ai_guard.shared.types import FileSpec

    artifacts: list[FileSpec] = []

    # G1: Rule documents
    artifacts.extend(generate_rule_docs(adapters, resolved_config.behavior))

    # G2: Hook files
    artifacts.extend(generate_hook_files(adapters, resolved_config.behavior))

    # G3: Tool configs from rulesets
    artifacts.extend(generate_tool_configs(project_root, rulesets))

    # G4: Pre-commit config
    artifacts.append(
        generate_precommit_config(resolved_config.code, resolved_config.languages)
    )

    # G5: Policy cache
    artifacts.append(
        generate_policy_cache(resolved_config.behavior, resolved_config.config_hash)
    )

    # G6: Git hooks
    git_hooks = generate_git_hooks(project_root)
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
    print("\nUsage: guard install --agent <name>[,<name>,...]")


def _print_install_summary(
    written_paths: list[str],
    agents: list[str],
) -> None:
    """Print installation summary.

    Args:
        written_paths: List of artifact paths written.
        agents: List of installed agent names.
    """
    print(f"\nAI Guard installed for: {', '.join(agents)}")
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


# ---------------------------------------------------------------------------
# Public command functions
# ---------------------------------------------------------------------------


def install_command(
    agents: list[str],
    project_root: Path,
    config_path: Path,
) -> None:
    """Execute the install command.

    Without agents, lists available agents. With agents, generates
    all artifacts and updates installation state.

    Args:
        agents: Agent names to install (empty to list available).
        project_root: Path to project root directory.
        config_path: Path to guard.yaml.
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

    # Load and resolve config
    try:
        raw_config = load_config(config_path)
        resolved = resolve_config(config_path)
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None

    rulesets: list[str] = raw_config.get("rulesets", [])

    # Read existing state for incremental install
    existing_state = read_state(project_root)
    existing_agents = existing_state.installed_agents if existing_state else []
    all_agents = _merge_agents(existing_agents, agents)

    # Resolve all adapters
    adapters = _resolve_adapters(all_agents)

    # Run generator pipeline
    try:
        written_paths = _run_generator_pipeline(
            resolved, adapters, project_root, rulesets
        )
    except ArtifactWriteError as e:
        print(f"Error: Failed to write artifacts: {', '.join(e.failed_paths)}")
        raise SystemExit(1) from None

    # Update state
    state = create_state(all_agents, resolved.config_hash, written_paths)
    write_state(project_root, state)

    _print_install_summary(written_paths, all_agents)


def update_command(
    project_root: Path,
    config_path: Path,
) -> None:
    """Execute the update command.

    Re-generates all artifacts for previously installed agents.

    Args:
        project_root: Path to project root directory.
        config_path: Path to guard.yaml.
    """
    existing_state = read_state(project_root)
    if existing_state is None:
        print("Error: AI Guard is not installed. Run 'guard install' first.")
        raise SystemExit(1)

    # Load and resolve config
    try:
        raw_config = load_config(config_path)
        resolved = resolve_config(config_path)
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None

    rulesets: list[str] = raw_config.get("rulesets", [])

    # Resolve adapters for installed agents
    try:
        adapters = _resolve_adapters(existing_state.installed_agents)
    except AdapterNotFoundError as e:
        print(f"Error: {e}")
        print("Consider reinstalling with 'guard install --agent <agents>'.")
        raise SystemExit(1) from None

    # Run generator pipeline
    try:
        written_paths = _run_generator_pipeline(
            resolved, adapters, project_root, rulesets
        )
    except ArtifactWriteError as e:
        print(f"Error: Failed to write artifacts: {', '.join(e.failed_paths)}")
        raise SystemExit(1) from None

    # Update state
    state = create_state(
        existing_state.installed_agents, resolved.config_hash, written_paths
    )
    write_state(project_root, state)

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

    # Clean up .ai-guard directory if empty
    ai_guard_dir = project_root / ".ai-guard"
    if ai_guard_dir.is_dir():
        with contextlib.suppress(OSError):
            ai_guard_dir.rmdir()  # Only removes if empty

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
