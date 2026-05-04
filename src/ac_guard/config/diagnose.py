"""Configuration-environment consistency diagnosis — the IO-bearing
half of config validation.

Where ``semantic.py`` is strictly zero-IO, this module touches the
filesystem, the user's PATH, and the project's git working tree to
cross-check the merged ``ResolvedConfig`` against the current runtime
reality. Examples: a hook ``entry`` references a tool that isn't on
PATH, a ruleset path doesn't exist, a language is declared but the
repo has no files matching it.

doctor (and any other caller doing a sanity check) calls
``diagnose_config(resolved, project_root)`` and renders the returned
``Diagnostic`` list — diagnostics carry their own severity so the
caller's only job is grouping / printing / exit-code logic. The
function never raises: configuration validity vs. environment fitness
are different failure modes, and reporting the latter as a list of
findings (rather than a thrown exception) keeps doctor in control of
exit-code policy.

The file boundary between ``semantic.py`` (zero-IO) and ``diagnose.py``
(IO-bearing) makes the contract physically visible: a future
contributor adding a new check has to pick a side, and the choice is
unambiguous.

Internal submodule — import the public surface via
:mod:`ac_guard.config` rather than reaching in here directly.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ac_guard.domain.languages import detect_language

if TYPE_CHECKING:
    from ac_guard.config.models import ResolvedConfig

__all__ = ["Diagnostic", "diagnose_config"]


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Diagnostic:
    """A single config-environment consistency finding to display.

    Attributes:
        level: Severity. ``"ok"`` is shown for transparency (so the
            user sees what was checked), ``"warn"`` is informational,
            ``"fail"`` should drive a non-zero exit code.
        path: Dot-notation field path the diagnostic refers to (kept
            consistent with :class:`ValidationIssue.path` so the same
            error grammar is shared between schema and runtime
            findings).
        message: Human-readable description of the finding.
    """

    level: Literal["ok", "warn", "fail"]
    path: str
    message: str


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def diagnose_config(resolved: ResolvedConfig, project_root: Path) -> list[Diagnostic]:
    """Diagnose configuration consistency against the current environment.

    Cross-checks the merged configuration against runtime reality:
    PATH for declared hook commands, ``git ls-files`` for declared
    languages, filesystem for local ruleset paths. Emits a
    ``Diagnostic`` per finding (ok / warn / fail); never raises.
    Callers (doctor and friends) render the list and decide exit code.

    Args:
        resolved: A fully-merged ``ResolvedConfig``.
        project_root: Project root path. Used as the base for
            project-relative file lookups (hook entries, rulesets)
            and as the cwd for ``git ls-files``.

    Returns:
        Concatenated diagnostics from each helper, in stable order.
    """
    diags: list[Diagnostic] = []
    diags.extend(_verify_command_paths(resolved, project_root))
    diags.extend(_verify_language_coverage(resolved, project_root))
    diags.extend(_verify_ruleset_paths(resolved, project_root))
    return diags


# ---------------------------------------------------------------------------
# _verify_command_paths
# ---------------------------------------------------------------------------


def _verify_command_paths(
    resolved: ResolvedConfig, project_root: Path
) -> list[Diagnostic]:
    """Check every ``repo: local`` + ``language: system`` hook entry.

    Take the first token of ``entry`` (via ``shlex.split``) and look
    for it in PATH or as a file under ``project_root``. Anything that
    can't be resolved is a ``fail`` — pre-commit would only surface
    the error at the first hook invocation.

    Non-system languages (python/node/docker/...) are skipped because
    pre-commit installs the entry into an isolated env, so we can't
    and shouldn't second-guess availability.

    Note: ``code.<stage>.checks[*].command`` would be a natural future
    extension here; today those go through pre-commit's own runtime
    discovery and are not pre-checked.
    """
    diags: list[Diagnostic] = []
    found_any = False
    for _stage_name, bucket in resolved.code.buckets():
        for repo in bucket.hooks:
            if repo.repo != "local":
                continue
            for hook in repo.hooks:
                if hook.extra.get("language") != "system":
                    continue
                entry = hook.extra.get("entry")
                if not isinstance(entry, str) or not entry.strip():
                    continue
                found_any = True
                tokens = shlex.split(entry)
                if not tokens:
                    continue
                token = tokens[0]
                location = _resolve_command_token(token, project_root)
                if location:
                    diags.append(
                        Diagnostic(
                            level="ok",
                            path=f"hook.{hook.id}",
                            message=f"{hook.id}: {token} ({location})",
                        )
                    )
                else:
                    diags.append(
                        Diagnostic(
                            level="fail",
                            path=f"hook.{hook.id}",
                            message=(
                                f"{hook.id}: {token} not in PATH or "
                                "project — install the tool or adjust "
                                "the guard.yaml entry"
                            ),
                        )
                    )

    if not found_any:
        diags.append(
            Diagnostic(
                level="ok",
                path="code.<stage>.hooks",
                message="No system-language local hooks to verify",
            )
        )
    return diags


def _resolve_command_token(token: str, project_root: Path) -> str | None:
    """Return a human-readable location string if ``token`` is runnable.

    Tries ``shutil.which`` (PATH) first, then checks whether the token
    resolves to a file under ``project_root``. Returns ``None`` if
    neither works.
    """
    if shutil.which(token):
        return "PATH"
    candidate = project_root / token
    if candidate.is_file():
        return "project-relative"
    return None


# ---------------------------------------------------------------------------
# _verify_language_coverage
# ---------------------------------------------------------------------------


# Files-per-undeclared-language threshold below which we stay silent.
# Avoids noise from scattered config files (.ts shim, single .go vendored).
_LANGUAGE_COVERAGE_MIN_FILES = 3


def _verify_language_coverage(
    resolved: ResolvedConfig, project_root: Path
) -> list[Diagnostic]:
    """Compare ``languages:`` declarations to git-tracked source files.

    Cases:

    * declared + has files → ``ok``
    * declared + zero files → ``warn`` (user may have forgotten to stage,
      or chose the wrong language name)
    * undeclared + ≥ ``_LANGUAGE_COVERAGE_MIN_FILES`` → ``warn``
      (format/lint shortcuts won't cover them)
    * undeclared + < threshold → silent (scattered config files)

    Outside a git repo (no ``.git`` / ``git ls-files`` returns non-zero),
    counts come back empty; declared languages then warn for "no files",
    which is the same signal as an empty repo and acceptable.
    """
    diags: list[Diagnostic] = []
    counts = _count_languages_by_extension(project_root)
    declared = set(resolved.languages.keys())

    for lang in sorted(declared):
        n = counts.get(lang, 0)
        if n > 0:
            diags.append(
                Diagnostic(
                    level="ok",
                    path=f"languages.{lang}",
                    message=f"{lang}: {n} files",
                )
            )
        else:
            diags.append(
                Diagnostic(
                    level="warn",
                    path=f"languages.{lang}",
                    message=(
                        f"{lang}: declared in languages: but no source "
                        f"files found under {project_root}"
                    ),
                )
            )

    undeclared = sorted(
        lang
        for lang, n in counts.items()
        if lang not in declared and n >= _LANGUAGE_COVERAGE_MIN_FILES
    )
    diags.extend(
        Diagnostic(
            level="warn",
            path="languages",
            message=(
                f"{lang}: {counts[lang]} files but no entry in "
                "languages: — format/lint shortcuts won't cover them"
            ),
        )
        for lang in undeclared
    )

    if not declared and not undeclared:
        diags.append(
            Diagnostic(
                level="ok",
                path="languages",
                message="No tracked source files to check",
            )
        )

    return diags


def _count_languages_by_extension(project_root: Path) -> Counter[str]:
    """Return ``{language_name: file_count}`` over git-tracked files.

    Falls back to an empty counter if ``git`` fails (e.g. not a repo) —
    doctor's environment check already reports git issues separately,
    so we stay silent here to avoid double-reporting.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return Counter()
    if result.returncode != 0:
        return Counter()
    counts: Counter[str] = Counter()
    for path in result.stdout.splitlines():
        lang = detect_language(path)
        if lang:
            counts[lang] += 1
    return counts


# ---------------------------------------------------------------------------
# _verify_ruleset_paths
# ---------------------------------------------------------------------------


def _verify_ruleset_paths(
    resolved: ResolvedConfig, project_root: Path
) -> list[Diagnostic]:
    """Verify local ruleset paths exist; remote refs are skipped.

    A ruleset entry is treated as remote (no IO) when it starts with a
    URL scheme (``http://`` / ``https://``) or with a git SSH prefix
    (``git@``). Anything else is taken as a filesystem path, resolved
    relative to ``project_root`` if not already absolute, and checked
    for existence.
    """
    diags: list[Diagnostic] = []
    if not resolved.rulesets:
        return diags
    for entry in resolved.rulesets:
        if _is_remote_ref(entry):
            diags.append(
                Diagnostic(
                    level="ok",
                    path="rulesets",
                    message=f"{entry} (remote ref, not IO-checked)",
                )
            )
            continue
        candidate = Path(entry)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        if candidate.exists():
            diags.append(
                Diagnostic(
                    level="ok",
                    path="rulesets",
                    message=f"{entry} → {candidate}",
                )
            )
        else:
            diags.append(
                Diagnostic(
                    level="fail",
                    path="rulesets",
                    message=f"local ruleset path not found: {entry}",
                )
            )
    return diags


def _is_remote_ref(entry: str) -> bool:
    return entry.startswith(("http://", "https://", "git@", "ssh://"))
