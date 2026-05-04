

---
globs: **/*
---

## Behavior Constraints

The following rules define what operations are permitted, blocked, or require approval.

### Read Operations

**Forbidden** (blocked):
- `file:.env*` — environment files contain secrets

> **Note**: This Agent does not support user confirmation prompts.
> Require-approval rules are treated as forbidden.

**Require Approval** → **Blocked** (no ask capability):
- `file:**/credentials.json` — contains credentials, confirm before reading

**Allowed** (permitted):
- `file:**/*.py`

### Write Operations

**Forbidden** (blocked):
- `file:.git/**` — repo internals must not be edited

> **Note**: This Agent does not support user confirmation prompts.
> Require-approval rules are treated as forbidden.

**Require Approval** → **Blocked** (no ask capability):
- `file:pyproject.toml` — dependency change — confirm intent

### Execute Operations

**Forbidden** (blocked):
- `^rm\s+-rf\s+/` — filesystem destruction

> **Note**: This Agent does not support user confirmation prompts.
> Require-approval rules are treated as forbidden.

**Require Approval** → **Blocked** (no ask capability):
- `shell:git push --force*` — rewrites remote history

**Allowed** (permitted):
- `shell:pytest *`
