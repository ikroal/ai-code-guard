"""install, update, and uninstall command implementations for AI Code Guard CLI.

Orchestrates config loading, adapter resolution, generator pipeline (G1-G7),
and state management to manage AI Code Guard artifact lifecycle.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ac_guard.adapters.registry import AdapterNotFoundError, get_adapter, list_adapters
from ac_guard.audit import prune_by_age
from ac_guard.config import (
    ConfigError,
    resolve_config,
)
from ac_guard.generator import (
    ArtifactWriteError,
    create_installation,
    delete_artifacts,
    delete_installation,
    generate_all,
    installation_path,
    read_installation,
    write_artifacts,
    write_installation,
)
from ac_guard.ruleset import load_ruleset_config

_LEGACY_RUNTIME_CACHE = ".ac-guard/policy.json"

if TYPE_CHECKING:
    from pathlib import Path

    from ac_guard.adapters.base import AgentAdapter
    from ac_guard.config import ResolvedConfig

__all__ = [
    "InstallRequest",
    "UninstallRequest",
    "UpdateRequest",
    "install_command",
    "uninstall_command",
    "update_command",
]


@dataclass(frozen=True)
class InstallRequest:
    """Inputs that drive a single ``ac-guard install`` invocation.

    Attributes:
        agents: Agent names to install (empty = list available, no-op install).
        project_root: Project root directory.
        config_path: Path to ``guard.yaml``.
        force: Overwrite existing tool config files materialised from rulesets.
    """

    agents: list[str]
    project_root: Path
    config_path: Path
    force: bool = False


@dataclass(frozen=True)
class UpdateRequest:
    """Inputs that drive a single ``ac-guard update`` invocation."""

    project_root: Path
    config_path: Path
    force: bool = False


@dataclass(frozen=True)
class UninstallRequest:
    """Inputs that drive a single ``ac-guard uninstall`` invocation."""

    project_root: Path
    keep_config: bool = False


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
    artifacts = generate_all(project_root, resolved_config, adapters, force=force)
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
) -> list[tuple[str, dict[str, Any]]]:
    """Load guard.yaml from each cached ruleset.

    For each ruleset name in the project config, delegates content
    access to :func:`ac_guard.ruleset.load_ruleset_config`. Warns (but
    does not fail) if a ruleset has no usable cached ``guard.yaml`` —
    either because the ruleset is not cached or because the cached
    file is missing/unparseable.

    Ruleset guard.yaml files are config fragments (they may lack
    ``version`` and ``project`` fields); schema validation is
    deferred to the merger.

    Args:
        project_root: Path to the project root.
        rulesets: List of ruleset names from the project config.

    Returns:
        List of ``(name, raw_config)`` pairs for rulesets that
        have a usable cached ``guard.yaml``.
    """
    pairs: list[tuple[str, dict[str, Any]]] = []
    for name in rulesets:
        data = load_ruleset_config(project_root, name)
        if data is not None:
            pairs.append((name, data))
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


def install_command(request: InstallRequest) -> None:
    """Execute the install command.

    Without agents, lists available agents. With agents, generates
    all artifacts and updates installation state.
    """
    if not request.agents:
        _print_available_agents()
        return

    agents = [a.strip().lower() for a in request.agents if a.strip()]

    available = list_adapters()
    unknown = [name for name in agents if name not in available]
    if unknown:
        print(
            f"Error: Unknown agent(s): {', '.join(unknown)}. "
            f"Available: {', '.join(available)}"
        )
        raise SystemExit(1)

    try:
        resolved = resolve_config(
            request.config_path,
            fetch_rulesets=lambda names: _load_ruleset_configs(
                request.project_root, names
            ),
        )
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None

    existing_state = read_installation(request.project_root)
    existing_agents = existing_state.installed_agents if existing_state else []
    all_agents = _merge_agents(existing_agents, agents)

    adapters = _resolve_adapters(all_agents)

    try:
        written_paths = _run_generator_pipeline(
            resolved,
            adapters,
            request.project_root,
            resolved.rulesets,
            force=request.force,
        )
    except ArtifactWriteError as e:
        print(f"Error: Failed to write artifacts: {', '.join(e.failed_paths)}")
        raise SystemExit(1) from None

    state = create_installation(all_agents, resolved.config_hash, written_paths)
    write_installation(request.project_root, state)

    _run_post_install_audit_maintenance(request.project_root, resolved)

    _print_install_summary(written_paths, all_agents)


def update_command(request: UpdateRequest) -> None:
    """Execute the update command.

    Re-generates all artifacts for previously installed agents.
    """
    existing_state = read_installation(request.project_root)
    if existing_state is None:
        print("Error: AI Code Guard is not installed. Run 'ac-guard install' first.")
        raise SystemExit(1)

    try:
        resolved = resolve_config(
            request.config_path,
            fetch_rulesets=lambda names: _load_ruleset_configs(
                request.project_root, names
            ),
        )
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None

    try:
        adapters = _resolve_adapters(existing_state.installed_agents)
    except AdapterNotFoundError as e:
        print(f"Error: {e}")
        print("Consider reinstalling with 'ac-guard install --agent <agents>'.")
        raise SystemExit(1) from None

    try:
        written_paths = _run_generator_pipeline(
            resolved,
            adapters,
            request.project_root,
            resolved.rulesets,
            force=request.force,
        )
    except ArtifactWriteError as e:
        print(f"Error: Failed to write artifacts: {', '.join(e.failed_paths)}")
        raise SystemExit(1) from None

    state = create_installation(
        existing_state.installed_agents, resolved.config_hash, written_paths
    )
    write_installation(request.project_root, state)

    _run_post_install_audit_maintenance(request.project_root, resolved)

    agents_str = ", ".join(existing_state.installed_agents)
    print(f"Updated {len(written_paths)} artifact(s) for agents: {agents_str}")


def uninstall_command(request: UninstallRequest) -> None:
    """Execute the uninstall command.

    Deletes all generated artifacts and state file.
    """
    existing_state = read_installation(request.project_root)
    if existing_state is None:
        print("Nothing to uninstall.")
        return

    deleted = delete_artifacts(request.project_root, existing_state.artifacts)

    if delete_installation(request.project_root):
        deleted.append(
            str(
                installation_path(request.project_root).relative_to(
                    request.project_root
                )
            )
        )

    ac_guard_dir = request.project_root / ".ac-guard"
    if ac_guard_dir.is_dir():
        with contextlib.suppress(OSError):
            ac_guard_dir.rmdir()  # Only removes if empty

    if not request.keep_config:
        config_path = request.project_root / "guard.yaml"
        if config_path.is_file():
            config_path.unlink()
            deleted.append("guard.yaml")

    not_deleted = set(existing_state.artifacts) - set(deleted)

    print(f"Uninstalled. Removed {len(deleted)} file(s).")
    if not_deleted:
        print("Warning: Could not delete:")
        for path in sorted(not_deleted):
            print(f"  {path}")
