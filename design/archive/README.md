# Archived Design Documents

This directory contains deprecated design documents from earlier iterations of AI Guard.

These documents are preserved for historical reference only. The current authoritative design is:

- **System Design**: `../AI_GUARD_SYSTEM_DESIGN.md`
- **Architecture Style Analysis**: `../ARCHITECTURE_STYLE_ANALYSIS.md`

## Archived Files

| File | Version | Status | Description |
|---|---|---|---|
| `AI_GUARD_DESIGN.md` | v2.0 | Deprecated | Initial detailed design with code examples |
| `AI_GUARD_DESIGN.md.backup` | v2.0 | Deprecated | Backup of v2.0 design |
| `AI_GUARD_DESIGN_v3.md` | v3.1 | Deprecated | Architecture-focused redesign |
| `AI_GUARD_DESIGN_v3.md.bak` | v3.1 | Deprecated | Backup of v3.1 design |

## Why Deprecated

The v2 and v3 designs were superseded by a complete redesign based on:
- Critical review of layered architecture applicability (see `ARCHITECTURE_STYLE_ANALYSIS.md`)
- Adoption of "shared modules + command orchestration" pattern
- Unified configuration system (guard.yaml) with simplified schema
- Comprehensive requirements analysis and module design

**Do not use these documents as implementation references.**
