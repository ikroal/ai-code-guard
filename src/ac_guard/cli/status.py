"""status, doctor, and agents command implementations for AI Code Guard CLI.

Provides diagnostic and informational commands for inspecting
AI Code Guard installation state, environment health, and agent capabilities.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ac_guard import __version__
from ac_guard.adapters.registry import get_adapter, list_adapters
from ac_guard.config import (
    ConfigError,
    diagnose_config,
    resolve_config,
)
from ac_guard.generator import read_installation

if TYPE_CHECKING:
    from pathlib import Path

    from ac_guard.config import ResolvedConfig

__all__ = [
    "AgentsRequest",
    "DoctorRequest",
    "StatusRequest",
    "agents_command",
    "doctor_command",
    "status_command",
]


@dataclass(frozen=True)
class StatusRequest:
    """Inputs for ``ac-guard status``.

    ``status`` is purely about *deployment* observation — installed
    agents, drift between guard.yaml and the install state, and
    artifact integrity. *Configuration content* observation lives in
    ``ac-guard show`` (e.g. ``show --section=behavior`` for the rules
    list that ``status --rules`` used to print).

    Attributes:
        project_root: Project root directory.
        config_path: Path to ``guard.yaml``.
        output_format: ``"text"`` or ``"json"``.
    """

    project_root: Path
    config_path: Path
    output_format: str = "text"


@dataclass(frozen=True)
class DoctorRequest:
    """Inputs for ``ac-guard doctor``.

    Attributes:
        project_root: Project root directory.
        config_path: Path to ``guard.yaml``.
        strict: Treat WARN severity as failure (CI-friendly).
    """

    project_root: Path
    config_path: Path
    strict: bool = False


@dataclass(frozen=True)
class AgentsRequest:
    """Inputs for ``ac-guard agents``."""

    project_root: Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_config_hash(path: Path) -> str:
    """SHA-256 of the file bytes, truncated to 8 hex chars."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


def status_command(request: StatusRequest) -> None:
    """Execute the status command.

    Shows installation status, drift detection, and artifact integrity.
    """
    state = read_installation(request.project_root)

    if request.output_format == "json":
        _status_json(state, request.project_root, request.config_path)
    else:
        _status_text(state, request.project_root, request.config_path)


def _status_text(
    state: object,
    project_root: Path,
    config_path: Path,
) -> None:
    """Output status as text."""
    if state is None:
        print("AI Code Guard is not installed.")
        print("Run 'ac-guard install --agent <name>' to install.")
        return

    # Installation info
    print(f"Installed agents: {', '.join(state.installed_agents)}")
    print(f"AI Code Guard version: {state.ac_guard_version}")
    print(f"Installed at: {state.installed_at.isoformat()}")

    # Version mismatch check
    if state.ac_guard_version != __version__:
        msg = (
            f"\nVersion mismatch: install version {state.ac_guard_version}, "
            f"current version {__version__}."
        )
        print(msg)
        print("Run 'ac-guard update' to sync.")

    # Drift detection
    if config_path.is_file():
        current_hash = _compute_config_hash(config_path)
        if current_hash != state.config_hash:
            print(
                "\nConfiguration drift detected: guard.yaml has changed "
                "since last install/update. Run 'ac-guard update'."
            )
        else:
            print("\nConfiguration: up to date (no drift)")
    else:
        print("\nWarning: guard.yaml not found.")

    # Artifact integrity check
    missing = [p for p in state.artifacts if not (project_root / p).is_file()]

    if missing:
        print(f"\nMissing artifacts ({len(missing)}):")
        for path in missing:
            print(f"  {path}")
        print("Run 'ac-guard update' to regenerate.")
    else:
        print(f"\nAll {len(state.artifacts)} artifact(s) present.")


