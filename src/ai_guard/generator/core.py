"""Generator core functions for AI Guard.

Implements G1-G7 primitives for artifact generation:
- G1: generate_rule_docs - Agent-specific rule documents
- G2: generate_hook_files - Agent-specific Hook scripts
- G3-G6: Agent-agnostic artifacts (WP1.3c)
- G7: write_artifacts - Write all artifacts to disk

Managed block markers and wrap_with_managed_block are defined in
shared.types (shared across modules).
"""

from __future__ import annotations

import json
import stat
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

from ai_guard import __version__
from ai_guard.generator.exceptions import ArtifactWriteError
from ai_guard.generator.models import STATE_FILE, GeneratedState
from ai_guard.shared.types import (
    MARKER_BEGIN,
    MARKER_END,
    FileSpec,
    wrap_with_managed_block,
)

if TYPE_CHECKING:
    from ai_guard.adapters.base import AgentAdapter
    from ai_guard.config.models import (
        BehaviorConfig,
        CodeConfig,
        LanguageTools,
        OperationRules,
        Rule,
    )

__all__ = [
    # G1/G2 primitives
    "generate_rule_docs",
    "generate_hook_files",
    # G3-G6 primitives
    "generate_policy_cache",
    "generate_git_hooks",
    "generate_tool_configs",
    "generate_precommit_config",
    # State management
    "read_state",
    "write_state",
    "create_state",
    # Managed block handling
    "replace_managed_block",
    "wrap_with_managed_block",
    # Artifact writing (G7)
    "write_artifacts",
    "delete_artifacts",
]


# ---------------------------------------------------------------------------
# Jinja2 Environment for Generator Templates
# ---------------------------------------------------------------------------

# Template directory for Generator (internal/private)
_GENERATOR_TEMPLATE_DIR = Path(__file__).parent / "_templates"

# Jinja2 environment (singleton)
_generator_env: Environment | None = None


def _get_generator_env() -> Environment:
    """Get or create Generator's Jinja2 environment."""
    global _generator_env
    if _generator_env is None:
        _generator_env = Environment(
            loader=FileSystemLoader(_GENERATOR_TEMPLATE_DIR),
            autoescape=False,  # YAML/shell scripts don't need HTML escaping
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _generator_env


# ---------------------------------------------------------------------------
# G1/G2 Primitives: Agent-specific artifact generation
# ---------------------------------------------------------------------------


def generate_rule_docs(
    adapters: list[AgentAdapter],
    behavior: BehaviorConfig,
) -> list[FileSpec]:
    """Generate rule documents for all specified agents (G1).

    Calls each adapter's render_rule_doc method to produce
    Agent-specific rule document content, wrapped with managed
    block markers.

    Args:
        adapters: List of AgentAdapter instances.
        behavior: BehaviorConfig containing read/write/execute rules.

    Returns:
        List of FileSpec objects for rule documents.
    """
    artifacts: list[FileSpec] = []
    for adapter in adapters:
        content = adapter.render_rule_doc(behavior)
        artifacts.append(
            FileSpec(
                path=adapter.rule_doc_path(),
                content=content,
            )
        )
    return artifacts


def generate_hook_files(
    adapters: list[AgentAdapter],
    behavior: BehaviorConfig,
) -> list[FileSpec]:
    """Generate Hook scripts for agents with Hook capability (G2).

    Only adapters with can_block=True produce Hook files.
    Calls each adapter's hook_files method to produce Agent-specific
    Hook script content.

    Args:
        adapters: List of AgentAdapter instances.
        behavior: BehaviorConfig (Hook scripts may embed rules or
            reference policy.json).

    Returns:
        List of FileSpec objects for Hook scripts and configs.
    """
    artifacts: list[FileSpec] = []
    for adapter in adapters:
        if adapter.capabilities.can_block:
            artifacts.extend(adapter.hook_files(behavior))
    return artifacts


# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------


def read_state(project_root: Path) -> GeneratedState | None:
    """Read installation state from .ai-guard/state.json.

    Args:
        project_root: Path to the project root directory.

    Returns:
        GeneratedState if state.json exists, None otherwise.
    """
    state_path = project_root / STATE_FILE
    if not state_path.is_file():
        return None
    content = state_path.read_text(encoding="utf-8")
    return GeneratedState.from_json(content)


def write_state(project_root: Path, state: GeneratedState) -> None:
    """Write installation state to .ai-guard/state.json.

    Creates the .ai-guard/ directory if it doesn't exist.

    Args:
        project_root: Path to the project root directory.
        state: The GeneratedState to write.
    """
    state_path = project_root / STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state.to_json(), encoding="utf-8")


