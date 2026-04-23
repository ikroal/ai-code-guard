"""Shared rendering utilities for Agent adapters.

Uses Jinja2 to load templates from adapters/_templates/ directory.
Templates are static files, not imported by Python, so they don't
trigger ALLOWED_DEPS checks.

This module provides:
- render_rule_doc(): Render rule document from template
- render_hook(): Render hook script from template
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from ac_guard.config import BehaviorConfig

__all__ = [
    "render_rule_doc",
    "render_hook",
    "get_template_dir",
]

# Template directory relative to this module (internal/private)
_TEMPLATE_DIR = Path(__file__).parent / "_templates"

# Jinja2 environment (singleton)
_env: Environment | None = None


def _get_env() -> Environment:
    """Get or create Jinja2 environment."""
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            autoescape=False,  # Markdown/shell scripts don't need HTML escaping
            trim_blocks=True,
            lstrip_blocks=True,
            # Preserve the final newline so generated Python hooks pass
            # ``black`` / ``ruff format`` out of the box.
            keep_trailing_newline=True,
        )
    return _env


def get_template_dir() -> Path:
    """Return the template directory path."""
    return _TEMPLATE_DIR


def render_rule_doc(template_name: str, behavior: BehaviorConfig) -> str:
    """Render rule document from template.

    Args:
        template_name: Template name without extension (e.g., "claude_code").
            Maps to templates/rule_docs/{template_name}.md.j2
        behavior: BehaviorConfig containing read/write/execute rules.

    Returns:
        Rendered Markdown content (without managed block markers).
        The writer layer (``write_artifacts``) invokes
        ``managed_block.wrap`` / ``managed_block.replace`` from
        ``ac_guard.domain.managed_block`` when the target file needs
        its managed block (re)written.
    """
    env = _get_env()
    template = env.get_template(f"rule_docs/{template_name}.md.j2")

    context = {
        "behavior": behavior,
        "operations": [
            ("Read", behavior.read),
            ("Write", behavior.write),
            ("Execute", behavior.execute),
        ],
    }

    return template.render(context)


def render_hook(template_name: str, behavior: BehaviorConfig) -> str:
    """Render hook script from template.

    Args:
        template_name: Template name without extension (e.g., "claude_code").
            Maps to templates/hooks/{template_name}.j2
        behavior: BehaviorConfig (for future embedding of rules).

    Returns:
        Rendered script content (Python, Shell, or TypeScript).
    """
    env = _get_env()
    template = env.get_template(f"hooks/{template_name}.j2")

    context = {
        "behavior": behavior,
        # Absolute path of the Python running `ac-guard install`.
        # Baked into the rendered hook so it can re-exec into an interpreter
        # that can actually import `ac_guard`, even when Claude Code launches
        # the hook from a shell whose `$PATH` lacks the project's venv.
        "python_executable": sys.executable,
    }

    return template.render(context)
