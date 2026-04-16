"""Generator core functions for AI Guard.

Implements state management, managed block handling, and artifact
writing primitives (G7).

Managed block markers and wrap_with_managed_block are defined in
shared.types (shared across modules).
"""

from __future__ import annotations

import stat
from datetime import datetime
from pathlib import Path

from ai_guard import __version__
from ai_guard.generator.exceptions import ArtifactWriteError
from ai_guard.generator.models import STATE_FILE, GeneratedState
from ai_guard.shared.types import (
    MARKER_BEGIN,
    MARKER_END,
    FileSpec,
    wrap_with_managed_block,
)

__all__ = [
    "read_state",
    "write_state",
    "replace_managed_block",
    "wrap_with_managed_block",
    "write_artifacts",
    "delete_artifacts",
]


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