def create_state(
    installed_agents: list[str],
    config_hash: str,
    artifacts: list[str],
) -> GeneratedState:
    """Create a new GeneratedState with current tool version.

    Args:
        installed_agents: List of agent identifiers being installed.
        config_hash: Hash of the guard.yaml configuration.
        artifacts: List of generated artifact paths.

    Returns:
        A new GeneratedState instance.
    """
    return GeneratedState(
        ai_guard_version=__version__,
        installed_agents=installed_agents,
        config_hash=config_hash,
        installed_at=datetime.now(),
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# Managed Block Handling
# ---------------------------------------------------------------------------
# Note: wrap_with_managed_block and MARKER constants are imported from
# adapters.base - they are shared types used by both modules.


def replace_managed_block(existing_content: str, new_content: str) -> str:
    """Replace content within managed block markers.

    If markers exist in existing_content, replaces the content between
    them. If markers don't exist, wraps new_content with markers and
    appends to existing content.

    Args:
        existing_content: The existing file content.
        new_content: The new managed content to insert.

    Returns:
        Updated content with managed block replaced or appended.
    """
    begin_idx = existing_content.find(MARKER_BEGIN)
    end_idx = existing_content.find(MARKER_END)

    if begin_idx == -1 or end_idx == -1 or begin_idx > end_idx:
        # Markers not found or malformed — wrap and append
        wrapped = wrap_with_managed_block(new_content)
        if existing_content.strip():
            # Ensure separation from existing content
            if not existing_content.endswith("\n"):
                existing_content += "\n"
            return existing_content + wrapped
        return wrapped

    # Markers found — replace content between them
    # Preserve content before BEGIN and after END
    before = existing_content[:begin_idx]
    after = existing_content[end_idx + len(MARKER_END) :]

    # Ensure proper line breaks
    if before and not before.endswith("\n"):
        before += "\n"
    if after and not after.startswith("\n"):
        after = "\n" + after

    return f"{before}{MARKER_BEGIN}\n{new_content}\n{MARKER_END}{after}"


# ---------------------------------------------------------------------------
# Artifact Writing (G7)
# ---------------------------------------------------------------------------


def write_artifacts(  # noqa: C901
    project_root: Path,
    artifacts: list[FileSpec],
    *,
    dry_run: bool = False,
) -> list[str]:
    """Write all artifacts to disk (G7 primitive).

    For each artifact:
    - Creates parent directories if needed
    - Handles managed blocks if file exists
    - Sets executable flag if required

    Args:
        project_root: Path to the project root directory.
        artifacts: List of FileSpec objects to write.
        dry_run: If True, don't actually write files (for preview).

    Returns:
        List of written artifact paths (relative to project root).

    Raises:
        ArtifactWriteError: If any file write fails due to permissions.
    """
    if dry_run:
        return [a.path for a in artifacts]

    written_paths: list[str] = []
    failed_paths: list[str] = []

    for artifact in artifacts:
        full_path = project_root / artifact.path

        try:
            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Handle managed blocks for existing files
            if full_path.is_file():
                existing = full_path.read_text(encoding="utf-8")
                # Check if file has managed block markers
                if MARKER_BEGIN in existing and MARKER_END in existing:
                    content = replace_managed_block(existing, artifact.content)
                else:
                    # No markers — overwrite entirely
                    content = artifact.content
            else:
                # New file — wrap with managed block for rule docs
                # (hook scripts and configs don't need managed blocks)
                if artifact.path.endswith(".md"):
                    content = wrap_with_managed_block(artifact.content)
                else:
                    content = artifact.content

            # Write file
            full_path.write_text(content, encoding="utf-8")

            # Set executable flag if required
            if artifact.executable:
                current_mode = full_path.stat().st_mode
                full_path.chmod(
                    current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )

            written_paths.append(artifact.path)

        except PermissionError:
            failed_paths.append(artifact.path)
        except OSError as e:
            # Other I/O errors (disk full, etc.)
            if "Permission denied" in str(e) or e.errno == 13:
                failed_paths.append(artifact.path)
            else:
                # Re-raise unexpected I/O errors
                raise

    if failed_paths:
        raise ArtifactWriteError(failed_paths=failed_paths)

    return written_paths


def delete_artifacts(
    project_root: Path,
    artifact_paths: list[str],
) -> list[str]:
    """Delete previously generated artifacts.

    Used by uninstall command to clean up generated files.

    Args:
        project_root: Path to the project root directory.
        artifact_paths: List of artifact paths to delete.

    Returns:
        List of deleted artifact paths.
    """
    deleted: list[str] = []
    for path in artifact_paths:
        full_path = project_root / path
        if full_path.is_file():
            try:
                full_path.unlink()
                deleted.append(path)
            except PermissionError:
                # Skip files we can't delete, report later
                pass
    return deleted


# ---------------------------------------------------------------------------
# G5: Policy Cache Generation
# ---------------------------------------------------------------------------


def generate_policy_cache(
    behavior: BehaviorConfig,
    config_hash: str,
) -> FileSpec:
    """Generate policy.json for Enforcer runtime (G5).

    The policy cache is consumed by Enforcer at runtime to enforce
    behavior constraints without re-parsing guard.yaml.

    Args:
        behavior: BehaviorConfig containing read/write/execute rules.
        config_hash: SHA hash of guard.yaml for drift detection.

    Returns:
        FileSpec for .ai-guard/policy.json
    """
    policy_data = {
        "config_hash": config_hash,
        "behavior": _serialize_behavior(behavior),
    }
    return FileSpec(
        path=".ai-guard/policy.json",
        content=json.dumps(policy_data, indent=2),
    )


def _serialize_behavior(behavior: BehaviorConfig) -> dict:
    """Serialize BehaviorConfig to dict for policy.json."""
    return {
        "read": _serialize_operation_rules(behavior.read),
        "write": _serialize_operation_rules(behavior.write),
        "execute": _serialize_operation_rules(behavior.execute),
    }


def _serialize_operation_rules(rules: OperationRules) -> dict:
    """Serialize OperationRules to dict for policy.json."""
    return {
        "forbidden": [_serialize_rule(r) for r in rules.forbidden],
        "require_approval": [_serialize_rule(r) for r in rules.require_approval],
        "allow": [_serialize_rule(r) for r in rules.allow],
    }


def _serialize_rule(rule: Rule) -> dict:
    """Serialize a single Rule to dict for policy.json.

    Only includes non-default fields to keep the output minimal.
    """
    result: dict = {"pattern": rule.pattern, "source": rule.source}
    if rule.reason is not None:
        result["reason"] = rule.reason
    if rule.message is not None:
        result["message"] = rule.message
    if rule.regex:
        result["regex"] = rule.regex
    return result


# ---------------------------------------------------------------------------
# G6: Git Hooks Generation
# ---------------------------------------------------------------------------


def generate_git_hooks(project_root: Path) -> list[FileSpec]:
    """Generate Git hook scripts (G6).

    Generates pre-commit and pre-push hooks that invoke
    'guard gate run --stage <stage>'.

    Args:
        project_root: Path to project root (to check .git existence).

    Returns:
        List of FileSpec for Git hooks (executable=True),
        or empty list if .git directory doesn't exist.

    Note:
        If .git directory doesn't exist, returns empty list.
        This is a warning-level condition - caller should log warning
        but continue generating other artifacts.
    """
    git_dir = project_root / ".git"
    if not git_dir.is_dir():
        return []

    artifacts: list[FileSpec] = []
    env = _get_generator_env()

    for hook_name in ["pre-commit", "pre-push"]:
        template = env.get_template(f"git_hooks/{hook_name}.j2")
        artifacts.append(
            FileSpec(
                path=f".git/hooks/{hook_name}",
                content=template.render(),
                executable=True,
            )
        )
    return artifacts


# ---------------------------------------------------------------------------
# G3: Tool Configs Generation
# ---------------------------------------------------------------------------


def generate_tool_configs(
    project_root: Path,
    rulesets: list[str],
) -> list[FileSpec]:
    """Copy tool config files from ruleset cache (G3).

    Rulesets are cloned to .ai-guard/cache/<ruleset-name>/.
    Tool config files (like .clang-format, pyproject.toml) are
    stored in the ruleset's 'files/' subdirectory.

    Args:
        project_root: Path to project root.
        rulesets: List of ruleset names installed.

    Returns:
        List of FileSpec for tool config files to be copied
        to project root directory.
    """
    artifacts: list[FileSpec] = []
    cache_dir = project_root / ".ai-guard" / "cache"

    for ruleset in rulesets:
        files_dir = cache_dir / ruleset / "files"
        if not files_dir.is_dir():
            continue

        for file_path in files_dir.iterdir():
            if file_path.is_file():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    artifacts.append(
                        FileSpec(
                            path=file_path.name,  # Copy to project root
                            content=content,
                        )
                    )
                except UnicodeDecodeError:
                    # Skip binary files
                    continue
    return artifacts


# ---------------------------------------------------------------------------
# G4: Pre-commit Config Generation
# ---------------------------------------------------------------------------

# Language to pre-commit types mapping
# pre-commit uses specific type identifiers for file matching
_LANGUAGE_TYPES = {
    "python": "python",
    "c": "c",
    "cpp": "c++",
    "typescript": "typescript",
    "javascript": "javascript",
    "go": "go",
    "rust": "rust",
    "java": "java",
}


def generate_precommit_config(
    code: CodeConfig,
    languages: dict[str, LanguageTools],
) -> FileSpec:
    """Generate .pre-commit-config.yaml (G4).

    Generates a pre-commit configuration with format and lint hooks
    for each configured language, plus any custom checks defined in
    CodeConfig.

    Args:
        code: CodeConfig with commit_format, push_lint, and checks.
        languages: Per-language tool mappings (format and lint tools).

    Returns:
        FileSpec for .pre-commit-config.yaml
    """
    env = _get_generator_env()
    template = env.get_template("precommit_config.yaml.j2")

    # Combine commit and push checks for the template
    all_checks = {**code.commit_checks, **code.push_checks}

    context = {
        "code": code,
        "languages": languages,
        "checks": all_checks,
        "lang_types": _LANGUAGE_TYPES,
        "version": __version__,
    }

    return FileSpec(
        path=".pre-commit-config.yaml",
        content=template.render(context),
    )
