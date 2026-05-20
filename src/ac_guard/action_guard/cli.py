"""Action guard CLI entry point for subprocess invocation.

Provides a thin JSON stdin/stdout interface for non-Python hooks
(OpenCode TypeScript) to call the Action guard engine.

Usage:
    echo '{"tool_name": "Write", "tool_input": {"file_path": "x.py"}}' | \
        python3 -m ac_guard.action_guard

Input (stdin JSON):
    {"tool_name": "...", "tool_input": {...}, "agent": "opencode", "project_root": "."}
    Only ``tool_name`` and ``tool_input`` are required. ``agent`` is
    recorded in the audit log to identify the caller; ``project_root``
    defaults to ``.``.

Output (stdout JSON):
    {"decision": "allow|deny|ask", "reason": "...", "pattern": "..."}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ac_guard.action_guard.core import evaluate

__all__: list[str] = []


def main() -> None:
    """Read tool call from stdin, evaluate, write decision to stdout."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        json.dump({"decision": "deny", "reason": "Invalid input"}, sys.stdout)
        print()
        return

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    project_root = Path(input_data.get("project_root", "."))
    agent = input_data.get("agent", "")

    result = evaluate(tool_name, tool_input, project_root, agent=agent)

    output: dict[str, str] = {"decision": result.decision.value}
    if result.matched_rule and result.matched_rule.reason:
        output["reason"] = result.matched_rule.reason
    if result.matched_rule and result.matched_rule.message:
        output["message"] = result.matched_rule.message
    if result.matched_rule:
        output["pattern"] = result.matched_rule.pattern

    json.dump(output, sys.stdout)
    print()


if __name__ == "__main__":
    main()
