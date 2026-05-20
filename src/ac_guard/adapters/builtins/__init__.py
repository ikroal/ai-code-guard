"""Built-in :class:`AgentAdapter` implementations.

Each module in this subpackage holds the strategy for one supported AI
coding agent. The set is closed — adapters live alongside the framework
contract (:mod:`ac_guard.adapters.base`) rather than being discovered
via plugin entry points. Callers should query the public registry
(:func:`ac_guard.adapters.get_adapter`) instead of importing adapter
classes directly.

This ``__init__`` re-exports the adapter classes so the registry can
import them in one line.
"""

from __future__ import annotations

from ac_guard.adapters.builtins.claude_code import ClaudeCodeAdapter
from ac_guard.adapters.builtins.codex import CodexAdapter
from ac_guard.adapters.builtins.copilot import CopilotAdapter
from ac_guard.adapters.builtins.kilocode import KiloCodeAdapter
from ac_guard.adapters.builtins.opencode import OpenCodeAdapter

__all__ = [
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "CopilotAdapter",
    "KiloCodeAdapter",
    "OpenCodeAdapter",
]
