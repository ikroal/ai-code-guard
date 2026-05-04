"""Tests for generator exceptions."""

from __future__ import annotations

import pytest

from ac_guard.generator.exceptions import (
    ArtifactWriteError,
    GeneratorError,
)


class TestGeneratorError:
    """GeneratorError base exception tests."""

    def test_is_exception(self) -> None:
        assert issubclass(GeneratorError, Exception)

    def test_can_raise(self) -> None:
        with pytest.raises(GeneratorError):
            raise GeneratorError("test error")

    def test_message(self) -> None:
        err = GeneratorError("test message")
        assert str(err) == "test message"


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
