# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

本项目变更记录遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/) 格式与 [语义化版本](https://semver.org/lang/zh-CN/spec/v2.0.0.html)。

## [Unreleased]

### Changed

- **BREAKING — Reporter API collapse** (follow-up to the earlier Reporter
  API restructure below). Further consolidation based on the "Reporter
  serves only **humans or Agents** — nothing else" principle.

  **Public surface is now a single `report(outcome, config, *, non_blocking=False)`:**

  ```python
  from ac_guard.reporter import (
      report,                                      # the one dispatch entry
      ReportConfig,                                # unified delivery intent
      FormatKind,                                  # TEXT / MARKDOWN / JSON
      TerminalCfg, FileCfg, GitPlatformCfg,        # channel configs (tagged union)
      ChannelError, NoPrContextError,              # errors
  )
  ```

  `format_terminal` / `format_markdown` / `format_json` / `post_pr_comment` /
  the `TerminalChannel` / `FileChannel` / `GitPlatformChannel` classes are
  **no longer public API** — they are implementation details. Callers choose
  format and channel via `ReportConfig`; `core.report` picks the matching
  formatter + channel and delivers. Permitted `(channel, format)` combinations
  are validated upfront and raise `ValueError` on mismatches:

  |               | TEXT | MARKDOWN | JSON |
  |---------------|:----:|:--------:|:----:|
  | TerminalCfg   |  ✅  |    ❌    |  ✅  |
  | FileCfg       |  ✅  |    ✅    |  ✅  |
  | GitPlatformCfg|  ❌  |    ✅    |  ❌  |

  **Migration:**

  ```python
  # Old
  print(format_terminal(outcome, verbosity="quiet"))
  post_pr_comment(outcome, pr_report, locale="en")

  # New
  report(outcome, ReportConfig(channel=TerminalCfg(), format=FormatKind.TEXT))
  if pr_report.enabled:
      report(outcome, ReportConfig(
          channel=GitPlatformCfg(
              platform=pr_report.platform,
              token_env=pr_report.token_env,
              api_url=pr_report.api_url,
          ),
          format=FormatKind.MARKDOWN,
          locale="en",
      ), non_blocking=True)
  ```

  **`format_terminal` no longer takes `verbosity`**. One text rendering is
  produced (multi-line with `[PASS]/[FAIL]/[SKIP]` indicators + violation
  list + summary). Information-density decisions (e.g. whether to truncate
  in a Git-hook environment) belong to the caller, not the reporter.

  **Git-platform channel constructors take `GitPlatformCfg`** (not
  `PrReportConfig`). `PrReportConfig.enabled` is a CLI-layer concern (``if
  pr_report.enabled: report(..., non_blocking=True)``), not a channel
  concern. Third-party channel authors need to update their `__init__`
  type annotation.

- **New layer: `ac_guard.domain`** holds cross-module intermediate data
  contracts that flow between modules. `StageOutcome` / `CheckResult` /
  `Violation` move from `ac_guard.checker.models` to `ac_guard.domain.models`.
  `ac_guard.checker.models` becomes a backward-compatibility shim, so
  `from ac_guard.checker import StageOutcome` continues to work unchanged.

  Admission to `ac_guard.domain` is gated by four criteria (documented in
  `src/ac_guard/domain/__init__.py`): cross-module intermediate, pure data
  (dataclass, no I/O, stdlib-only), ≥2 non-test consumers, and PR-level
  change-impact review. This prevents the classical
  `shared`/`common`-module anti-pattern.

- **BREAKING — Reporter API restructure** following the same
  `deriving-module-api` methodology used for audit. Three axes (I / P /
  O: input / processing / channel) with format and channel treated as
  orthogonal dimensions. The public surface collapses to three pure
  rendering primitives plus a symmetric channel family.

  **L3 data model rename** (in `checker`, reused by reporter):
  - `ac_guard.checker.CheckReport` → `ac_guard.checker.StageOutcome`.
    One instance = one stage run (pre-commit / pre-push / ...). The
    old name suggested a rendered report, which clashed with reporter's
    own output.

  **Channel abstraction unified + symmetric**:
  - Every channel implements `output(payload: str) -> None` and is
    format-agnostic: it accepts an already-rendered string and delivers
    it to its physical destination.
  - `ReportChannel.send(markdown, config)` is replaced by
    `ReportChannel.output(payload)`; `config` moves to the constructor
    (`__init__(self, config)` for Git-platform channels).
  - `name` becomes a `ClassVar[str]` class attribute (not an abstract
    property), enabling registration without instantiation.
  - `get_channel(name)` now returns the channel **class**; callers
    construct instances with channel-specific arguments.

  **New channels** (auto-registered):
  - `TerminalChannel(stream=sys.stdout)` — print to a text stream.
  - `FileChannel(path)` — write to a local file.

  **Git-platform family factored via template method**:
  - `GitPlatformChannel` base class carries the shared token / repo
    resolution + HTTP POST flow. GitHub, GitLab, Gitea, and Bitbucket
    each implement only the six hooks that differ (DEFAULT_API_URL,
    REPO_ENV_VAR, `_resolve_pr`, `_post_url`, `_auth_headers`, and
    optionally `_encode_repo` / `_wrap_body`). Each concrete channel
    shrinks from ~150–200 lines to ~75–95 lines (with docstrings).

  **Module layout**:
  - New `ac_guard.reporter.channels/` subpackage. The old single-file
    modules moved and were renamed:
    - `reporter.channel_base` → `reporter.channels.base`
    - `reporter.channel_{github,gitlab,gitea,bitbucket}` →
      `reporter.channels.{github,gitlab,gitea,bitbucket}`
    - `reporter._http` → `reporter.channels._http`
    - `reporter._git_info` → `reporter.channels._git_info`
  - `_templates/` stays at `reporter/_templates/` — it is
    `formatting.py`'s resource, not a channel resource.
  - `post_pr_comment` now lives in `reporter.channels.git_platform`
    (with the base class) and is re-exported at `ac_guard.reporter`.

  **`format_gate` removed**:
  - Exit code is a business decision (block commit / push), not a
    report format, and now lives in the CLI.
  - `format_terminal`'s `"quiet"` verbosity now appends failing check
    names on failure (`"pre-commit: FAILED (lint, test)"`), preserving
    the information density gate output previously had.
  - Replacement:
    ```
    # before
    msg, code = format_gate(outcome)
    print(msg); sys.exit(code)

    # after
    print(format_terminal(outcome, verbosity="quiet"))
    sys.exit(0 if outcome.passed else 1)
    ```

  **Migration for third-party channels**:
  - Inherit `GitPlatformChannel` (not `ReportChannel`) for PR-comment
    channels — you get token + repo + HTTP for free and only implement
    six platform-specific hooks.
  - Rename `send(markdown, config)` → `output(payload)` and move `config`
    into `__init__`.
  - Replace `@property def name(...)` with a plain `name = "..."` class
    attribute.

  Top-level `ac_guard.reporter` public surface is now:
  `format_terminal`, `format_markdown`, `format_json`, `post_pr_comment`,
  `ChannelError` (5 names). The channel family is accessible via
  `ac_guard.reporter.channels`.

- **BREAKING — Audit module extracted** to an independent top-level
  module with a primitive-derived public API. Audit logging is no
  longer conceptually part of "reporter"; it now lives at
  `ac_guard.audit` with its own 4-primitive API derived via the
  `deriving-module-api` methodology (S/B/Q 9-dimensional analysis
  + coverage + minimality proof).

  **API rename**:
  - `ac_guard.reporter.audit.append_audit_log(record, root, path)` →
    `ac_guard.audit.append_record(record, root, path)`
  - `ac_guard.reporter.audit.apply_retention(root, path, retention_days=X)` →
    `ac_guard.audit.prune_by_age(root, path, max_age_days=X)`

  **New primitives exposed**:
  - `iter_records(root, path) -> Iterator[dict]` — streaming read.
  - `rewrite_records(records, root, path) -> None` — **atomic**
    full-file replacement (temp + `os.replace`), crash-safe.

  **Other changes**:
  - `prune_by_age` and `rewrite_records` now use atomic writes;
    partial-state corruption on mid-write crash is no longer
    possible.
  - `reporter/__init__.py` no longer re-exports `append_audit_log`
    / `apply_retention`.

  **Migration**:
  ```
  reporter.audit   → audit
  append_audit_log → append_record
  apply_retention(..., retention_days=X) → prune_by_age(..., max_age_days=X)
  ```
  See `src/ac_guard/audit/__init__.py` for responsibility contract
  and derivation rationale.

### Added

- ac-guard is now self-hosted via dogfooding on its own repository.
  The repo ships a committed `guard.yaml` and runs its commit gate
  through `ac-guard install --agent claude-code`; ruff format / lint
  live inside the ac-guard managed block of `.pre-commit-config.yaml`,
  while interrogate, bandit, import-linter, conventional-pre-commit
  and the pre-commit-hooks hygiene suite sit outside the block and
  survive every regeneration (see
  [#73](https://github.com/ikroal/ai-code-guard/issues/73) and
  [#74](https://github.com/ikroal/ai-code-guard/issues/74)).
- `.pre-commit-config.yaml` now participates in the managed-block
  preservation mechanism via YAML-safe `# AI-GUARD:BEGIN` / `# AI-GUARD:END`
  markers. Projects can add their own pre-commit repos outside the block
  and `ac-guard install` / `ac-guard update` will leave them untouched
  while regenerating the ac-guard-owned hooks inside.
  ([#113](https://github.com/ikroal/ai-code-guard/issues/113))
- Default `execute.forbidden` picks up four more hardening rules on
  top of the `--no-verify` family: `CI=<val> git commit/push`
  (CI env-var bypass), `--force-with-lease`, short `-f`, and the
  `<remote> +<branch>` shorthand — all scoped to `main` / `master`.
  ([#105](https://github.com/ikroal/ai-code-guard/issues/105))
- Enforcer escalates `git commit` to `ask` when the repository has no
  pre-commit hook installed, with guidance to run `ac-guard install`
  or `pre-commit install` — no silent auto-install.
  ([#106](https://github.com/ikroal/ai-code-guard/issues/106))
- `check`, `verify`, and `gate run` now auto-dispatch `post_pr_comment`
  when `output.pr_report.enabled: true`, closing the last mile of the
  PR-report feature (previously callers had to invoke the primitive by
  hand). A new `NoPrContextError` (subclass of `ChannelError`) is raised
  by every channel when no PR/MR can be identified; `post_pr_comment`
  silently skips in that case, so enabling `pr_report` in a shared
  `guard.yaml` does not produce warnings on local branches. Real
  failures (missing token, HTTP 5xx, unresolvable repo) continue to log
  a stderr warning without affecting exit code.
  ([#66](https://github.com/ikroal/ai-code-guard/issues/66))

### Removed

- Empty `ac_guard.templates` package dropped. The directory only ever
  contained an empty `__init__.py` and had zero code or test references;
  the real Jinja templates live in each feature module's private
  `_templates/` (`cli/_templates`, `generator/_templates`,
  `adapters/_templates`, `reporter/_templates`). `.importlinter` layer
  spec updated to drop the stale `templates` leaf.

### Fixed

- Default system `execute.forbidden` now covers four additional
  hook-bypass patterns on top of `--no-verify`:
  `SKIP=<id> git commit/push` (pre-commit env-var bypass),
  `git -c core.hooksPath=…` (one-shot hook-path override),
  `git config core.hooksPath <path>` (permanent override — read/unset
  forms still pass through), and `git rebase --exec/-x` (arbitrary
  command execution inside rebase). All four ship as `regex`
  rules with `_source: system` and remain user-removable via the
  standard `behavior.execute.forbidden.remove` escape hatch.
  ([#104](https://github.com/ikroal/ai-code-guard/issues/104))
- Built-in `commit.format` / `push.lint` shortcuts now invoke the
  language-specific hook IDs (`format-<lang>` / `lint-<lang>`) that the
  Generator actually emits, so `ac-guard check` passes out of the box for
  every preset. ([#92](https://github.com/ikroal/ai-code-guard/issues/92))
- `git commit --no-verify` and `git push --no-verify` are now added to
  `execute.forbidden` as system rules, matching the README's "the agent
  cannot skip the gate" promise.
  ([#93](https://github.com/ikroal/ai-code-guard/issues/93))
- Rule-document files (`CLAUDE.md`, `AGENTS.md`,
  `.cursor/rules/behavior.mdc`, `.kilocode/rules/behavior.md`,
  `.github/copilot-instructions.md`) no longer accumulate duplicate
  `<!-- AI-GUARD:BEGIN -->` / `<!-- AI-GUARD:END -->` markers on each
  `ac-guard update`. Adapters now return raw Markdown and the writer
  layer owns wrapping. `.mdc` files are wrapped alongside `.md`.
  ([#94](https://github.com/ikroal/ai-code-guard/issues/94))
- Push-stage build is now a precondition: when `build` fails, `lint`
  and `push.checks` are no longer executed — they are reported as
  `skipped` with `Skipped: build failed`. Prevents wasted CI time and
  matches the design doc §6.5.3 intent.
  ([#77](https://github.com/ikroal/ai-code-guard/issues/77))
- `output.locale` is now honored by the terminal formatter. Setting
  `output.locale: zh-CN` in `guard.yaml` switches the stage heading,
  summary line, and total-time label to Chinese; `[PASS]` / `[FAIL]`
  / `[SKIP]` indicators stay ASCII for alignment. Unknown locales
  fall back to English.
  ([#76](https://github.com/ikroal/ai-code-guard/issues/76))
- Audit logging is now actually written. Enforcer `evaluate()`
  appends a JSON record to `.ac-guard/audit.jsonl` per policy
  decision when `output.audit.enabled: true`, capturing timestamp /
  agent / tool / operation / scheme / target / decision / reason /
  matched_rule / policy_hash. `apply_retention()` is called at the
  end of `ac-guard install` / `ac-guard update` so the
  `output.audit.retention` field takes effect.
  ([#75](https://github.com/ikroal/ai-code-guard/issues/75))

### Changed

- **Breaking**: the Enforcer runtime cache file has been renamed from
  `.ac-guard/policy.json` to `.ac-guard/runtime.json`. The file now
  carries both behavior rules and audit config, so the new name
  reflects that. `ac-guard install` / `update` delete the legacy
  `policy.json` automatically on first run.
- `code.commit.naming` is now a no-op that the checker surfaces as a
  `[SKIP]` result — the shortcut is reserved for a follow-up release
  ([#95](https://github.com/ikroal/ai-code-guard/issues/95)). The
  `standard` and `strict` presets no longer opt in by default.
- When `guard.yaml` declares `project.language` but omits `languages`,
  the merger auto-populates the tool mapping from
  `defaults/languages.yaml` so built-in `format` / `lint` shortcuts work
  without extra configuration.
- Generated Claude Code / OpenCode / Cursor hook scripts keep their
  trailing newline, so the very first `ac-guard check` run no longer
  trips `black` / `prettier`.

## [0.1.0] - 2026-0X-XX

首个公开预览版本。核心能力覆盖 AI Agent 看护系统的两条主线：
**运行时行为拦截**（`pre_tool_use` hook + Enforcer）
与 **代码质量门禁**（`pre-commit` / `pre-push` Checker）。

First public preview. Covers the two pillars of AI agent guardianship:
**runtime behavior interception** (`pre_tool_use` hook + Enforcer)
and **code-quality gates** (`pre-commit` / `pre-push` Checker).

### Added

**Config & Generator (M1)**

- `guard.yaml` schema, loader, validator, and multi-source merger. (#2, #3, #4)
- Generator core with six artifact primitives G1–G6: rule docs, hooks, tool configs, pre-commit manifests, scripts, and auxiliary files. (#5, #6, #7)
- `AgentAdapter` ABC and five adapters: Claude Code, Cursor, Windsurf, GitHub Copilot, Gemini CLI. (#8)
- CLI commands: `init`, `install`, `update`, `uninstall`, `status`, `doctor`, `agents`, `version`. (#9, #10, #11)

**Enforcer & Hooks (M2)**

- Pattern matching engine supporting glob + regex across paths and commands. (#13)
- Core decision engine with `allow` / `deny` / `ask` three-state policy output. (#14)
- Hook script templates integrated with Enforcer. (#15)
- Audit logging infrastructure and `PolicyDecision` type. (#16)

**Checker & Reporter (M3)**

- Checker orchestration module coordinating `commit` and `push` stages. (#18)
- Reporter with terminal output and Markdown rendering. (#19)
- CLI commands: `check`, `verify`, `run`, `gate`. (#20)

**Ruleset Management (M4)**

- Ruleset `fetch` with local cache and checksum verification. (#45)
- `checks/` script copying and `files/` skip semantics. (#46)
- CLI commands: `ruleset list`, `ruleset show`. (#47)

**PR Report & Polish (M5)**

- `ReportChannel` abstract base and GitHub implementation. (#49)
- GitLab, Gitea, and Bitbucket channels with smart PR detection. (#50)
- Global `--format json` output mode for `check`, `verify`, and `status`. (#51)
- `validation list` and `validation report` commands. (#52)

**Release Pipeline (partial M6)**

- PyPI packaging via hatchling with full project metadata and classifiers. (#68, PR #87)
- GitHub Actions release workflow using PyPI Trusted Publisher. (#68, PR #87)

### Changed

- CLI executable renamed from `guard` to `ac-guard` for better discoverability and to avoid naming collisions. The `guard.yaml` config filename and the `ac_guard` Python package name are unchanged. (PR #87, PR #88)
- Project branding unified as **ac-guard** (AI Code Guard). (PR #88, PR #89)

### Known Limitations

- `post_pr_comment` is not yet invoked automatically by the CLI; call it manually from CI for now. ([#66](https://github.com/ikroal/ai-code-guard/issues/66))
- HTTP requests have no retry/backoff; transient network failures surface directly. ([#67](https://github.com/ikroal/ai-code-guard/issues/67))
- `code.commit.naming: true` is accepted but produces a `[SKIP]` result — a concrete naming check implementation is planned in a follow-up. ([#95](https://github.com/ikroal/ai-code-guard/issues/95))

[Unreleased]: https://github.com/ikroal/ai-code-guard/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ikroal/ai-code-guard/releases/tag/v0.1.0
