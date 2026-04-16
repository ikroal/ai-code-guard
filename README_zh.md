![CI](https://github.com/ikroal/ai-code-guard/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![License](https://img.shields.io/badge/license-MIT-green)

# AI Guard

AI 编码 Agent 的看护系统。一份 `guard.yaml` 约束行为并保障代码质量，适配 Claude Code、Cursor、OpenCode、Copilot 和 KiloCode。

一个配置文件替代分散的 Agent 规则文档、零散的 Hook 脚本和手动的 pre-commit 配置。

- **运行时拦截** — Agent Hook 在操作执行前阻止危险行为（强制推送、密钥访问、配置篡改）
- **代码质量门禁** — 提交和推送时自动执行格式化、Lint、命名和自定义检查
- **防绕过保护** — Agent 无法修改自身约束、禁用 Hook 或跳过检查
- **5 个 Agent，1 份配置** — `guard.yaml` 生成各 Agent 专属的规则文档、Hook 脚本、pre-commit 配置和策略文件

## 安装

```bash
pip install ai-guard
```

## 快速开始

```bash
guard init --language python          # 创建 guard.yaml
guard install --agent claude-code     # 生成规则 + hooks
guard check                           # 运行质量检查
```

## 支持的 Agent

| Agent | 运行时 Hook | 代码质量 | 规则文档 |
|-------|:---:|:---:|---|
| Claude Code | deny + ask | 是 | `CLAUDE.md` |
| Cursor | deny | 是 | `.cursor/rules/behavior.mdc` |
| OpenCode | deny + ask | 是 | `AGENTS.md` |
| GitHub Copilot | — | 是 | `.github/copilot-instructions.md` |
| KiloCode | — | 是 | `.kilocode/rules/behavior.md` |

有运行时 Hook 的 Agent 在操作执行前拦截。没有 Hook 的 Agent 通过规则文档获得行为约束。所有 Agent 都有 pre-commit 质量门禁。

## 配置

```yaml
behavior:
  write:
    forbidden:
      - pattern: "file:.git/**"
      - pattern: "file:**/.env"
    require_approval:
      - pattern: "file:guard.yaml"
  execute:
    forbidden:
      - pattern: "shell:git push --force*"
      - pattern: "shell:git commit --no-verify*"

code:
  commit:
    format: true
    naming: true
  push:
    lint: true
```

模式使用 `{scheme}:{glob}` 格式 — `file:`、`shell:`、`mcp:`、`web:`。添加 `regex: true` 启用正则。

规则按优先级求值：**forbidden**（阻止）> **require_approval**（询问用户）> **allow** > 默认放行。

完整配置参见 [guard.yaml 参考](design/AI_GUARD_SYSTEM_DESIGN.md)。

## 命令

| 命令 | 说明 |
|------|------|
| `guard init` | 从预设生成 `guard.yaml` |
| `guard install --agent <name>` | 生成规则、Hook 和配置 |
| `guard update` | 配置变更后重新生成 |
| `guard uninstall` | 移除生成的产物 |
| `guard check` | 运行提交阶段检查 |
| `guard verify` | 运行推送阶段验证 |
| `guard run <name>` | 运行单项检查 |
| `guard gate run --stage <s>` | Git Hook 入口 |
| `guard status` | 安装状态与漂移检测 |
| `guard doctor` | 环境诊断 |
| `guard agents` | Agent 能力矩阵 |

## 工作原理

`guard install` 读取 `guard.yaml` 并一次性生成所有产物 — 规则文档、Hook 脚本、`.pre-commit-config.yaml` 和 `.ai-guard/policy.json`。运行时不做配置解析。

Agent 工作时，Hook 脚本加载预构建的策略文件，将每个操作与规则匹配。禁止的操作被阻止，需要审批的操作提示用户确认，其余放行。每次决策记录到 `.ai-guard/audit.jsonl`。

提交和推送时，pre-commit Hook 运行格式化、Lint、命名和自定义检查。Agent 无法跳过这些检查，因为 `git commit --no-verify` 本身就是被禁止的模式。

## 开发

```bash
pip install -e ".[dev]"
pytest                    # 624 个测试
ruff check .
```

## 许可证

[MIT](LICENSE)
