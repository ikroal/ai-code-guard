![CI](https://github.com/ikroal/ai-code-guard/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-624%20passed-brightgreen)

# AI Guard

**Guardrails for AI coding agents — behavior constraints + code quality gates, one config for all agents.**

[English](README.md) | [中文](README_zh.md)

---

AI coding agents (Claude Code, Cursor, OpenCode, Copilot, etc.) can autonomously read files, write code, and execute shell commands. Without guardrails, they can force-push, access secrets, skip hooks, or introduce quality regressions.

**AI Guard** provides a unified system that:

- **Intercepts dangerous operations at runtime** via agent-native hooks (deny force-push, block secret access, require approval for config changes)
- **Enforces code quality gates** at commit and push time (formatting, linting, naming conventions, custom checks)
- **Works across all major AI agents** from a single `guard.yaml` configuration file

## Quick Start

```bash
# Install
pip install ai-guard

# Initialize configuration
guard init --language python

# Install guardrails for your AI agent
guard install --agent claude-code

# Check code quality
guard check
```

## How It Works

```
guard.yaml (single source of truth)
    |
    +---> Generator ---> Rule docs (CLAUDE.md, .cursor/rules/, ...)
    |                 +-> Hook scripts (interceptor.py, check.sh, ...)
    |                 +-> .pre-commit-config.yaml
    |                 +-> .ai-guard/policy.json
    |
    +---> Enforcer (runtime) ---> allow / deny / ask
    |         reads policy.json
    |         matches patterns (glob + regex)
    |         fail-closed on errors
    |
    +---> Checker (commit/push) ---> PASS / FAIL
              format + naming + lint
              custom checks
              build verification
```

## Supported Agents

| Agent | Runtime Interception | Code Quality Gates | Rule Doc |
|-------|---------------------|-------------------|----------|
| **Claude Code** | Hook (deny + ask) | Full | `CLAUDE.md` |
| **Cursor** | Hook (deny only) | Full | `.cursor/rules/behavior.mdc` |
| **OpenCode** | Plugin (deny + ask) | Full | `AGENTS.md` |
| **GitHub Copilot** | Rule doc only | Full | `.github/copilot-instructions.md` |
| **KiloCode** | Rule doc only | Full | `.kilocode/rules/behavior.md` |

**Runtime interception** means the agent's hook system blocks forbidden operations before they execute. Agents without hook support still receive behavior rules in their rule documents as soft constraints.

## Configuration

All rules live in `guard.yaml`:

```yaml
version: 1
project:
  name: my-project
  language: python

behavior:
  write:
    forbidden:
      - pattern: "file:.git/**"
        reason: "Git internals are read-only"
      - pattern: "file:**/.env"
        reason: "Secret files must not be modified"
    require_approval:
      - pattern: "file:.github/workflows/**"
        message: "CI config changes need review"
    allow:
      - pattern: "file:src/**"
      - pattern: "file:tests/**"
  execute:
    forbidden:
      - pattern: "shell:git push --force*"
        reason: "Force push is not allowed"
      - pattern: "shell:git commit --no-verify*"
        reason: "Cannot skip hooks"

code:
  commit:
    format: true
    naming: true
    checks:
      license-header:
        command: "./scripts/check-license.sh"
        types: [python]
  push:
    lint: true
    checks:
      test:
        command: "pytest --cov"
        pass_filenames: false
```

### Pattern Syntax

Patterns use `{scheme}:{glob_or_regex}` format:

| Scheme | Resource | Example |
|--------|----------|---------|
| `file:` | File paths | `file:**/.env`, `file:.git/**` |
| `shell:` | Shell commands | `shell:git push --force*` |
| `mcp:` | MCP tools | `mcp:memory:delete_*` |
| `web:` | Web URLs | `web:*.internal.com` |

Default matching is **glob** (`*` and `**`). Add `regex: true` for regex:

```yaml
- pattern: "shell:git\\s+push\\s+--force.*"
  regex: true
```

### Three-Tier Decision Logic

```
forbidden       --> DENY   (blocks the operation)
require_approval --> ASK    (prompts for confirmation)
allow           --> ALLOW  (explicitly permits)
no match        --> ALLOW  (default)
```

Priority: forbidden > require_approval > allow > default.

## CLI Commands

### Lifecycle

| Command | Description |
|---------|-------------|
| `guard init --language <lang>` | Generate `guard.yaml` from presets (minimal/standard/strict) |
| `guard install --agent <name>` | Generate rule docs, hooks, and configs for agents |
| `guard update` | Regenerate all artifacts after config changes |
| `guard uninstall` | Remove all generated artifacts |

### Code Quality

| Command | Description |
|---------|-------------|
| `guard check [--files ...]` | Run commit-stage checks (format + naming + custom) |
| `guard verify [--skip-build]` | Run full push-stage validation |
| `guard run <name>` | Run a single named check |
| `guard gate run --stage <stage>` | Git hook entry point (minimal output) |

### Diagnostics

| Command | Description |
|---------|-------------|
| `guard status [--rules]` | Installation state, drift detection, artifact integrity |
| `guard doctor` | Environment diagnostics (Python, Git, pre-commit) |
| `guard agents` | Agent capability matrix with install status |
| `guard version` | Print version |

## Architecture

```
src/ai_guard/
  config/      Load, validate, merge guard.yaml
  generator/   Produce rule docs, hooks, tool configs, git hooks
  adapters/    Agent-specific rendering (5 adapters)
  enforcer/    Runtime pattern matching + policy decisions
  checker/     Commit/push check orchestration
  reporter/    Audit logging + terminal/Markdown/gate formatting
  cli/         Typer CLI with 13 commands
```

### Key Design Decisions

- **Fail-closed**: Enforcer errors default to deny (not allow)
- **Generation vs. execution**: All config parsing happens at `install` time; runtime hooks only evaluate pre-built policy
- **Exit-code only**: Checks pass or fail based on exit code, no output parsing
- **Non-blocking audit**: Audit log failures never affect policy decisions
- **Agent-agnostic core**: Enforcer and Checker know nothing about specific agents

## Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests (624 tests)
pytest

# Lint
ruff check .

# Pre-commit hooks
pre-commit install
pre-commit install --hook-type commit-msg
```

### Project Status

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 | Config + Generator + CLI | Done |
| Phase 2 | Enforcer + Agent Bridge | Done |
| Phase 3 | Checker + Reporter | Done |
| Phase 4 | Ruleset Management | Planned |
| Phase 5 | PR Report & Polish | Planned |

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`feat/your-feature`)
3. Follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages
4. Ensure `pytest` passes and `ruff check .` is clean
5. Open a pull request

## License

[MIT License](LICENSE)
