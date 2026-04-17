"""AgentAdapter registry for registration and lookup.

Provides a central registry where adapters are registered by name
and can be retrieved for use by the Generator module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from ac_guard.adapters.base import AgentAdapter

__all__ = [
    "AdapterNotFoundError",
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "clear_registry",
]

# Internal registry storage
_REGISTRY: dict[str, AgentAdapter] = {}


class AdapterNotFoundError(Exception):
    """Raised when get_adapter is called with an unregistered name."""

    def __init__(self, name: str, available: list[str]) -> None:
        super().__init__(
            f"Agent adapter '{name}' not found. Available: {', '.join(available)}"
        )
        self.name = name
        self.available = available


def register_adapter(adapter: AgentAdapter) -> None:
    """Register an AgentAdapter by its name.

    Args:
        adapter: The AgentAdapter instance to register.

    Raises:
        ValueError: If an adapter with the same name is already registered.
    """
    name = adapter.name
    if name in _REGISTRY:
        raise ValueError(f"Adapter '{name}' is already registered")
    _REGISTRY[name] = adapter


def get_adapter(name: str) -> AgentAdapter:
    """Retrieve a registered AgentAdapter by name.

    Args:
        name: The adapter identifier (e.g., "claude-code").

    Returns:
        The registered AgentAdapter instance.

    Raises:
        AdapterNotFoundError: If no adapter is registered with that name.
    """
    if name not in _REGISTRY:
        raise AdapterNotFoundError(name, list_adapters())
    return _REGISTRY[name]


def list_adapters() -> list[str]:
    """List all registered adapter names.

    Returns:
        Sorted list of registered adapter identifiers.
    """
    return sorted(_REGISTRY.keys())


def clear_registry() -> None:
    """Clear all registered adapters.

    Used primarily for testing to reset the registry state.
    """
    _REGISTRY.clear()


# ---------------------------------------------------------------------------
# Built-in Adapters
# ---------------------------------------------------------------------------

# Import adapters lazily to avoid circular imports at module load time.
# The _register_builtins function is called when this module is imported,
# but actual adapter classes are imported only when needed.
_BUILTIN_ADAPTER_NAMES: Final[tuple[str, ...]] = (
    "claude-code",
    "cursor",
    "opencode",
    "copilot",
    "kilocode",
)


def _register_builtins() -> None:
    """Register all built-in adapters."""
    from ac_guard.adapters.claude_code import ClaudeCodeAdapter
    from ac_guard.adapters.copilot import CopilotAdapter
    from ac_guard.adapters.cursor import CursorAdapter
    from ac_guard.adapters.kilocode import KiloCodeAdapter
    from ac_guard.adapters.opencode import OpenCodeAdapter

    register_adapter(ClaudeCodeAdapter())
    register_adapter(CursorAdapter())
    register_adapter(OpenCodeAdapter())
    register_adapter(CopilotAdapter())
    register_adapter(KiloCodeAdapter())


# Auto-register builtins when this module is imported
_register_builtins()
