"""Action guard tool call classifier (E2 primitive).

Maps ``(tool_name, tool_input)`` to ``(operation, scheme, target)``
for downstream pattern matching by the matcher (E3).
"""

from __future__ import annotations

from typing import Any

__all__ = ["classify"]

# Tool name sets for classification
_READ_TOOLS = frozenset({"Read", "read_file", "Glob", "glob"})
_WRITE_TOOLS = frozenset({"Write", "write_file"})
_EDIT_TOOLS = frozenset({"Edit", "edit_file", "edit"})
_NOTEBOOK_TOOLS = frozenset({"NotebookEdit", "notebook_edit"})
_SHELL_TOOLS = frozenset({"Bash", "bash", "Task", "task"})
_WEB_TOOLS = frozenset({"WebFetch", "WebSearch"})


def classify(tool_name: str, tool_input: dict[str, Any]) -> tuple[str, str, str]:
    """Classify a tool call into (operation, scheme, target).

    Maps tool names to operation types and extracts the
    target resource identifier from tool_input.

    Args:
        tool_name: Tool name from the AI agent (e.g.,
            ``"Read"``, ``"Write"``, ``"Bash"``).
        tool_input: Tool arguments dict.

    Returns:
        Tuple of (operation, scheme, target) where:
        - operation: ``"read"`` | ``"write"`` | ``"execute"`` | ``"unknown"``
        - scheme: ``"file"`` | ``"shell"`` | ``"mcp"`` | ``"web"`` | ``""``
        - target: extracted resource identifier
    """
    # Read operations
    if tool_name in _READ_TOOLS:
        target = tool_input.get("file_path", tool_input.get("pattern", ""))
        return ("read", "file", target)

    # Write operations
    if tool_name in _WRITE_TOOLS:
        return ("write", "file", tool_input.get("file_path", ""))

    if tool_name in _EDIT_TOOLS:
        target = tool_input.get("file_path", tool_input.get("path", ""))
        return ("write", "file", target)

    if tool_name in _NOTEBOOK_TOOLS:
        return ("write", "file", tool_input.get("notebook_path", ""))

    # Shell execute operations
    if tool_name in _SHELL_TOOLS:
        target = tool_input.get("command", tool_input.get("prompt", ""))
        return ("execute", "shell", target)

    # MCP operations (mcp__ prefix)
    if tool_name.startswith("mcp__"):
        # Convert mcp__server__tool → server:tool for pattern matching
        parts = tool_name.removeprefix("mcp__").split("__", 1)
        mcp_target = ":".join(parts)
        return ("execute", "mcp", mcp_target)

    # Web operations
    if tool_name in _WEB_TOOLS:
        target = tool_input.get("url", tool_input.get("query", ""))
        return ("execute", "web", target)

    # Unknown tool
    return ("unknown", "", "")
