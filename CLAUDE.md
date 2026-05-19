<!-- AI-GUARD:BEGIN -->



## Behavior Constraints

The following rules define what operations are permitted, blocked, or require approval.

### Read Operations



### Write Operations

**Forbidden** (blocked):
- `file:.env*` — Environment files contain secrets- `file:**/credentials*` — Credential files are protected- `file:**/*.pem` — Private keys must not be checked in

**Require Approval** (ask user):
- `file:.importlinter` — Editing the import-linter contract changes module layering- `file:scripts/**` — scripts/ contains guard infrastructure (lint checkers etc.); edits weaken enforcement- `file:guard.yaml`- `file:.ac-guard/**`- `file:.pre-commit-config.yaml`- `file:.git/hooks/**`

### Execute Operations

**Forbidden** (blocked):
- `shell:git commit --no-verify*` — --no-verify skips pre-commit checks- `shell:git push --no-verify*` — --no-verify skips pre-push checks- `shell:SKIP=\S+\s+git\s+(?:commit|push)\b.*` — SKIP= env-var bypasses pre-commit hooks- `shell:git\s+.*-c\s+core\.hooks[Pp]ath=\S+.*` — git -c core.hooksPath overrides the hook path- `shell:(?i)git\s+config\s.*core\.hookspath\s+\S+.*` — git config core.hooksPath permanently overrides the hook path- `shell:git\s+rebase\s+.*(?:--exec|-x\s+).*` — git rebase --exec can run arbitrary commands bypassing per-commit hooks- `shell:CI=\S+\s+git\s+(?:commit|push)\b.*` — CI= env-var can trick tools into skipping pre-commit checks- `shell:git\s+push\s+.*--force(?:-with-lease)?\b.*\b(?:main|master)\b.*` — force push to protected branch rewrites shared history- `shell:git\s+push\s+.*\b(?:main|master)\b.*--force(?:-with-lease)?\b.*` — force push to protected branch rewrites shared history- `shell:git\s+push\s+.*-f\b.*\b(?:main|master)\b.*` — force push (-f) to protected branch rewrites shared history- `shell:git\s+push\s+\S+\s+\+(?:main|master)\b.*` — git push <remote> +<branch> is an alias for force push to the protected branch



<!-- AI-GUARD:END -->
