![CI](https://github.com/ikroal/ai-code-guard/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-624%20passed-brightgreen)

# AI Guard

**AI 编码 Agent 看护系统 — 行为约束 + 代码质量门禁，一份配置适配所有 Agent。**

[English](README.md) | [中文](README_zh.md)

---

AI 编码 Agent（Claude Code、Cursor、OpenCode、Copilot 等）能够自主读写文件、执行命令和生成代码。没有护栏的情况下，它们可能会强制推送、访问密钥、跳过检查或引入质量退化。

**AI Guard** 提供统一的看护系统：

- **运行时拦截危险操作** — 通过 Agent 原生 Hook 阻止强制推送、封禁密钥访问、需要审批才能修改配置
- **提交/推送时执行代码质量门禁** — 自动检查格式化、Lint、命名规范和自定义检查项
- **一份配置适配所有主流 AI Agent** — 单一 `guard.yaml` 驱动全部规则生成

## 快速开始

```bash
# 安装
pip install ai-guard

# 初始化配置
guard init --language python

# 为 AI Agent 安装护栏
guard install --agent claude-code

# 检查代码质量
guard check
```

## 工作原理

```
guard.yaml（单一配置源）
    |
    +---> Generator ---> 规则文档 (CLAUDE.md, .cursor/rules/, ...)
    |                 +-> Hook 脚本 (interceptor.py, check.sh, ...)
    |                 +-> .pre-commit-config.yaml
    |                 +-> .ai-guard/policy.json
    |
    +---> Enforcer（运行时）---> allow / deny / ask
    |         读取 policy.json
    |         模式匹配（glob + regex）
    |         错误时 fail-closed
    |
    +---> Checker（提交/推送时）---> PASS / FAIL
              格式化 + 命名 + Lint
              自定义检查
              构建验证
```

## 支持的 Agent

| Agent | 运行时拦截 | 代码质量门禁 | 规则文档 |
|-------|-----------|------------|---------|
| **Claude Code** | Hook（deny + ask） | 完整 | `CLAUDE.md` |
| **Cursor** | Hook（仅 deny） | 完整 | `.cursor/rules/behavior.mdc` |
| **OpenCode** | Plugin（deny + ask） | 完整 | `AGENTS.md` |
| **GitHub Copilot** | 仅规则文档 | 完整 | `.github/copilot-instructions.md` |
| **KiloCode** | 仅规则文档 | 完整 | `.kilocode/rules/behavior.md` |

**运行时拦截** 指 Agent 的 Hook 系统在操作执行前阻止禁止的操作。不支持 Hook 的 Agent 仍会在规则文档中收到行为约束作为软约束。

## 配置

所有规则集中在 `guard.yaml`：

```yaml
version: 1
project:
  name: my-project
  language: python

behavior:
  write:
    forbidden:
      - pattern: "file:.git/**"
        reason: "Git 内部文件只读"
      - pattern: "file:**/.env"
        reason: "密钥文件禁止修改"
    require_approval:
      - pattern: "file:.github/workflows/**"
        message: "CI 配置变更需要审批"
    allow:
      - pattern: "file:src/**"
      - pattern: "file:tests/**"
  execute:
    forbidden:
      - pattern: "shell:git push --force*"
        reason: "禁止强制推送"
      - pattern: "shell:git commit --no-verify*"
        reason: "禁止跳过 hooks"

code:
  commit:
    format: true
    naming: true
  push:
    lint: true
    checks:
      test:
        command: "pytest --cov"
        pass_filenames: false
```

### 模式语法

模式使用 `{scheme}:{glob_or_regex}` 格式：

| Scheme | 资源类型 | 示例 |
|--------|---------|------|
| `file:` | 文件路径 | `file:**/.env`, `file:.git/**` |
| `shell:` | Shell 命令 | `shell:git push --force*` |
| `mcp:` | MCP 工具 | `mcp:memory:delete_*` |
| `web:` | Web URL | `web:*.internal.com` |

默认使用 **glob** 匹配。添加 `regex: true` 启用正则：

```yaml
- pattern: "shell:git\\s+push\\s+--force.*"
  regex: true
```

### 三层决策逻辑

```
forbidden        --> DENY   （阻止操作）
require_approval --> ASK    （提示确认）
allow            --> ALLOW  （显式许可）
无匹配            --> ALLOW  （默认放行）
```

优先级：forbidden > require_approval > allow > 默认。

## CLI 命令

### 生命周期

| 命令 | 说明 |
|------|------|
| `guard init --language <lang>` | 从预设生成 `guard.yaml`（minimal/standard/strict） |
| `guard install --agent <name>` | 为 Agent 生成规则文档、Hook 脚本和配置 |
| `guard update` | 配置变更后重新生成所有工件 |
| `guard uninstall` | 移除所有生成的工件 |

### 代码质量

| 命令 | 说明 |
|------|------|
| `guard check [--files ...]` | 运行提交阶段检查（format + naming + 自定义） |
| `guard verify [--skip-build]` | 运行完整推送阶段验证 |
| `guard run <name>` | 运行单个指定检查项 |
| `guard gate run --stage <stage>` | Git Hook 内部入口（精简输出） |

### 诊断

| 命令 | 说明 |
|------|------|
| `guard status [--rules]` | 安装状态、配置漂移检测、工件完整性 |
| `guard doctor` | 环境诊断（Python、Git、pre-commit） |
| `guard agents` | Agent 能力矩阵与安装状态 |
| `guard version` | 打印版本号 |

## 架构

```
src/ai_guard/
  config/      加载、验证、合并 guard.yaml
  generator/   生成规则文档、Hook 脚本、工具配置、Git Hooks
  adapters/    Agent 适配器（5 个实现）
  enforcer/    运行时模式匹配与策略决策
  checker/     提交/推送检查编排
  reporter/    审计日志 + 终端/Markdown/Gate 格式化
  cli/         Typer CLI（13 个命令）
```

### 核心设计决策

- **Fail-closed**：Enforcer 异常默认 deny（非 allow）
- **生成与执行分离**：所有配置解析在 `install` 时完成；运行时 Hook 仅评估预构建的 policy
- **仅判断退出码**：检查项通过/失败仅基于命令退出码，不解析输出
- **非阻塞审计**：审计日志写入失败不影响策略决策
- **Agent 无关核心**：Enforcer 和 Checker 不感知具体 Agent

## 开发

```bash
# 开发模式安装
pip install -e ".[dev]"

# 运行测试（624 个测试）
pytest

# Lint
ruff check .

# Pre-commit Hooks
pre-commit install
pre-commit install --hook-type commit-msg
```

### 项目状态

| 阶段 | 范围 | 状态 |
|------|------|------|
| Phase 1 | Config + Generator + CLI | 已完成 |
| Phase 2 | Enforcer + Agent Bridge | 已完成 |
| Phase 3 | Checker + Reporter | 已完成 |
| Phase 4 | Ruleset 管理 | 规划中 |
| Phase 5 | PR 报告 & 完善 | 规划中 |

## 参与贡献

欢迎贡献！请遵循：

1. Fork 仓库
2. 创建功能分支（`feat/your-feature`）
3. 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/)
4. 确保 `pytest` 通过且 `ruff check .` 无报错
5. 提交 Pull Request

## 许可证

[MIT License](LICENSE)
