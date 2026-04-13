# AI Guard 系统设计文档

> **版本**: v3.1  
> **状态**: 设计定稿（架构边界统一 + 可靠性增强）  
> **目标**: 提供完整的 AI 行为约束与代码看护系统设计  
> **v3.1 更新**: 新增漂移检测、失败语义、Pattern 边界处理、Agent 能力提示等可靠性设计  

---

## 目录

- [1. 概述](#1-概述)
- [2. 双维度约束模型](#2-双维度约束模型)
- [3. 架构设计](#3-架构设计)
- [4. 关键设计（端到端链路）](#4-关键设计端到端链路)
- [5. 实施路线图](#5-实施路线图)
- [附录](#附录)
- [附录 D. v3.1 新增章节索引](#附录-d-v31-新增章节索引)

---

## 1. 概述

### 1.1 系统定位与目标

AI Guard 是一个面向 AI 编码 Agent 的看护系统，解决两类核心问题：

| 问题类型 | 具体表现 | 解决方式 |
|---|---|---|
| 行为失控 | 危险命令、敏感文件修改、绕过检查 | 运行时行为拦截 |
| 代码质量失控 | 规范不一致、测试不足、覆盖率不达标 | 提交前后代码验证 |

### 1.2 设计原则

1. **配置单一真相源**：配置层输出 `ResolvedPolicy`，其他层只消费。
2. **生成与执行分离**：安装时生成静态工件，运行时/提交时只执行。
3. **行为约束与代码约束分离**：前者实时判定，后者提交门禁。
4. **Agent 协议适配独立**：适配层做协议转换，不承载策略判断。

### 1.3 系统边界

**系统负责**：
- 行为约束（read/write/execute）
- 代码看护（静态检查、语义分析、动态验证、质量门禁）
- 规则集驱动的配置与工件生成

**系统不负责**：
- 自研 lint/test 引擎（复用 pre-commit 与成熟工具）
- 接管 AI 对话流程（只处理工具调用与提交门禁）

---

## 2. 双维度约束模型

### 2.1 行为约束维度（Runtime）

目标：在 AI 工具调用发生前进行策略判定。

| 操作类型 | 示例工具 | 约束来源 | 判定结果 |
|---|---|---|---|
| Read | read/grep/glob/webfetch | behavior 配置 | allow / deny / ask |
| Write | edit/write/apply_patch | behavior 配置 | allow / deny / ask |
| Execute | bash/shell | behavior 配置 | allow / deny / ask |

### 2.2 代码看护维度（Commit/Push）

目标：在代码进入仓库前做质量验证。

| 检查层 | 时机 | 代表项 |
|---|---|---|
| 静态检查 | pre-commit | 格式、命名、custom checks |
| 语义分析 | pre-commit / pre-push | clang-tidy 完整检查 |
| 动态验证 + 门禁 | pre-push | test / coverage / asan |

### 2.3 双维度协同

- 行为约束解决"能不能做（operation-level）"
- 代码看护解决"做得好不好（artifact-level）"

两者构成完整闭环：**先约束行为，再验证产物**。

---

## 3. 架构设计

### 3.1 五层架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI 层                                    │
│                   (命令解析、流程编排)                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       配置层                                     │
│        (加载/合并/校验 → 输出 ResolvedPolicy)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        核心层                                    │
│   ┌───────────┐  ┌───────────────────┐  ┌───────────────────┐  │
│   │Materializer│ │ Runtime Enforcement│ │ Verification      │  │
│   │ (物化器)   │ │   (运行时判定)     │ │ Orchestrator      │  │
│   │            │ │                   │ │ (验证编排器)       │  │
│   └───────────┘  └───────────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent 适配层（Agent Bridge）                  │
│          (协议转换：Agent事件 ↔ ToolCall ↔ Agent响应)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       输出层（Output Pipeline）                  │
│               (Content → Renderer → Channel)                     │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 各层职责与接口

#### 3.2.1 CLI 层

职责：命令入口、流程编排、错误与进度反馈。

| 命令 | 触发链路 | 说明 |
|---|---|---|
| `guard init` | 配置层 → Materializer | 初始化 guard.yaml，生成初始工件 |
| `guard install` | 配置层 → Materializer | 安装 hooks、生成所有工件 |
| `guard update` | 配置层 → Materializer | 更新工件（配置变更后） |
| `guard check` | Verification Orchestrator | 手动触发代码检查 |
| `guard verify` | Verification Orchestrator | 手动触发完整验证（含动态） |
| `guard gate run` | Git hook → Verification Orchestrator | 自动触发入口 |

#### 3.2.2 配置层（唯一解释权）

职责：加载、合并、校验配置，并输出 `ResolvedPolicy`。

**输入来源**：

| 来源 | 优先级 | 说明 |
|---|---|---|
| 内置默认 | 最低 | AI Guard 内置的基线配置 |
| 规则集（ruleset） | 中 | 公司/团队统一规范，可远程或本地 |
| 项目配置（guard.yaml） | 高 | 项目级自定义 |
| CLI 覆盖 | 最高 | 命令行参数覆盖 |

**输出**：`ResolvedPolicy`

> 配置层是配置语义唯一 owner；核心层和适配层禁止重复解析配置。

#### 3.2.3 核心层（三组件）

| 组件 | 职责 | 输入 | 输出 | 执行时机 |
|---|---|---|---|---|
| Materializer | 安装期工件生成 | ResolvedPolicy | 静态工件 | 安装时 |
| Runtime Enforcement | 运行时行为判定 | ToolCall + ResolvedPolicy | PolicyDecision | 运行时 |
| Verification Orchestrator | 提交验证编排 | stage + changed files + 工件 | CheckReport | 提交时 |

**关键边界**：
- Materializer 只"生成"，不"执行"
- Verification Orchestrator 只"执行编排"，不"生成配置"
- Runtime Enforcement 只做行为约束，不做代码质量验证

#### 3.2.4 Agent 适配层（Agent Bridge）

职责：协议转换与能力降级。

- 输入转换：Agent event → `ToolCall`
- 输出转换：`PolicyDecision` → Agent-specific response
- 能力降级：如不支持 ask 则降级 deny

**Agent 能力差异**：

| Agent | Hook 机制 | can_block | can_ask | 拦截方式 |
|---|---|---|---|---|
| Claude Code | PreToolUse Hook | ✅ | ✅ | 返回 deny/ask |
| Cursor | 多 Hook | ✅ | ⚠️ 部分 | 返回 permission |
| OpenCode | 插件内事件 | ✅ | ✅ | throw Error |
| Copilot | 无 Hook | ❌ | ❌ | 仅规则文档 |

#### 3.2.5 输出层（Output Pipeline）

职责：结果渲染与分发。

```
Content → Renderer → Channel
```

| Content 类型 | 来源 | 包含内容 |
|---|---|---|
| PolicyDecision | Runtime Enforcement | allow/deny/ask + message |
| CheckReport | Verification Orchestrator | violations + summary + metrics |
| InstallSummary | Materializer | 工件生成结果 |
| StatusReport | CLI | 安装状态、Agent 状态 |

---

### 3.3 三条主数据流

#### 3.3.1 安装流（init/install）

```
CLI 命令
  │
  ▼
配置层（加载/合并/校验 → ResolvedPolicy）
  │
  ▼
Materializer（生成所有静态工件）
  │
  ▼
输出层（写入文件）
```

工件清单：
- 规则文档（CLAUDE.md / AGENTS.md / ...）
- Agent Hook/插件配置
- 工具配置（.clang-format/.clang-tidy/...）
- `.pre-commit-config.yaml`
- Git hooks（.git/hooks/pre-commit, .git/hooks/pre-push）

#### 3.3.2 运行时行为约束流

```
Agent 工具调用事件
  │
  ▼
Agent Bridge（转换为统一 ToolCall）
  │
  ▼
Runtime Enforcement（策略判定 → PolicyDecision）
  │
  ▼
Agent Bridge（转回 Agent 协议格式）
  │
  ▼
执行/阻断
```

#### 3.3.3 提交验证流（commit/push）

```
git commit/push
  │
  ▼
.git/hooks/pre-commit | pre-push
  │
  ▼
guard gate run --stage commit | push
  │
  ▼
Verification Orchestrator
  │
  ▼
pre-commit 框架执行（调用各检查工具）
  │
  ▼
CheckReport（通过/阻断）
```

### 3.4 关键架构决策

1. **配置层保留并作为唯一真相源**：避免多处解析导致漂移。  
2. **配置生成与执行分离**：解决 `.pre-commit-config.yaml` owner 冲突。  
3. **代码看护委托 pre-commit 生态**：避免重复造轮子。  
4. **适配层与核心层分离**：支持后续接入更多 Agent（KiloCode/CodeX/Gemini）。

---

## 4. 关键设计（端到端链路）

### 4.1 CLI 入口与编排链路

#### 端到端视角

```
用户输入命令
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                        CLI 层                                    │
│                                                                 │
│   ┌─────────────┐                                               │
│   │ 命令解析     │  解析参数、flag、选项                         │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 命令路由     │  根据命令类型分发到对应链路                    │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ├────────────────┬────────────────┬─────────────────┐  │
│          ▼                ▼                ▼                  │  │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │  │
│   │ 生命周期命令 │  │ 检查命令     │  │ 门禁命令     │         │  │
│   │ init/install │  │ check/verify │  │ gate run    │         │  │
│   └─────────────┘  └─────────────┘  └─────────────┘         │  │
└─────────────────────────────────────────────────────────────────┘
```

#### 命令路由规则

| 命令类型 | 命令 | 走向 | 说明 |
|---|---|---|---|
| **生命周期命令** | `init`、`install`、`update`、`uninstall` | 配置层 → Materializer | 生成/更新/删除工件 |
| **检查命令** | `check`、`verify` | Verification Orchestrator | 手动触发代码检查 |
| **门禁命令** | `gate run --stage commit/push` | Git hook → Verification Orchestrator | 自动触发入口 |
| **信息命令** | `status`、`agents` | 配置层 | 查看安装状态 |
| **规则集命令** | `ruleset add`、`ruleset update` | 配置层 | 管理规则集 |

#### 关键设计点

- CLI 只做编排，不做策略判断
- 每条命令统一返回结构化结果（exit code + JSON 输出），便于脚本化调用
- 命令执行失败时，输出层负责格式化错误信息

#### 验证方法

```bash
# 验证命令路由正确性
guard init --agent claude-code    # 应走配置层 → Materializer
guard check                      # 应走 Verification Orchestrator
guard gate run --stage commit    # 应走 Git hook → Verification Orchestrator
guard status                     # 应走配置层
```

---

### 4.2 配置物化链路（Install-Time）

#### 端到端视角

```
guard install --agent claude-code
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      配置层                                      │
│                                                                 │
│   ┌─────────────┐                                               │
│   │ 配置加载     │  加载 defaults + ruleset + guard.yaml         │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 配置合并     │  三级合并（默认 → 规则集 → 项目）             │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 配置校验     │  schema 校验 + 字段一致性检查                 │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ResolvedPolicy                                                │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Materializer                               │
│                                                                 │
│   ┌─────────────┐                                               │
│   │ 规则文档生成  │  ResolvedPolicy → CLAUDE.md / AGENTS.md     │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ Hook 配置生成 │  Agent 特定的 Hook/插件文件                  │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 工具配置复制  │  规则集中的 .clang-format 等 → 项目目录      │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ pre-commit  │  ResolvedPolicy → .pre-commit-config.yaml     │
│   │ 配置生成     │                                               │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   静态工件清单                                                   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      输出层                                      │
│                                                                 │
│   写入所有工件到项目目录                                         │
│   输出 InstallSummary                                           │
└─────────────────────────────────────────────────────────────────┘
```

#### Artifact Owner（唯一）

| 工件 | Owner | 来源 |
|---|---|---|
| 规则文档（CLAUDE.md 等） | Materializer | 从 ResolvedPolicy 生成 |
| Agent Hook/插件文件 | Materializer | 从 ResolvedPolicy 生成 |
| 工具配置（.clang-format 等） | Materializer | 从规则集复制 |
| `.pre-commit-config.yaml` | Materializer | 从 ResolvedPolicy 生成 |
| `.git/hooks/*` | Materializer | 从模板生成 |

#### 关键设计点

- 所有静态工件都在安装时生成一次，后续只消费不重新生成
- `ResolvedPolicy` 是 Materializer 的唯一输入，配置语义不由 Materializer 解释
- 工具配置从规则集复制，而非从 ResolvedPolicy 重新生成（避免格式差异）
- `.pre-commit-config.yaml` 由 Materializer 统一生成，Verification Orchestrator 只消费

#### 漂移检测机制

**问题背景**：用户修改 `guard.yaml` 后可能忘记执行 `guard update`，导致生成的工件与当前配置不一致。

**设计原则**：用户有责任在配置变更后执行 `update`，但系统提供友好提醒。

**检测机制**：

```
安装时（guard install/update）：
  ├─ 计算 guard.yaml 内容的 hash（如 SHA-256 前 8 位）
  ├─ 在每个生成的工件中嵌入 hash
  │   ├─ CLAUDE.md：<!-- AI-GUARD-HASH: abc12345 -->
  │   ├─ interceptor.py：POLICY_HASH = "abc12345"
  │   └─ .pre-commit-config.yaml：注释标记 # AI-GUARD-HASH: abc12345
  └─ 记录到 .ai-guard/state.json

运行时启动检查：
  ├─ 读取 .ai-guard/state.json 获取安装时的 hash
  ├─ 计算当前 guard.yaml 的 hash
  ├─ 对比是否一致
  └─ 不一致时输出警告（不阻止执行）
```

**警告输出示例**：

```
⚠️  检测到配置漂移！
    当前 guard.yaml 已修改，但工件未更新。
    请运行 `guard update` 同步最新配置。
    当前生效的是旧配置版本。
```

**设计选择**：

| 选项 | 行为 | 选择 |
|---|---|---|
| 检测到漂移后警告 | 提醒用户但不阻止 | ✅ 采用 |
| 检测到漂移后拒绝 | 强制用户 update | ❌ 不采用（UX 摩擦大） |
| 不检测 | 完全依赖用户自觉 | ❌ 不采用（问题难排查） |

#### 验证方法

```bash
# 验证工件生成完整性
guard install --agent claude-code
ls -la CLAUDE.md                    # 应存在
ls -la .claude/settings.json        # 应存在
ls -la .clang-format               # 应存在
ls -la .pre-commit-config.yaml     # 应存在
cat .pre-commit-config.yaml        # 应包含正确的 hooks 配置
```

---

### 4.3 运行时行为约束链路（Runtime）

#### 端到端视角

```
AI Agent 发起工具调用
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Agent Hook 机制                                 │
│                                                                 │
│   PreToolUse Hook 触发（Agent 特定事件）                        │
│   传入：tool_name + tool_args                                   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Agent Bridge                                    │
│                                                                 │
│   ┌─────────────┐                                               │
│   │ 输入转换     │  Agent 事件 → 统一 ToolCall                   │
│   └──────┬──────┘                                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Runtime Enforcement                             │
│                                                                 │
│   ┌─────────────┐                                               │
│   │ 工具分类     │  确定操作类型（read/write/execute）           │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 目标提取     │  提取检查目标（路径/命令/MCP server:tool）    │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 规则匹配     │  Pattern 匹配（支持通配符、正则）            │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   PolicyDecision（allow / deny / ask + message）                │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Agent Bridge                                    │
│                                                                 │
│   ┌─────────────┐                                               │
│   │ 输出转换     │  PolicyDecision → Agent 协议格式              │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 能力降级     │  Agent 不支持 ask 时降级为 deny               │
│   └──────┬──────┘                                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
Agent 执行或阻断操作
```

#### 判定规则优先级

| 优先级 | 规则类型 | 处理 |
|---|---|---|
| 1（最高） | forbidden | 直接 deny |
| 2 | require_approval | ask（等待用户确认） |
| 3 | write_allowlist | 在白名单内则 allow |
| 4（最低） | 默认 | allow |

#### Pattern 匹配逻辑

```
输入目标路径：src/main.c

匹配顺序：
1. 精确匹配：src/main.c
2. 通配符匹配：src/**/*.c
3. 目录匹配：src/**
4. 扩展名匹配：*.c
5. 前缀匹配：src/
```

#### Pattern 边界处理

**问题背景**：AI 传入的路径可能包含各种边界情况，匹配逻辑需要正确处理。

**路径预处理流程**：

```
AI 传入路径 → 路径归一化 → 项目边界检查 → Pattern 匹配
```

**路径归一化规则**：

| 输入路径 | 归一化结果 | 处理说明 |
|---|---|---|
| `./src/main.c` | `src/main.c` | 去掉 `./` 前缀 |
| `src/../include/header.h` | `include/header.h` | 解析 `..` 路径段 |
| `/project/src/main.c` | `src/main.c` | 绝对路径转相对路径（基于项目根） |
| `src//main.c` | `src/main.c` | 合并连续分隔符 |

**项目边界检查**：

| 检查项 | 说明 | 处理 |
|---|---|---|
| 路径逃逸 | `../outside/file.c` 逃出项目目录 | **deny** + 提示"路径超出项目范围" |
| 路径遍历 | 路径中包含 `..` 但未逃逸 | 归一化后继续匹配 |
| 符号链接 | 路径包含符号链接 | 解析后检查是否在项目内 |

**通配符语义定义**：

| Pattern | 匹配规则 | 示例 |
|---|---|---|
| `*` | 匹配单层任意字符（不含 `/`） | `src/*.c` 匹配 `src/main.c`，不匹配 `src/sub/main.c` |
| `**` | 匹配任意层级（含空路径） | `src/**` 匹配 `src/`、`src/main.c`、`src/sub/main.c` |
| `**/` | 匹配任意层级目录 | `**/test/` 匹配任意位置的 test 目录 |
| `/**` | 匹配目录下所有内容 | `src/**` 匹配 src 目录下所有文件和子目录 |

**边界情况测试用例**：

```
配置：forbidden: ["third_party/**"]

测试用例：
  ✅ third_party/lib.c         → deny（匹配）
  ✅ third_party/sub/lib.c     → deny（** 递归匹配）
  ✅ ./third_party/lib.c       → deny（归一化后匹配）
  ❌ src/third_party_mock.c    → allow（不是 third_party 目录）
  ❌ third_party               → deny（** 匹配空路径，目录本身也禁止）
  
配置：forbidden: ["*.env"]

测试用例：
  ✅ .env                      → deny（匹配）
  ✅ config/.env               → deny（匹配）
  ❌ .env.example              → allow（不匹配）
  
配置：forbidden: ["shell:git commit --no-verify"]

测试用例：
  ✅ git commit --no-verify              → deny
  ✅ git commit --no-verify -m "msg"     → deny（后缀匹配）
  ⚠️ git  commit --no-verify             → 需要归一化空格
  ⚠️ git commit -n                       → 需要等价形式检测（可选增强）
```

**实现建议**：

1. 使用成熟的 glob 库（如 Python `pathspec`、Node `micromatch`）
2. 匹配前必须进行路径归一化
3. 必须检查路径是否在项目边界内
4. 添加边界情况的单元测试覆盖

#### 异常处理（失败语义）

**设计原则**：采用 **fail-closed** 策略，异常时优先拦截以保证安全。

| 异常场景 | 处理方式 | 理由 |
|---|---|---|
| Agent 不支持 ask | 降级为 deny | 安全优先 |
| Hook 脚本执行超时 | 返回 deny + 超时提示 | 安全优先 |
| Pattern 匹配代码崩溃 | 返回 deny + 错误提示 | 安全优先（fail-closed） |
| Pattern 格式错误 | 返回 deny + 配置错误提示 | 配置错误不应放行 |
| Agent Bridge 转换失败 | 返回 deny + 转换错误提示 | 无法判断时安全优先 |
| 配置文件缺失 | 区分情况处理 | 见下表 |

**配置文件缺失的处理策略**：

| 场景 | 处理方式 | 理由 |
|---|---|---|
| 首次运行未 install | 提示运行 `guard install` + 允许操作 | 引导用户完成初始化 |
| 配置被删除（本该存在） | deny + 提示恢复配置 | 安全优先 |

**失败语义总结**：

```
默认行为：deny（fail-closed）
例外情况：
  ├─ 首次运行未 install → allow + 引导提示
  └─ Agent 能力不足（can_block=false）→ 无法拦截（非异常）
```

#### 关键设计点

- Runtime Enforcement 是纯策略判定内核，不关心 Agent 协议细节
- Agent Bridge 只负责协议适配，不做策略判断
- 不在该链路执行 test/lint/coverage（那是 Verification Orchestrator 的职责）
- 判定依据是安装时生成的配置快照，而非实时读取 behavior.yaml

#### 验证方法

```bash
# 验证行为拦截
# 1. 尝试写入禁止文件
# 应返回 deny

# 2. 尝试写入需审批文件
# 应返回 ask

# 3. 尝试写入白名单文件
# 应返回 allow
```

---

### 4.4 提交验证链路（Commit/Push）

#### 端到端视角

```
git commit / git push
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Git Hook（安装时由 Materializer 生成）          │
│                                                                 │
│   .git/hooks/pre-commit  或  .git/hooks/pre-push               │
│   触发：guard gate run --stage commit / push                   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Verification Orchestrator                       │
│                                                                 │
│   ┌─────────────┐                                               │
│   │ 阶段识别     │  确定是 commit 还是 push 阶段                 │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 变更检测     │  识别变更文件列表                             │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 检查编排     │  按阶段调度对应的检查层                       │
│   └──────┬──────┘                                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  pre-commit 框架                                │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │ commit 阶段：                                           │  │
│   │   静态检查：clang-format + naming + custom checks       │  │
│   │   语义分析：clang-tidy（完整检查）                       │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │ push 阶段（commit 阶段全部通过后）：                     │  │
│   │   动态验证：test + coverage                             │  │
│   │   质量门禁：阈值检查                                     │  │
│   └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  结果汇总                                        │
│                                                                 │
│   汇总为 CheckReport：                                          │
│   - violations（违规列表）                                      │
│   - summary（通过/失败）                                        │
│   - metrics（覆盖率、测试数等）                                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
通过/阻断 git commit / git push
```

#### 三层检查详解

| 检查层 | 时机 | 编译依赖 | 代表项 | 耗时 |
|---|---|---|---|---|
| 静态检查 | pre-commit | 不需要 | 格式化、命名、custom checks | 极低（毫秒级） |
| 语义分析 | pre-push | 需要 compile_commands.json | clang-tidy 完整检查 | 中等（秒级） |
| 动态验证 + 门禁 | pre-push | 需要编译 + 运行 | test、coverage、asan | 高（分钟级） |

#### 触发方式对比

| 触发方式 | 入口 | 时机 | 说明 |
|---|---|---|---|
| 自动 | `.git/hooks/pre-commit` | git commit 前 | 日常主路径 |
| 自动 | `.git/hooks/pre-push` | git push 前 | 门禁主路径 |
| 手动 | `guard check` | 任意时机 | 本地预检 |
| 手动 | `guard verify` | 任意时机 | 完整验证（含动态） |

#### 关键设计点

- Verification Orchestrator 只负责编排，不负责生成配置（`.pre-commit-config.yaml` 由 Materializer 生成）
- 检查逻辑委托给 pre-commit 框架和成熟工具（clang-format/clang-tidy/pytest 等）
- 手动触发与自动触发复用同一套检查编排逻辑
- 检查失败时，输出层负责格式化违规信息

#### 验证方法

```bash
# 验证自动触发
git commit    # 应触发 pre-commit，执行静态检查
git push      # 应触发 pre-push，执行语义分析 + 动态验证

# 验证手动触发
guard check   # 应执行静态检查
guard verify  # 应执行完整验证（含 test/coverage）
```

---

### 4.5 Agent 适配链路

#### 端到端视角

```
Agent 事件（Agent 特定格式）
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Agent Bridge                                    │
│                                                                 │
│   ┌─────────────┐                                               │
│   │ 协议识别     │  确定 Agent 类型                              │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 输入转换     │  Agent 事件 → 统一 ToolCall                   │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 输出转换     │  PolicyDecision → Agent 协议格式              │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ 能力降级     │  根据 Agent 能力调整决策                       │
│   └──────┬──────┘                                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
Agent 接收并执行/阻断
```

#### 三种 Agent 适配策略

| Agent 类型 | 代表 | 适配方式 | 说明 |
|---|---|---|---|
| 外部 Hook 型 | Claude Code、Cursor | 生成 Python 脚本，脚本内调用核心库 | 需要脚本桥接 |
| 插件型 | OpenCode | 插件内直接调用核心库 | 性能最优 |
| 无 Hook 型 | Copilot、KiloCode | 仅规则文档，无运行时拦截 | 代码看护仍有效 |

#### 能力降级规则

| Agent 能力 | 无能力时降级为 | 说明 |
|---|---|---|
| can_block = false | 不降级（无法拦截） | 仅靠规则文档引导 |
| can_ask = false | ask → deny | 不支持用户确认时，转为拒绝 |
| can_rewrite_input = false | 不降级 | 无法修改输入 |

#### Agent 能力提示设计

**问题背景**：不同 Agent 的 Hook 能力不同，用户需要知道哪些策略在当前 Agent 上生效。

**安装时提示**：

```
$ guard install --agent copilot

✅ 规则文档已生成：.github/copilot-instructions.md
✅ Git hooks 已安装：.git/hooks/pre-commit, .git/hooks/pre-push

⚠️  重要提示：Copilot 能力限制

  Copilot 不支持 Hook 机制（can_block=false, can_ask=false），
  以下策略将无法在运行时生效：

  ❌ file_protection.forbidden     → 无法拦截，依赖 AI 遵守规则文档
  ❌ file_protection.require_approval → 无法 ask，依赖人工审查
  ❌ command_restriction.forbidden   → 无法拦截，依赖 AI 遵守规则文档

  ✅ 仍有效的保障机制：
  ├─ 规则文档（.github/copilot-instructions.md）引导 AI 行为
  ├─ pre-commit 检查（代码格式、命名规范等）
  ├─ pre-push 门禁（测试、覆盖率等）
  └─ 人工 Code Review

  建议：对高敏感操作，依赖 CI/服务端验证作为最终保障
```

**状态查询提示**：

```
$ guard status

项目：my-project
Agent：Claude Code, Cursor

┌─────────────────────────────────────────────────────────────┐
│ Agent 能力矩阵                                               │
├─────────────┬────────────┬─────────┬───────────────────────┤
│ Agent       │ can_block  │ can_ask │ 生效策略              │
├─────────────┼────────────┼─────────┼───────────────────────┤
│ Claude Code │ ✅         │ ✅      │ 全部                  │
│ Cursor      │ ✅         │ ⚠️ 部分  │ 全部（ask 降级 deny） │
│ Copilot     │ ❌         │ ❌      │ 仅规则文档 + 提交门禁 │
└─────────────┴────────────┴─────────┴───────────────────────┘

配置状态：✅ 已安装（hash: abc12345）
最后更新：2025-04-02 10:30:00
```

**策略配置时的能力检查**：

如果用户配置了某个 Agent 不支持的策略，在 `guard install` 时给出警告：

```
$ guard install --agent copilot

⚠️  策略兼容性警告

  配置中包含以下策略，但 Copilot 不支持：
  
  - file_protection.forbidden:
      pattern: "secrets/**"
      reason: "禁止访问 secrets 目录"
    
  该策略无法在 Copilot 上运行时生效。
  仍要继续安装吗？[y/N]
```

**设计原则**：

| 原则 | 说明 |
|---|---|
| **透明化** | 用户明确知道哪些策略生效、哪些不生效 |
| **不隐藏** | 不支持的策略不假装生效，明确告知限制 |
| **引导替代** | 提示用户可依赖的其他保障机制 |

#### 关键设计点

- Agent Bridge 只做协议转换，不做策略判断
- 新增 Agent 只需实现一个 Bridge，不影响核心层
- 无 Hook 型 Agent 仍可通过规则文档 + 代码看护链路生效

#### 验证方法

```bash
# 验证多 Agent 支持
guard install --agent claude-code    # 应生成 .claude/ 文件
guard install --agent cursor         # 应生成 .cursor/ 文件
guard install --agent copilot        # 应仅生成规则文档
```

---

### 4.6 输出与可观测性链路

#### 端到端视角

```
检查结果 / 判定结果
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Output Pipeline                                 │
│                                                                 │
│   ┌─────────────┐                                               │
│   │ Content     │  结构化数据（PolicyDecision/CheckReport 等）  │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ Renderer    │  格式转换（Markdown/JSON/Console）             │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ Channel     │  输出目标（终端/文件/GitHub PR 评论）         │
│   └──────┬──────┘                                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
用户 / 系统消费
```

#### Content 类型定义

| Content 类型 | 来源 | 包含内容 | 输出时机 |
|---|---|---|---|
| PolicyDecision | Runtime Enforcement | allow/deny/ask + message + rule_id | 实时 |
| CheckReport | Verification Orchestrator | violations + summary + metrics | 提交时 |
| InstallSummary | Materializer | 工件清单 + 生成状态 | 安装时 |
| StatusReport | CLI | Agent 状态 + 安装状态 | 查询时 |

#### Renderer 类型

| Renderer | 输出格式 | 用途 |
|---|---|---|
| MarkdownRenderer | Markdown | 规则文档、PR 评论 |
| JsonRenderer | JSON | API 输出、脚本消费 |
| ConsoleRenderer | ANSI 终端 | 终端显示（带颜色、进度） |

#### Channel 类型

| Channel | 输出目标 | 配置 |
|---|---|---|
| ConsoleChannel | 终端 stdout | 无需配置 |
| FileChannel | 文件系统 | path 参数 |
| GitHubChannel | PR 评论 | token + repo + pr_number |

#### 推荐审计字段

| 字段 | 说明 |
|---|---|
| `timestamp` | 事件时间 |
| `agent` | Agent 类型 |
| `tool` | 工具名称 |
| `stage` | 阶段（install/runtime/commit/push） |
| `decision` | 决策（allow/deny/ask） |
| `reason` | 判定原因 |
| `rule_id` | 命中规则 ID |

#### 关键设计点

- 输出层不参与策略判断和编排
- 同一 Content 可用不同 Renderer 渲染
- 审计字段标准化，便于后续扩展

---

### 4.7 关键权衡与边界

#### 职责归属表

| 边界 | 归属 | 不允许 |
|---|---|---|
| 配置定义/解释 | 配置层 | 核心层/适配层重复解析 |
| 静态工件生成 | Materializer | Verification Orchestrator 生成配置 |
| 运行时行为判定 | Runtime Enforcement | 代码质量验证 |
| commit/push 检查编排 | Verification Orchestrator | 重新生成配置 |
| Agent 协议转换 | Agent Bridge | 策略判断 |
| 结果渲染与分发 | Output Pipeline | 策略判断 |

#### Must Have

1. 配置单一真相源（ResolvedPolicy）
2. 配置生成与执行分离
3. 代码看护委托 pre-commit 生态
4. Agent 适配与核心判定分离

#### Must NOT Have

1. 核心层重复解析配置
2. Verification Orchestrator 生成 `.pre-commit-config.yaml`
3. Agent Bridge 做策略判断
4. 自研 lint/test 引擎

#### 边界原则

> **一个职责只归一个 owner**。  
> 如果两个组件都在做同一件事，说明职责划分有问题。

---

## 5. 实施路线图

### 5.1 Phase 划分

#### Phase 1：配置层 + Materializer

**目标**：完成配置单一真相源与工件生成

**交付物**：
- ResolvedPolicy 输出契约
- Materializer（规则文档、工具配置、pre-commit 配置生成）
- CLI 基础命令（init/install/status）

**验证标准**：
- `guard init --agent claude-code` 生成完整配置
- CLAUDE.md 包含完整规则
- `.pre-commit-config.yaml` 配置正确

#### Phase 2：Runtime Enforcement + Agent Bridge

**目标**：完成运行时行为约束链路

**交付物**：
- Runtime Enforcement 核心逻辑
- Agent Bridge（Claude Code + Cursor）
- Pattern 匹配引擎

**验证标准**：
- 拦截禁止的文件写入
- 拦截禁止的命令执行
- 返回正确的 deny/ask 决策

#### Phase 3：Verification Orchestrator

**目标**：完成代码看护链路

**交付物**：
- Verification Orchestrator（pre-commit 编排）
- check/verify 命令
- CheckReport 标准结构

**验证标准**：
- pre-commit 检查正确执行
- 手动触发可用
- 结果汇总正确

#### Phase 4：多 Agent 扩展 + 可观测性增强

**目标**：完成多 Agent 适配与审计能力

**交付物**：
- OpenCode Agent Bridge
- Output Pipeline 增强
- 审计日志

**验证标准**：
- 多 Agent 配置正确生成
- 审计字段完整
- 输出格式多样

### 5.2 里程碑

| 里程碑 | 交付内容 |
|---|---|
| M1 | 配置单一真相源与工件生成可用 |
| M2 | 行为约束链路可用 |
| M3 | 代码看护链路可用 |
| M4 | 多 Agent 扩展与审计可用 |

### 5.3 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| Agent Hook 协议变更 | 运行时拦截失效 | 适配层隔离 + 版本探测 |
| 工具链兼容差异 | 检查误报/漏报 | ruleset 分语言版本化 |
| 配置漂移 | 执行结果不一致 | 强制 `ResolvedPolicy` 单入口 |

---

## 附录

### A. 最小目录建议

```
ai-guard/
├── cli/
│   ├── guard.py
│   └── commands/
├── config/
│   ├── loader.py         # 配置加载/合并/校验
│   └── defaults/
├── core/
│   ├── materializer/
│   │   ├── rule_doc.py       # 规则文档生成
│   │   ├── hook_config.py    # Hook 配置生成
│   │   ├── tool_config.py    # 工具配置复制
│   │   └── precommit.py      # .pre-commit-config.yaml 生成
│   ├── runtime_enforcement/
│   │   ├── interceptor.py    # 策略判定核心
│   │   └── pattern.py        # Pattern 匹配引擎
│   └── verification_orchestrator/
│       ├── orchestrator.py   # 检查编排
│       └── report.py         # 结果汇总
├── adapters/
│   ├── base.py               # Agent Bridge 基类
│   ├── claude_code.py
│   ├── cursor.py
│   ├── opencode.py
│   └── copilot.py
├── output/
│   ├── content/
│   ├── renderer/
│   └── channel/
└── templates/
```

### B. 术语表

| 术语 | 含义 |
|---|---|
| ResolvedPolicy | 配置层产出的统一可执行配置对象 |
| Materializer | 安装期静态工件生成组件 |
| Runtime Enforcement | 运行时行为约束判定组件 |
| Verification Orchestrator | 提交验证编排组件 |
| Agent Bridge | Agent 协议转换组件 |
| Output Pipeline | 结果渲染与分发组件 |
| PolicyDecision | 行为约束判定结果（allow/deny/ask） |
| CheckReport | 代码验证检查报告 |

### C. 文档一致性检查清单

- [x] 版本更新为 v3.1
- [x] 核心层仅三组件（无旧命名冲突）
- [x] `.pre-commit-config.yaml` owner 唯一（Materializer）
- [x] 第4章按 4.1–4.7 组织
- [x] 无重复的旧 3.x 架构段落
- [x] 每条链路有输入/输出契约
- [x] 每条链路有验证方法
- [x] 新增漂移检测机制（4.2）
- [x] 新增完整失败语义定义（4.3）
- [x] 新增 Pattern 边界处理设计（4.3）
- [x] 新增 Agent 能力提示设计（4.5）

### D. v3.1 新增章节索引

| 章节 | 内容 | 位置 |
|---|---|---|
| 漂移检测机制 | 配置-工件一致性检测与警告 | 4.2 配置物化链路 |
| 异常处理（失败语义） | fail-closed 策略与完整异常处理表 | 4.3 运行时行为约束链路 |
| Pattern 边界处理 | 路径归一化、项目边界检查、通配符语义 | 4.3 运行时行为约束链路 |
| Agent 能力提示设计 | 安装时提示、状态查询、兼容性警告 | 4.5 Agent 适配链路 |
