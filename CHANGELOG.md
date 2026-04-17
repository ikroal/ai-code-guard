# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

本项目变更记录遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/) 格式与 [语义化版本](https://semver.org/lang/zh-CN/spec/v2.0.0.html)。

## [Unreleased]

### Fixed

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

### Changed

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

- Audit logging is not yet wired into every Enforcer call path. ([#75](https://github.com/ikroal/ai-code-guard/issues/75))
- `output.locale` is not propagated to every formatter. ([#76](https://github.com/ikroal/ai-code-guard/issues/76))
- Push-stage build failure does not fail-fast as aggressively as commit-stage. ([#77](https://github.com/ikroal/ai-code-guard/issues/77))
- `post_pr_comment` is not yet invoked automatically by the CLI; call it manually from CI for now. ([#66](https://github.com/ikroal/ai-code-guard/issues/66))
- HTTP requests have no retry/backoff; transient network failures surface directly. ([#67](https://github.com/ikroal/ai-code-guard/issues/67))
- `code.commit.naming: true` is accepted but produces a `[SKIP]` result — a concrete naming check implementation is planned in a follow-up. ([#95](https://github.com/ikroal/ai-code-guard/issues/95))

[Unreleased]: https://github.com/ikroal/ai-code-guard/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ikroal/ai-code-guard/releases/tag/v0.1.0
