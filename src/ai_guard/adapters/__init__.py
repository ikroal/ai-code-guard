"""Agent adapters module for AI Guard.

Provides AgentAdapter abstract base class, AgentCapabilities dataclass,
and registry functions for managing Agent-specific file generation strategies.

Built-in adapters are auto-registered on module import:
- claude-code (can_block=True, can_ask=True)
- cursor (can_block=True, can_ask=False)
- opencode (can_block=True, can_ask=True)
- copilot (can_block=False, can_ask=False)
- kilocode (can_block=False, can_ask=False)
"""

from ai_guard.adapters.base import AgentAdapter, AgentCapabilities
from ai_guard.adapters.registry import (
    AdapterNotFoundError,
    clear_registry,
    get_adapter,
    list_adapters,
    register_adapter,
)

__all__ = [
    # Base types
    "AgentAdapter",
    "AgentCapabilities",
    # Registry functions
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "clear_registry",
    # Exceptions
    "AdapterNotFoundError",
]
