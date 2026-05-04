"""Tests for ac_guard.domain.stages — pre-commit lifecycle stage registry.

The registry is a single ``frozenset`` of stage names that ac-guard
allows users to configure under ``code.<stage>``. The set is a domain
contract: any change must come with a deliberate code review, because
config schema validation rejects ``code.<stage>`` keys outside this
set.
"""

from __future__ import annotations

from ac_guard.domain import stages

# Snapshot of stages ac-guard recognizes today. Changing this set
# changes user-visible config validation behavior.
_EXPECTED_STAGES = frozenset(
    {
        "pre-commit",
        "pre-push",
        "commit-msg",
        "pre-merge-commit",
        "pre-rebase",
    }
)


class TestKnownStagesShape:
    """The registry is a frozenset[str] of stage names."""

    def test_contents_match_expected(self) -> None:
        assert stages.KNOWN_STAGES == _EXPECTED_STAGES

    def test_is_frozenset(self) -> None:
        assert isinstance(stages.KNOWN_STAGES, frozenset)

    def test_all_entries_are_str(self) -> None:
        for stage in stages.KNOWN_STAGES:
            assert isinstance(stage, str)
            assert stage, "empty stage name is not allowed"

    def test_no_whitespace_in_names(self) -> None:
        """Stage names are pre-commit hook ids; whitespace is invalid."""
        for stage in stages.KNOWN_STAGES:
            assert stage.strip() == stage
            assert " " not in stage


class TestPublicSurface:
    """Module's public contract is exactly KNOWN_STAGES."""

    def test_all_lists_known_stages_only(self) -> None:
        assert set(stages.__all__) == {"KNOWN_STAGES"}

    def test_re_exported_from_domain_package(self) -> None:
        """`from ac_guard.domain import stages` resolves to this module."""
        from ac_guard import domain

        assert "stages" in domain.__all__
        assert domain.stages is stages
