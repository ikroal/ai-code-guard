# AI Guard 系统设计文档

> **版本**: v1.0  
> **状态**: 设计定稿  
> **日期**: 2026-04-13  
> **摘要**: 本文档描述 AI Guard 系统的完整设计方案。AI Guard 是一个面向 AI 编码 Agent 的看护系统，通过双维度约束模型（运行时行为拦截与提交期代码验证）为 AI 辅助编码过程建立安全与质量保障体系。文档涵盖业界调研、需求分析、架构设计、配置系统、模块设计、接口定义、数据模型、运维方案、测试策略及演进规划。

---

## 目录

- [1. 引言](#1-引言)
- [2. 业界调研与相关工作](#2-业界调研与相关工作)
- [3. 需求分析](#3-需求分析)
- [4. 架构设计](#4-架构设计)
- [5. 配置系统设计](#5-配置系统设计)
- [6. 模块详细设计](#6-模块详细设计)
- [7. 接口设计](#7-接口设计)
- [8. 数据模型设计](#8-数据模型设计)
- [9. 部署与运维设计](#9-部署与运维设计)
- [10. 测试策略](#10-测试策略)
- [11. 演进规划](#11-演进规划)
- [附录](#附录)

---

## 1. 引言

### 1.1 背景与动机

大语言模型（LLM）驱动的 AI 编码 Agent（如 Claude Code、Cursor、OpenCode 等）正在深刻改变软件开发流程。这些 Agent 具备文件读写、命令执行、代码生成等能力，能够显著提升开发效率。然而，Agent 的高度自主性也带来了两类系统性风险：

**行为风险**。AI Agent 可能执行超出预期的操作，包括但不限于：修改敏感配置文件、执行破坏性命令（如 `git push --force`）、绕过代码检查机制（如 `git commit --no-verify`）、访问受限资源等。这些行为在缺乏约束的环境中难以被及时发现和阻止。

**质量风险**。AI 生成的代码可能不符合项目编码规范（命名、格式、文档要求），引入架构层面的耦合（违反模块依赖规则），或缺少充分的测试覆盖。这些质量问题在 AI 高速生成代码的背景下尤为突出——人工 Review 的速度难以匹配 AI 的产出速度。

当前，开发者通常依赖以下手段应对上述风险：手动配置各 Agent 的规则文件（如 CLAUDE.md、.cursor/rules/）、依赖 Agent 自身的权限系统、以及依靠人工 Code Review。这些手段存在三个共性缺陷：**规则分散**（不同 Agent 各自维护，难以统一）、**缺乏强制性**（规则文档仅为引导，不具备拦截能力）、**无法复用**（项目间无法共享规则集）。

AI Guard 正是为解决上述问题而设计的系统。

### 1.2 系统定位与目标

AI Guard 是一个面向 AI 编码 Agent 的**看护系统**（Guardian System），旨在通过统一的配置驱动，为 AI 辅助编码过程建立完整的安全与质量保障体系。

系统的核心目标包括：

1. **行为可控**：在 AI Agent 的工具调用发生前进行策略判定，对危险操作实施拦截或要求用户确认。
2. **质量可验**：在代码提交和推送阶段自动执行规范检查与质量验证，确保入库代码满足项目标准。
3. **配置统一**：以单一配置文件（guard.yaml）驱动所有 Agent 的规则生成、行为约束和检查编排。
4. **多端适配**：一份配置适配多个 AI Agent，屏蔽不同 Agent 的 Hook 机制差异。
5. **可审计**：记录 AI Agent 的操作决策日志，支持事后追溯与合规审查。

### 1.3 系统边界

**系统负责的范畴**：

- 行为约束：基于策略的运行时工具调用拦截（Read/Write/Execute 维度）
- 代码看护：提交前静态检查与推送前动态验证的编排与结果收集
- 配置管理：配置加载、多源合并、Schema 校验
- 工件生成：规则文档、Hook 脚本、工具配置、Git Hook 等工件的自动化生成
- Agent 适配：将统一的策略转换为各 Agent 特定的配置格式
- 结果报告：检查结果的多格式渲染与多渠道分发

**系统不负责的范畴**：

- 代码检查引擎的实现：复用 pre-commit 框架及成熟工具（clang-format、black、eslint 等），不自研检查逻辑
- AI 对话流程的管理：不介入 Agent 的对话生成过程，仅处理工具调用和提交门禁
- 代码托管平台功能：仅上传检查报告至 PR 评论，不提供代码托管、分支管理等能力
- 持续集成流水线：不替代 CI/CD 系统，但可作为 CI 的一个检查步骤集成

### 1.4 术语表

| 术语 | 定义 |
|---|---|
| **AI 编码 Agent** | 基于大语言模型的自动化编码工具，具备文件操作和命令执行能力 |
| **guard.yaml** | AI Guard 的项目级配置文件，是系统的单一配置真相源 |
| **ResolvedConfig** | 经过多源合并和校验后的最终配置对象，供各模块消费 |
| **PolicyDecision** | 行为约束的判定结果，取值为 allow / deny / ask |
| **CheckReport** | 代码检查的结构化结果报告 |
| **规则集（Ruleset）** | 可复用的规则包，包含行为约束、检查项定义和工具配置 |
| **工件（Artifact）** | 由 Generator 生成的静态文件，包括规则文档、Hook 脚本、工具配置等 |
| **托管块（Managed Block）** | 规则文档中由 AI Guard 管理的区域，update 时自动替换，不影响用户自定义内容 |
| **scheme** | Pattern 中的资源类型前缀（file: / shell: / mcp: / web:） |

---

## 2. 业界调研与相关工作

### 2.1 AI 编码 Agent 的安全现状

当前主流 AI 编码 Agent 的能力与约束机制可概括为以下格局：

| Agent | 核心能力 | Hook 机制 | 约束方式 |
|---|---|---|---|
| Claude Code | 文件读写、命令执行、MCP 调用 | PreToolUse / PostToolUse Hook | 规则文档（CLAUDE.md）+ Hook 拦截 |
| Cursor | 文件编辑、命令执行、Web 搜索 | 多类型 Hook（beforeShellExecution 等） | 规则文件（.cursor/rules/）+ Hook |
| OpenCode | 文件读写、命令执行、MCP 调用 | 插件内事件系统 | 规则文档（AGENTS.md）+ 插件拦截 |
| GitHub Copilot | 代码补全、文件编辑 | 无 Hook 机制 | 规则文档（copilot-instructions.md） |
| KiloCode | 文件读写、命令执行 | 无 Hook 机制 | 规则文档（.kilocode/rules/） |

可以观察到两个关键现象：

1. **约束能力的碎片化**。不同 Agent 的 Hook 机制互不兼容，规则文档格式各异。同一套约束规则需要在每个 Agent 上分别配置，维护成本随 Agent 数量线性增长。

2. **约束强度的不均衡**。具备 Hook 机制的 Agent（Claude Code、Cursor、OpenCode）可以实现运行时拦截，但无 Hook 机制的 Agent（Copilot、KiloCode）仅能通过规则文档进行"软约束"，无法强制阻止违规操作。

### 2.2 现有工具与方案对比

#### 2.2.1 Git Hook 管理工具

| 工具 | 定位 | 优势 | 局限 |
|---|---|---|---|
| **pre-commit** | Python 生态的 Git Hook 框架 | 插件生态丰富、支持多语言、缓存机制 | 不感知 AI Agent，无运行时拦截能力 |
| **husky** | Node.js 生态的 Git Hook 管理 | npm 集成便捷 | 仅管理 Hook 生命周期，不提供检查逻辑 |
| **lefthook** | Go 实现的 Git Hook 管理器 | 高性能、零依赖 | 同 husky，不感知 AI Agent |

这些工具解决了"代码提交时的自动化检查"问题，但均不具备 AI Agent 行为拦截能力。

#### 2.2.2 代码质量平台

| 平台 | 定位 | 优势 | 局限 |
|---|---|---|---|
| **SonarQube** | 代码质量与安全分析平台 | 规则丰富、支持多语言、CI 集成 | 重量级、需独立部署、不面向 AI 场景 |
| **CodeClimate** | 代码质量 SaaS | 无需部署、GitHub 集成好 | SaaS 依赖、无本地约束能力 |

这些平台提供深度的代码分析能力，但设计初衷面向人类开发者的 CI 流程，不适用于 AI Agent 实时工具调用的拦截场景。

#### 2.2.3 配置共享方案

| 方案 | 机制 | 启发 |
|---|---|---|
| ESLint Shareable Configs | npm 包发布共享配置 | 规则集可版本化分发 |
| Prettier Shared Config | npm/Git 仓库共享 | 一处维护、多处引用 |
| pre-commit 的 repo 机制 | Git 仓库作为 Hook 来源 | 远程规则复用 |

这些方案验证了"配置外部化与共享"的可行性，为 AI Guard 的规则集设计提供了参考。

### 2.3 差距分析

现有工具覆盖了"代码提交检查"和"静态分析"两个领域，但在 AI 辅助编码场景中存在以下空白：

| 能力需求 | Git Hook 工具 | 质量平台 | AI Guard |
|---|---|---|---|
| AI 运行时行为拦截 | ❌ | ❌ | ✅ |
| 多 Agent 统一配置 | ❌ | ❌ | ✅ |
| Agent Hook 适配 | ❌ | ❌ | ✅ |
| 规则文档自动生成 | ❌ | ❌ | ✅ |
| 提交检查编排 | ✅ | ✅ | ✅（复用 pre-commit） |
| 深度代码分析 | ❌ | ✅ | ❌（委托外部工具） |

AI Guard 的独特价值在于**连接 AI Agent 的行为管控与代码质量管控**，这是现有工具未覆盖的交叉领域。

### 2.4 设计启发

从业界实践中提取的设计启发：

| 来源 | 启发 | 在 AI Guard 中的体现 |
|---|---|---|
| pre-commit 的 Hook 编排 | 不自研检查引擎，编排成熟工具 | Checker 委托 pre-commit 执行检查 |
| ESLint 的共享配置机制 | 规则集可外部化、可版本化 | rulesets 支持 Git 仓库引用 |
| pre-commit 的 `types` 过滤 | 按文件类型路由检查工具 | checks 的 types 字段实现语言级过滤 |
| Terraform 的 Provider 模式 | 核心逻辑与外部适配分离 | AgentAdapter 策略模式隔离 Agent 差异 |
| fail2ban 的 fail-closed 策略 | 安全系统异常时应拒绝而非放行 | Enforcer 异常时默认 deny |

---

## 3. 需求分析

### 3.1 核心问题

AI Guard 旨在解决 AI 辅助编码过程中的五类核心问题：

| 编号 | 问题 | 具体表现 | 影响域 |
|---|---|---|---|
| P1 | AI 行为不可控 | Agent 修改敏感文件、执行危险命令、绕过检查机制 | 安全 |
| P2 | AI 代码质量不可控 | 生成代码不符合规范、缺少测试覆盖、架构违规 | 质量 |
| P3 | 约束规则维护困难 | 规则散落各处、团队间难以统一和共享 | 运维效率 |
| P4 | 多 Agent 适配碎片化 | 不同 Agent 的 Hook 机制各异，约束规则无法复用 | 开发效率 |
| P5 | 审计可追溯性缺失 | 无法回溯 AI 的操作决策和被拦截的行为 | 合规 |

### 3.2 目标用户

| 角色 | 场景 | 核心诉求 |
|---|---|---|
| 个人开发者 | 使用 AI Agent 辅助编码 | 快速建立基本护栏，防止 AI 越界操作 |
| 团队技术负责人 | 为团队统一 AI 编码规范 | 一次配置、团队共享、新项目快速复用 |
| 项目维护者 | 在现有项目中引入 AI 看护 | 无侵入安装、与现有工具链兼容 |
| 规则集作者 | 维护公司或社区级规则集 | 版本化管理、跨项目分发 |

### 3.3 核心场景

**S1 — 初始化看护**。开发者希望通过一条命令为项目建立 AI 看护体系，包括行为约束配置和代码检查规则的自动生成。

**S2 — 运行时行为拦截**。当 AI Agent 尝试修改禁止的文件或执行危险命令时，系统在操作执行前自动拦截并向 Agent 返回拒绝原因。

**S3 — 提交质量门禁**。AI 生成的代码在 `git commit` 时自动经过格式化、命名等静态检查，在 `git push` 时经过测试、覆盖率等动态验证。

**S4 — 多 Agent 统一适配**。同一份 guard.yaml 配置可同时适配 Claude Code、Cursor 等不同 Agent，生成各自格式的规则文档和 Hook 配置。

**S5 — 规则集复用**。规则集作者维护一套公司规则，各项目通过 Git 仓库引用直接使用，项目配置可覆盖规则集的部分设置。

**S6 — 现有工具链兼容**。AI Guard 复用 pre-commit 框架及 clang-format、black、eslint 等成熟工具执行检查，不替代这些工具。

**S7 — 合规审计**。每次行为判定记录至审计日志，包含时间、Agent、工具、决策、命中规则等字段，支持事后查询。

**S8 — PR 质量报告**。代码通过门禁后，检查报告自动发布至 PR 评论，支持 GitHub、GitLab 等主流平台及其自部署实例。

**S9 — 规则集社区共享**。规则集可通过 Git 仓库公开共享，远期支持社区注册中心。

### 3.4 功能需求与优先级

采用 MoSCoW 方法对功能需求进行优先级分级：

**Must Have（必须实现）**：

| 编号 | 需求 | 对应场景 |
|---|---|---|
| F1 | 运行时行为拦截（Read/Write/Execute 分类判定） | S2 |
| F2 | 多级决策机制（allow / deny / ask） | S2 |
| F3 | Pattern 匹配引擎（glob + regex，含路径归一化） | S2 |
| F5 | 静态检查编排（生成 .pre-commit-config.yaml，委托 pre-commit） | S3, S6 |
| F9 | 统一配置文件（guard.yaml 单一入口） | S1 |
| F11 | 配置多源合并（默认 → 规则集 → 项目） | S1, S5 |
| F13 | Agent 适配框架（抽象接口 + 多实现） | S4 |
| F15 | 规则文档生成 | S1, S4 |
| F16 | Hook 配置生成 | S1, S4 |
| F17 | 生命周期命令（init / install / update / uninstall） | S1 |

**Should Have（应当实现）**：F6 动态验证编排、F7 质量门禁、F10 规则集引用、F14 Agent 能力降级、F18 操作命令、F19 信息命令、F20 漂移检测。

**Could Have（可选实现）**：F4 操作审计日志、F8 PR 质量报告。

**Won't Have（本期不做）**：F12 规则集社区共享。

### 3.5 非功能需求

| 类别 | 需求 | 指标 |
|---|---|---|
| 性能 | Hook 响应时间 | PreToolUse Hook 判定 < 300ms（含 Python 启动） |
| 性能 | 静态检查耗时 | pre-commit 检查 < 5s（常规变更） |
| 兼容性 | 运行环境 | Python >= 3.10, Git >= 2.20, macOS / Linux |
| 安全性 | 异常处理策略 | fail-closed（异常时默认拦截） |
| 安全性 | 路径安全 | 检测并阻止路径遍历攻击（`../` 逃逸） |
| 可扩展性 | Agent 适配 | 新增 Agent 只需实现 AgentAdapter 接口 |
| 可扩展性 | 输出渠道 | 新增报告平台只需实现 ReportChannel 接口 |

### 3.6 外部约束

| 约束 | 来源 | 影响 |
|---|---|---|
| Agent Hook 能力不均 | 各 Agent 设计差异 | 部分 Agent 无法运行时拦截，仅能软约束 |
| Git Hook 不可跨仓库 | Git 机制限制 | Git Hook 需在每个项目中独立安装 |
| pre-commit 框架依赖 | 复用策略 | Checker 模块与 pre-commit 存在运行时耦合 |
| 工具配置格式多样 | 各工具独立设计 | Generator 需为每种工具生成特定格式的配置文件 |

---

## 4. 架构设计

### 4.1 设计原则

基于需求分析和业界调研，确立以下设计原则：

**原则 1：配置单一真相源**。guard.yaml 是系统唯一的配置入口，经解析合并后产出 ResolvedConfig，所有模块只消费 ResolvedConfig，不独立解析配置。

**原则 2：生成与执行分离**。安装时（`guard install`）完成所有配置解析和工件生成；运行时（PreToolUse Hook）和提交时（Git Hook）仅执行判定和检查，不重新解析配置。

**原则 3：行为约束与代码看护正交**。行为约束（Enforcer）解决"能不能做"，代码看护（Checker）解决"做得好不好"。两者独立运行，互不依赖。

**原则 4：Agent 适配不承载策略**。Agent 差异仅体现在生成时的格式转换，策略判定逻辑（Enforcer）和检查编排逻辑（Checker）对 Agent 类型无感知。

**原则 5：复用而非重建**。代码检查能力委托给 pre-commit 生态及成熟工具，AI Guard 专注于配置统一、工件生成和编排协调。

### 4.2 架构风格选型与论证

#### 4.2.1 候选风格分析

**分层架构**（Layered Architecture）。将系统组织为若干水平层，请求从顶层穿透至底层。核心假设：存在贯穿所有层的主请求路径。

**管道架构**（Pipeline Architecture）。将处理过程组织为线性阶段序列，数据单向流过。核心假设：数据经过固定的有序处理阶段。

**共享模块 + 命令编排**（Shared Modules + Command Orchestration）。系统由功能内聚的模块组成，每个 CLI 命令按需组合所需模块。核心假设：多个入口编排不同模块子集。

#### 4.2.2 分层架构的不适用性

AI Guard 的初始设计曾采用五层架构（CLI → 配置层 → 核心层 → Agent 适配层 → 输出层）。经验证，三条主要执行路径中，没有任何一条穿透全部五层：

| 执行路径 | CLI | 配置 | Generator | Enforcer | Checker | 适配 | 输出 |
|---|---|---|---|---|---|---|---|
| `guard install` | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| PreToolUse Hook | ❌ | ✅* | ❌ | ✅ | ❌ | ❌ | ✅ |
| `git commit` | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ |

> *运行时读取的是安装时生成的配置缓存

分层架构的核心假设不成立，强行套用会产生大量空穿透。

#### 4.2.3 业界实证

业界成熟 CLI 工具的架构实践：

| 工具 | 架构模式 | 特征 |
|---|---|---|
| Terraform | 共享核心 + 命令处理器 | 各命令独立编排 Provider/State/Engine |
| Docker CLI | 共享 API Client + 命令处理器 | build/run/push 各自独立 |
| kubectl | 共享配置 + 命令处理器 | 每个命令一个 handler 函数 |
| ESLint | 共享核心 + 多入口 | CLI 和 API 共享相同处理管道 |

共同特征：模块按需组合，命令驱动编排，非严格分层。

#### 4.2.4 选型结论

采用**共享模块 + 命令编排**模式。各 CLI 命令作为编排者，按需组合功能模块完成特定任务。模块之间通过接口协作，不预设层级关系。

### 4.3 系统架构总览

```
CLI (typer)
 ├─→ Config (加载/合并/校验 → ResolvedConfig)
 ├─→ Generator (消费 ResolvedConfig → 生成工件) ──→ AgentAdapter
 ├─→ Checker (编排检查) ──→ Reporter
 └─→ (直接输出: status / doctor / agents / version)

Enforcer ← 独立入口，由生成的 Hook 脚本触发 ──→ Reporter (审计)

guard gate run ← Git Hook 触发 ──→ Checker ──→ Reporter
```

### 4.4 模块划分与职责边界

| 模块 | 职责 | 禁止的越界行为 |
|---|---|---|
| **Config** | 加载、合并、校验配置 → 产出 ResolvedConfig | 不生成文件，不做策略判定 |
| **Generator** | 消费 ResolvedConfig → 生成所有静态工件 | 不解析配置（只消费 ResolvedConfig） |
| **AgentAdapter** | 提供 Agent 特定的文件生成策略 | 不参与运行时适配 |
| **Enforcer** | 运行时规则匹配 → 策略判定 | 不执行代码检查，不生成文件 |
| **Checker** | 编排 pre-commit 及验证项的执行 | 不生成配置，不做行为判定 |
| **Reporter** | 结构化结果的格式化与多渠道分发 | 不参与判定逻辑和编排逻辑 |

**边界原则**：一个职责只归一个模块。若两个模块在做同一件事，说明职责划分存在缺陷。

### 4.5 三条执行路径

#### 4.5.1 安装路径

```
guard install --agent claude-code
  │
  Config.resolve() → ResolvedConfig
  │
  Generator:
    G1 generate_rule_doc (per Agent)
    G2 generate_hook_files (per Agent)
    G3 generate_tool_configs
    G4 generate_precommit_config
    G5 generate_policy_cache
    G6 generate_git_hooks
    G7 write_artifacts
  │
  更新 state.json → 打印安装摘要
```

#### 4.5.2 运行时路径

```
AI Agent 工具调用
  │
  Agent Hook 机制触发生成的 Hook 脚本
  │
  Hook 脚本：协议转换（Agent 格式 → 统一 ToolCall）
  │
  Enforcer.evaluate():
    E1 load_policy (从 policy.json)
    E2 classify (确定操作类型和目标)
    E3 match (规则匹配)
    E4 decide (产出 PolicyDecision)
  │
  Hook 脚本：协议转换（PolicyDecision → Agent 格式）
  │
  Reporter.append_audit_log()
```

#### 4.5.3 提交验证路径

```
git commit / git push
  │
  .git/hooks/pre-commit 或 pre-push
  │
  guard gate run --stage commit|push
  │
  Checker.run():
    K1 detect_stage
    K2 get_changed_files
    K3 run_precommit (内置检查)
    K4 run_checks (命令检查项)
    K5 run_build (push 阶段前置条件)
    K6 aggregate → CheckReport
  │
  Reporter.print_report() 或 exit code 0/1
```

### 4.6 技术选型

| 决策项 | 选择 | 理由 |
|---|---|---|
| 实现语言 | Python >= 3.10 | 开发效率高、团队熟悉、pre-commit 生态原生契合 |
| CLI 框架 | typer | 类型提示风格简洁、Rich 集成美化输出、自动补全开箱即用 |
| 配置格式 | YAML | 人类可读性好、与 pre-commit 配置格式一致 |
| 检查框架 | pre-commit | 插件生态丰富、不重复造轮子 |
| 模板引擎 | Jinja2 | 成熟稳定、适合生成规则文档和报告 |
| 分发方式 | pip / pipx | Python 标准分发渠道 |
| 策略缓存 | JSON | 运行时快速加载，避免每次 Hook 调用解析 YAML |

### 4.7 架构决策记录

**ADR-1：Agent 适配作为 Generator 的策略模式，而非独立架构层**

- 背景：初始设计将 Agent 适配层独立为一个架构层。
- 分析：Agent 差异仅体现在安装时的文件生成格式，运行时 Hook 脚本在安装时已内嵌协议转换。不存在运行时的动态 Agent 适配。
- 决策：AgentAdapter 作为 Generator 内部的策略模式，不独立为架构层。

**ADR-2：行为约束判定采用 fail-closed 策略**

- 背景：Enforcer 异常时（配置缺失、Pattern 匹配崩溃）应放行还是拦截？
- 分析：AI Guard 作为安全系统，放行未知操作的风险高于误拦截的影响。
- 决策：除"首次使用未 install"外，所有异常场景默认 deny。

**ADR-3：代码检查委托 pre-commit 而非自研**

- 背景：是否自研静态检查和代码格式化引擎？
- 分析：pre-commit 已有丰富的插件生态、成熟的缓存和并行机制。自研成本高且难以匹配其质量。
- 决策：AI Guard 只生成 `.pre-commit-config.yaml` 并调用 `pre-commit run`，不自研检查引擎。

**ADR-4：checks 判定基于 exit code 而非输出解析**

- 背景：检查项（如 coverage）是否需要 AI Guard 解析工具输出？
- 分析：解析不同工具的输出格式成本高且脆弱。大多数工具支持通过参数实现阈值判定（如 `pytest --cov-fail-under=80`）。
- 决策：AI Guard 仅根据 command 的 exit code 判定通过与否，不解析标准输出。

**ADR-5：配置合并采用追加 + 显式移除策略**

- 背景：多源配置合并时，列表字段（forbidden/allow 等）应覆盖还是追加？
- 分析：覆盖策略可能导致内置安全规则被意外丢失；纯追加策略不允许用户移除不需要的默认规则。
- 决策：列表字段追加合并，用户通过 `remove` 字段显式移除特定规则。系统保护规则（SYSTEM）不可移除。

---

## 5. 配置系统设计

### 5.1 设计理念

配置系统的设计遵循以下原则：

**最小配置原则**。新项目仅需 `project.language` 一个必填字段即可启用 AI Guard，内置默认配置提供基线保护。

**渐进增强原则**。用户可从最小配置逐步添加自定义规则、引用规则集、配置多语言支持，系统不要求一次性完整配置。

**约定优于配置**。scheme 前缀（`file:` / `shell:` / `mcp:`）统一标识资源类型；`commit` / `push` 分段标识检查阶段；内置开关（format / naming / lint）覆盖最常见需求。

**安全默认**。内置默认规则保护敏感文件（.env、*.pem）和危险操作（`git push --force`、`sudo`）。系统保护规则（guard.yaml 自身、.ai-guard/ 目录）不可被用户移除。

### 5.2 guard.yaml 完整 Schema

```yaml
version: 1                                # 配置格式版本号（用于未来 schema 迁移）

project:
  name: "my-project"                      # 可选，默认取当前目录名
  language: "python"                      # 必填，主语言

rulesets:                                 # 可选，按顺序合并
  - "git@github.com:company/base-rules.git"
  - "git@github.com:company/python-rules.git"

languages:                                # 可选，多语言项目的工具配置
  python:
    tools:
      format: "black"
      lint: "ruff"
  typescript:
    tools:
      format: "prettier"
      lint: "eslint"

behavior:                                 # 可选，行为约束规则（追加到内置默认）
  read:
    forbidden:
      - pattern: "file:**/token.*"
        reason: "令牌文件"
      - pattern: "mcp:memory:search"
        reason: "禁止搜索记忆内容"
    require_approval:
      - pattern: "file:**/.gitignore"
        message: "Git 忽略配置访问需要确认"

  write:
    forbidden:
      - pattern: "file:vendor/**"
        reason: "依赖目录禁止修改"
    require_approval:
      - pattern: "file:.github/workflows/**"
        message: "CI 配置修改需要确认"
    allow:
      - pattern: "file:scripts/**"
    remove:
      - pattern: "file:build/**"          # 移除内置默认中的此规则

  execute:
    forbidden:
      - pattern: "shell:docker push*"
        reason: "禁止推送镜像"
      - pattern: "shell:git commit\\s+(--no-verify|--no-v|-n)"
        reason: "禁止跳过 hooks"
        regex: true                       # 启用正则匹配

code:                                     # 可选，代码检查配置
  commit:                                 # commit 阶段（不依赖编译）
    format: true                          # 内置开关：格式化
    naming: true                          # 内置开关：命名检查
    checks:                               # 命令检查项
      license_header:
        command: "./scripts/check-license.sh"
        types: [python]

  push:                                   # push 阶段（可能需要编译或运行）
    lint: true                            # 内置开关：语义级 lint
    checks:
      test:
        command: "pytest"
        timeout: 300
      coverage:
        command: "pytest --cov --cov-fail-under=80"
      asan:
        command: "./build.sh test --asan"
        enabled: false

build:
  command: "make build"                   # 可选，push 阶段的编译前置条件

output:                                   # 可选，输出配置
  verbosity: "normal"                     # "quiet" | "normal" | "verbose"
  audit:
    enabled: true
    path: ".ai-guard/audit.jsonl"
    retention: 30                         # 保留天数，0 表示永久
  pr_report:
    enabled: false
    platform: "github"                    # "github" | "gitlab" | "gitea" | "bitbucket"
    api_url: "https://github.company.com/api/v3"  # 自部署实例地址
    token_env: "GITHUB_TOKEN"             # 从环境变量读取平台令牌
```

### 5.3 配置合并策略

#### 5.3.1 合并顺序

```
内置默认 → 规则集 1 → 规则集 2 → ... → guard.yaml
```

优先级从左到右递增，后者可覆盖或扩展前者。

#### 5.3.2 合并规则

| 字段类型 | 合并行为 | 示例 |
|---|---|---|
| 列表字段（forbidden/require_approval/allow） | **追加** | 规则集和用户的规则追加到默认列表之后 |
| `remove` 列表 | **从合并结果中精确匹配移除** | pattern 字符串完全相同才移除 |
| `checks` 字典 | **字段级覆盖**（deep merge） | 同名 key 的字段由后者覆盖 |
| 标量值（timeout / verbosity 等） | **后者覆盖前者** | 用户配置覆盖规则集配置 |

#### 5.3.3 系统保护规则

以下规则由系统自动注入，标记为 SYSTEM 来源，不可通过 `remove` 移除：

```yaml
write:
  require_approval:
    - pattern: "file:guard.yaml"
    - pattern: "file:.ai-guard/**"
    - pattern: "file:.pre-commit-config.yaml"
    - pattern: "file:.git/hooks/**"
```

用户尝试移除系统保护规则时，系统输出警告并忽略该操作。

#### 5.3.4 规则来源追踪

合并过程中，每条规则标记其来源，用于 `guard status --rules` 的展示和 policy.json 的存储：

| 来源标记 | 含义 |
|---|---|
| `default` | 来自内置默认配置 |
| `ruleset:<name>` | 来自指定的规则集 |
| `user` | 来自项目 guard.yaml |
| `system` | 系统保护规则（不可移除） |

### 5.4 规则集架构

规则集采用与 guard.yaml 相同的配置格式，附带需要复制到项目的文件。这一设计确保规则集的学习成本为零。

```
company-rules/                          # 规则集根目录
├── guard.yaml                          # 与项目 guard.yaml 同格式
├── files/                              # 工具配置文件（复制到项目根目录）
│   ├── .clang-format
│   ├── .clang-tidy
│   └── pyproject.toml
└── checks/                             # 自定义检查脚本（复制到 .ai-guard/checks/）
    ├── file_prefix.py
    └── doxygen_brief.py
```

安装时处理流程：

1. 克隆规则集至 `.ai-guard/cache/`
2. 合并规则集的 guard.yaml 至配置（追加语义）
3. 复制 `files/` 目录下的文件至项目根目录
4. 复制 `checks/` 目录下的脚本至 `.ai-guard/checks/`

### 5.5 多语言协同

多语言支持的核心机制是 pre-commit 的文件类型路由（`types` 字段）。Generator 根据 `languages` 配置为每种语言生成对应的 pre-commit hook，每个 hook 通过 `types` 限定仅处理匹配的文件。

| 检查类型 | 多语言行为 | 由谁负责 |
|---|---|---|
| format / naming / lint（内置检查） | 按文件类型自动路由至对应语言工具 | Generator 生成 + pre-commit 执行 |
| checks 中的命令检查项 | 项目级命令，不区分语言 | 用户命令自行处理 |
| checks 中带 `types` 的检查项 | 按文件类型过滤后执行 | Checker 过滤 + 命令执行 |

语言默认工具映射存放在 `config/defaults/languages.yaml`（非硬编码），新增语言支持只需编辑此文件：

```yaml
c:      { format: "clang-format",        lint: "clang-tidy" }
python: { format: "black",               lint: "ruff" }
typescript: { format: "prettier",         lint: "eslint" }
go:     { format: "gofmt",               lint: "golangci-lint" }
rust:   { format: "rustfmt",             lint: "clippy" }
java:   { format: "google-java-format",  lint: "spotbugs" }
```

---

## 6. 模块详细设计

各模块统一按以下结构描述：职责与边界、原语操作、编排流程、异常处理、扩展点。

### 6.1 Config 模块

#### 6.1.1 职责与边界

加载 guard.yaml、内置默认配置和规则集，按合并策略合并为 ResolvedConfig。Config 是配置语义的唯一解释者，其他模块不得独立解析配置文件。

#### 6.1.2 原语操作

| 编号 | 原语 | 输入 | 输出 |
|---|---|---|---|
| C1 | resolve_config | guard.yaml 路径 + defaults + rulesets | ResolvedConfig |

C1 内部流程：加载内置默认 → 逐个加载规则集并合并 → 加载 guard.yaml 并合并 → 处理 remove → Schema 校验 → 计算 config_hash → 返回 ResolvedConfig。

#### 6.1.3 异常处理

| 异常 | 处理 |
|---|---|
| guard.yaml 不存在 | 返回错误，提示 `guard init` |
| YAML 语法错误 | 返回错误，标注行号和错误类型 |
| Schema 校验失败 | 返回错误，列出所有违规字段 |
| 规则集克隆失败 | 返回错误，提示检查网络或 URL |
| remove 目标不存在 | 输出警告（可能拼写错误），继续执行 |
| remove 目标为 SYSTEM 规则 | 输出警告（不可移除），忽略该 remove |

#### 6.1.4 扩展点

- 新增配置字段：修改 Schema 定义和 ResolvedConfig 数据类
- 新增合并策略：在 merger 中添加字段级合并规则
- 新增配置来源：在 resolve 流程中插入新的加载阶段

### 6.2 Generator 模块

#### 6.2.1 职责与边界

消费 ResolvedConfig，生成所有静态工件并写入磁盘。Generator 不解析配置（只消费 ResolvedConfig），不参与运行时判定和检查编排。

#### 6.2.2 原语操作

| 编号 | 原语 | 输入 | 输出 |
|---|---|---|---|
| G1 | generate_rule_doc | ResolvedConfig + AgentAdapter | FileSpec（规则文档） |
| G2 | generate_hook_files | ResolvedConfig + AgentAdapter | list[FileSpec]（Hook 脚本 + 配置） |
| G3 | generate_tool_configs | ResolvedConfig + ruleset files | list[FileSpec]（工具配置） |
| G4 | generate_precommit_config | ResolvedConfig.code + languages | FileSpec（.pre-commit-config.yaml） |
| G5 | generate_policy_cache | ResolvedConfig | FileSpec（policy.json） |
| G6 | generate_git_hooks | — | list[FileSpec]（.git/hooks/*） |
| G7 | write_artifacts | list[FileSpec] | 文件写入磁盘 |

#### 6.2.3 编排流程（install 命令）

```
C1 → [G1+G2 per Agent] → G3 → G4 → G5 → G6 → G7 → 更新 state.json
```

install 为增量操作：新增 Agent 追加至已有列表，为全部 Agent 重新生成工件以保证一致性。

#### 6.2.4 托管块机制

规则文档中由 AI Guard 生成的区域使用标记界定：

```markdown
<!-- AI-GUARD:BEGIN -->
（自动生成内容，update 时替换）
<!-- AI-GUARD:END -->

（用户自定义内容，update 时保留）
```

#### 6.2.5 异常处理

| 异常 | 处理 |
|---|---|
| 文件写入权限不足 | 报错，列出无权限的文件路径 |
| .git 目录不存在 | 警告，跳过 Git Hooks 安装，继续生成其他工件 |
| Agent 适配器未注册 | 报错，列出可用的 Agent 名称 |

#### 6.2.6 扩展点

- 新增工件类型：在 Generator 中添加新的 generate_* 原语
- 新增 Agent：实现 AgentAdapter 接口并注册

### 6.3 AgentAdapter 模块

#### 6.3.1 职责与边界

为 Generator 提供 Agent 特定的文件生成策略。每个 Adapter 声明 Agent 的能力（can_block / can_ask）并实现规则文档和 Hook 文件的生成方法。

#### 6.3.2 接口定义

```python
class AgentAdapter(ABC):
    name: str
    capabilities: AgentCapabilities    # can_block, can_ask

    def rule_doc_path(self) -> str
    def render_rule_doc(self, behavior: BehaviorConfig) -> str
    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]
```

#### 6.3.3 已实现的适配器

| 适配器 | Agent | can_block | can_ask | 规则文档路径 |
|---|---|---|---|---|
| ClaudeCodeAdapter | Claude Code | ✅ | ✅ | `CLAUDE.md` |
| CursorAdapter | Cursor | ✅ | ⚠️ 部分 | `.cursor/rules/behavior.mdc` |
| OpenCodeAdapter | OpenCode | ✅ | ✅ | `AGENTS.md` |
| CopilotAdapter | GitHub Copilot | ❌ | ❌ | `.github/copilot-instructions.md` |
| KiloCodeAdapter | KiloCode | ❌ | ❌ | `.kilocode/rules/behavior.md` |

#### 6.3.4 能力降级

不支持 Hook 的 Agent（Copilot、KiloCode）安装时给出明确警告，说明哪些策略无法在运行时生效，并提示依赖 Git Hook 和规则文档提供的保护。

#### 6.3.5 扩展点

新增 Agent 只需：实现 AgentAdapter 子类 → 在 Registry 中注册。无需修改 Generator 或其他模块。

### 6.4 Enforcer 模块

#### 6.4.1 职责与边界

运行时规则匹配引擎。接收统一格式的 ToolCall，基于策略缓存（policy.json）执行判定，返回 PolicyDecision。Enforcer 不经过 CLI 入口，由安装时生成的 Hook 脚本直接调用。

#### 6.4.2 策略缓存机制

install/update 时生成 `.ai-guard/policy.json`，包含合并后的最终行为策略（JSON 格式）及 config_hash。Enforcer 运行时直接加载此文件，无需解析 YAML。

漂移检测：Enforcer 启动时比对当前 guard.yaml 的 hash 与 policy.json 中的 config_hash，不一致时向 stderr 输出警告，但不阻止执行（使用旧策略继续判定）。

#### 6.4.3 原语操作

| 编号 | 原语 | 输入 | 输出 |
|---|---|---|---|
| E1 | load_policy | policy.json 路径 | Policy 对象 |
| E2 | classify | tool_name, tool_args | (operation, scheme, target) |
| E3 | match | target, rules | 命中的规则或 None |
| E4 | decide | match 结果 | PolicyDecision (allow / deny / ask) |

#### 6.4.4 编排流程

```
evaluate(tool_call):
  E1 → E2 → E3 → E4 → Reporter.append_audit_log() → return decision
```

#### 6.4.5 判定优先级

当同一目标匹配多条规则时：`forbidden > require_approval > allow > 默认 allow`。

Pattern 匹配支持两种模式：glob（默认）和 regex（`regex: true` 显式声明）。

#### 6.4.6 异常处理（fail-closed）

| 异常场景 | 处理方式 | 理由 |
|---|---|---|
| policy.json 缺失（未 install） | 输出引导提示 + allow | 首次使用不阻塞 |
| policy.json 解析失败 | **deny** + 错误提示 | fail-closed |
| 未知工具类型 | allow | 不在管控范围 |
| Pattern 匹配崩溃 | **deny** + 错误提示 | fail-closed |
| config_hash 不一致 | 警告 + 用旧策略继续 | 提醒但不阻塞 |

#### 6.4.7 扩展点

- 新增操作类型（read/write/execute 之外）：在 classify 中添加映射规则
- 新增 scheme 类型：在 match 中添加对应的目标提取和匹配逻辑

### 6.5 Checker 模块

#### 6.5.1 职责与边界

编排代码检查的执行。Checker 通过 subprocess 调用 pre-commit 执行内置检查，通过 subprocess 执行用户定义的命令检查项，汇总结果为 CheckReport。

#### 6.5.2 原语操作

| 编号 | 原语 | 输入 | 输出 |
|---|---|---|---|
| K1 | detect_stage | CLI 参数 | "commit" 或 "push" |
| K2 | get_changed_files | stage | 变更文件列表 |
| K3 | run_precommit | files, config | 内置检查结果 |
| K4 | run_checks | checks config, files | 命令检查项结果 |
| K5 | run_build | build config | 编译结果 |
| K6 | aggregate | 所有结果 | CheckReport |

#### 6.5.3 阶段编排

```
commit 阶段: K2 → K3(format+naming) → K4(commit.checks) → K6
push 阶段:   先完整执行 commit 阶段
             → 失败则停止（阶段间 fail-fast）
             K5(build) → K3(lint) → K4(push.checks) → K6
```

失败策略：同一阶段内全部执行（收集所有错误），阶段间 fail-fast（前一阶段失败则不执行后续阶段）。

#### 6.5.4 checks 执行模式

| `types` 字段 | `pass_filenames` | `{files}` 占位符 | 执行行为 |
|---|---|---|---|
| 未设置 | — | — | 项目级命令，原样执行 |
| 已设置 | true（默认） | 未使用 | 匹配文件追加至命令末尾 |
| 已设置 | true（默认） | 已使用 | `{files}` 被替换为匹配文件列表 |
| 已设置 | false | — | 仅作为跳过条件，命令原样执行 |

所有命令在项目根目录（guard.yaml 所在目录）执行。

#### 6.5.5 异常处理

| 异常 | 处理 |
|---|---|
| pre-commit 未安装 | 报错，提示 `pip install pre-commit` 或 `guard doctor` |
| 命令超时 | 标记为失败，记录超时信息 |
| 命令执行异常 | 标记为失败，捕获 stderr |

#### 6.5.6 扩展点

- 新增内置检查类型（format/naming/lint 之外）：在 run_precommit 中添加
- 替换 pre-commit 为其他框架：修改 K3 的实现

### 6.6 Reporter 模块

#### 6.6.1 职责与边界

将结构化结果（CheckReport / PolicyDecision）格式化为指定格式，并输出到指定渠道。Reporter 不参与任何判定或编排逻辑。

#### 6.6.2 原语操作

| 编号 | 原语 | 调用方 | 输出目标 | 引入阶段 |
|---|---|---|---|---|
| R1 | print_check_report | Checker（check/verify） | 终端 Rich 格式化 | Phase 3 |
| R2 | print_gate_result | Checker（gate run） | 终端精简文本 | Phase 3 |
| R3 | append_audit_log | Enforcer | .ai-guard/audit.jsonl | Phase 2 |
| R4 | post_pr_comment | Checker | PR 评论（HTTP API） | Could Have |

#### 6.6.3 渲染格式

| 格式 | 用途 | 实现方式 |
|---|---|---|
| Rich 终端 | check / verify 命令输出 | Rich 库直接渲染 |
| 纯文本 | gate run 输出（Git Hook 环境） | 字符串拼接 |
| Markdown | PR 评论 | Jinja2 模板（`templates/report.md.j2`） |
| JSON | `--format json` 机器消费 | dataclass 序列化 |

#### 6.6.4 异常处理

| 异常 | 处理 |
|---|---|
| 审计日志写入失败 | 向 stderr 输出警告，不影响主流程 |
| PR 评论发布失败 | 向 stderr 输出警告，不影响 exit code |

#### 6.6.5 扩展点

新增报告渠道时引入 ReportChannel 接口：

```python
class ReportChannel(ABC):
    def send(self, report: CheckReport, rendered_markdown: str) -> None: ...
```

Channel 选择由 CLI 命令层根据 `output.pr_report` 配置决定。`api_url` 字段支持自部署平台实例。

---

## 7. 接口设计

### 7.1 CLI 命令接口

#### 7.1.1 生命周期命令

| 命令 | 参数 | 行为 |
|---|---|---|
| `guard init` | `--language`（必填）, `--ruleset`, `--interactive` | 检测项目信息，生成 guard.yaml 模板 |
| `guard install` | `--agent`（逗号分隔） | 无 --agent 时列出可选 Agent；有则生成工件 + 安装 Git Hooks |
| `guard update` | — | 读取 state.json，重新生成全部工件 |
| `guard uninstall` | `--keep-config` | 按 state.json 删除全部工件 |

#### 7.1.2 操作命令

| 命令 | 参数 | 行为 |
|---|---|---|
| `guard check` | `--files` | 手动触发 commit 级检查 |
| `guard verify` | `--skip-build` | 手动触发 push 级完整验证 |
| `guard run <name>` | `--stage commit\|push` | 运行单个检查项（commit 优先，可用 --stage 指定） |
| `guard gate run` | `--stage commit\|push` | Git Hook 内部入口，精简输出，exit code 0/1 |

#### 7.1.3 诊断与信息命令

| 命令 | 参数 | 行为 |
|---|---|---|
| `guard status` | `--rules` | 安装状态 + 漂移检测 + 工件完整性；`--rules` 展示完整规则列表及来源 |
| `guard doctor` | — | 环境诊断（工具链、配置、文件完整性、漂移） |
| `guard agents` | — | Agent 能力矩阵 + 已安装标记 |
| `guard version` | — | 版本号 |

#### 7.1.4 规则集与验证项命令

| 命令 | 行为 |
|---|---|
| `guard ruleset list` | 列出可用规则集 |
| `guard ruleset show <name>` | 查看规则集详情 |
| `guard ruleset fetch <url>` | 获取或更新规则集 |
| `guard ruleset cache clear` | 清理规则集缓存 |
| `guard validation list` | 列出可用验证项 |
| `guard validation report` | 查看验证报告 |

### 7.2 模块间内部接口

模块间通过数据类进行协作，核心数据类型契约见第 8 章数据模型设计。

关键调用关系：

```
CLI → Config.resolve() → ResolvedConfig
CLI → Generator.generate(ResolvedConfig, agents) → list[FileSpec]
CLI → Checker.run(ResolvedConfig, stage) → CheckReport
Hook → Enforcer.evaluate(ToolCall, policy) → PolicyDecision
Checker → Reporter.print_check_report(CheckReport)
Enforcer → Reporter.append_audit_log(PolicyDecision)
```

### 7.3 Agent Hook 接口

各 Agent 的 Hook 脚本由 Generator 在安装时生成。协议转换逻辑内嵌在生成的脚本中，Enforcer 模块仅处理统一的 ToolCall 格式。

| Agent | Hook 入口 | 输入格式 | 输出格式 |
|---|---|---|---|
| Claude Code | `.claude/hooks/interceptor.py`（stdin JSON） | `{"tool_name": "...", "tool_input": {...}}` | `{"hookSpecificOutput": {"permissionDecision": "deny/allow/ask"}}` |
| Cursor | `.cursor/hooks/check.sh`（stdin JSON） | Cursor 特定格式 | `{"permission": "deny"}` |
| OpenCode | `.opencode/plugins/ai-guard.ts`（插件 API） | `{tool, args}` | `throw Error("...")` 阻止 |
| Copilot / KiloCode | 无 Hook | — | — |

### 7.4 外部系统接口

| 外部系统 | 交互方式 | 使用场景 |
|---|---|---|
| Git | 命令行调用 | 变更文件检测、Hook 安装 |
| pre-commit | `subprocess.run(["pre-commit", "run", ...])` | 静态检查执行 |
| GitHub / GitLab API | HTTP REST API | PR 评论发布 |
| 规则集 Git 仓库 | `git clone` | 规则集获取 |

---

## 8. 数据模型设计

### 8.1 ResolvedConfig

```python
@dataclass
class Rule:
    pattern: str
    reason: str | None = None
    message: str | None = None
    regex: bool = False
    source: str = "user"              # "default" | "ruleset:<name>" | "user" | "system"

@dataclass
class OperationRules:
    forbidden: list[Rule]
    require_approval: list[Rule]
    allow: list[Rule]

@dataclass
class BehaviorConfig:
    read: OperationRules
    write: OperationRules
    execute: OperationRules

@dataclass
class CheckItem:
    command: str
    timeout: int = 300
    enabled: bool = True
    types: list[str] | None = None
    pass_filenames: bool = True

@dataclass
class CodeConfig:
    commit_format: bool = True
    commit_naming: bool = True
    commit_checks: dict[str, CheckItem] = field(default_factory=dict)
    push_lint: bool = True
    push_checks: dict[str, CheckItem] = field(default_factory=dict)

@dataclass
class LanguageTools:
    format: str
    lint: str

@dataclass
class OutputConfig:
    verbosity: str = "normal"
    audit: AuditConfig = field(default_factory=AuditConfig)
    pr_report: PrReportConfig = field(default_factory=PrReportConfig)

@dataclass
class ResolvedConfig:
    version: int
    project_name: str
    project_language: str
    behavior: BehaviorConfig
    code: CodeConfig
    languages: dict[str, LanguageTools]
    output: OutputConfig
    build_command: str | None = None
    config_hash: str = ""
```

### 8.2 运行时数据

#### state.json

```json
{
  "ai_guard_version": "0.1.0",
  "installed_agents": ["claude-code", "cursor"],
  "config_hash": "a3f8c2e1",
  "installed_at": "2026-04-13T10:30:00",
  "artifacts": ["CLAUDE.md", ".claude/settings.json", ".pre-commit-config.yaml"]
}
```

#### policy.json

```json
{
  "config_hash": "a3f8c2e1",
  "behavior": {
    "write": {
      "forbidden": [
        {"pattern": "file:.git/**", "reason": "...", "source": "default"},
        {"pattern": "file:vendor/**", "reason": "...", "source": "user"}
      ],
      "require_approval": [
        {"pattern": "file:guard.yaml", "message": "...", "source": "system"}
      ],
      "allow": [
        {"pattern": "file:src/**", "source": "default"}
      ]
    }
  }
}
```

### 8.3 审计数据

`.ai-guard/audit.jsonl`，JSON Lines 格式，每行一条审计记录：

```json
{
  "timestamp": "2026-04-13T10:30:00.123Z",
  "agent": "claude-code",
  "tool": "write",
  "operation": "write",
  "scheme": "file",
  "target": "third_party/lib.c",
  "decision": "deny",
  "reason": "第三方库禁止修改",
  "matched_rule": "file:third_party/**",
  "policy_hash": "a3f8c2e1"
}
```

### 8.4 报告数据

```python
@dataclass
class Violation:
    file: str
    line: int | None = None
    column: int | None = None
    severity: str = "error"
    code: str = ""
    message: str = ""
    source: str = ""

@dataclass
class CheckResult:
    name: str
    passed: bool
    violations: list[Violation]
    metrics: dict
    duration_ms: int = 0

@dataclass
class CheckReport:
    stage: str
    passed: bool
    results: list[CheckResult]
    duration_ms: int
    summary: str
```

### 8.5 生成工件清单

| 工件 | 生成原语 | 描述 |
|---|---|---|
| 规则文档（CLAUDE.md 等） | G1 | Agent 特定的行为约束文档 |
| Hook 脚本 + 配置 | G2 | Agent 特定的拦截脚本和注册配置 |
| 工具配置（.clang-format 等） | G3 | 从规则集复制的工具配置文件 |
| .pre-commit-config.yaml | G4 | pre-commit 框架配置 |
| .ai-guard/policy.json | G5 | 策略缓存（Enforcer 消费） |
| .git/hooks/pre-commit, pre-push | G6 | Git Hook 脚本 |
| .ai-guard/state.json | install 命令 | 安装状态记录 |

---

## 9. 部署与运维设计

### 9.1 安装方式

```bash
pip install ai-guard        # pip 安装
pipx install ai-guard       # pipx 隔离安装（推荐）
```

### 9.2 项目集成流程

```
Step 1: guard init --language python
  → 生成 guard.yaml

Step 2: guard install --agent claude-code
  → 生成所有工件 + 安装 Git Hooks

Step 3: 日常使用
  → AI Agent 工具调用自动经过行为拦截
  → git commit/push 自动经过代码检查

Step 4: 配置变更后
  → 编辑 guard.yaml
  → guard update
```

### 9.3 升级策略

state.json 中记录 `ai_guard_version`。`guard status` 检测当前工具版本与 state.json 中记录的版本，不一致时提示 `guard update` 重新生成工件。

guard.yaml 中的 `version` 字段用于配置格式版本迁移。当 schema 升级时（如 v1 → v2），`guard update` 检测版本差异并执行迁移逻辑。

### 9.4 诊断与排错

`guard doctor` 提供系统化的环境诊断：

| 检查类别 | 检查项 |
|---|---|
| 工具依赖 | Python >= 3.10, pre-commit, Git >= 2.20, 语言工具链 |
| 配置状态 | guard.yaml 语法、Schema 校验、合并可行性 |
| 文件完整性 | .ai-guard/ 目录、state.json、全部 artifacts |
| 权限状态 | Git Hooks 可执行权限 |
| 漂移检测 | config_hash 一致性 |

---

## 10. 测试策略

### 10.1 单元测试

| 模块 | 测试重点 |
|---|---|
| Config | 合并逻辑（追加、remove、标量覆盖、SYSTEM 规则保护）、Schema 校验、hash 计算 |
| Generator | 各原语输出正确性、托管块更新、多 Agent 工件生成 |
| AgentAdapter | 各 Agent 的文件路径和内容格式 |
| Enforcer | Pattern 匹配（glob + regex）、判定优先级、fail-closed 行为 |
| Checker | 阶段编排、fail-fast 策略、types 过滤、pass_filenames 行为 |
| Reporter | 各格式渲染正确性、审计日志格式 |

### 10.2 集成测试

- install → status → update → uninstall 生命周期完整性
- 漂移检测端到端：修改 guard.yaml → status 报警 → update 消除
- 多 Agent 安装：install --agent A → install --agent B → 两者共存

### 10.3 Phase 验证方法

**Phase 1 验证**：guard init → install → status → agents → doctor → update → uninstall 全流程可用。

**Phase 2 验证**：AI Agent 写入 forbidden 路径被拦截；执行 forbidden 命令被拦截；require_approval 路径触发 ask。

**Phase 3 验证**：git commit 触发 pre-commit 检查；git push 触发完整验证；guard check/verify 手动执行正确。

---

## 11. 演进规划

### 11.1 Phase 划分

| Phase | 目标 | 交付 |
|---|---|---|
| 1 | Config + Generator + CLI 骨架 | 8 个命令可用，工件生成完整 |
| 2 | Enforcer + Agent Bridge | 运行时行为拦截生效 |
| 3 | Checker + Reporter | 代码看护完整闭环 |
| 后续 | 审计 + PR 报告 + 规则集管理 | 合规与协作能力 |

### 11.2 已知局限与未来扩展点

#### 局限 1：Checker 与 pre-commit 框架存在运行时耦合

**现状**：Checker 通过 `subprocess.run(["pre-commit", "run", ...])` 直接调用 pre-commit。若用户项目使用 lefthook、husky 或企业自研检查框架，需修改 Checker 核心代码。

**当前缓解措施**：pre-commit 调用集中在 Checker 内部的单一函数中，未散落各处，为未来替换预留了清晰的修改点。

**扩展方向**：引入 CheckFramework 接口抽象。Checker 依赖该接口而非具体框架，不同框架实现各自的 CheckFramework 子类。guard.yaml 中通过配置字段选择使用哪个框架实现。

**触发引入的条件**：出现需要支持 pre-commit 以外检查框架的实际用户需求。

#### 局限 2：无插件系统

**现状**：新增 Agent 适配器、报告渠道、检查类型均需修改 AI Guard 源码。对于 AI Guard 团队未预见的 Agent（如新兴 AI 编码工具）或企业内部输出渠道（如飞书、钉钉），用户无法在不改源码的前提下进行扩展。

**当前缓解措施**：AgentAdapter、ReportChannel 均已定义为抽象基类（ABC），接口稳定。当前通过代码内注册方式管理实现类。

**扩展方向**：引入插件发现机制。扫描 `.ai-guard/plugins/` 目录，自动导入并注册其中的 AgentAdapter / ReportChannel 子类。类似 pytest 的插件发现模式，接口不变，仅注册方式从代码内注册变为文件发现注册。

**触发引入的条件**：社区贡献者数量增长，出现不改源码扩展的明确需求。

#### 局限 3：无配置格式迁移机制

**现状**：guard.yaml 中预留了 `version: 1` 字段用于标识配置格式版本，但尚未实现从旧版本自动迁移至新版本的逻辑。当 guard.yaml schema 发生 breaking change 时，用户需手动修改配置文件。

**当前缓解措施**：`version` 字段已预留，Config 模块的 Schema 校验会检查版本号。

**扩展方向**：实现 `guard migrate` 命令。读取当前 guard.yaml 的版本号，查找对应的迁移函数链（v1→v2, v2→v3, ...），自动转换配置格式，备份旧文件为 `guard.yaml.bak`。每个版本升级定义一个迁移函数，支持链式跨版本迁移。

**触发引入的条件**：guard.yaml schema 的第一次 breaking change。

#### 局限 4：目录扫描型脚本无法限定为仅检查变更文件

**现状**：当 checks 配置了 `types` 过滤但用户脚本通过自行扫描目录（如 `os.listdir()`、`find` 命令）确定检查范围时，`pass_filenames: false` 仅能实现"无匹配文件时跳过执行"，无法使脚本仅处理变更文件。脚本仍会检查全部文件——结果正确但可能冗余。

**根本原因**：AI Guard 无法透明地改变任意脚本的文件发现逻辑。创建临时目录仅放匹配文件的方案会破坏 import 路径和相对引用。

**当前缓解措施**：文档中明确说明此局限，推荐用户优先使用接受文件参数的工具（大多数 lint 工具天然支持）。

**扩展方向**：提供环境变量 `AI_GUARD_CHANGED_FILES`（空格分隔的变更文件列表），脚本可选择性读取此变量以缩小检查范围。此方案不强制脚本行为，仅提供可选信息。

**触发引入的条件**：持续优化，可在任何 Phase 中实现。

#### 局限 5：无运行时监控与可观测性

**现状**：AI Guard 的运行状态仅能通过 `guard status` 和 `guard doctor` 人工查看，无持续监控能力。在大规模部署场景下（如企业同时在数十个项目中使用 AI Guard），无法集中监控拦截率、Hook 延迟、审计日志增长等指标。

**当前缓解措施**：审计日志（audit.jsonl）以 JSON Lines 格式记录所有行为判定的原始数据。企业可基于现有日志采集系统（如 ELK Stack、Loki）消费此文件，自行构建监控看板。

**扩展方向**：引入 metrics 采集端点。每次 Enforcer/Checker 执行后推送指标（判定次数、deny 次数、延迟直方图、检查失败率等）至 Prometheus Pushgateway 或 StatsD。guard.yaml 的 `output.metrics` 配置块控制采集行为。

**触发引入的条件**：企业大规模部署，出现集中监控的明确需求。

### 11.3 设计教训

在本系统的设计过程中积累了以下经验教训：

1. **产品视角先于工程视角**。应先设计完整的命令集和用户交互流程（产品视角），再规划分期实现（工程视角）。按 Phase 切片设计会导致遗漏关键命令。

2. **从用户场景推导接口**。命令集应从"用户在什么场景下需要交互"推导，而非从"模块需要什么入口"推导。后者会遗漏不对应特定模块的命令（如 doctor、agents）。

3. **职责归属必须唯一**。每个操作只归属一个模块。resolve_config 属于 Config 而非 Generator；协议转换属于生成的 Hook 脚本而非运行时适配层。

4. **区分用户命令与内部命令**。`gate run` 是 Git Hook 调用的内部命令，遗漏它会导致提交验证链路断裂。

5. **各模块的设计深度应当一致**。后设计的模块容易因疲劳而草率，应以统一的检查清单验证每个模块的完整度。

6. **不假设用户脚本的能力**。用户脚本可能不接受文件参数，应提供显式的 `pass_filenames` 控制而非假设默认行为。

---

## 附录

### 附录 A：Agent 能力矩阵

| Agent | Hook 机制 | can_block | can_ask | 规则文档 |
|---|---|---|---|---|
| Claude Code | PreToolUse Hook | ✅ | ✅ | CLAUDE.md |
| Cursor | 多类型 Hook | ✅ | ⚠️ 部分 | .cursor/rules/ |
| OpenCode | 插件事件系统 | ✅ | ✅ | AGENTS.md |
| GitHub Copilot | 无 | ❌ | ❌ | copilot-instructions.md |
| KiloCode | 无 | ❌ | ❌ | .kilocode/rules/ |

### 附录 B：内置默认行为规则

```yaml
# read.forbidden
- pattern: "file:**/.env"           # 敏感配置
- pattern: "file:**/*.pem"          # 证书文件
- pattern: "file:**/*.key"          # 密钥文件
- pattern: "file:**/credentials.*"  # 凭证文件
- pattern: "file:**/secrets/**"     # 密钥目录

# write.forbidden
- pattern: "file:.git/**"           # Git 内部文件
- pattern: "file:third_party/**"    # 第三方库
- pattern: "file:build/**"          # 构建产物
- pattern: "file:dist/**"           # 分发产物

# write.allow
- pattern: "file:src/**"
- pattern: "file:tests/**"
- pattern: "file:docs/**"

# execute.forbidden
- pattern: "shell:git commit --no-verify*"
- pattern: "shell:git push --force*"
- pattern: "shell:git push -f*"
- pattern: "shell:git config core.hooksPath*"
- pattern: "shell:rm -rf /*"
- pattern: "shell:sudo *"

# execute.allow
- pattern: "shell:git status*"
- pattern: "shell:git diff*"
- pattern: "shell:git log*"
- pattern: "shell:git branch*"
```

### 附录 C：语言默认工具映射

| 语言 | 格式化工具 | Lint 工具 |
|---|---|---|
| C / C++ | clang-format | clang-tidy |
| Python | black | ruff |
| TypeScript | prettier | eslint |
| Go | gofmt | golangci-lint |
| Rust | rustfmt | clippy |
| Java | google-java-format | spotbugs |

### 附录 D：Markdown 报告模板

```markdown
## AI Guard Check Report

**Stage**: {{ report.stage }} | **Duration**: {{ (report.duration_ms / 1000) | round(1) }}s | **Result**: {% if report.passed %}✅ PASSED{% else %}❌ FAILED{% endif %}

### Results

| Check | Status | Violations | Duration |
|-------|--------|------------|----------|
{% for r in report.results -%}
| {{ r.name }} | {% if r.passed %}✅ Pass{% else %}❌ Fail{% endif %} | {{ r.violations | length }} | {{ (r.duration_ms / 1000) | round(1) }}s |
{% endfor %}

{% if not report.passed -%}
### Violations

{% for r in report.results if not r.passed -%}
**{{ r.name }}** ({{ r.violations[0].source if r.violations else 'unknown' }})
{% for v in r.violations -%}
- `{{ v.file }}{% if v.line %}:{{ v.line }}{% endif %}` — {{ v.message }}
{% endfor %}
{% if not r.violations -%}
- Check failed (exit code non-zero)
{% endif %}

{% endfor %}
{% endif -%}
---
*Generated by AI Guard at {{ timestamp }}*
```

---

**文档状态**：✅ 设计定稿  
**下一步**：按照 Phase 1 计划开始实现
