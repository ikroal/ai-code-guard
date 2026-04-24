"""Tests for Action guard tool call classifier (E2)."""

from __future__ import annotations

from ac_guard.action_guard.classifier import classify


class TestClassifyReadOps:
    """Tests for read operation classification."""

    def test_read_file(self) -> None:
        """Read tool classifies as read/file."""
        op, scheme, target = classify("Read", {"file_path": "src/main.py"})
        assert op == "read"
        assert scheme == "file"
        assert target == "src/main.py"

    def test_read_file_lowercase(self) -> None:
        """read_file tool classifies as read/file."""
        op, scheme, target = classify("read_file", {"file_path": "README.md"})
        assert op == "read"
        assert scheme == "file"
        assert target == "README.md"

    def test_glob_tool(self) -> None:
        """Glob tool classifies as read/file using pattern."""
        op, scheme, target = classify("Glob", {"pattern": "src/**/*.py"})
        assert op == "read"
        assert scheme == "file"
        assert target == "src/**/*.py"


class TestClassifyWriteOps:
    """Tests for write operation classification."""

    def test_write_file(self) -> None:
        """Write tool classifies as write/file."""
        op, scheme, target = classify("Write", {"file_path": "out.txt"})
        assert op == "write"
        assert scheme == "file"
        assert target == "out.txt"

    def test_edit_file(self) -> None:
        """Edit tool classifies as write/file."""
        op, scheme, target = classify("Edit", {"file_path": "src/app.py"})
        assert op == "write"
        assert scheme == "file"
        assert target == "src/app.py"

    def test_notebook_edit(self) -> None:
        """NotebookEdit classifies as write/file."""
        op, scheme, target = classify(
            "NotebookEdit", {"notebook_path": "analysis.ipynb"}
        )
        assert op == "write"
        assert scheme == "file"
        assert target == "analysis.ipynb"


class TestClassifyExecuteOps:
    """Tests for execute operation classification."""

    def test_bash_command(self) -> None:
        """Bash tool classifies as execute/shell."""
        op, scheme, target = classify("Bash", {"command": "git status"})
        assert op == "execute"
        assert scheme == "shell"
        assert target == "git status"

    def test_task_tool(self) -> None:
        """Task tool classifies as execute/shell."""
        op, scheme, target = classify("Task", {"command": "npm test"})
        assert op == "execute"
        assert scheme == "shell"
        assert target == "npm test"

    def test_mcp_tool(self) -> None:
        """MCP tool (mcp__ prefix) classifies as execute/mcp."""
        op, scheme, target = classify("mcp__memory__search", {"query": "test"})
        assert op == "execute"
        assert scheme == "mcp"
        assert "memory" in target

    def test_web_fetch(self) -> None:
        """WebFetch classifies as execute/web."""
        op, scheme, target = classify("WebFetch", {"url": "https://example.com"})
        assert op == "execute"
        assert scheme == "web"
        assert "https://example.com" in target

    def test_web_search(self) -> None:
        """WebSearch classifies as execute/web."""
        op, scheme, _target = classify("WebSearch", {"query": "python docs"})
        assert op == "execute"
        assert scheme == "web"


class TestClassifyUnknown:
    """Tests for unknown tool classification."""

    def test_unknown_tool(self) -> None:
        """Unknown tool returns unknown operation."""
        op, _scheme, _target = classify("SomeFutureTool", {"arg": "value"})
        assert op == "unknown"

    def test_empty_tool_input(self) -> None:
        """Empty tool input doesn't crash."""
        op, _scheme, target = classify("Read", {})
        assert op == "read"
        assert target == ""
