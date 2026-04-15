"""Tests for generator exceptions."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_guard.generator.exceptions import (
    AdapterNotRegisteredError,
    ArtifactWriteError,
    GeneratorError,
    GitDirectoryNotFoundError,
)


class TestGeneratorError:
    """GeneratorError base exception tests."""

    def test_is_exception(self) -> None:
        assert issubclass(GeneratorError, Exception)

    def test_can_raise(self) -> None:
        with pytest.raises(GeneratorError):
            raise GeneratorError("test error")

    def test_message(self) -> None:
        try:
            raise GeneratorError("test message")
        except GeneratorError as e:
            assert str(e) == "test message"


class TestArtifactWriteError:
    """ArtifactWriteError tests."""

    def test_failed_paths_attribute(self) -> None:
        err = ArtifactWriteError(failed_paths=["a.txt", "b.txt"])
        assert err.failed_paths == ["a.txt", "b.txt"]

    def test_str_contains_paths(self) -> None:
        err = ArtifactWriteError(failed_paths=["file1.txt", "file2.txt"])
        assert "file1.txt" in str(err)
        assert "file2.txt" in str(err)
        assert "permission denied" in str(err)

    def test_inherits_generator_error(self) -> None:
        assert issubclass(ArtifactWriteError, GeneratorError)


class TestGitDirectoryNotFoundError:
    """GitDirectoryNotFoundError tests."""

    def test_project_root_attribute(self) -> None:
        path = Path("/tmp/project")
        err = GitDirectoryNotFoundError(path)
        assert err.project_root == path

    def test_message_contains_path(self) -> None:
        path = Path("/tmp/myproject")
        err = GitDirectoryNotFoundError(path)
        assert "myproject" in str(err)
        assert ".git" in str(err)

    def test_inherits_generator_error(self) -> None:
        assert issubclass(GitDirectoryNotFoundError, GeneratorError)


class TestAdapterNotRegisteredError:
    """AdapterNotRegisteredError tests."""

    def test_attributes(self) -> None:
        err = AdapterNotRegisteredError(
            agent_name="unknown-agent",
            available_agents=["claude-code", "cursor"],
        )
        assert err.agent_name == "unknown-agent"
        assert err.available_agents == ["claude-code", "cursor"]

    def test_str_contains_agent_name(self) -> None:
        err = AdapterNotRegisteredError(
            agent_name="myagent",
            available_agents=["agent1", "agent2"],
        )
        assert "myagent" in str(err)
        assert "agent1" in str(err)
        assert "agent2" in str(err)

    def test_inherits_generator_error(self) -> None:
        assert issubclass(AdapterNotRegisteredError, GeneratorError)