def _status_json(state: object, project_root: Path, config_path: Path) -> None:
    """Output status as JSON.

    Args:
        state: Installation or None.
        project_root: Path to project root.
        config_path: Path to guard.yaml.
    """
    if state is None:
        print(json.dumps({"installed": False}))
        return

    # Compute drift
    drift = False
    if config_path.is_file():
        current_hash = _compute_config_hash(config_path)
        drift = current_hash != state.config_hash

    # Check missing artifacts
    missing = [p for p in state.artifacts if not (project_root / p).is_file()]

    data = {
        "installed": True,
        "installed_agents": state.installed_agents,
        "ac_guard_version": state.ac_guard_version,
        "current_version": __version__,
        "installed_at": state.installed_at.isoformat(),
        "config_hash": state.config_hash,
        "config_drift": drift,
        "artifacts": state.artifacts,
        "missing_artifacts": missing,
    }
    print(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# doctor command
# ---------------------------------------------------------------------------


def doctor_command(request: DoctorRequest) -> None:
    """Execute the doctor command.

    Performs systematic environment diagnostics. FAIL always exits 1;
    with ``strict=True`` any WARN also exits 1 (useful for CI).
    """
    tally = _Tally()

    print("AI Code Guard Doctor")
    print("=" * 40)

    # 1. Tool dependencies
    print("\n1. Tool Dependencies")
    _check_python(tally)
    _check_git(tally)
    _check_pre_commit(tally)

    # 2. Configuration state
    print("\n2. Configuration")
    resolved = _check_config(request.config_path, tally)

    # 3. File integrity
    print("\n3. File Integrity")
    _check_file_integrity(request.project_root, tally)

    # 4. Drift detection
    print("\n4. Drift Detection")
    _check_drift(request.project_root, request.config_path, tally)

    # 5. Config-environment consistency diagnosis (skip if load failed).
    # Stage-semantic fit (format/lint placement) is enforced at semantic
    # validation, not here — broken configs fail step 2 above. The
    # remaining IO-bearing checks (hook PATH resolvability, language
    # coverage, ruleset paths) live in ``config.diagnose``; doctor
    # renders the Diagnostic list and aggregates the tally.
    if resolved is not None:
        print("\n5. Configuration Diagnosis")
        _render_diagnosis(resolved, request.project_root, tally)

    # Exit policy: FAIL always exits 1. WARN exits 1 only under --strict.
    if tally.fail > 0 or (request.strict and tally.warn > 0):
        print(
            f"\n{tally.fail} failure(s), {tally.warn} warning(s). "
            "Run 'ac-guard install' or fix guard.yaml and re-run doctor."
        )
        raise SystemExit(1)


class _Tally:
    """Aggregate WARN / FAIL counts across doctor checks."""

    def __init__(self) -> None:
        self.warn = 0
        self.fail = 0

    def warn_inc(self) -> None:
        self.warn += 1

    def fail_inc(self) -> None:
        self.fail += 1


def _check_python(tally: _Tally) -> None:
    """Check Python version."""
    version = sys.version.split()[0]
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 10:
        print(f"  [ok] Python {version}")
    else:
        print(f"  [FAIL] Python {version} (requires >= 3.10)")
        tally.fail_inc()


def _check_git(tally: _Tally) -> None:
    """Check git availability."""
    git_path = shutil.which("git")
    if git_path:
        print(f"  [ok] git found at {git_path}")
    else:
        print("  [FAIL] git not found. Install git.")
        tally.fail_inc()


def _check_pre_commit(tally: _Tally) -> None:
    """Check pre-commit availability."""
    pc_path = shutil.which("pre-commit")
    if pc_path:
        print(f"  [ok] pre-commit found at {pc_path}")
    else:
        print("  [WARN] pre-commit not found. Install: pip install pre-commit")
        tally.warn_inc()


def _check_config(config_path: Path, tally: _Tally) -> ResolvedConfig | None:
    """Validate guard.yaml — returns ResolvedConfig so later checks can reuse it.

    Returns None on invalid/missing config so the remaining per-config
    checks can be skipped without raising.
    """
    if not config_path.is_file():
        print(f"  [FAIL] guard.yaml not found at {config_path}")
        print("         Run 'ac-guard init' to create one.")
        tally.fail_inc()
        return None

    try:
        resolved = resolve_config(config_path)
    except ConfigError as e:
        print(f"  [FAIL] guard.yaml: {e}")
        tally.fail_inc()
        return None

    print(f"  [ok] guard.yaml valid ({config_path})")
    return resolved


def _check_file_integrity(project_root: Path, tally: _Tally) -> None:
    """Check artifact file integrity."""
    state = read_installation(project_root)
    if state is None:
        print("  [WARN] Not installed (no state.json)")
        tally.warn_inc()
        return

    missing = []
    for artifact_path in state.artifacts:
        full_path = project_root / artifact_path
        if not full_path.is_file():
            missing.append(artifact_path)

    if missing:
        print(f"  [FAIL] {len(missing)} artifact(s) missing:")
        for path in missing:
            print(f"         {path}")
        print("         Run 'ac-guard update' to regenerate.")
        tally.fail_inc()
    else:
        print(f"  [ok] All {len(state.artifacts)} artifact(s) present")


def _check_drift(project_root: Path, config_path: Path, tally: _Tally) -> None:
    """Check configuration drift."""
    state = read_installation(project_root)
    if state is None:
        print("  [SKIP] Not installed")
        return

    if not config_path.is_file():
        print("  [WARN] guard.yaml not found")
        tally.warn_inc()
        return

    current_hash = _compute_config_hash(config_path)
    if current_hash != state.config_hash:
        print("  [WARN] Configuration drift detected")
        print("         Run 'ac-guard update' to sync.")
        tally.warn_inc()
    else:
        print("  [ok] No drift")


# ---------------------------------------------------------------------------
# Configuration diagnosis renderer (delegates to config.diagnose_config)
# ---------------------------------------------------------------------------


def _render_diagnosis(
    resolved: ResolvedConfig, project_root: Path, tally: _Tally
) -> None:
    """Run configuration-environment diagnosis and print findings.

    All the actual logic — hook PATH resolution, language coverage,
    ruleset path existence — lives in ``config.diagnose``. Doctor's
    only job here is to render each ``Diagnostic`` in the existing
    ``[ok] / [WARN] / [FAIL]`` style and feed the tally so the exit
    policy stays uniform across check sections.
    """
    diags = diagnose_config(resolved, project_root)
    for d in diags:
        if d.level == "fail":
            print(f"  [FAIL] {d.message}")
            tally.fail_inc()
        elif d.level == "warn":
            print(f"  [WARN] {d.message}")
            tally.warn_inc()
        else:
            print(f"  [ok] {d.message}")


# ---------------------------------------------------------------------------
# agents command
# ---------------------------------------------------------------------------


def agents_command(request: AgentsRequest) -> None:
    """Execute the agents command.

    Displays agent capability matrix with installation status.
    """
    state = read_installation(request.project_root)
    installed = set(state.installed_agents) if state else set()

    print("Agent Capability Matrix")
    print("-" * 72)
    print(f"{'Agent':<15} {'Block':<7} {'Ask':<7} {'Rule Doc':<25} {'Status'}")
    print("-" * 72)

    for name in list_adapters():
        adapter = get_adapter(name)
        caps = adapter.capabilities
        block_str = "yes" if caps.can_block else "no"
        ask_str = "yes" if caps.can_ask else "no"
        doc_path = adapter.rule_doc_path()
        status_str = "INSTALLED" if name in installed else "-"
        print(f"  {name:<13} {block_str:<7} {ask_str:<7} {doc_path:<25} {status_str}")

    print("-" * 72)
    if installed:
        print(f"\n{len(installed)} agent(s) installed.")
    else:
        print("\nNo agents installed. Run 'ac-guard install --agent <name>'.")
