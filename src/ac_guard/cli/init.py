"""init command implementation for AI Code Guard CLI.

Generates a guard.yaml configuration file based on presets and user options.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

from ac_guard import __version__
from ac_guard.cli.presets import AVAILABLE_PRESETS, load_preset

__all__ = ["InitRequest", "init_command"]


@dataclass(frozen=True)
class InitRequest:
    """Bundle of inputs that drive a single ``ac-guard init`` invocation.

    Attributes:
        language: Project programming language (required).
        preset: Configuration preset name (``minimal`` / ``standard`` / ``strict``).
        rulesets: Ruleset references to embed in the generated config.
        force: Overwrite an existing ``guard.yaml`` if present.
        output: Destination path of the generated ``guard.yaml``.
    """

    language: str
    preset: str
    rulesets: list[str]
    force: bool
    output: Path


# Jinja2 environment for header template
_TEMPLATE_DIR = Path(__file__).parent / "_templates"
_jinja_env: Environment | None = None


def _get_jinja_env() -> Environment:
    """Get or create the Jinja2 environment for CLI templates."""
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _jinja_env


def _get_project_name() -> str:
    """Get the project name from the current directory."""
    return Path.cwd().name


def _merge_config(
    preset_config: dict[str, Any],
    language: str,
    rulesets: list[str],
    project_name: str,
) -> dict[str, Any]:
    """Merge preset config with user-provided parameters.

    Args:
        preset_config: Base configuration from preset.
        language: Project programming language.
        rulesets: List of ruleset references to include.
        project_name: Project display name.

    Returns:
        Merged configuration dict ready for YAML serialization.
    """
    merged = copy.deepcopy(preset_config)

    # Set project info
    merged["project"] = {
        "name": project_name,
        "language": language,
    }

    # Add rulesets if provided
    if rulesets:
        merged["rulesets"] = rulesets

    # Ensure version field
    if "version" not in merged:
        merged["version"] = 1

    return merged


def _render_guard_yaml(
    config: dict[str, Any],
    preset: str,
) -> str:
    """Render the guard.yaml content.

    Combines a Jinja2 header with YAML serialization of the config.

    Args:
        config: Configuration dict to serialize.
        preset: Preset name for header comment.

    Returns:
        Complete guard.yaml content string.
    """
    # Render header with Jinja2
    env = _get_jinja_env()
    template = env.get_template("guard_yaml.j2")

    header = template.render(
        version=__version__,
        preset=preset,
        project_name=config.get("project", {}).get("name", ""),
        language=config.get("project", {}).get("language", ""),
        rulesets=config.get("rulesets", []),
    )

    # Serialize the full config to YAML
    # Use explicit_start to add document separator ---
    yaml_content = yaml.dump(
        config,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        explicit_start=False,
    )

    # Combine header + YAML content
    # Header already contains version/project/rulesets, so we need to
    # strip those from yaml_content to avoid duplication
    lines = yaml_content.split("\n")
    filtered_lines: list[str] = []
    skip_until_next_section = False

    for line in lines:
        # Skip version, project, rulesets (handled by template)
        if line.startswith("version:"):
            continue
        if line.startswith("project:"):
            skip_until_next_section = True
            continue
        if line.startswith("rulesets:"):
            skip_until_next_section = True
            continue
        if skip_until_next_section:
            # Check if we've reached a new top-level key
            if line and not line.startswith(" ") and not line.startswith("-"):
                skip_until_next_section = False
            else:
                continue
        filtered_lines.append(line)

    body = "\n".join(filtered_lines).strip()

    return header.rstrip() + "\n" + body + "\n"


def init_command(request: InitRequest) -> None:
    """Execute the init command.

    Creates a guard.yaml configuration file based on the selected preset
    and the parameters carried by ``request``.
    """
    if request.output.exists() and not request.force:
        print(f"Error: {request.output} already exists. Use --force to overwrite.")
        raise SystemExit(1)

    if request.preset not in AVAILABLE_PRESETS:
        print(
            f"Error: Unknown preset '{request.preset}'. Available: {AVAILABLE_PRESETS}"
        )
        raise SystemExit(1)

    preset_config = load_preset(request.preset)
    project_name = _get_project_name()
    config = _merge_config(
        preset_config, request.language, request.rulesets, project_name
    )
    yaml_content = _render_guard_yaml(config, request.preset)

    request.output.write_text(yaml_content, encoding="utf-8")

    print(f"Created {request.output}")
    print("\nNext steps:")
    print("  1. Review and edit the configuration file")
    print("  2. Run 'ac-guard install --agent <agent>' to generate artifacts")
    print("\nAvailable agents:")
    print("  claude-code, opencode, copilot, kilocode")
