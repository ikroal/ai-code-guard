# AI Guard 系统设计文档

> **版本**: v2.0  
> **状态**: 设计完成（规则集架构 + 验证项注册机制）  
> **目标**: 提供完整的 AI 行为约束与代码看护系统设计  
> **v2.0 重大更新**:
> - **规则集架构**：支持外部规则集导入，公司/项目统一维护规范
> - **验证项注册机制**：动态验证层支持用户注册自定义验证项
> - **标准输出格式**：定义 AI Guard 标准输出格式，用户编写适配脚本
> - **工具编排策略**：复用成熟工具（clang-tidy/ESLint/dependency-cruiser等），不重复造轮子
> - **三层划分修正**：按执行时机划分，明确编译依赖关系

---

## 1. 概述

### 1.1 系统定位与目标

AI Guard 是一个面向 AI 编码 Agent 的**看护系统**，旨在解决以下核心问题：

| 问题类型 | 具体表现 | AI Guard 解决方案 |
|---------|---------|------------------|
| **行为失控** | AI 执行危险命令、修改关键文件、绕过检查机制 | 实时拦截 + 禁止清单 |
| **代码质量** | AI 生成代码不符合项目规范、缺少测试覆盖 | 静态检查 + 质量门禁 |
| **规范分散** | 约束规则散落在多个文件，难以维护迁移 | 统一配置文件 guard.yaml |
| **Agent 差异** | 不同 AI Agent 的约束方式各异，无法复用 | Agent 适配层统一处理 |

**目标用户**：
- 使用 AI Agent 辅助编码的开发者
- 需要统一代码规范的团队
- 希望将现有看护系统迁移到新项目的维护者

### 1.2 核心设计理念

| 设计理念 | 具体内涵 | 实现体现 |
|---------|---------|---------|
| **统一配置** | 所有约束规则集中在一个 YAML 文件 | `guard.yaml` 作为单一真相源 |
| **多 Agent 支持** | 同一配置可适配不同 AI Agent | CLI `--agent` 参数 + Agent 适配层 |
| **三层生效** | 约束在事前、事中、事后三个阶段生效 | 文档引导 → Hook 拦截 → Commit 验证 |
| **双维度约束** | 行为约束 + 代码看护形成完整闭环 | 配置分为 `behavior` 和 `code` 两个区块 |

### 1.3 适用场景

| 场景类型 | 适用性 | 说明 |
|---------|--------|------|
| **新项目初始化** | ✅ 完全适用 | `guard init` 快速建立看护体系 |
| **现有项目迁移** | ✅ 完全适用 | `guard install` 安装到现有项目 |
| **多项目统一规范** | ✅ 完全适用 | 复用同一 guard.yaml 模板 |
| **团队协作项目** | ✅ 完全适用 | 配置文件可纳入版本控制 |
| **多 Agent 环境** | ✅ 完全适用 | 一份配置支持多个 Agent 同时使用 |

---

## 2. 双维度约束模型

### 2.1 行为约束维度

#### 2.1.1 完整性论证

**核心问题**：如何确保行为约束覆盖所有 AI 可能产生的风险操作？

**推导逻辑**：

从"AI 可执行的操作类型"出发，建立完整的约束矩阵：

> **系统边界声明**：当前行为约束模型针对**文件读写 + 命令执行型编码 Agent**（如 Claude Code、Cursor、OpenCode）。
> 若 Agent 支持浏览器操作、HTTP 请求、MCP 调用、环境变量访问、剪贴板读写等能力，需扩展"外部资源访问"维度。

```
AI 操作类型        约束层级          风险等级          对应配置项
────────────────────────────────────────────────────────────────
Read (读取)       无限制            低               -
                  需审批            中               path_access.require_approval
                  禁止              高               path_access.forbidden

Write (写入)       无限制            低               -
                  允许白名单        中               file_protection.write_allowlist
                  需审批            高               file_protection.require_approval
                  禁止              极高             file_protection.forbidden

Execute (执行)     无限制            低               -
                  自动允许          中               command_restriction.auto_allow
                  需审批            高               -
                  禁止              极高             command_restriction.forbidden
```

**为什么 `file_protection`、`command_restriction`、`path_access` 是完整的？**

1. **覆盖所有操作类型**：AI 与代码库的交互只有三种：读取文件、写入文件、执行命令。三个配置项恰好对应这三种操作。

2. **覆盖所有风险层级**：从"无限制"到"禁止"，每个层级都有对应的处理方式：
   - 无限制：不做任何检查
   - 允许/自动允许：白名单机制，快速放行安全操作
   - 需审批：拦截并提示用户确认
   - 禁止：直接拒绝并返回错误

3. **无遗漏证明**：
   - AI 想读取敏感文件？ → `path_access.forbidden` 拦截
   - AI 想写入禁止目录？ → `file_protection.forbidden` 拦截
   - AI 想执行危险命令？ → `command_restriction.forbidden` 拦截
   - AI 想修改检查系统？ → `file_protection.require_approval` 提示确认

**结论**：三个配置项形成的约束矩阵完整覆盖了 AI 行为风险的所有可能情况。

#### 2.1.2 闭环机制

行为约束的闭环由三层生效机制构成：

```
┌─────────────────────────────────────────────────────────────────┐
│  第一层：事前文档告知                                            │
│  ├─ 生成 CLAUDE.md / .cursor/rules/ 等规则文档                  │
│  ├─ AI 在执行前已知晓约束边界                                    │
│  └─ 效果：主动规避 70% 违规行为                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  第二层：事中 Hook 拦截                                          │
│  ├─ PreToolUse Hook 实时检查每个操作                            │
│  ├─ 违规操作被拦截，返回错误信息                                 │
│  └─ 效果：阻止 90% 剩余违规行为                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  第三层：事后无法绕过                                            │
│  ├─ git commit --no-verify 被禁止                               │
│  ├─ git config core.hooksPath 被禁止                            │
│  ├─ 即使 AI 尝试绕过，命令本身被拦截                             │
│  └─ 效果：形成最终的闭环保护                                     │
└─────────────────────────────────────────────────────────────────┘
```

**闭环论证**：

- **正向闭环**：文档告知 → AI 尝试合规 → 合规操作放行 → 代码进入看护流程
- **反向闭环**：AI 尝试违规 → Hook 拦截 → 返回错误 → AI 修正行为或用户介入
- **无法逃逸**：绕过机制本身被约束，形成递归保护

### 2.2 代码看护维度

#### 2.2.1 完整性论证

##### 开篇：AI 代码的典型质量问题

AI 生成的代码可能出现哪些问题？让我们从一个真实场景说起：

```
AI 帮你写了一个新功能，代码提交了。第二天同事 review：

同事 A："这变量名 abc 是什么意思？看不懂"
同事 B："函数没写注释，我不知道它要干什么"
同事 C："utils 怎么依赖了 interface？架构乱了"
同事 D："缩进是 2 空格还是 4 空格？能不能统一？"

代码能跑，但质量一塌糊涂。
```

这些问题的共同点是：**不需要运行代码就能发现**。

这就是"代码看护"要解决的核心问题——在代码入库前，系统性地拦截各类质量问题。

##### 三层看护的金字塔结构

从"发现问题的成本"出发，我们设计了一个金字塔：

```
                    ┌───────────────┐
                    │   质量门禁     │  ← 需要编译/运行，成本高
                    │  (工程健康度)  │     pre-push 执行
                    ├───────────────┤
                    │   动态验证     │  ← 需要运行代码，成本中
                    │  (功能正确性)  │     pre-push 执行
            ┌───────┴───────────────┴───────┐
            │        静态检查               │  ← 看文本即可，成本低
            │      (代码本体质量)           │     pre-commit 执行
            └───────────────────────────────┘
```

**为什么这样分层？**

| 层级 | 怎么发现问题 | 执行时机 | 开发者体验 |
|-----|------------|---------|-----------|
| 静态检查 | 看一眼代码文本 | 每次 commit | 快，几秒内反馈 |
| 动态验证 | 运行代码看结果 | 每次 push | 中等，几十秒 |
| 质量门禁 | 编译 + 深度分析 | 每次 push | 慢，几分钟 |

下面逐层解释"为什么这些维度是完整的"。

---

##### 第一层：静态检查

**问题**：静态检查为什么只需要关注 naming、documentation、structure、style 四个维度？

**答案**：因为这四类元素穷尽了"打开代码文件能看到的一切"。

试试这个思想实验：打开任意一个 `.c` 或 `.py` 文件，你看到什么？

```
#include "mem_gateway.h"        ← 结构关系（include 语句）

/**
 * @brief 初始化记忆引擎       ← 注释（documentation）
 */
int GsPD_MemSysInit(...)        ← 标识符（naming）
{
    int memoryId = 0;           ← 标识符 + 格式
    if (condition) {            ← 格式（缩进、括号）
        ...
    }
}
```

逐项分析：

| 你看到的 | 属于哪个维度 | 检查什么 |
|---------|------------|---------|
| 函数名、变量名、类名、宏名 | **Naming** | 命名是否符合约定（前缀、风格、禁用词） |
| 注释、文档字符串、类型说明 | **Documentation** | 文档是否完整、格式是否正确 |
| include/import 语句、模块依赖 | **Structure** | 依赖关系是否合规、层级是否正确 |
| 缩进、空格、换行、括号位置 | **Style** | 格式是否统一 |

**还有别的吗？** 没有。这四类元素就是代码文本的全部。

> **那复杂度、重复代码、潜在 Bug 呢？**
> 
> 这些需要"理解代码语义"才能判断，属于**语义级分析**（如 clang-tidy），执行成本高，放在质量门禁层。

**静态检查各维度的典型规则**：

| 维度 | 典型检查项 | 不通过的后果 |
|-----|-----------|-------------|
| **Naming** | 公开 API 必须有 `GsPD_` 前缀；内部变量禁止 `snake_case` | 代码难读、风格混乱 |
| **Documentation** | 公开函数必须有 `@brief`；文档覆盖率 ≥ 80% | 维护困难、新人无法理解 |
| **Structure** | 下层模块不能依赖上层；禁止直接调用平台 API | 架构腐化、耦合严重 |
| **Style** | 缩进 4 空格；行宽不超过 80 字符 | 代码审查争论、阅读困难 |

---

##### 第二层：动态验证

**问题**：静态检查通过了，代码就正确吗？

**答案**：当然不是。静态检查只能验证"代码长得对不对"，无法验证"代码跑得对不对"。

继续思想实验：一段命名规范、文档完整、格式统一的代码，可能有什么问题？

```
// 命名规范 ✅ 文档完整 ✅ 格式统一 ✅

int calculateDiscount(int price, int rate) {
    return price * rate;  // Bug: 应该是 price * rate / 100
}

// 测试用例覆盖了这个 Bug 吗？不知道。
// 内存会泄漏吗？不知道。
// 性能达标吗？不知道。
```

这些问题的共同点：**必须运行代码才能发现**。

```
需要运行代码才能验证的问题：
├─ 逻辑是否正确？ → 功能测试
├─ 测试是否充分？ → 覆盖率检查
└─ 内存是否安全？ → ASAN（AddressSanitizer）
```

**动态验证的三个核心项**：

| 验证项 | 怎么验证 | 发现什么问题 |
|-------|---------|------------|
| **功能测试** | 运行测试用例 | 逻辑错误、边界条件、回归问题 |
| **覆盖率检查** | 统计代码执行比例 | 测试盲区、未覆盖的分支 |
| **ASAN** | 运行时内存检测 | 内存泄漏、越界访问、悬空指针 |

> **为什么只选这三个？**
> 
> 性能测试、并发测试、兼容性测试也属于动态验证，但成本过高，适合放在 CI 流水线而非每次推送的门禁中。

---

##### 第三层：质量门禁

**问题**：动态验证和静态检查已经覆盖了代码质量，为什么还需要"质量门禁"这个概念？

**答案**：质量门禁不是"另一种检查"，而是"检查的执行容器"。

把它想象成一个**检查站**：

```
                    ┌─────────────────────────────┐
                    │      质量门禁（检查站）       │
                    │                             │
                    │  ┌─────────────────────┐   │
                    │  │  clang-tidy (lint)  │   │ ← 语义级静态分析
                    │  └─────────────────────┘   │
                    │  ┌─────────────────────┐   │
                    │  │  build              │   │ ← 编译验证
                    │  └─────────────────────┘   │
                    │  ┌─────────────────────┐   │
                    │  │  test + coverage    │   │ ← 动态验证
                    │  └─────────────────────┘   │
                    │  ┌─────────────────────┐   │
                    │  │  ASAN               │   │ ← 内存检测
                    │  └─────────────────────┘   │
                    │                             │
                    │  全部通过 → 放行            │
                    │  任意失败 → 拦截            │
                    └─────────────────────────────┘
```

**质量门禁 = 执行入口 + 通过标准**

| 门禁项 | 通过标准 | 不通过的后果 |
|-------|---------|-------------|
| **lint** | 无错误、无警告 | 潜在 Bug 入库 |
| **build** | 编译成功 | 代码无法构建 |
| **test** | 全部通过 | 功能缺陷 |
| **coverage** | ≥ 80% | 测试不充分 |
| **ASAN** | 无内存错误 | 内存问题 |

**为什么 lint 和 build 放在门禁层而不是静态检查层？**

```
静态检查（文本级）         质量门禁（语义级）
─────────────────────     ─────────────────────
正则匹配，毫秒级           需要 AST，秒级
不需要编译信息             需要编译信息
发现"格式"问题             发现"语义"问题

示例：
  - "变量名是 snake_case" → 静态检查能发现
  - "这里可能空指针解引用" → 需要 clang-tidy（门禁）
```

---

##### 三层协同：一个完整案例

让我们看一个 AI 编码的完整流程：

```
场景：AI 为 GsPDMemo 项目添加了一个新的内存分配函数

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第一步：AI 写完代码，开发者执行 git commit
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

触发 pre-commit 静态检查：

  ✅ Naming: 函数名 GsPD_AllocMemory 有 GsPD_ 前缀
  ✅ Naming: 内部变量 heapPtr 是 camelCase
  ❌ Documentation: 缺少 @brief 注释
  
  → 拦截！开发者补充注释后重新提交

  ✅ Documentation: 注释完整
  ✅ Structure: include 路径符合层级规则
  ✅ Style: 缩进 4 空格，行宽 76 字符
  
  → 通过，允许提交

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第二步：开发者执行 git push
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

触发 pre-push 质量门禁：

  ✅ build: 编译成功
  ✅ test: 15 个测试全部通过
  ✅ coverage: 新增代码覆盖率 92%
  ✅ clang-tidy: 无警告
  ✅ ASAN: 无内存问题
  
  → 通过，代码推送到远程仓库

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
结果：质量有保障的代码入库
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**三层各司其职**：

| 层级 | 职责 | 类比 |
|-----|------|------|
| 静态检查 | 确保"代码长得对" | 入门安检，快速 |
| 动态验证 | 确保"代码跑得对" | 功能测试，核心 |
| 质量门禁 | 确保"整体没问题" | 综合检查站，完整 |

---

##### 为什么这个模型是完整的？

从"代码问题的发现方式"来验证：

```
代码问题
├─ 看文本就能发现的 → 静态检查覆盖
│   ├─ 命名问题 → Naming
│   ├─ 文档问题 → Documentation
│   ├─ 架构问题 → Structure
│   └─ 格式问题 → Style
│
├─ 运行才能发现的 → 动态验证覆盖
│   ├─ 逻辑错误 → Test
│   ├─ 覆盖不足 → Coverage
│   └─ 内存问题 → ASAN
│
└─ 需要深度分析的 → 质量门禁覆盖
    ├─ 潜在 Bug → lint
    └─ 编译问题 → build

结论：任何代码质量问题，必然属于上述某一类。
```

---

##### 与行业标准的关系澄清

**问题**：行业标准（SonarQube、ESLint）定义了更多维度（Security、Bug Detection、Complexity 等），为什么我们只定义四个静态检查维度？

**答案**：这是**定义边界不同**导致的。我们将"静态分析"拆分为两层：

```
行业标准"静态分析"               我们的分层模型
──────────────────────────────────────────────────────
Security（安全）         →     Quality Gates (lint)
Bug Detection（缺陷）    →     Quality Gates (lint)
Complexity（复杂度）     →     Quality Gates (lint) 或 Static Checks
──────────────────────────────────────────────────────
Naming（命名）           →     Static Checks
Documentation（文档）    →     Static Checks
Structure（结构）        →     Static Checks
Style（风格）            →     Static Checks
```

**分层依据**：

| 检查类型 | 执行成本 | 依赖编译 | 适合阶段 |
|---------|---------|---------|---------|
| **文本级静态检查** | 极低（毫秒级） | 否 | pre-commit（每次提交） |
| **语义级静态分析** | 中等（秒级） | 是 | pre-push（lint 门禁） |

**为什么这样分层？**

1. **pre-commit 要求快速**：开发者每次提交都会触发，延迟必须低于 5 秒
2. **语义分析需要编译**：安全检查、Bug 检测需要 AST、类型信息、数据流分析
3. **成本分层**：高频操作低成本低延迟，低频操作高成本高价值

**结论**：我们的四维度模型专注于**文本级静态检查**，与语义级分析（lint 门禁）共同构成完整的代码看护体系。

#### 2.2.2 闭环机制

代码看护的闭环由 Git Hook 生效机制构成：

```
┌─────────────────────────────────────────────────────────────────┐
│  git add (暂存代码)                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  git commit (触发 pre-commit Hook)                               │
│  ├─ 执行静态检查：命名、文档、结构、风格                          │
│  ├─ 检查失败 → 拒绝提交，必须修复                                 │
│  └─ 检查通过 → 允许提交                                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  git push (触发 pre-push Hook)                                   │
│  ├─ 执行质量门禁：测试、覆盖率、Lint、构建                        │
│  ├─ 门禁失败 → 拒绝推送，必须修复                                 │
│  └─ 门禁通过 → 允许推送                                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  代码进入远程仓库                                                │
│  ├─ 已通过所有看护检查                                           │
│  └─ 质量得到保障                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**闭环论证**：

- **正向闭环**：AI 编写代码 → 静态检查通过 → 测试通过 → 门禁通过 → 代码入库
- **反向闭环**：检查/门禁失败 → 提交被拒绝 → 必须修复 → 重新检查 → 直到通过
- **强制执行**：Git Hook 是 Git 原生机制，无法在不触发的情况下提交代码

### 2.3 维度协同关系

行为约束与代码看护形成互补的双维度体系：

| 维度 | 关注点 | 生效时机 | 作用对象 |
|-----|--------|---------|---------|
| **行为约束** | AI 做了什么 | 操作执行前 | AI 的行为 |
| **代码看护** | AI 做得怎样 | 代码提交前 | AI 的产物 |

**协同逻辑**：

```
行为约束：防止 AI 做"不该做的事"
    ├─ 不修改关键文件
    ├─ 不执行危险命令
    └─ 不绕过检查机制
          ↓
代码看护：确保 AI 做的"该做的事"质量达标
    ├─ 命名符合规范
    ├─ 文档完整
    ├─ 测试覆盖
    └─ 门禁通过
          ↓
最终效果：AI 既不越界，又保证质量
```

---

## 3. 三层生效机制

### 3.1 事前引导层（规则文档）

**机制**：在 AI 执行任何操作之前，已通过规则文档知晓约束边界。

| Agent | 规则文档位置 | 生成方式 |
|-------|-------------|---------|
| Claude Code | `CLAUDE.md` | `guard install --agent claude-code` |
| OpenCode | `.opencode/rules/*.md` | `guard install --agent opencode` |
| Cursor | `.cursor/rules/*.md` | `guard install --agent cursor` |
| KiloCode | `.kilocode/rules/*.md` | `guard install --agent kilocode` |
| GitHub Copilot | `.github/copilot-instructions.md` | `guard install --agent copilot` |

**文档内容结构**：

```markdown
<!-- AI-GUARD:BEGIN:behavior -->
## 🚫 行为约束

### 文件保护
- **禁止修改**：third_party/**, build/**
- **需审批**：.claude/hooks/** (检查系统文件)
- **写入白名单**：src/**, include/**

### 命令限制
- **禁止执行**：git commit --no-verify (禁止跳过检查)
- **自动允许**：git status, git diff
<!-- AI-GUARD:END:behavior -->

<!-- AI-GUARD:BEGIN:code -->
## 📋 代码规范

### 命名规范
- 公开 API：GsPD_ 前缀 + PascalCase
- 内部函数：PascalCase
- 内部变量：camelCase

### 文档要求
- 公开 API 必须有中文 Doxygen 注释
- 超过 30 行的函数必须有阶段注释
<!-- AI-GUARD:END:code -->

<!-- 用户可在托管块外添加自定义内容 -->
## 项目特定说明
...
```

**效果**：AI 在生成代码时会主动遵循规范，减少 70% 的违规行为。

### 3.2 事中拦截层（PreToolUse Hook）

**机制**：AI 每次调用工具前，Hook 实时检查操作是否合规。

**PreToolUse 工作流程**：

```
┌─────────────────────────────────────────────────────────────────┐
│  AI 发起工具调用请求                                            │
│  例：write_file(path="third_party/lib.c", content="...")        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Claude Code 触发 PreToolUse Hook                               │
│  ├─ 调用 interceptor.py                                         │
│  └─ 传入工具名称、参数                                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  interceptor.py 执行检查                                        │
│  ├─ 解析 guard.yaml                                             │
│  ├─ 检查 path 是否在 file_protection.forbidden 中               │
│  ├─ 发现 "third_party/**" 是禁止路径                            │
│  └─ 决策：拒绝操作                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  返回错误给 AI                                                  │
│  {                                                              │
│    "error": "file_protection_violation",                        │
│    "message": "禁止修改 third_party/** 目录下的文件",            │
│    "path": "third_party/lib.c"                                  │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  AI 收到错误，调整行为                                          │
│  ├─ AI 理解约束                                                 │
│  └─ 选择合规的替代方案                                          │
└─────────────────────────────────────────────────────────────────┘
```

**拦截类型与处理**：

| 违规类型 | 处理方式 | 返回信息示例 |
|---------|---------|-------------|
| **文件禁止修改** | 直接拒绝 | `"禁止修改 third_party/** 目录"` |
| **文件需审批** | 提示确认 | `"修改 .claude/hooks/ 需要确认，是否继续？"` |
| **命令禁止执行** | 直接拒绝 | `"禁止执行 git commit --no-verify"` |
| **命令自动允许** | 直接放行 | 无检查，正常执行 |

### 3.3 事后验证层（pre-commit / pre-push）

**机制**：代码提交前，Git Hook 自动执行检查和门禁验证。

#### 三层划分（按执行时机 + 编译依赖）

| 层级 | 执行时机 | 是否需要编译 | 检查内容 | 执行成本 |
|-----|---------|------------|---------|---------|
| **静态检查** | pre-commit | ❌ 不需要 | 格式化、命名规范、custom_checks | 极低（毫秒级） |
| **语义分析** | pre-push | ✅ 需要 | clang-tidy 完整检查、cppcheck | 中等（秒级） |
| **动态验证** | pre-push | ✅+运行 | test、coverage、ASAN | 高（分钟级） |

#### 编译依赖说明

| 工具/检查 | 是否需要编译 | 原因 |
|----------|------------|------|
| **clang-format** | ❌ | 只处理文本格式 |
| **clang-tidy（命名检查）** | ❌ | 只检查标识符拼写 |
| **clang-tidy（完整检查）** | ✅ | 需要类型信息、AST、数据流分析 |
| **cppcheck** | ⚠️ 可选 | 可无编译信息运行，但效果有限 |
| **测试/覆盖率** | ✅ | 需要运行编译产物 |
| **ASAN/MSAN/UBSAN** | ✅ | 需要特殊编译 + 运行 |

#### pre-commit 执行流程

```bash
git commit -m "feat: add new feature"
    ↓
触发 pre-commit Hook
    ↓
执行静态检查（不需要编译，快速）
    ├─ clang-format              # 格式化（自动修复）
    ├─ clang-tidy --checks=readability-identifier-naming  # 仅命名检查
    └─ custom_checks             # 自定义检查
        ├─ file_prefix           # 文件命名前缀
        ├─ dependency_layer      # 模块依赖层级
        └─ doxygen_brief         # Doxygen 注释检查
    ↓
结果判断
    ├─ 全部通过 → 允许提交
    └─ 有失败 → 拒绝提交，显示错误信息
```

#### pre-push 执行流程

```bash
git push origin main
    ↓
触发 pre-push Hook
    ↓
Step 1: Build（前置条件）
    └─ 执行编译，生成 compile_commands.json
    ↓
Step 2: 语义分析（需要编译产物）
    ├─ clang-tidy（完整检查）
    └─ cppcheck（可选）
    ↓
Step 3: 动态验证（需要编译产物 + 运行）
    ├─ test                      # 测试套件
    ├─ coverage                  # 覆盖率检查
    └─ asan                      # AddressSanitizer（可选）
    ↓
结果判断
    ├─ 全部通过 → 允许推送
    └─ 有失败 → 拒绝推送，必须修复
```

### 3.4 闭环论证

**为什么三层机制形成闭环？**

```
                    事前引导层
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ↓               ↓               ↓
   AI 知晓约束     AI 尝试合规      AI 尝试违规
        │               │               │
        │               │               ↓
        │               │         事中拦截层
        │               │               │
        │               │               ↓
        │               │         返回错误
        │               │               │
        │               ↓               ↓
        │         合规操作放行     AI 修正行为
        │               │               │
        └───────────────┼───────────────┘
                        ↓
                 代码进入暂存
                        │
                        ↓
                 事后验证层
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ↓               ↓               ↓
   检查通过         检查失败        门禁失败
        │               │               │
        ↓               ↓               ↓
   代码入库       拒绝提交        拒绝推送
                        │               │
                        ↓               ↓
                   必须修复         必须修复
                        │               │
                        └───────────────┘
                                ↓
                        重新检查直到通过
```

**闭环证明**：

1. **正向路径完整**：知晓约束 → 合规执行 → 检查通过 → 代码入库
2. **反向路径完整**：违规 → 拦截 → 错误反馈 → 修正 → 重试
3. **无法逃逸**：绕过机制被禁止，检查失败无法提交，门禁失败无法推送
4. **强制修复**：只有通过所有检查才能入库，质量得到保障

---

## 4. 五层架构设计

### 4.1 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户                                      │
│                    运行 guard 命令                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  第一层：CLI 层                                                  │
│  ├─ guard init      初始化配置                                  │
│  ├─ guard install   安装到项目                                  │
│  ├─ guard update    更新规则文档                                │
│  ├─ guard check     手动检查                                    │
│  ├─ guard verify    验证门禁                                    │
│  ├─ guard agents    显示 Agent 信息                             │
│  └─ guard status    显示安装状态                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  第二层：配置层                                                  │
│  ├─ guard.yaml 解析                                             │
│  ├─ 默认配置 + 项目配置 + 用户覆盖                               │
│  └─ 配置验证与合并                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  第三层：核心层                                                  │
│  ├─ Generator: 生成规则文档 (CLAUDE.md 等)                      │
│  ├─ Interceptor: 行为拦截 (PreToolUse Hook)                     │
│  ├─ Validator: 代码验证 (pre-commit/pre-push)                   │
│  └─ Language Plugin: 语言特定检查规则                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  第四层：Agent 适配层                                            │
│  ├─ ClaudeCodeAdapter: 生成 settings.json + CLAUDE.md           │
│  ├─ OpenCodeAdapter: 生成 Plugin + rules/                       │
│  ├─ CursorAdapter: 生成 hooks.json + rules/                     │
│  ├─ KilocodeAdapter: 仅生成 rules/ (警告无 Hook)                │
│  └─ CopilotAdapter: 仅生成 copilot-instructions.md              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  第五层：输出层                                                  │
│  ├─ Content: CheckReport, ConstraintDoc, WarningMessage         │
│  ├─ Renderer: MarkdownRenderer, JsonRenderer, HtmlRenderer      │
│  └─ Channel: ConsoleChannel, FileChannel, GitHubChannel         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        用户/AI                                   │
│                    查看输出结果                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 CLI 层

**职责**：用户交互入口，命令解析与路由。

**命令详解**：

| 命令 | 功能 | 参数 | 输出 |
|-----|------|-----|------|
| `guard init` | 创建 guard.yaml | `--language`, `--template` | 配置文件 |
| `guard install` | 安装到项目 | `--agent` (多选) | 规则文档 + Hook + 安装摘要 |
| `guard update` | 更新规则文档 | 无 | 更新托管块内容 |
| `guard check` | 手动触发静态检查 | `--files`, `--rules` | 检查报告 |
| `guard verify` | 手动触发门禁验证 | `--gate` (可选) | 验证报告 |
| `guard agents` | 显示 Agent 信息 | 无 | Agent 能力矩阵 |
| `guard status` | 显示安装状态 | 无 | 当前项目配置状态 |

**命令执行流程**：

```bash
guard install --agent claude-code,cursor
    ↓
解析参数
    ├─ agent: ["claude-code", "cursor"]
    └─ 加载 guard.yaml
    ↓
执行安装
    ├─ Generator 生成规则文档
    ├─ ClaudeCodeAdapter 生成 Claude Code 文件
    ├─ CursorAdapter 生成 Cursor 文件
    └─ 安装 Git Hooks
    ↓
输出结果
    ├─ 终端显示安装摘要
    ├─ 终端显示 Agent 能力状态
    └─ 文件写入项目目录
```

### 4.3 配置层

**职责**：配置解析、验证、合并。

**配置来源层级**：

```
优先级从低到高：
┌─────────────────────────────────────────────────────────────────┐
│  1. 内置默认配置                                                │
│  ├─ 语言通用规则                                                │
│  └─ 基础行为约束                                                │
└─────────────────────────────────────────────────────────────────┘
                              +
┌─────────────────────────────────────────────────────────────────┐
│  2. 项目配置 (guard.yaml)                                       │
│  ├─ 项目特定规则                                                │
│  ├─ 覆盖默认配置                                                │
└─────────────────────────────────────────────────────────────────┘
                              +
┌─────────────────────────────────────────────────────────────────┐
│  3. 用户覆盖 (--override)                                       │
│  ├─ 命令行临时覆盖                                              │
│  ├─ 用于调试或特殊情况                                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                      最终生效配置
```

**配置验证**：

- YAML 语法验证
- 字段类型验证
- 必填字段检查
- 路径模式有效性检查
- 依赖关系一致性检查

### 4.4 核心层

**职责**：看护系统的核心逻辑实现，包括规则文档生成、行为拦截、检查编排、工具管理。

**架构演进说明**：

> 原设计中 Validator 直接执行检查。新设计将检查执行委托给 pre-commit 框架，
> Validator 职责调整为"配置生成 + 检查编排"，新增 Tool Manager 负责工具生命周期管理。
> 这符合"不重复造轮子"原则，AI Guard 专注于配置统一和编排，而非重复实现检查逻辑。

**核心层内部结构**：

```
核心层
├─ Generator: 生成规则文档 (CLAUDE.md 等)
├─ Interceptor: 行为拦截 (PreToolUse Hook)
├─ Validator: 代码验证编排（配置生成 + 检查编排）
│   ├─ Config Generator: 生成工具配置文件
│   ├─ Pre-commit Generator: 生成 .pre-commit-config.yaml
│   └─ Check Runner: 调用 pre-commit 执行检查
├─ Tool Manager: 工具生命周期管理
│   ├─ Tool Detector: 检测工具安装状态
│   ├─ Tool Installer: 提供安装指导/自动安装
│   └─ Tool Mapper: guard.yaml → 工具参数映射
└─ Language Plugin: 语言特定配置模板
```

#### Generator（生成器）

**功能**：从 behavior.yaml 生成各 Agent 的规则文档（软约束）。

```python
class Generator:
    def generate(self, config: BehaviorConfig, agent: str) -> str:
        """
        根据配置和 Agent 类型生成规则文档。
        
        Args:
            config: behavior.yaml 配置对象
            agent: Agent 类型 (claude-code, cursor, opencode, copilot)
        
        Returns:
            生成的规则文档内容 (Markdown)
        """
        sections = []
        
        # 根据 Agent 能力过滤支持的 scheme
        supported_schemes = self._get_supported_schemes(agent)
        
        # 生成读取限制章节
        if any(s in supported_schemes for s in ["file", "mcp", "web", "api"]):
            sections.append(self._render_read_restriction(
                config.read_restriction, 
                supported_schemes
            ))
        
        # 生成写入限制章节
        if any(s in supported_schemes for s in ["file", "mcp", "api"]):
            sections.append(self._render_write_restriction(
                config.write_restriction, 
                supported_schemes
            ))
        
        # 生成执行限制章节
        if "shell" in supported_schemes:
            sections.append(self._render_execute_restriction(
                config.execute_restriction
            ))
        
        return "\n\n".join(sections)
    
    def _get_supported_schemes(self, agent: str) -> list[str]:
        """获取 Agent 支持的 scheme"""
        SUPPORTED_SCHEMES = {
            "claude-code": ["file", "mcp", "web", "api", "shell"],
            "cursor": ["file", "web", "shell"],           # MCP 支持 beta
            "opencode": ["file", "mcp", "web", "shell"],
            "copilot": ["file", "web"],                   # 仅规则文档，无执行
        }
        return SUPPORTED_SCHEMES.get(agent, ["file", "shell"])
    
    def _render_write_restriction(self, restriction, supported_schemes: list) -> str:
        """渲染写入限制章节"""
        lines = ["## 🚫 写入限制"]
        
        # 按 scheme 分组渲染
        for scheme in ["file", "mcp", "api"]:
            if scheme not in supported_schemes:
                continue
            
            # forbidden
            rules = self._filter_by_scheme(restriction.forbidden, scheme)
            if rules:
                lines.append(f"\n### 禁止写入 ({scheme.upper()})")
                for rule in rules:
                    pattern = self._extract_pattern(rule["pattern"], scheme)
                    lines.append(f"- **{pattern}**")
                    if rule.get("reason"):
                        lines.append(f"  - {rule['reason']}")
            
            # require_approval
            rules = self._filter_by_scheme(restriction.require_approval, scheme)
            if rules:
                lines.append(f"\n### 需审批 ({scheme.upper()})")
                for rule in rules:
                    pattern = self._extract_pattern(rule["pattern"], scheme)
                    lines.append(f"- **{pattern}**")
                    if rule.get("message"):
                        lines.append(f"  - {rule['message']}")
        
        return "\n".join(lines)
    
    def _render_read_restriction(self, restriction, supported_schemes: list) -> str:
        """渲染读取限制章节"""
        lines = ["## 📂 读取限制"]
        
        for scheme in ["file", "mcp", "web", "api"]:
            if scheme not in supported_schemes:
                continue
            
            rules = self._filter_by_scheme(restriction.forbidden, scheme)
            if rules:
                lines.append(f"\n### 禁止读取 ({scheme.upper()})")
                for rule in rules:
                    pattern = self._extract_pattern(rule["pattern"], scheme)
                    lines.append(f"- **{pattern}**")
                    if rule.get("reason"):
                        lines.append(f"  - {rule['reason']}")
        
        return "\n".join(lines)
    
    def _render_execute_restriction(self, restriction) -> str:
        """渲染执行限制章节"""
        lines = ["## 🔒 执行限制"]
        
        rules = self._filter_by_scheme(restriction.forbidden, "shell")
        if rules:
            lines.append("\n### 禁止执行")
            for rule in rules:
                pattern = self._extract_pattern(rule["pattern"], "shell")
                lines.append(f"- `{pattern}`")
                if rule.get("reason"):
                    lines.append(f"  - {rule['reason']}")
        
        return "\n".join(lines)
    
    def _filter_by_scheme(self, rules: list, scheme: str) -> list:
        """按 scheme 过滤规则"""
        prefix = f"{scheme}:"
        return [r for r in rules if r["pattern"].startswith(prefix)]
    
    def _extract_pattern(self, pattern: str, scheme: str) -> str:
        """提取 scheme 后的模式部分"""
        prefix = f"{scheme}:"
        return pattern[len(prefix):] if pattern.startswith(prefix) else pattern
```

##### 生成的规则文档示例

**输入**：behavior.yaml（见 5.2 节）

**输出**：CLAUDE.md 中的行为约束章节

```markdown
<!-- AI-GUARD:BEGIN:behavior -->
## 📂 读取限制

### 禁止读取 (FILE)
- **.env**
  - 敏感配置文件
- **secrets/**
  - 密钥目录
- **.pem**
  - 证书文件

### 禁止读取 (MCP)
- **memory:search**
  - 禁止搜索记忆内容

### 禁止读取 (WEB)
- **internal.company.com**
  - 禁止访问内部域名

## 🚫 写入限制

### 禁止写入 (FILE)
- **third_party/**
  - 第三方库，禁止修改
- **build/**
  - 构建产物，禁止修改
- **.git/**
  - Git 内部文件，禁止修改

### 禁止写入 (MCP)
- **memory:delete_***
  - 禁止删除记忆

### 需审批 (FILE)
- **.claude/hooks/**
  - 检查系统文件修改需要确认

## 🔒 执行限制

### 禁止执行
- `git commit --no-verify`
  - 禁止跳过 pre-commit hooks
- `git push --force`
  - 禁止强制推送
<!-- AI-GUARD:END:behavior -->
```

**效果**：AI 在执行前阅读规则文档，主动规避 70% 的违规行为。

#### Interceptor（拦截器）

**功能**：PreToolUse Hook 的核心检查逻辑（硬约束）。

```python
class Interceptor:
    # 工具类型映射
    TOOL_OPERATION_MAP = {
        # Read tools → operation="read"
        "read": "read",
        "grep": "read",
        "glob": "read",
        "webfetch": "read",
        "websearch": "read",
        # Write tools → operation="write"
        "edit": "write",
        "write": "write",
        "apply_patch": "write",
        # Execute tools → operation="execute"
        "bash": "execute",
    }
    
    # 工具 scheme 映射
    TOOL_SCHEME_MAP = {
        "read": "file",
        "grep": "file",
        "glob": "file",
        "webfetch": "web",
        "websearch": "web",
        "edit": "file",
        "write": "file",
        "apply_patch": "file",
        "bash": "shell",
    }
    
    MCP_TOOL_PREFIX = "mcp__"
    
    def check(self, tool_name: str, tool_args: dict, config: BehaviorConfig) -> Result:
        """
        检查工具调用是否合规。
        
        Args:
            tool_name: 工具名称 (read, write, bash, mcp__server__tool, etc.)
            tool_args: 工具参数
            config: behavior.yaml 配置
        
        Returns:
            Result(action="allow" / "reject" / "confirm")
        """
        # 1. 分类工具：确定 和 scheme
        operation, scheme = self._classify_tool(tool_name, tool_args)
        
        # 2. 获取对应的限制配置
        restriction = self._get_restriction(config, operation)
        if not restriction:
            return Result(action="allow")
        
        # 3. 提取匹配目标
        target = self._extract_target(tool_name, tool_args, scheme)
        if not target:
            return Result(action="allow")
        
        # 4. 执行规则检查
        return self._check_against_rules(target, scheme, restriction)
    
    def _classify_tool(self, tool_name: str, tool_args: dict) -> tuple[str, str]:
        """
        分类工具：确定操作类型和 scheme。
        
        Returns:
            (operation, scheme) 元组
        """
        # MCP 工具特殊处理
        if tool_name.startswith(self.MCP_TOOL_PREFIX):
            # mcp__memory__search → scheme="mcp"
            # 根据 tool 名称推断操作类型
            server, tool = self._parse_mcp_tool(tool_name)
            operation = self._infer_mcp_operation(tool)
            return operation, "mcp"
        
        # 普通工具查表
        operation = self.TOOL_OPERATION_MAP.get(tool_name, "unknown")
        scheme = self.TOOL_SCHEME_MAP.get(tool_name, "file")
        
        return operation, scheme
    
    def _parse_mcp_tool(self, tool_name: str) -> tuple[str, str]:
        """解析 MCP 工具名称"""
        # mcp__memory__search → ("memory", "search")
        parts = tool_name[len(self.MCP_TOOL_PREFIX):].split("__", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return parts[0], ""
    
    def _infer_mcp_operation(self, tool: str) -> str:
        """从 MCP tool 名称推断操作类型"""
        # 写操作关键词
        write_keywords = ["write", "create", "delete", "update", "add", "remove", "send"]
        for keyword in write_keywords:
            if keyword in tool.lower():
                return "write"
        return "read"
    
    def _get_restriction(self, config: BehaviorConfig, operation: str):
        """获取对应的限制配置"""
        if operation == "read":
            return config.read_restriction
        elif operation == "write":
            return config.write_restriction
        elif operation == "execute":
            return config.execute_restriction
        return None
    
    def _extract_target(self, tool_name: str, tool_args: dict, scheme: str) -> str:
        """
        提取匹配目标。
        
        根据工具类型和 scheme 提取用于匹配的字符串。
        """
        if scheme == "file":
            # 文件路径
            return tool_args.get("file_path") or tool_args.get("path") or ""
        
        elif scheme == "shell":
            # Shell 命令
            return tool_args.get("command") or ""
        
        elif scheme == "web":
            # Web URL/域名
            return tool_args.get("url") or ""
        
        elif scheme == "mcp":
            # MCP server:tool 格式
            server, tool = self._parse_mcp_tool(tool_name)
            return f"{server}:{tool}"
        
        elif scheme == "api":
            # API service:action 格式（需要从参数推断）
            return tool_args.get("action") or ""
        
        return ""
    
    def _check_against_rules(self, target: str, scheme: str, restriction) -> Result:
        """按规则检查"""
        prefix = f"{scheme}:"
        
        # 1. 检查 forbidden（优先级最高）
        for rule in restriction.forbidden:
            pattern = rule["pattern"]
            if not pattern.startswith(prefix):
                continue
            if self._match_pattern(target, pattern, scheme):
                return Result(
                    action="reject",
                    message=rule.get("reason", "操作被禁止")
                )
        
        # 2. 检查 require_approval
        for rule in restriction.require_approval:
            pattern = rule["pattern"]
            if not pattern.startswith(prefix):
                continue
            if self._match_pattern(target, pattern, scheme):
                return Result(
                    action="confirm",
                    message=rule.get("message", "需要确认")
                )
        
        # 3. 检查 allow（如果有）
        if hasattr(restriction, 'allow') and restriction.allow:
            for rule in restriction.allow:
                pattern = rule["pattern"]
                if not pattern.startswith(prefix):
                    continue
                if self._match_pattern(target, pattern, scheme):
                    return Result(action="allow")
        
        # 4. 默认允许
        return Result(action="allow")
    
    def _match_pattern(self, target: str, pattern: str, scheme: str) -> bool:
        """
        模式匹配。
        
        Args:
            target: 实际目标
            pattern: 完整 pattern（如 "file:**/.env"）
            scheme: scheme 类型
        """
        # 提取 pattern 中的路径部分
        path_pattern = pattern[len(f"{scheme}:"):]
        
        if scheme == "file":
            return self._match_glob(target, path_pattern)
        elif scheme == "shell":
            return self._match_shell(target, path_pattern)
        elif scheme == "mcp":
            return self._match_mcp(target, path_pattern)
        elif scheme == "web":
            return self._match_domain(target, path_pattern)
        elif scheme == "api":
            return self._match_api(target, path_pattern)
        
        return False
    
    def _match_glob(self, path: str, pattern: str) -> bool:
        """Glob 模式匹配（支持 ** 和 *）"""
        import fnmatch
        # 使用 fnmatch 或自定义 glob 实现
        return fnmatch.fnmatch(path, pattern)
    
    def _match_shell(self, cmd: str, pattern: str) -> bool:
        """Shell 命令匹配（支持 * 通配符）"""
        import re
        # 将 * 转换为 .*
        regex = "^" + re.escape(pattern).replace("\\*", ".*") + "$"
        return re.match(regex, cmd) is not None
    
    def _match_mcp(self, target: str, pattern: str) -> bool:
        """MCP 工具匹配"""
        # pattern: "memory:delete_*"
        # target: "memory:delete_entities"
        import re
        parts = pattern.split(":", 1)
        if len(parts) != 2:
            return False
        
        server_pattern, tool_pattern = parts
        target_parts = target.split(":", 1)
        if len(target_parts) != 2:
            return False
        
        target_server, target_tool = target_parts
        
        # 匹配 server
        if server_pattern != "*" and not self._wildcard_match(target_server, server_pattern):
            return False
        
        # 匹配 tool
        return self._wildcard_match(target_tool, tool_pattern)
    
    def _match_domain(self, url: str, pattern: str) -> bool:
        """域名匹配"""
        from urllib.parse import urlparse
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc
        return self._wildcard_match(domain, pattern)
    
    def _match_api(self, target: str, pattern: str) -> bool:
        """API 匹配（格式：service:action）"""
        return self._match_mcp(target, pattern)  # 同 MCP 格式
    
    def _wildcard_match(self, text: str, pattern: str) -> bool:
        """通配符匹配"""
        import re
        regex = "^" + re.escape(pattern).replace("\\*", ".*") + "$"
        return re.match(regex, text) is not None
```

##### 检查流程示例

**场景 1：写入禁止目录**

```
AI 发起操作：
  tool_name: "write"
  tool_args: { "file_path": "third_party/lib.c", "content": "..." }

Interceptor 检查流程：
  1. _classify_tool:
     - tool_name="write" → operation="write", scheme="file"
  
  2. _get_restriction:
     - operation="write" → config.write_restriction
  
  3. _extract_target:
     - scheme="file" → target="third_party/lib.c"
  
  4. _check_against_rules:
     - 遍历 forbidden 规则
     - pattern="file:third_party/**" → prefix 匹配
     - _match_pattern("third_party/lib.c", "third_party/**", "file")
     - _match_glob → True
     - 返回 Result(action="reject", message="第三方库，禁止修改")

返回给 Agent：
  {
    "hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "deny",
      "permissionDecisionReason": "第三方库，禁止修改"
    }
  }
```

**场景 2：MCP 工具调用**

```
AI 发起操作：
  tool_name: "mcp__memory__delete_entities"
  tool_args: { "ids": ["123", "456"] }

Interceptor 检查流程：
  1. _classify_tool:
     - tool_name 以 "mcp__" 开头
     - _parse_mcp_tool → server="memory", tool="delete_entities"
     - _infer_mcp_operation("delete_entities") → operation="write"
     - 返回 (operation="write", scheme="mcp")
  
  2. _get_restriction:
     - operation="write" → config.write_restriction
  
  3. _extract_target:
     - scheme="mcp" → target="memory:delete_entities"
  
  4. _check_against_rules:
     - pattern="mcp:memory:delete_*"
     - _match_mcp("memory:delete_entities", "memory:delete_*")
     - server 匹配, tool 匹配 → True
     - 返回 Result(action="reject", message="禁止删除记忆")
```

**场景 3：执行禁止命令**

```
AI 发起操作：
  tool_name: "bash"
  tool_args: { "command": "git commit --no-verify -m 'test'" }

Interceptor 检查流程：
  1. _classify_tool:
     - tool_name="bash" → operation="execute", scheme="shell"
  
  2. _get_restriction:
     - operation="execute" → config.execute_restriction
  
  3. _extract_target:
     - scheme="shell" → target="git commit --no-verify -m 'test'"
  
  4. _check_against_rules:
     - pattern="shell:git commit --no-verify"
     - _match_shell("git commit ...", "git commit --no-verify")
     - 返回 Result(action="reject", message="禁止跳过 pre-commit hooks")
```

##### 结果类型定义

```python
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class PolicyResult:
    """统一的策略决策结果"""
    decision: str              # "allow" | "deny" | "ask"
    reason: Optional[str] = None
    user_message: Optional[str] = None    # 给用户看的信息
    agent_message: Optional[str] = None   # 给 AI 看的信息
    updated_input: Optional[dict] = None  # 重写后的输入参数
```

| decision | 含义 | Agent 处理方式 |
|----------|------|--------------|
| `allow` | 检查通过 | 继续执行操作 |
| `deny` | 检查失败 | 拒绝执行，返回错误给 AI |
| `ask` | 需用户确认 | 暂停执行，显示提示等待用户确认 |

#### AgentAdapter（Agent 适配层）

**设计原则**：
- **高内聚**：能力声明与实现聚合在同一类中
- **开闭原则**：新增 Agent 只需继承子类并注册，无需修改现有代码
- **单一职责**：AgentAdapter 负责生成静态配置文件，格式转换逻辑嵌入生成的代码中

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

# ==================== 基础类型 ====================

@dataclass
class AgentCapabilities:
    """Agent 能力声明"""
    can_block: bool = True                    # 能否拦截操作
    can_ask: bool = True                      # 是否支持 ask（确认）
    can_rewrite_input: bool = True            # 能否重写输入参数
    uses_external_hooks: bool = True          # 是否使用外部进程 Hook
    supported_operations: list[str] = field(  # 支持的操作类型
        default_factory=lambda: ["read", "write", "execute", "mcp"]
    )


@dataclass
class FileSpec:
    """生成的文件规格"""
    path: str
    content: str
    marker: str = None  # 支持增量更新的标记


# ==================== 抽象基类 ====================

class AgentAdapter(ABC):
    """
    Agent 适配器抽象基类。
    
    职责：生成 Agent 特定的规则文档和 Hook 配置。
    
    遵循开闭原则：
    - 对扩展开放：新增 Agent 只需继承此类
    - 对修改关闭：无需修改现有代码
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称（用于注册和查询）"""
        pass
    
    @property
    @abstractmethod
    def capabilities(self) -> AgentCapabilities:
        """声明此 Agent 的能力"""
        pass
    
    @abstractmethod
    def generate_rule_doc(self, content: str) -> list[FileSpec]:
        """生成规则文档文件"""
        pass
    
    @abstractmethod
    def generate_hook_config(self, config: "BehaviorConfig") -> list[FileSpec]:
        """
        生成 Hook 配置文件或插件代码。
        
        格式转换逻辑嵌入在生成的代码中，而非作为单独方法。
        """
        pass


# ==================== 具体实现 ====================

class ClaudeCodeAdapter(AgentAdapter):
    """Claude Code 适配器"""
    
    @property
    def name(self) -> str:
        return "claude-code"
    
    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_block=True,
            can_ask=True,
            can_rewrite_input=True,
            uses_external_hooks=True,
            supported_operations=["read", "write", "execute", "mcp", "web"],
        )
    
    def generate_rule_doc(self, content: str) -> list[FileSpec]:
        return [
            FileSpec(
                path="CLAUDE.md",
                content=content,
                marker="AI-GUARD:behavior"
            )
        ]
    
    def generate_hook_config(self, config: "BehaviorConfig") -> list[FileSpec]:
        return [
            FileSpec(path=".claude/hooks/interceptor.py", content=self._generate_hook_script()),
            FileSpec(path=".claude/settings.json", content=self._generate_settings()),
        ]
    
    def _generate_hook_script(self) -> str:
        """生成 PreToolUse hook 脚本，内嵌格式转换逻辑"""
        return '''#!/usr/bin/env python3
"""AI Guard Interceptor for Claude Code"""
import sys
import json

config = load_behavior_config()
interceptor = Interceptor(config)

def main():
    input_data = json.load(sys.stdin)
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    
    result = interceptor.check(tool_name, tool_input, config)
    
    # === PolicyResult → Claude Code JSON 格式转换 ===
    if result.decision == "deny":
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": result.user_message or result.reason,
                "updatedInput": result.updated_input
            }
        }
        print(json.dumps(output))
        sys.exit(0)
    elif result.decision == "ask":
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": result.user_message or result.reason
            }
        }
        print(json.dumps(output))
        sys.exit(0)
    
    # allow: exit 0 with no output
    sys.exit(0)

if __name__ == "__main__":
    main()
'''
    
    def _generate_settings(self) -> str:
        return json.dumps({
            "hooks": {
                "PreToolUse": [{
                    "matcher": "*",
                    "hooks": [{
                        "type": "command",
                        "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/interceptor.py"
                    }]
                }]
            }
        }, indent=2)


class CursorAdapter(AgentAdapter):
    """Cursor 适配器"""
    
    @property
    def name(self) -> str:
        return "cursor"
    
    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_block=True,
            can_ask=False,  # Cursor preToolUse 的 ask 未完全实现
            can_rewrite_input=True,
            uses_external_hooks=True,
            supported_operations=["read", "execute", "mcp"],  # write 无法在执行前拦截
        )
    
    def generate_rule_doc(self, content: str) -> list[FileSpec]:
        return [
            FileSpec(
                path=".cursor/rules/behavior.mdc",
                content=f"---\nalwaysApply: true\n---\n\n{content}"
            )
        ]
    
    def generate_hook_config(self, config: "BehaviorConfig") -> list[FileSpec]:
        hook_script = self._generate_hook_script()
        hooks_json = self._generate_hooks_json()
        return [
            FileSpec(path=".cursor/hooks/check.sh", content=hook_script),
            FileSpec(path=".cursor/hooks.json", content=hooks_json),
        ]
    
    def _generate_hook_script(self) -> str:
        """生成 hook 脚本，内嵌格式转换逻辑"""
        return '''#!/bin/bash
# AI Guard Interceptor for Cursor

read -d '' input_json
result=$(python3 -c "
import sys, json
from interceptor import check
input_data = json.loads('$input_json')
result = check(input_data)

# === PolicyResult → Cursor JSON 格式转换 ===
if result.decision == 'deny':
    output = {
        'permission': 'deny',
        'userMessage': result.user_message or result.reason,
        'agentMessage': result.agent_message
    }
    print(json.dumps(output))
elif result.decision == 'ask':
    # Cursor 不完全支持 ask，降级为 deny
    output = {
        'permission': 'deny',
        'userMessage': '[需确认] ' + (result.user_message or result.reason)
    }
    print(json.dumps(output))
")
echo "$result"
'''
    
    def _generate_hooks_json(self) -> str:
        hooks = {
            "version": 1,
            "hooks": {
                "beforeShellExecution": [{"command": "$PROJECT_DIR/.cursor/hooks/check.sh"}],
                "beforeReadFile": [{"command": "$PROJECT_DIR/.cursor/hooks/check.sh"}],
                "beforeMCPExecution": [{"command": "$PROJECT_DIR/.cursor/hooks/check.sh"}],
            }
        }
        return json.dumps(hooks, indent=2)


class OpenCodeAdapter(AgentAdapter):
    """OpenCode 适配器 - 生成插件代码而非配置文件"""
    
    @property
    def name(self) -> str:
        return "opencode"
    
    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_block=True,
            can_ask=True,
            can_rewrite_input=True,
            uses_external_hooks=False,  # OpenCode 使用插件，不是外部进程
            supported_operations=["read", "write", "execute", "mcp", "web"],
        )
    
    def generate_rule_doc(self, content: str) -> list[FileSpec]:
        return [FileSpec(path="AGENTS.md", content=content)]
    
    def generate_hook_config(self, config: "BehaviorConfig") -> list[FileSpec]:
        # OpenCode 不生成配置文件，而是生成插件代码
        plugin_code = self._generate_plugin_code(config)
        return [FileSpec(path=".opencode/plugins/ai-guard.ts", content=plugin_code)]
    
    def _generate_plugin_code(self, config: "BehaviorConfig") -> str:
        """生成 TypeScript 插件代码，内嵌检查逻辑"""
        # 生成检查规则
        read_checks = self._generate_read_checks(config.read_restriction)
        write_checks = self._generate_write_checks(config.write_restriction)
        execute_checks = self._generate_execute_checks(config.execute_restriction)
        
        return f'''import {{ Plugin }} from "@opencode-ai/plugin"

export const AIGuardPlugin: Plugin = async (ctx) => {{
  return {{
    "tool.execute.before": async (input, output) => {{
      // === Read checks ===
      if (input.tool === "read") {{
        const path = output.args.filePath
        {read_checks}
      }}
      
      // === Write checks ===
      if (input.tool === "edit" || input.tool === "write") {{
        const path = output.args.filePath
        {write_checks}
      }}
      
      // === Execute checks ===
      if (input.tool === "bash") {{
        const cmd = output.args.command
        {execute_checks}
      }}
    }},
  }}
}}

// 格式转换：OpenCode 插件通过 throw Error 阻止执行
// throw new Error("禁止访问 .env 文件")
'''
    
    def _generate_read_checks(self, restriction) -> str:
        """生成读取检查代码"""
        checks = []
        for rule in restriction.forbidden:
            pattern = rule["pattern"]
            if pattern.startswith("file:"):
                path = pattern[5:]
                checks.append(f'if (path.match("{path}")) throw new Error("{rule.get("reason", "禁止访问")}")')
        return "\n        ".join(checks)
    
    def _generate_write_checks(self, restriction) -> str:
        """生成写入检查代码"""
        checks = []
        for rule in restriction.forbidden:
            pattern = rule["pattern"]
            if pattern.startswith("file:"):
                path = pattern[5:]
                checks.append(f'if (path.match("{path}")) throw new Error("{rule.get("reason", "禁止修改")}")')
        return "\n        ".join(checks)
    
    def _generate_execute_checks(self, restriction) -> str:
        """生成执行检查代码"""
        checks = []
        for rule in restriction.forbidden:
            pattern = rule["pattern"]
            if pattern.startswith("shell:"):
                cmd = pattern[6:]
                checks.append(f'if (cmd.includes("{cmd}")) throw new Error("{rule.get("reason", "禁止执行")}")')
        return "\n        ".join(checks)


class CopilotAdapter(AgentAdapter):
    """GitHub Copilot 适配器 - 仅规则文档，无 Hook 能力"""
    
    @property
    def name(self) -> str:
        return "copilot"
    
    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_block=False,       # 无执行能力
            can_ask=False,
            can_rewrite_input=False,
            uses_external_hooks=False,
            supported_operations=[],  # 无执行操作
        )
    
    def generate_rule_doc(self, content: str) -> list[FileSpec]:
        return [FileSpec(path=".github/copilot-instructions.md", content=content)]
    
    def generate_hook_config(self, config: "BehaviorConfig") -> list[FileSpec]:
        return []  # Copilot 不支持 hooks


# ==================== 注册机制 ====================

class AgentRegistry:
    """
    Agent 注册中心。
    
    遵循开闭原则：
    - 新增 Agent 只需创建 AgentAdapter 子类并注册
    - 无需修改现有代码
    """
    
    _adapters: dict[str, type[AgentAdapter]] = {}
    
    @classmethod
    def register(cls, adapter_class: type[AgentAdapter]) -> None:
        """注册 Agent 适配器"""
        instance = adapter_class()
        cls._adapters[instance.name] = adapter_class
    
    @classmethod
    def get(cls, name: str) -> AgentAdapter:
        """获取 Agent 适配器实例"""
        if name not in cls._adapters:
            raise ValueError(f"Unknown agent: {name}")
        return cls._adapters[name]()
    
    @classmethod
    def list(cls) -> list[str]:
        """列出所有已注册的 Agent"""
        return list(cls._adapters.keys())
    
    @classmethod
    def get_capabilities(cls, name: str) -> AgentCapabilities:
        """获取 Agent 能力声明"""
        return cls.get(name).capabilities


# 自动注册内置 Agent
AgentRegistry.register(ClaudeCodeAdapter)
AgentRegistry.register(CursorAdapter)
AgentRegistry.register(OpenCodeAdapter)
AgentRegistry.register(CopilotAdapter)
```

##### 使用示例

```python
# 获取 Agent 适配器
adapter = AgentRegistry.get("claude-code")

# 查询能力
print(adapter.capabilities.can_ask)           # True
print(adapter.capabilities.uses_external_hooks)  # True

# 生成配置
rule_docs = adapter.generate_rule_doc(markdown_content)
hook_configs = adapter.generate_hook_config(behavior_config)

# 列出所有支持的 Agent
print(AgentRegistry.list())  # ["claude-code", "cursor", "opencode", "copilot"]
```

##### 添加新 Agent（开闭原则验证）

```python
# 只需新增一个类，无需修改任何现有代码
class NewAgentAdapter(AgentAdapter):
    @property
    def name(self) -> str:
        return "new-agent"
    
    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_block=True,
            can_ask=True,
            uses_external_hooks=True,
        )
    
    def generate_rule_doc(self, content: str) -> list[FileSpec]:
        return [FileSpec(path="RULES.md", content=content)]
    
    def generate_hook_config(self, config: "BehaviorConfig") -> list[FileSpec]:
        return [FileSpec(path="new-agent-hooks.json", content="...")]

# 注册（可以在插件中完成）
AgentRegistry.register(NewAgentAdapter)
```

##### Agent 输出对比

| Agent | 规则文档 | Hook 配置 | Hook 机制 | 支持的操作 |
|-------|---------|----------|----------|-----------|
| **Claude Code** | `CLAUDE.md` | `.claude/settings.json` + `hooks/*.py` | 外部进程 | Read + Write + Execute + MCP + Web |
| **Cursor** | `.cursor/rules/behavior.mdc` | `.cursor/hooks.json` + `hooks/*.sh` | 外部进程 | Read + Execute + MCP（Write 无法拦截） |
| **OpenCode** | `AGENTS.md` | `.opencode/plugins/ai-guard.ts` | 插件内 | Read + Write + Execute + MCP + Web |
| **Copilot** | `.github/copilot-instructions.md` | 无 | 无 | 仅软约束（无执行能力） |

##### Agent 能力差异表

| 能力 | Claude Code | Cursor | OpenCode | Copilot |
|-----|-------------|--------|----------|---------|
| `can_block` | ✅ | ✅ | ✅ | ❌ |
| `can_ask` | ✅ | ⚠️ 部分 | ✅ | ❌ |
| `can_rewrite_input` | ✅ | ✅ | ✅ | ❌ |
| `uses_external_hooks` | ✅ | ✅ | ❌ | ❌ |
| **Write 拦截** | ✅ PreToolUse | ❌ 仅事后通知 | ✅ tool.execute.before | ❌ |

```

#### Validator（验证器）

**功能**：代码质量检查的编排器（而非直接执行器）。

> **职责演进**：原设计 Validator 直接执行命名/文档/结构/风格检查。
> 新设计将检查委托给 pre-commit 框架 + 外部成熟工具（clang-format/black/prettier 等）。
> Validator 专注于生成配置文件和编排检查流程。

**内部子组件**：

| 子组件 | 功能 | 输出 |
|-------|------|------|
| **Config Generator** | 从 guard.yaml 生成各工具配置 | `.clang-format`, `.eslintrc`, `pyproject.toml` |
| **Pre-commit Generator** | 生成 pre-commit 框架配置 | `.pre-commit-config.yaml` |
| **Check Runner** | 调用 pre-commit 执行检查 | 检查结果（通过/失败） |

```python
class Validator:
    def generate_tool_configs(self, config: GuardConfig) -> list[FileSpec]:
        """
        生成外部工具配置文件。
        
        Args:
            config: guard.yaml 配置（已合并三级配置）
        
        Returns:
            需要生成的配置文件列表 [(path, content), ...]
        """
        files = []
        
        # 遍历语言配置，生成对应工具配置
        for language, lang_config in config.languages.items():
            tool_mapper = ToolMapper(language)
            
            # 格式化工具配置
            if lang_config.tools.format == "clang-format":
                files.append((".clang-format", 
                              tool_mapper.map_to_clang_format(lang_config.code.style)))
            elif lang_config.tools.format == "black":
                files.append(("pyproject.toml", 
                              tool_mapper.map_to_black(lang_config.code.style)))
            elif lang_config.tools.format == "prettier":
                files.append((".prettierrc", 
                              tool_mapper.map_to_prettier(lang_config.code.style)))
            
            # Lint 工具配置
            if lang_config.tools.lint == "clang-tidy":
                files.append((".clang-tidy", 
                              tool_mapper.map_to_clang_tidy(lang_config.code)))
            elif lang_config.tools.lint == "eslint":
                files.append((".eslintrc", 
                              tool_mapper.map_to_eslint(lang_config.code)))
        
        return files
    
    def generate_precommit_config(self, config: GuardConfig) -> str:
        """
        生成 .pre-commit-config.yaml。
        
        Args:
            config: guard.yaml 配置
        
        Returns:
            pre-commit 配置文件内容
        """
        # 根据语言配置生成对应的 repo/hooks
        hooks = []
        for language, lang_config in config.languages.items():
            if lang_config.tools.format:
                hooks.append(self._make_format_hook(language, lang_config))
            if lang_config.tools.lint:
                hooks.append(self._make_lint_hook(language, lang_config))
        
        # 添加自定义检查（命名、文档、结构）
        hooks.extend(self._make_custom_hooks(config))
        
        return yaml.dump({"repos": hooks})
    
    def run_checks(self, files: list, config: GuardConfig) -> CheckReport:
        """
        调用 pre-commit 执行检查。
        
        Args:
            files: 待检查的文件列表
            config: guard.yaml 配置
        
        Returns:
            检查报告
        """
        # 调用 pre-commit CLI
        result = subprocess.run(
            ["pre-commit", "run", "--files", *files],
            capture_output=True
        )
        
        # 解析结果为 CheckReport
        return self._parse_precommit_output(result.stdout, result.returncode)
```

#### Tool Manager（工具管理器）

**功能**：管理外部工具的生命周期（检测、安装、配置映射）。

> **新增组件**：原设计中工具安装隐含在 install 命令中。
> 新设计将工具管理职责独立为 Tool Manager，支持工具检测、安装指导、参数映射。

**内部子组件**：

| 子组件 | 功能 | 使用场景 |
|-------|------|---------|
| **Tool Detector** | 检测工具是否安装 | install/check 前检测 |
| **Tool Installer** | 提供安装指导或自动安装 | install 时处理缺失工具 |
| **Tool Mapper** | guard.yaml 配置 → 工具参数 | 配置生成时映射参数 |

```python
class ToolManager:
    def detect_tools(self, config: GuardConfig) -> dict[str, ToolStatus]:
        """
        检测所需工具的安装状态。
        
        Args:
            config: guard.yaml 配置
        
        Returns:
            工具状态字典 {"clang-format": ToolStatus, ...}
        """
        required_tools = self._get_required_tools(config)
        status = {}
        
        for tool in required_tools:
            status[tool] = ToolStatus(
                name=tool,
                installed=self._is_installed(tool),
                version=self._get_version(tool) if self._is_installed(tool) else None
            )
        
        return status
    
    def install_tool(self, tool: str, method: str = "auto") -> InstallResult:
        """
        安装工具。
        
        Args:
            tool: 工具名称
            method: 安装方式 ("auto", "prompt", "manual")
        
        Returns:
            安装结果
        """
        if method == "auto":
            return self._auto_install(tool)
        elif method == "prompt":
            return self._prompt_install(tool)
        else:
            return InstallResult(status="manual", instructions=self._get_install_cmd(tool))
    
    def get_missing_tools_prompt(self, status: dict[str, ToolStatus]) -> str:
        """
        生成缺失工具的安装提示。
        
        Args:
            status: 工具状态字典
        
        Returns:
            格式化的安装提示文本
        """
        missing = [t for t, s in status.items() if not s.installed]
        
        prompt = "检测到以下工具未安装：\n"
        for tool in missing:
            prompt += f"  ├─ {tool}\n"
            prompt += f"  │   安装命令：{self._get_install_cmd(tool)}\n"
            prompt += f"  │   影响：{self._get_impact(tool)}\n"
        
        prompt += "\n请选择处理方式：\n"
        prompt += "  1. 自动安装所有（推荐）\n"
        prompt += "  2. 稍后手动安装\n"
        prompt += "  3. 查看详情并逐个选择\n"
        
        return prompt


class ToolMapper:
    """guard.yaml 配置 → 外部工具参数映射"""
    
    def __init__(self, language: str):
        self.language = language
    
    def map_to_clang_format(self, style_config: dict) -> str:
        """
        将 guard.yaml style 配置映射为 .clang-format 内容。
        
        Args:
            style_config: guard.yaml 中的 style 配置
        
        Returns:
            .clang-format YAML 内容
        """
        return yaml.dump({
            "BasedOnStyle": "LLVM",
            "IndentWidth": style_config.indent,
            "ColumnLimit": style_config.line_width,
            "BreakBeforeBraces": style_config.brace_style,
            # ... 其他映射
        })
    
    def map_to_eslint(self, code_config: dict) -> str:
        """映射为 .eslintrc 配置"""
    
    def map_to_prettier(self, style_config: dict) -> str:
        """映射为 .prettierrc 配置"""
    
    def map_to_black(self, style_config: dict) -> str:
        """映射为 pyproject.toml [tool.black] 配置"""
```

#### Language Plugin（语言插件）

**功能**：为不同编程语言提供配置模板和工具映射。

> **职责演进**：原设计 Language Plugin 提供检查规则。
> 新设计调整为提供"配置模板"和"工具映射"，检查规则由外部工具执行。

| 语言 | 插件文件 | 提供内容 |
|-----|---------|---------|
| C/C++ | `plugins/c.py` | 默认命名/文档/结构配置模板 + clang-format/clang-tidy 映射 |
| Python | `plugins/python.py` | PEP8 默认配置模板 + black/pylint 映射 |
| TypeScript | `plugins/typescript.py` | TypeScript 默认配置模板 + prettier/ESLint 映射 |
| Go | `plugins/go.py` | Go 默认配置模板 + gofmt/golangci-lint 映射 |
| Rust | `plugins/rust.py` | Rust 默认配置模板 + rustfmt/clippy 映射 |

```python
class LanguagePlugin:
    def get_default_config(self) -> dict:
        """
        返回语言默认配置模板。
        
        Returns:
            默认配置字典（包含 naming, documentation, structure, style）
        """
    
    def get_tool_mapping(self) -> dict:
        """
        返回语言 → 工具映射。
        
        Returns:
            {"format": "clang-format", "lint": "clang-tidy", ...}
        """
    
    def get_config_schema(self) -> dict:
        """
        返回配置字段 schema（用于验证）。
        
        Returns:
            {"naming.prefix": {"type": "string", "required": True}, ...}
        """
```

### 4.5 Agent 适配层

**职责**：将核心层输出转换为各 Agent 所需的具体格式。

**适配器接口**：

```python
class AgentAdapter:
    def adapt(self, core_output: CoreOutput, project_path: str) -> list[FileSpec]:
        """
        将核心层输出转换为 Agent 特定文件。
        
        Args:
            core_output: Generator/Interceptor/Validator 的输出
            project_path: 项目根目录
        
        Returns:
            需要写入的文件列表 [(path, content), ...]
        """
```

**各 Agent 适配详情**：

| Agent | 生成的文件 | Hook 配置 | 特殊处理 |
|-------|-----------|----------|---------|
| Claude Code | `CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/*.py` | PreToolUse/PostToolUse | 最完整支持 |
| OpenCode | `.opencode/rules/*.md`, Plugin 配置 | Plugin Hook | 需安装 Plugin |
| Cursor | `.cursor/rules/*.md`, `.cursor/hooks.json` | PreToolUse | 直接支持 |
| KiloCode | `.kilocode/rules/*.md` | 无 | 显示警告 |
| GitHub Copilot | `.github/copilot-instructions.md` | 无 | 显示警告 |

### 4.6 输出层

**职责**：内容生成、渲染、输出分发。

**架构模式**：Content → Renderer → Channel

```
┌─────────────────────────────────────────────────────────────────┐
│  Content (内容对象)                                             │
│  ├─ CheckReport: 检查结果报告                                   │
│  ├─ ConstraintDoc: 约束规则文档                                 │
│  ├─ WarningMessage: 警告信息                                    │
│  ├─ InstallSummary: 安装摘要                                    │
│  └─ AgentStatus: Agent 状态信息                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Renderer (渲染器)                                              │
│  ├─ MarkdownRenderer: 渲染为 Markdown                           │
│  ├─ JsonRenderer: 渲染为 JSON                                   │
│  ├─ HtmlRenderer: 渲染为 HTML                                   │
│  └─ ConsoleRenderer: 渲染为终端输出                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Channel (输出通道)                                             │
│  ├─ ConsoleChannel: 输出到终端                                  │
│  ├─ FileChannel: 写入文件                                       │
│  ├─ GitHubChannel: 发布为 PR 评论                               │
│  └─ WebhookChannel: 发送到外部服务                              │
└─────────────────────────────────────────────────────────────────┘
```

**扩展机制**：

添加新渲染器：
```python
class MyCustomRenderer(Renderer):
    def render(self, content: Content) -> str:
        # 自定义渲染逻辑
        return rendered_content
```

添加新输出通道：
```python
class SlackChannel(Channel):
    def output(self, rendered: str, config: OutputConfig):
        # 发送到 Slack
        slack_api.post(rendered)
```

---

## 5. 配置系统设计

### 5.1 设计理念

#### 核心原则

| 原则 | 说明 | 实现方式 |
|-----|------|---------|
| **复用成熟工具** | 不重复造轮子，工具已有完善的规则定义 | 集成 clang-tidy/ESLint/dependency-cruiser 等 |
| **规则集外部化** | 公司/项目统一维护规则集，而非每项目重复配置 | 支持 Git/本地/内置规则集导入 |
| **用户最小化配置** | 用户只需选择规则集 + 填写项目特定命令 | guard.yaml 极简化 |
| **标准输出格式** | 定义 AI Guard 标准格式，用户编写适配脚本 | validation-result.yaml |

### 5.2 规则集架构

#### 什么是规则集？

**规则集**是完整的规范包，包含：

| 内容 | 说明 |
|-----|------|
| **工具配置** | `.clang-format`, `.clang-tidy`, `.eslintrc` 等 |
| **自定义检查脚本** | 工具不支持的检查（文件前缀、依赖层级等） |
| **验证项定义** | 动态验证层可注册的验证项模板 |
| **适配脚本** | 将工具输出转换为 AI Guard 标准格式 |

#### 规则集目录结构

```
company-guard-rules/
│
├─ c/                              # C 语言规则集
│   ├─ rule.yaml                   # 规则集元信息
│   │
│   ├─ static/                     # 第一层：静态检查
│   │   ├─ .clang-format           # 格式化配置
│   │   ├─ .clang-tidy             # Lint 配置（包含命名规范）
│   │   └─ custom_checks/          # 工具不支持的检查
│   │       ├─ file_prefix.py      # 文件命名前缀
│   │       ├─ dependency_layer.py # 模块依赖层级
│   │       └─ doxygen.py          # Doxygen 注释检查
│   │
│   ├─ semantic/                   # 第二层：语义分析（可选）
│   │   └─ config.yaml
│   │
│   ├─ validation/                 # 第三层：动态验证
│   │   ├─ config.yaml             # 验证项注册定义
│   │   └─ adapters/               # 适配脚本
│   │       ├─ adapter_test.py     # 测试结果适配
│   │       ├─ adapter_coverage.py # 覆盖率结果适配
│   │       └─ adapter_asan.py     # ASAN 结果适配
│   │
│   └─ build/                      # 前置条件
│       └─ config.yaml
│
├─ python/
│   ├─ static/
│   │   ├─ pyproject.toml          # black/ruff/mypy 配置
│   │   └─ .importlinter           # 模块依赖检测
│   └─ ...
│
├─ ts/
│   ├─ static/
│   │   ├─ .eslintrc.json
│   │   ├─ .prettierrc
│   │   └─ .dependency-cruiser.js  # 模块依赖检测
│   └─ ...
│
└─ shared/
    └─ behavior.yaml               # 通用行为约束
```

#### 规则集元信息（rule.yaml）

```yaml
# c/rule.yaml
name: "company-c-rules"
version: "1.0.0"
description: "公司 C 语言代码规范规则集"

# 包含的配置文件
configs:
  static:
    format: ".clang-format"
    lint: ".clang-tidy"
    custom_checks:
      - "custom_checks/file_prefix.py"
      - "custom_checks/dependency_layer.py"
      - "custom_checks/doxygen.py"

# 支持的验证项
validation_items:
  - "test"
  - "coverage"
  - "asan"
  - "msan"
  - "ubsan"
```

#### 行为约束配置（behavior.yaml）

**位置**：`shared/behavior.yaml`（规则集中的共享配置）

**设计原则**：
- 统一格式：所有资源用 `pattern` 字段统一表达
- 操作语义：按 Read/Write/Execute 三类操作命名
- 预置默认：提供通用默认规则集
- Agent 适配：统一定义，不支持项忽略

##### 操作类型与资源范围

**操作类型**：

| 操作类型 | 含义 | 典型工具 |
|---------|------|---------|
| **Read** | 读取信息（不修改状态） | read, grep, glob, webfetch, websearch |
| **Write** | 写入/修改状态 | edit, write, apply_patch |
| **Execute** | 执行命令/程序 | bash, shell |

**资源范围（scheme）**：

| Scheme | 含义 | 覆盖维度 |
|--------|------|---------|
| `file` | 本地文件系统 | Local Read/Write |
| `mcp` | MCP 工具调用 | Remote Read/Write |
| `web` | Web 域名访问 | Remote Read |
| `api` | 第三方服务 API | Remote Read/Write |
| `shell` | Shell 命令 | Local Execute |

##### 完整格式定义

```yaml
# shared/behavior.yaml - 行为约束配置

# ==================== 读取限制 ====================
# 控制 AI 的读取操作（Local Read + Remote Read）

read_restriction:
  # 禁止读取：直接拒绝
  forbidden:
    # Local Read - 文件系统
    - pattern: "file:**/.env"
      reason: "敏感配置文件"
    - pattern: "file:**/secrets/**"
      reason: "密钥目录"
    - pattern: "file:**/*.pem"
      reason: "证书文件"
    - pattern: "file:**/*.key"
      reason: "密钥文件"
    - pattern: "file:**/credentials.*"
      reason: "凭证文件"
    
    # Remote Read - MCP 工具
    - pattern: "mcp:memory:search"
      reason: "禁止搜索记忆内容"
    
    # Remote Read - Web 域名
    - pattern: "web:*.internal.company.com"
      reason: "禁止访问内部域名"
    - pattern: "web:admin.*"
      reason: "禁止访问管理后台"
  
  # 需审批：提示用户确认
  require_approval:
    - pattern: "file:**/.gitignore"
      message: "Git 忽略配置访问需要确认"
    - pattern: "mcp:database:query"
      message: "数据库查询需要确认"

# ==================== 写入限制 ====================
# 控制 AI 的写入操作（Local Write + Remote Write）

write_restriction:
  # 禁止写入：直接拒绝
  forbidden:
    # Local Write - 文件系统
    - pattern: "file:third_party/**"
      reason: "第三方库，禁止修改"
    - pattern: "file:build/**"
      reason: "构建产物，禁止修改"
    - pattern: "file:dist/**"
      reason: "构建产物，禁止修改"
    - pattern: "file:.git/**"
      reason: "Git 内部文件，禁止修改"
    
    # Remote Write - MCP 工具
    - pattern: "mcp:memory:delete_*"
      reason: "禁止删除记忆"
    - pattern: "mcp:filesystem:write_*"
      reason: "禁止通过 MCP 写入文件"
    
    # Remote Write - API
    - pattern: "api:github:create_*"
      reason: "禁止创建 GitHub 资源"
    - pattern: "api:slack:send_*"
      reason: "禁止发送 Slack 消息"
  
  # 需审批：提示用户确认
  require_approval:
    - pattern: "file:.claude/hooks/**"
      message: "检查系统文件修改需要确认"
    - pattern: "file:.github/workflows/**"
      message: "CI 配置修改需要确认"
    - pattern: "mcp:github:create_pr"
      message: "创建 PR 需要确认"
  
  # 写入白名单：允许直接写入
  allow:
    - pattern: "file:src/**"
    - pattern: "file:include/**"
    - pattern: "file:tests/**"
    - pattern: "file:docs/**"

# ==================== 执行限制 ====================
# 控制 AI 的命令执行操作（Local Execute）

execute_restriction:
  # 禁止执行：直接拒绝
  forbidden:
    - pattern: "shell:git commit --no-verify"
      reason: "禁止跳过 pre-commit hooks"
    - pattern: "shell:git commit (--no-verify|--no-v|-n)"
      reason: "禁止跳过 pre-commit hooks（变体）"
      regex: true
    - pattern: "shell:git push --force"
      reason: "禁止强制推送到远程"
    - pattern: "shell:git push (--force|-f)"
      reason: "禁止强制推送（变体）"
      regex: true
    - pattern: "shell:git config core.hooksPath"
      reason: "禁止修改 hooks 路径"
    - pattern: "shell:SKIP=*"
      reason: "禁止使用 SKIP 跳过 hooks"
    - pattern: "shell:rm -rf /*"
      reason: "危险命令"
    - pattern: "shell:sudo *"
      reason: "禁止执行 sudo"
  
  # 自动允许：无需检查
  allow:
    - pattern: "shell:git status"
    - pattern: "shell:git diff"
    - pattern: "shell:git log"
    - pattern: "shell:git branch"
    - pattern: "shell:ls"
    - pattern: "shell:cat"
    - pattern: "shell:grep"
    - pattern: "shell:find"
    - pattern: "shell:pwd"
```

##### Pattern 格式规范

**基本格式**：

```
{scheme}:{path_pattern}
```

**各 Scheme 格式**：

| Scheme | 格式 | 示例 | 通配符 |
|--------|------|------|--------|
| `file` | `file:{glob_path}` | `file:**/.env` | `**`, `*` (glob) |
| `mcp` | `mcp:{server}:{tool}` | `mcp:memory:search` | `*` (通配) |
| `web` | `web:{domain_pattern}` | `web:*.internal.com` | `*` (通配) |
| `api` | `api:{service}:{action}` | `api:github:create_issue` | `*` (通配) |
| `shell` | `shell:{command_pattern}` | `shell:git push --force` | `*` (通配) 或 `regex: true` |

**规则字段**：

| 字段 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `pattern` | string | ✅ | 匹配模式 |
| `reason` | string | ❌ | 禁止原因（forbidden 用） |
| `message` | string | ❌ | 确认提示（require_approval 用） |
| `regex` | boolean | ❌ | 是否为正则模式（默认 false） |

##### 配置项说明

| 配置项 | 操作类型 | 资源范围 | 拦截行为 |
|-------|---------|---------|---------|
| `read_restriction.forbidden` | Read | file, mcp, web, api | 直接拒绝 |
| `read_restriction.require_approval` | Read | file, mcp, web, api | 提示确认 |
| `write_restriction.forbidden` | Write | file, mcp, api | 直接拒绝 |
| `write_restriction.require_approval` | Write | file, mcp, api | 提示确认 |
| `write_restriction.allow` | Write | file, mcp, api | 直接放行 |
| `execute_restriction.forbidden` | Execute | shell | 直接拒绝 |
| `execute_restriction.allow` | Execute | shell | 直接放行 |

##### 匹配优先级

当多个规则匹配同一操作时，按以下优先级处理：

```
forbidden > require_approval > allow
```

**示例**：

```yaml
write_restriction:
  forbidden:
    - pattern: "file:src/**/*.test.ts"
  allow:
    - pattern: "file:src/**"

# AI 尝试写入 src/foo.test.ts
# 匹配两条规则：forbidden 和 allow
# forbidden 优先级更高 → 拒绝操作
```

##### Agent 能力适配

统一定义，Agent 不支持的 scheme 自动忽略：

| Agent | 支持的 Scheme | 说明 |
|-------|--------------|------|
| Claude Code | file, mcp, web, api, shell | 完整支持 |
| Cursor | file, web, shell | MCP 支持中（Beta） |
| OpenCode | file, mcp, web, shell | 完整支持 |
| KiloCode | file, shell | 待确认 |
| GitHub Copilot | 无执行能力 | 仅生成规则文档（软约束） |

**适配逻辑**：Interceptor 检查时，若 Agent 不支持某 scheme，则跳过该类规则检查。

##### 默认规则集

AI Guard 内置默认 `behavior.yaml`，提供通用保护规则：

**内置默认包含**：

| 类型 | 默认规则 |
|-----|---------|
| **Write Forbidden** | `file:third_party/**`, `file:build/**`, `file:.git/**` |
| **Read Forbidden** | `file:**/.env`, `file:**/*.pem`, `file:**/*.key` |
| **Execute Forbidden** | `shell:git commit --no-verify`, `shell:git push --force`, `shell:sudo *` |
| **Write Allow** | `file:src/**`, `file:tests/**`, `file:docs/**` |

**用户可通过 guard.yaml 覆盖默认规则**。

### 5.3 用户配置（guard.yaml）

#### 极简配置

```yaml
# guard.yaml
project:
  name: "GsPDMemo"
  language: "c"

# 引用规则集
ruleset: "git@github.com:company/guard-rules.git#c"

# 前置条件：编译
build:
  command: "./build.sh"

# 动态验证：注册需要的验证项
validation:
  test:
    command: "./build.sh test"
  coverage:
    command: "./build.sh test --coverage"
    threshold: 80
  asan:
    enabled: true
    command: "./build.sh test --asan"
```

#### 规则集来源

| 来源 | 格式 | 说明 |
|-----|------|------|
| **Git 仓库** | `git@github.com:company/rules.git#c` | 推荐，版本控制 |
| **本地路径** | `./local-rules/c` | 本地开发/测试 |
| **内置规则集** | `builtin://c-standard` | AI Guard 内置基础规则 |

#### 覆盖规则集配置

```yaml
# guard.yaml
project:
  name: "GsPDMemo"
  language: "c"

ruleset: "git@github.com:company/guard-rules.git#c"

# 行为约束覆盖
behavior:
  file_protection:
    require_approval:
      - path: ".claude/hooks/**"
        message: "检查系统文件修改需要确认"

# 验证项配置覆盖
validation:
  test:
    command: "./build.sh test"
    timeout: 600              # 覆盖规则集默认超时
```

### 5.4 验证项注册机制

#### 为什么需要注册机制？

| 问题 | 解决方案 |
|-----|---------|
| 不同语言验证内容不同 | 用户注册需要的验证项 |
| 验证项输出格式各异 | 用户编写适配脚本，输出标准格式 |
| 无法预知用户需求 | 提供扩展机制，而非硬编码 |

#### 验证项定义（规则集中）

```yaml
# c/validation/config.yaml
registered_validations:
  test:
    name: "单元测试"
    description: "运行单元测试"
    adapter: "adapters/adapter_test.py"
    config_schema:
      command:
        type: "string"
        required: true
      timeout:
        type: "integer"
        default: 300
  
  coverage:
    name: "代码覆盖率"
    description: "检查代码覆盖率是否达标"
    adapter: "adapters/adapter_coverage.py"
    config_schema:
      command:
        type: "string"
        required: true
      threshold:
        type: "integer"
        default: 80
      report_path:
        type: "string"
        default: "build/coverage"
  
  asan:
    name: "内存错误检测"
    description: "AddressSanitizer 内存错误检测"
    adapter: "adapters/adapter_asan.py"
    config_schema:
      command:
        type: "string"
        required: true
      enabled:
        type: "boolean"
        default: false
```

#### 不同语言的验证项

| 语言 | 验证项 |
|-----|--------|
| **C/C++** | test, coverage, asan, msan, ubsan |
| **Python** | test, coverage, type_check (mypy), security (bandit) |
| **TypeScript** | test, coverage, e2e |
| **Go** | test, coverage, race |

### 5.5 标准输出格式

#### 设计原则

> **AI Guard 定义标准格式，用户编写适配脚本输出此格式。**

| 原因 | 说明 |
|-----|------|
| 验证内容不可预测 | 不同项目验证的东西差异很大 |
| 工具输出格式多变 | 同一工具不同版本输出格式可能变化 |
| AI Guard 无法穷举 | 不可能支持所有工具的所有输出格式 |

#### 标准格式定义

```yaml
# validation-result.yaml
schema_version: "1.0"

# 基本信息
validation:
  name: "test"                  # 验证项名称
  type: "test"                  # test / coverage / lint / sanitizer / custom

# 执行状态
status: "pass"                  # pass / fail / skip / error
duration_ms: 4523

# 摘要（一行描述）
summary: "50 tests passed, 0 failed"

# 指标（标准化字段 + 扩展字段）
metrics:
  # 标准字段
  total: 50
  passed: 50
  failed: 0
  skipped: 0
  
  # 扩展字段（根据验证类型）
  duration_s: 4.523

# 违规列表
violations:
  - file: "src/memory.c"
    line: 156
    column: 5
    severity: "error"           # error / warning / info
    code: "ASSERTION_FAILED"
    message: "Expected 5, got 3"
    context: "assert(count == 5)"

# 报告路径（可选）
reports:
  html: "build/coverage/index.html"
  xml: "build/test-results/junit.xml"
  log: "build/test.log"
```

#### 不同验证类型的标准字段

| 验证类型 | 标准字段 |
|---------|---------|
| **test** | total, passed, failed, skipped |
| **coverage** | line_coverage, branch_coverage, function_coverage, threshold |
| **lint** | errors, warnings |
| **sanitizer** | errors, leaks |

#### 适配脚本示例

```python
#!/usr/bin/env python3
# adapters/adapter_test.py
# 将 GTest 输出转换为 AI Guard 标准格式

import sys
import xml.etree.ElementTree as ET
import yaml

def parse_gtest_xml(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    total = passed = failed = skipped = 0
    violations = []
    
    for testsuite in root.findall('.//testsuite'):
        total += int(testsuite.get('tests', 0))
        failed += int(testsuite.get('failures', 0))
        
        for testcase in testsuite.findall('testcase'):
            failure = testcase.find('failure')
            if failure is not None:
                violations.append({
                    'file': testcase.get('classname', ''),
                    'line': 0,
                    'severity': 'error',
                    'code': 'TEST_FAILED',
                    'message': failure.get('message', ''),
                })
    
    passed = total - failed
    
    return {
        'schema_version': '1.0',
        'validation': {'name': 'test', 'type': 'test'},
        'status': 'pass' if failed == 0 else 'fail',
        'summary': f"{total} tests, {passed} passed, {failed} failed",
        'metrics': {'total': total, 'passed': passed, 'failed': failed},
        'violations': violations
    }

if __name__ == '__main__':
    result = parse_gtest_xml(sys.argv[1])
    print(yaml.dump(result, default_flow_style=False))
```

### 5.6 custom_checks 定位

#### 什么是 custom_checks？

**custom_checks 是静态检查层的补充，处理工具不支持的检查。**

| 检查类型 | 工具支持 | 是否需要 custom_checks |
|---------|---------|---------------------|
| **格式化** | clang-format/black/prettier | ❌ 不需要 |
| **命名规范** | clang-tidy `readability-identifier-naming` | ❌ 不需要 |
| **Lint** | clang-tidy/pylint/ESLint | ❌ 不需要 |
| **文件命名前缀** | 无工具支持 | ✅ 需要脚本 |
| **模块依赖层级** | 部分语言有（dependency-cruiser/import-linter） | ⚠️ C/C++ 需要 |
| **文档注释检查** | 无工具支持（C Doxygen） | ✅ 需要脚本 |

#### custom_checks 输出格式

```yaml
schema_version: "1.0"
validation:
  name: "file_prefix"
  type: "static"
status: "fail"
summary: "2 naming violations found"
violations:
  - file: "src/memory/store.c"
    line: 0
    severity: "error"
    code: "MISSING_PREFIX"
    message: "File should start with 'mem_' prefix"
```

### 5.7 模块依赖检测方案

#### 业界工具对比

| 语言 | 工具 | 成熟度 |
|-----|------|-------|
| **TypeScript/JS** | dependency-cruiser | ⭐⭐⭐⭐⭐ 最成熟 |
| **Java** | ArchUnit | ⭐⭐⭐⭐⭐ 最成熟 |
| **Python** | import-linter | ⭐⭐⭐⭐ 成熟 |
| **C/C++** | 无成熟工具 | ⭐⭐ 缺失 |

#### AI Guard 策略

| 语言 | 策略 | 工具 |
|-----|------|------|
| **TypeScript/JS** | 集成成熟工具 | dependency-cruiser |
| **Java** | 集成成熟工具 | ArchUnit |
| **Python** | 集成成熟工具 | import-linter |
| **C/C++** | 自定义脚本 | custom_checks/dependency_layer.py |

#### C/C++ 模块依赖检测脚本

```python
# custom_checks/dependency_layer.py

def check_dependency_layer(file_path, include_stmt, modules):
    """
    检查 include 是否违反依赖层级。
    
    1. 根据文件路径确定所属模块
    2. 根据 include 路径确定依赖模块
    3. 检查依赖是否在允许列表中
    """
    current_module = find_module(file_path, modules)
    include_module = find_module(include_stmt, modules)
    
    if include_module not in current_module['allowed_deps']:
        return Violation(
            file=file_path,
            message=f"'{current_module['name']}' 不能依赖 '{include_module}'"
        )
```

### 5.8 配置生成流程

```
guard install
    │
    ├─ Step 1: 解析 guard.yaml
    │   └─ 发现 ruleset: "git@github.com:company/guard-rules.git#c"
    │
    ├─ Step 2: 获取规则集
    │   └─ Git clone 到 .ai-guard/cache/
    │
    ├─ Step 3: 加载规则集配置
    │   ├─ 读取 c/rule.yaml
    │   ├─ 加载 static/.clang-format
    │   ├─ 加载 static/.clang-tidy
    │   └─ 加载 validation/config.yaml
    │
    ├─ Step 4: 应用用户覆盖
    │   └─ 合并 guard.yaml 中的 validation 配置
    │
    ├─ Step 5: 生成工具配置
    │   ├─ .clang-format → 项目根目录
    │   ├─ .clang-tidy → 项目根目录
    │   ├─ .pre-commit-config.yaml → 项目根目录
    │   └─ custom_checks/ → .ai-guard/custom_checks/
    │
    └─ Step 6: 安装 Git Hooks
        └─ pre-commit install
```

---

## 6. CLI 命令设计

### 6.1 设计理念

#### 生命周期状态机

CLI 命令围绕 AI Guard 的生命周期设计：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AI Guard 生命周期                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│    ┌──────────┐        ┌──────────┐        ┌──────────┐               │
│    │   S0     │  init  │   S1     │ install│   S2     │               │
│    │  未配置  │ -----> │  已配置  │ -----> │  已安装  │               │
│    └──────────┘        └──────────┘        └──────────┘               │
│         ^                   │                   │                      │
│         │                   │                   │ check/verify/run     │
│         │                   │                   v                      │
│         │                   │             ┌──────────┐                 │
│         │                   │             │   S3     │                 │
│         │                   │             │  使用中  │                 │
│         │                   │             └──────────┘                 │
│         │                   │                   │                      │
│         │    uninstall      │      update       │                      │
│         └───────────────────┴───────────────────┘                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 命令分类

```
guard
│
├─ 生命周期命令（状态转换）
│   ├─ init          S0 → S1    创建配置
│   ├─ install       S1 → S2    安装系统
│   ├─ update        S2 → S2'   更新文档
│   └─ uninstall     S2/S3 → S0 卸载清理
│
├─ 操作命令（执行检查）
│   ├─ check         执行静态检查
│   ├─ verify        执行门禁验证
│   └─ run           运行单个验证项
│
├─ 资源命令（规则集管理）
│   ├─ ruleset list    列出可用规则集
│   ├─ ruleset show    查看规则集详情
│   ├─ ruleset fetch   获取/更新规则集
│   └─ ruleset cache   缓存管理
│
├─ 结果命令（查看报告）
│   ├─ validation list    列出可用验证项
│   └─ validation report  生成/查看报告
│
└─ 信息命令（了解状态）
    ├─ status        当前安装状态
    ├─ agents        支持的 Agent
    └─ version       版本信息
```

### 6.2 生命周期命令

#### init 命令

**功能**：在项目中初始化配置。

```bash
guard init [OPTIONS]

OPTIONS:
  --ruleset URL       指定规则集（Git URL 或本地路径）
  --language LANG     指定主语言（默认自动检测）
  --name NAME         项目名称（默认从目录名推断）
```

**执行流程**：

```
guard init --ruleset git@github.com:company/guard-rules.git#c
    ↓
检测项目信息
    ├─ 扫描目录结构
    ├─ 检测主语言
    └─ 推断项目名称
    ↓
获取规则集
    ├─ 克隆到 .ai-guard/cache/
    └─ 读取规则集元信息
    ↓
生成 guard.yaml
    ├─ 填充项目信息
    ├─ 引用规则集
    └─ 写入配置文件
    ↓
输出结果
    ├─ 显示生成的配置
    └─ 提示下一步：guard install
```

#### install 命令

**功能**：安装 AI Guard 到项目。

```bash
guard install [OPTIONS]

OPTIONS:
  --agent AGENTS      指定 Agent（逗号分隔，默认全部）
  --no-hooks          不安装 Git Hooks
```

**执行流程**：

```
guard install --agent claude-code,cursor
    ↓
解析配置
    ├─ 读取 guard.yaml
    ├─ 加载规则集
    └─ 解析 Agent 列表
    ↓
生成工具配置
    ├─ .clang-format
    ├─ .clang-tidy
    └─ .pre-commit-config.yaml
    ↓
生成 Agent 文件
    ├─ ClaudeCodeAdapter: CLAUDE.md, .claude/settings.json
    ├─ CursorAdapter: .cursor/rules/, .cursor/hooks.json
    └─ 写入文件
    ↓
安装 Git Hooks
    ├─ .git/hooks/pre-commit
    ├─ .git/hooks/pre-push
    └─ 设置执行权限
    ↓
输出安装摘要
```

**安装摘要示例**：

```
✅ AI Guard 安装完成

规则集: company-c-rules v1.0.0
Agent: claude-code, cursor

生成的文件:
  ├─ guard.yaml
  ├─ .clang-format
  ├─ .clang-tidy
  ├─ .pre-commit-config.yaml
  ├─ CLAUDE.md
  ├─ .claude/settings.json
  └─ .claude/hooks/

Git Hooks:
  ├─ pre-commit: ✅ 已安装
  └─ pre-push: ✅ 已安装

下一步:
  1. 运行 guard check 测试检查
  2. 开始使用 AI Agent 编码
```

#### update 命令

**功能**：更新规则文档（保留用户自定义内容）。

```bash
guard update [OPTIONS]

OPTIONS:
  --force             强制覆盖所有内容（不保留用户内容）
```

**托管块机制**：

```markdown
<!-- AI-GUARD:BEGIN:behavior -->
... AI Guard 自动生成的行为约束内容 ...
<!-- AI-GUARD:END:behavior -->

<!-- AI-GUARD:BEGIN:code -->
... AI Guard 自动生成的代码规范内容 ...
<!-- AI-GUARD:END:code -->

## 项目特定说明

用户可以在这里添加自定义内容。
update 命令不会修改托管块以外的内容。
```

#### uninstall 命令

**功能**：卸载 AI Guard。

```bash
guard uninstall [OPTIONS]

OPTIONS:
  --keep-config       保留 guard.yaml
  --keep-cache        保留规则集缓存
```

**执行流程**：

```
guard uninstall
    ↓
确认卸载
    └─ 提示用户确认
    ↓
清理文件
    ├─ 删除 Agent 文件（CLAUDE.md 等）
    ├─ 删除工具配置（.clang-format 等）
    ├─ 删除 Git Hooks
    └─ 可选：删除 guard.yaml
    ↓
输出结果
    └─ 显示已删除的文件列表
```

### 6.3 操作命令

#### check 命令

**功能**：执行静态检查（pre-commit 级别）。

```bash
guard check [OPTIONS]

OPTIONS:
  --files FILES       指定检查文件（默认检查暂存文件）
  --rules RULES       指定检查规则（逗号分隔）
  --fix               自动修复可修复的问题
```

**执行流程**：

```
guard check
    ↓
获取待检查文件
    └─ 默认：git diff --cached --name-only
    ↓
执行静态检查（不需要编译）
    ├─ clang-format（格式化）
    ├─ clang-tidy --checks=readability-identifier-naming
    └─ custom_checks
    ↓
输出检查报告
    ├─ 通过：✅ 无问题
    └─ 失败：❌ 显示违规列表
```

#### verify 命令

**功能**：执行门禁验证（pre-push 级别）。

```bash
guard verify [OPTIONS]

OPTIONS:
  --validation NAMES  指定验证项（逗号分隔，默认全部）
  --skip-build        跳过编译（使用已有编译产物）
```

**执行流程**：

```
guard verify
    ↓
Build（前置条件）
    └─ 执行编译命令
    ↓
语义分析
    └─ clang-tidy（完整检查）
    ↓
动态验证
    ├─ test
    ├─ coverage
    └─ asan（如果启用）
    ↓
输出验证报告
```

#### run 命令

**功能**：运行单个验证项（精细化调试）。

```bash
guard run <validation-name> [OPTIONS]

OPTIONS:
  --args ARGS         传递给验证项的额外参数
```

**示例**：

```bash
guard run test                    # 运行测试
guard run coverage --args 90      # 运行覆盖率检查，阈值 90%
guard run asan                    # 运行 ASAN
```

### 6.4 规则集命令

#### ruleset list 命令

**功能**：列出可用规则集。

```bash
guard ruleset list [OPTIONS]

OPTIONS:
  --remote            显示远程可用规则集（需联网）
```

**输出示例**：

```
本地规则集:
  ├─ c (company-c-rules v1.0.0)
  └─ python (company-python-rules v1.2.0)

内置规则集:
  ├─ builtin://c-standard
  ├─ builtin://python-standard
  └─ builtin://typescript-standard
```

#### ruleset show 命令

**功能**：查看规则集详情。

```bash
guard ruleset show <name>
```

**输出示例**：

```
规则集: company-c-rules
版本: v1.0.0
来源: git@github.com:company/guard-rules.git#c

包含内容:
  ├─ static/.clang-format
  ├─ static/.clang-tidy
  ├─ static/custom_checks/file_prefix.py
  ├─ static/custom_checks/dependency_layer.py
  └─ validation/config.yaml

验证项:
  ├─ test
  ├─ coverage
  ├─ asan
  ├─ msan
  └─ ubsan
```

#### ruleset fetch 命令

**功能**：获取或更新规则集。

```bash
guard ruleset fetch <url> [OPTIONS]

OPTIONS:
  --branch BRANCH     指定分支（默认 main）
  --tag TAG           指定标签
```

#### ruleset cache 命令

**功能**：规则集缓存管理。

```bash
guard ruleset cache list           # 列出缓存的规则集
guard ruleset cache clear          # 清除所有缓存
guard ruleset cache clear <name>   # 清除指定规则集缓存
```

### 6.5 验证项命令

#### validation list 命令

**功能**：列出可用的验证项。

```bash
guard validation list
```

**输出示例**：

```
可用验证项:

测试验证:
  ├─ test          单元测试
  ├─ coverage      代码覆盖率
  └─ e2e           端到端测试（可选）

内存检测:
  ├─ asan          AddressSanitizer
  ├─ msan          MemorySanitizer（可选）
  └─ ubsan         UndefinedBehaviorSanitizer（可选）

已启用:
  ├─ test: ✅
  ├─ coverage: ✅ (threshold: 80%)
  └─ asan: ✅
```

#### validation report 命令

**功能**：生成或查看验证报告。

```bash
guard validation report [OPTIONS]

OPTIONS:
  --format FORMAT     输出格式（markdown/json/html，默认 markdown）
  --output PATH       输出路径（默认终端输出）
```

### 6.6 信息命令

#### status 命令

**功能**：显示当前安装状态。

```bash
guard status
```

**输出示例**：

```
AI Guard 状态: 已安装 (v2.0.0)

项目: GsPDMemo
语言: C
规则集: company-c-rules v1.0.0

配置文件: guard.yaml
  ├─ 行为约束: 3 条规则
  ├─ 验证项: 3 个启用
  └─ 质量门禁: 覆盖率 80%

已安装 Agent:
  ├─ Claude Code (全生效)
  └─ Cursor (全生效)

Git Hooks:
  ├─ pre-commit: ✅ 已安装
  └─ pre-push: ✅ 已安装

规则文档:
  ├─ CLAUDE.md: ✅ 存在
  └─ 最后更新: 2024-01-15
```

#### agents 命令

**功能**：显示支持的 Agent 信息。

```bash
guard agents
```

**输出示例**：

```
支持的 Agent:

┌─────────────────────────────────────────────────────────────────┐
│ Agent         │ PreToolUse │ Rules Doc │ Hook     │ 生效状态   │
├─────────────────────────────────────────────────────────────────┤
│ Claude Code   │ ✅         │ CLAUDE.md  │ settings │ 全生效     │
│ Cursor        │ ✅         │ rules/     │ hooks.json│ 全生效    │
│ OpenCode      │ ✅ Plugin  │ rules/     │ plugin   │ 全生效     │
│ KiloCode      │ ❌         │ rules/     │ 无       │ 仅代码看护 │
│ GitHub Copilot│ ❌         │ instructions│ 无      │ 仅代码看护 │
└─────────────────────────────────────────────────────────────────┘

推荐: Claude Code, Cursor, OpenCode 支持完整看护功能。
```

#### version 命令

**功能**：显示版本信息。

```bash
guard version
```

#### doctor 命令

**功能**：诊断环境问题，根据项目语言配置动态检查。

```bash
guard doctor
```

**检查项框架**：

| 检查类别 | 检查项 | 说明 |
|---------|--------|------|
| **工具检查** | pre-commit 是否安装 | 通用，所有项目必需 |
| | 语言工具链（按配置） | 根据项目语言动态检查 |
| **配置检查** | guard.yaml 语法是否正确 | 通用 |
| | 语言配置文件（按规则集） | 根据规则集动态检查 |
| **文件检查** | 规则集是否存在 | 通用 |
| | Git Hooks 是否有执行权限 | 通用 |
| | Agent 约束文档是否存在 | 按配置的 Agent 类型检查 |
| **依赖检查** | 编译产物（按语言） | 根据语言动态检查 |

**语言动态检查映射**：

| 语言 | 工具链检查 | 配置文件检查 | 编译产物检查 |
|------|-----------|-------------|-------------|
| C/C++ | clang-format, clang-tidy, cmake | .clang-format, .clang-tidy | compile_commands.json |
| Python | black, ruff, pytest | pyproject.toml, ruff.toml | 无（静态语言） |
| TypeScript | prettier, eslint, npm/node | .prettierrc, .eslintrc | tsconfig.json, dist/ |
| Go | gofmt, go vet, go test | 无（内置） | 无 |
| Java | gradle/maven, spotless | spotless配置 | build/ |

**输出示例（C/C++ 项目）**：

```
检查环境...

工具检查:
  ✅ pre-commit 已安装 (v3.6.0)
  ✅ clang-format 已安装 (v17.0.6)
  ✅ clang-tidy 已安装 (v17.0.6)
  ✅ cmake 已安装 (v3.28.0)

配置检查:
  ✅ guard.yaml 语法正确
  ✅ .clang-format 语法正确
  ✅ .clang-tidy 语法正确

文件检查:
  ✅ 规则集存在: company-c-rules v1.0.0
  ✅ Git Hooks 有执行权限
  ✅ CLAUDE.md 存在

依赖检查:
  ⚠️ compile_commands.json 不存在（需要先编译）

环境检查通过 ✅
```

**输出示例（Python 项目）**：

```
检查环境...

工具检查:
  ✅ pre-commit 已安装 (v3.6.0)
  ✅ black 已安装 (v24.1.0)
  ✅ ruff 已安装 (v0.1.0)
  ✅ pytest 已安装 (v7.4.0)

配置检查:
  ✅ guard.yaml 语法正确
  ✅ pyproject.toml 语法正确

文件检查:
  ✅ 规则集存在: company-python-rules v1.0.0
  ✅ Git Hooks 有执行权限
  ✅ CLAUDE.md 存在

环境检查通过 ✅
```

**错误示例**：

```
检查环境...

工具检查:
  ✅ pre-commit 已安装 (v3.6.0)
  ✅ clang-format 已安装 (v17.0.6)
  ❌ clang-tidy 未安装
     安装命令: brew install llvm
  ✅ cmake 已安装 (v3.28.0)

配置检查:
  ✅ guard.yaml 语法正确
  ❌ .clang-format 语法错误
     第 15 行: 未知键 'IndentSize'
     提示: 应为 'IndentWidth'

环境检查失败 ❌
  错误: 2
  警告: 0
```

### 6.7 命令参数设计原则

| 原则 | 说明 | 示例 |
|-----|------|------|
| **默认值合理** | 常用场景无需参数 | `guard check` 检查暂存文件 |
| **可选参数丰富** | 高级场景可定制 | `guard check --files src/*.c` |
| **互斥参数明确** | 避免歧义 | `--agent` 只能指定 Agent |
| **短参数支持** | 常用参数有简写 | `-a` = `--agent` |
| **子命令分组** | 相关命令分组 | `ruleset list/show/fetch` |

### 6.8 闭环证明

#### 生命周期闭环

| 转换 | 命令 | 逆操作 | 命令 |
|-----|------|--------|------|
| S0 → S1 | `init` | S1 → S0 | 删除 guard.yaml |
| S1 → S2 | `install` | S2 → S1 | `uninstall --keep-config` |
| S2 → S3 | `check`/`verify`/`run` | S3 → S2 | 无需转换 |
| S2/S3 → S0 | `uninstall` | - | - |

#### 资源闭环

| 资源操作 | 命令 |
|---------|------|
| 获取规则集 | `ruleset fetch` |
| 查看规则集 | `ruleset list/show` |
| 更新规则集 | `ruleset fetch` / `ruleset cache clear` |
| 清理缓存 | `ruleset cache clear` |

#### 操作闭环

| 操作阶段 | 命令 |
|---------|------|
| 查看可用 | `validation list` |
| 选择执行 | `check` / `verify` / `run` |
| 查看结果 | `validation report` |

---

## 7. Agent 适配设计

### 7.1 Agent 能力矩阵

| Agent | PreToolUse | PostToolUse | Rules Doc | Hook Mechanism | 生效状态 |
|-------|------------|-------------|-----------|----------------|----------|
| **Claude Code** | ✅ 原生支持 | ✅ 可选（默认关闭） | CLAUDE.md | .claude/settings.json | **全生效** |
| **OpenCode** | ✅ Plugin | ✅ 可选（默认关闭） | .opencode/rules/ | Plugin system | **全生效** |
| **Cursor** | ✅ 原生支持 | ✅ 可选（默认关闭） | .cursor/rules/ | .cursor/hooks.json | **全生效** |
| **KiloCode** | ❌ 不支持 | ❌ 不支持 | .kilocode/rules/ | 无 | **仅代码看护生效** |
| **GitHub Copilot** | ❌ 不支持 | ❌ 不支持 | .github/copilot-instructions.md | 无 | **仅代码看护生效** |

> **说明**：PostToolUse "✅ 可选（默认关闭）" 表示 Agent 技术上支持该能力，但 AI Guard 默认不启用，需用户在 `output.post_tool_use.enabled: true` 时才生成对应配置。

**生效状态说明**：

| 生效状态 | 行为约束 | 代码看护 | 原因 |
|---------|---------|---------|------|
| **全生效** | ✅ | ✅ | Agent 支持 PreToolUse Hook |
| **仅代码看护生效** | ❌ | ✅ | Agent 不支持 Hook，但 pre-commit/pre-push 是 Git 原生机制 |

### 7.2 Claude Code 适配

**生成的文件结构**：

```
project/
├─ CLAUDE.md                      # 规则文档
├─ .claude/
│   ├─ settings.json              # Hook 配置
│   └─ hooks/
│       ├─ enforce_check_system.py # PreToolUse Hook（必需）
│       ├─ auto_pr_report.py      # PostToolUse Hook（可选，默认不启用）
│       └─ utils.py               # 辅助函数
├─ .git/hooks/
│   ├─ pre-commit                 # Git pre-commit Hook
│   └─ pre-push                   # Git pre-push Hook
```

**settings.json 结构（默认配置，PostToolUse 关闭）**：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/enforce_check_system.py"
          }
        ]
      }
    ]
  }
}
```

**settings.json 结构（启用 PostToolUse 时）**：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/enforce_check_system.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/auto_pr_report.py",
            "timeout": 60000
          }
        ]
      }
    ]
  }
}
```

> **注意**：PostToolUse 默认关闭，仅在 `output.post_tool_use.enabled: true` 时生成配置。

### 7.3 OpenCode 适配

**生成的文件结构**：

```
project/
├─ .opencode/
│   ├─ rules/
│   │   ├─ behavior.md            # 行为约束
│   │   ├─ code-style.md          # 代码规范
│   │   └─ structure.md           # 结构规则
│   └─ plugins/
│       └─ ai-guard/
│           ├─ plugin.json        # Plugin 配置
│           ├─ interceptor.js     # PreToolUse Hook（必需）
│           └─ reporter.js        # PostToolUse Hook（可选，默认不启用）
├─ .git/hooks/
│   ├─ pre-commit
│   └─ pre-push
```

**Plugin 配置（默认，PostToolUse 关闭）**：

```json
{
  "name": "ai-guard",
  "version": "1.0.0",
  "hooks": {
    "preToolUse": "./plugins/ai-guard/interceptor.js"
  }
}
```

**Plugin 配置（启用 PostToolUse 时）**：

```json
{
  "name": "ai-guard",
  "version": "1.0.0",
  "hooks": {
    "preToolUse": "./plugins/ai-guard/interceptor.js",
    "postToolUse": "./plugins/ai-guard/reporter.js"
  }
}
```

### 7.4 Cursor 适配

**生成的文件结构**：

```
project/
├─ .cursor/
│   ├─ rules/
│   │   ├─ behavior.mdc           # 行为约束 (.mdc = Cursor 规则格式)
│   │   ├─ code-style.mdc         # 代码规范
│   │   └─ always-apply.mdc       # 全局应用规则
│   └─ hooks.json                 # Hook 配置
├─ scripts/
│   └─ hooks/
│       ├─ interceptor.py         # PreToolUse Hook 脚本
│       └─ reporter.py            # PostToolUse Hook 脚本（可选）
├─ .git/hooks/
│   ├─ pre-commit
│   └─ pre-push
```

**hooks.json 结构（默认，PostToolUse 关闭）**：

```json
{
  "preToolUse": {
    "command": "python3 scripts/hooks/interceptor.py",
    "timeout": 5000
  }
}
```

**hooks.json 结构（启用 PostToolUse 时）**：

```json
{
  "preToolUse": {
    "command": "python3 scripts/hooks/interceptor.py",
    "timeout": 5000
  },
  "postToolUse": {
    "command": "python3 scripts/hooks/reporter.py",
    "timeout": 10000
  }
}
```

### 7.5 不支持 Hook 的 Agent 处理策略

**场景**：安装 KiloCode 或 GitHub Copilot 时。

**处理流程**：

```
guard install --agent kilocode
    ↓
检测 Agent 能力
    ├─ 查询能力矩阵
    ├─ 发现 KiloCode 不支持 PreToolUse
    └─ 触发警告逻辑
    ↓
生成规则文档
    ├─ 仅生成 .kilocode/rules/
    ├─ 不生成 Hook 文件
    └─ Git Hooks 仍然安装（pre-commit/pre-push）
    ↓
显示安装摘要 + 警告
```

**警告信息**：

```
⚠️  Agent Capability Warning

KiloCode does not support PreToolUse hooks.
Behavior constraints (file protection, command restriction) will NOT be effective.

Available protections:
  ✅ Code quality checks (pre-commit)
  ✅ Quality gates (pre-push)
  ✅ Rules document guidance (.kilocode/rules/)

Unavailable protections:
  ❌ Real-time behavior interception (PreToolUse)
  ❌ Command restriction enforcement
  ❌ File protection enforcement

Recommendation:
  Consider using Claude Code, Cursor, or OpenCode for full protection.
  Or use KiloCode in combination with a supported Agent.
```

---

## 8. 输出层设计

### 8.1 Content → Renderer → Channel 模式

**设计理念**：分离关注点，实现可扩展性。

| 组件 | 职责 | 扩展性 |
|-----|------|--------|
| **Content** | 数据结构，包含要输出的信息 | 添加新的 Content 类型 |
| **Renderer** | 格式转换，将 Content 转为特定格式 | 添加新的 Renderer |
| **Channel** | 输出分发，将渲染结果发送到目标 | 添加新的 Channel |

**流程示意**：

```
Content (CheckReport)
    ├─ violations: list[Violation]
    ├─ summary: str
    └─ timestamp: datetime
          ↓
Renderer (MarkdownRenderer)
    ├─ render_violations()
    ├─ render_summary()
    └─ 输出 Markdown 字符串
          ↓
Channel (GitHubChannel)
    ├─ post_as_pr_comment()
    └─ 发送到 GitHub PR
```

### 8.2 渲染器扩展机制

**内置渲染器**：

| 渲染器 | 输出格式 | 用途 |
|-------|---------|------|
| MarkdownRenderer | Markdown | 规则文档、PR 评论 |
| JsonRenderer | JSON | API 输出、程序消费 |
| HtmlRenderer | HTML | Web 报告、可视化 |
| ConsoleRenderer | ANSI 终端 | 终端显示 |

**添加自定义渲染器**：

```python
# my_renderer.py
from ai_guard.output import Renderer, Content

class SlackMarkdownRenderer(Renderer):
    """为 Slack 格式优化的 Markdown 渲染器"""
    
    def render(self, content: Content) -> str:
        if isinstance(content, CheckReport):
            return self._render_report(content)
        elif isinstance(content, WarningMessage):
            return self._render_warning(content)
    
    def _render_report(self, report: CheckReport) -> str:
        # Slack 特定格式：使用 :emoji: 而非 unicode
        lines = []
        for v in report.violations:
            lines.append(f":x: `{v.file}:{v.line}` - {v.message}")
        return "\n".join(lines)

# 注册渲染器
ai_guard.output.register_renderer("slack-md", SlackMarkdownRenderer)
```

**使用自定义渲染器**：

```yaml
# guard.yaml
output:
  doc_format: "slack-md"
  channels:
    - "slack"
```

### 8.3 输出通道扩展机制

**内置通道**：

| 通道 | 输出目标 | 配置 |
|-----|---------|------|
| ConsoleChannel | 终端 stdout | 无需配置 |
| FileChannel | 文件系统 | path 参数 |
| GitHubChannel | GitHub PR 评论 | token, repo 参数 |
| WebhookChannel | HTTP POST | url, headers 参数 |

**添加自定义通道**：

```python
# my_channel.py
from ai_guard.output import Channel, OutputConfig

class SlackChannel(Channel):
    """发送到 Slack 的输出通道"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def output(self, rendered: str, config: OutputConfig):
        import requests
        payload = {
            "text": rendered,
            "username": "AI Guard",
            "icon_emoji": ":robot_face:"
        }
        requests.post(self.webhook_url, json=payload)

# 注册通道
ai_guard.output.register_channel("slack", SlackChannel)
```

**配置使用**：

```yaml
# guard.yaml
output:
  channels:
    - type: "slack"
      webhook_url: "${SLACK_WEBHOOK_URL}"
```

---

## 9. 关键技术决策

### 9.1 Hook 选择决策

**问题**：为什么选择 PreToolUse + pre-commit + pre-push？

**分析**：

| Hook 类型 | 执行时机 | 可覆盖的检查 | Agent 依赖性 |
|----------|---------|-------------|-------------|
| **PreToolUse** | AI 工具调用前 | 行为约束 | Agent 必须支持 |
| **PostToolUse** | AI 工具调用后 | 结果验证、报告生成 | Agent 必须支持 |
| **pre-commit** | git commit 前 | 代码静态检查 | Git 原生，无依赖 |
| **pre-push** | git push 前 | 质量门禁 | Git 原生，无依赖 |

**决策理由**：

1. **行为约束必须用 PreToolUse**：
   - 行为约束检查的是"AI 要做什么"，必须在执行前拦截
   - pre-commit 只能检查已产生的代码，无法阻止违规操作

2. **代码看护必须用 pre-commit/pre-push**：
   - 代码质量检查需要完整的文件内容，PostToolUse 时机不对
   - pre-commit 是 Git 标准机制，所有 Agent 通用

3. **PostToolUse 默认关闭**：
   - PostToolUse 的主要用途是报告生成，属于可选功能
   - 开启会增加延迟，影响 AI 响应速度
   - 仅在需要实时报告时开启

**最终选择**：PreToolUse（行为）+ pre-commit（静态检查）+ pre-push（门禁）

### 9.2 Update 命令托管块设计

**问题**：为什么用托管块而非全文件覆盖？

**场景分析**：

```
用户在 CLAUDE.md 中添加了项目特定说明：

CLAUDE.md
├─ [托管块: behavior] ← AI Guard 生成
├─ [托管块: code]     ← AI Guard 生成
├─ 项目特定说明        ← 用户添加
│   "本项目使用自定义内存管理..."
│   "测试框架是 GTest..."
├─ 团队约定            ← 用户添加
│   "提交前必须运行 lint..."

如果 update 命令全文件覆盖：
    ├─ 用户添加的内容丢失
    └─ 每次更新都需要手动恢复
```

**托管块方案**：

```
CLAUDE.md
├─ <!-- AI-GUARD:BEGIN:behavior -->
│   ... 自动生成内容，update 时替换 ...
│   <!-- AI-GUARD:END:behavior -->
├─ <!-- AI-GUARD:BEGIN:code -->
│   ... 自动生成内容，update 时替换 ...
│   <!-- AI-GUARD:END:code -->
├─ [托管块外内容]
│   ... 用户添加内容，update 时保留 ...
```

**决策理由**：

1. **保留用户自定义内容**：用户可以添加项目特定说明，不会被覆盖
2. **自动化更新仍有效**：托管块内容根据 guard.yaml 自动更新
3. **明确的边界**：托管块标记清晰界定哪些是自动生成内容

### 9.3 PostToolUse 可选性决策

**问题**：为什么 PostToolUse 默认关闭？

**PostToolUse 的潜在用途**：

| 用途 | 价值 | 缺点 |
|-----|------|------|
| **实时报告生成** | 每次 AI 操作后生成报告 | 增加延迟，干扰 AI 流程 |
| **结果验证** | 验证 AI 生成内容是否合规 | 可由 pre-commit 覆盖 |
| **自动 PR 评论** | 推送后自动生成 PR 报告 | 可由 CI 覆盖 |

**决策理由**：

1. **延迟影响**：PostToolUse 在每次工具调用后执行，增加 AI 响应延迟
2. **功能重叠**：大部分验证功能可由 pre-commit 覆盖
3. **用户选择**：仅在需要实时报告时开启，作为可选功能

**配置方式**：

```yaml
# guard.yaml
output:
  post_tool_use:
    enabled: false  # 默认关闭
    command: "python3 .claude/hooks/auto_pr_report.py"
```

### 9.4 配置 Agent 无关性决策

**问题**：为什么配置中不体现 Agent 类型信息？

**场景对比**：

```
方案 A：配置包含 Agent 信息

guard.yaml
├─ agents:
│   ├─ claude-code:
│   │   rules: {...}
│   ├─ cursor:
│   │   rules: {...}
│   └─ kilocode:
│       rules: {...}

问题：
    ├─ 配置复杂度高
    ├─ 同一规则需要在多个 Agent 配置中重复
    ├─ 迁移到新 Agent 需要新增配置
    └─ 维护困难
```

```
方案 B：配置 Agent 无关（最终方案）

guard.yaml
├─ project: {...}
├─ behavior: {...}
├─ code: {...}
├─ gates: {...}
├─ output: {...}

优势：
    ├─ 配置简洁，规则统一
    ├─ 同一规则适用于所有 Agent
    ├─ 新增 Agent 无需修改配置
    ├─ CLI 参数指定 Agent 类型
```

**决策理由**：

1. **统一规则**：同一项目对所有 Agent 应有相同的约束
2. **易于迁移**：一份配置可用于多个 Agent
3. **降低复杂度**：配置文件简洁，易于维护
4. **CLI 承担差异**：Agent 差异由 CLI + Adapter 层处理

### 9.5 外部工具集成决策

**问题**：为什么不自己实现检查脚本，而是集成外部成熟工具？

**分析**：

| 检查维度 | 成熟工具 | 成熟度 | AI Guard 价值 |
|---------|---------|-------|--------------|
| **Naming（命名）** | clang-tidy (C/C++), pylint (Python), ESLint (JS/TS) | 极高 | 配置统一，命名规则整合 |
| **Documentation（文档）** | doxygen (C/C++), pydocstyle (Python), TSDoc (TS) | 极高 | 文档风格统一配置 |
| **Structure（结构）** | import-linter (Python), dependency-cruiser (JS/TS) | 高 | 依赖层级规则配置化 |
| **Style（风格）** | clang-format (C/C++), black (Python), prettier (JS/TS) | 极高 | 格式规则统一，避免争论 |
| **Lint（静态分析）** | clang-tidy, pylint, ESLint | 极高 | 规则集管理，阈值配置 |
| **Security（安全）** | bandit (Python), ESLint security rules | 高 | 安全规则集整合 |
| **Complexity（复杂度）** | lizard (多语言), radon (Python) | 高 | 复杂度阈值配置 |

**为什么不自己实现**：

1. **工具成熟度高**：上述工具经过多年打磨，功能完整、稳定、广泛使用
2. **维护成本为零**：无需投入精力维护检查逻辑，仅需维护配置
3. **社区支持**：工具持续更新，新语言特性、新规则自动获得
4. **无需 AST 解析**：复杂检查（类型推断、数据流分析）工具已实现
5. **无需证明正确性**：工具被广泛验证，AI Guard 无需重新验证

**AI Guard 的独特价值**：

| 价值点 | 说明 |
|-------|------|
| **配置统一** | 多工具配置集中到 guard.yaml，一处配置多处生效 |
| **工具编排** | 自动生成 .pre-commit-config.yaml，编排工具执行顺序 |
| **语言适配** | 根据语言自动选择合适工具和配置模板 |
| **Agent 特性** | 生成 Agent 专用规则文档（CLAUDE.md 等），引导 AI |
| **安装简化** | 一条命令完成工具检测、安装、配置生成、Hook 安装 |

**工具集成架构**：

```
guard.yaml（统一配置源）
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  AI Guard Core                                                  │
│  ├─ Config Parser: 解析 guard.yaml                              │
│  ├─ Tool Mapper: 映射配置到外部工具参数                           │
│  ├─ Config Generator: 生成各工具配置文件                          │
│  │   ├─ .clang-format        ← C/C++ 格式配置                    │
│  │   ├─ .eslintrc            ← JS/TS 检查配置                    │
│  │   ├─ pyproject.toml       ← Python black/isort 配置           │
│  │   └─ .pre-commit-config.yaml ← Hook 编排配置                  │
│  └─ Doc Generator: 生成规则文档 (CLAUDE.md)                       │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  pre-commit Framework                                           │
│  ├─ Hook 管理                                                   │
│  ├─ 并行执行                                                    │
│  ├─ 缓存机制                                                    │
│  ├─ CI 集成                                                     │
│  └───────────────────────────────────────────────────────────── │
│  外部工具执行                                                    │
│  ├─ clang-format    (C/C++ 格式化)                               │
│  ├─ clang-tidy      (C/C++ 静态分析)                             │
│  ├─ black           (Python 格式化)                              │
│  ├─ pylint          (Python 静态分析)                            │
│  ├─ prettier        (JS/TS/JSON/YAML 格式化)                     │
│  ├─ ESLint          (JS/TS 静态分析)                             │
│  └─ ...                                                          │
└─────────────────────────────────────────────────────────────────┘
    ↓
检查结果（通过/失败 + 详细报告）
```

**结论**：AI Guard 专注于"配置统一 + 工具编排 + Agent 特性"，复用成熟工具完成实际检查。

### 9.6 工具安装策略决策

**问题**：如何处理工具未安装的情况？

**分析**：

| 策略 | 优点 | 缺点 |
|-----|------|------|
| **硬性要求** | 确保所有检查可用 | 阻塞安装流程，用户体验差 |
| **自动安装** | 用户无需手动操作 | 可能覆盖用户现有配置，意外行为 |
| **仅警告** | 不阻塞流程 | 用户可能忽略，检查缺失 |
| **组合策略** | 平衡灵活性和完整性 | 实现复杂度稍高 |

**最终决策：组合策略**

```
guard install 流程
    ↓
检测所需工具
    ├─ 已安装 → 跳过
    ├─ 未安装 → 提示用户
    │   ├─ 用户选择"自动安装" → 执行安装
    │   ├─ 用户选择"稍后安装" → 记录缺失，继续
    │   └─ 用户选择"跳过" → 标记为禁用，继续
    └───────────────────────────────────────────
    ↓
生成配置文件
    ├─ 已安装工具 → 生成对应配置
    ├─ 未安装工具 → 生成配置但标记为待安装
    └─ 跳过工具 → 不生成配置
    ↓
安装 pre-commit hooks
    ├─ 仅安装已可用工具的 Hook
    └─ 缺失工具的 Hook 暂不生效
    ↓
输出安装摘要
    ├─ 已安装：工具列表
    ├─ 待安装：工具列表 + 安装命令
    └─ 已跳过：工具列表 + 影响说明
```

**安装提示格式**：

```
检测到以下工具未安装：
  ├─ clang-format (C/C++ 格式化)
  │   安装命令：brew install clang-format
  │   影响：C/C++ 代码格式检查不可用
  ├─ black (Python 格式化)
  │   安装命令：pip install black
  │   影响：Python 代码格式检查不可用

请选择处理方式：
  1. 自动安装所有（推荐）
  2. 稍后手动安装
  3. 查看详情并逐个选择

输入选择 [1/2/3]: _
```

**缺失工具时的检查行为**：

```python
# 检查执行时发现工具缺失
def run_check(tool_name, config):
    if not is_tool_installed(tool_name):
        if config.get('missing_tools_warn'):
            # 警告但继续（不阻塞提交）
            print(f"[WARNING] {tool_name} 未安装，跳过此检查")
            return CheckResult(status='skipped', reason='tool_missing')
        else:
            # 配置为必须时，阻塞提交
            return CheckResult(status='blocked', reason='tool_missing')
    # 正常执行
    return run_tool_check(tool_name, config)
```

**默认配置**：

```yaml
# guard.yaml
tools:
  missing_behavior: 'warn'  # 默认：警告但继续
  # 可选值：
  #   'warn'    - 警告但不阻塞
  #   'block'   - 阻塞直到安装
  #   'skip'    - 无提示跳过
```

**结论**：组合策略确保灵活性（不阻塞安装）同时提供清晰的缺失提示和安装指导。

### 9.7 规则集架构决策

**问题**：如何让公司/项目统一维护规范，避免每项目重复配置？

**分析**：

| 方案 | 优点 | 缺点 |
|-----|------|------|
| **每项目独立配置** | 灵活 | 重复劳动，难以统一 |
| **内置模板** | 开箱即用 | 无法满足所有需求 |
| **外部规则集** | 统一维护，版本控制 | 需要额外学习 |

**最终决策：外部规则集**

**规则集职责划分**：

| 内容 | 规则集负责 | 用户配置负责 |
|-----|----------|------------|
| 工具配置 | ✅ `.clang-format`, `.clang-tidy` | ❌ |
| 自定义检查脚本 | ✅ `custom_checks/*.py` | ❌ |
| 验证项定义 | ✅ `validation/config.yaml` | ❌ |
| 适配脚本 | ✅ `adapters/*.py` | ❌ |
| 项目特定命令 | ❌ | ✅ `./build.sh test` |
| 验证项启用/禁用 | ❌ | ✅ `asan.enabled: true` |
| 行为约束覆盖 | 部分 | ✅ 项目特定覆盖 |

**用户配置简化**：

```yaml
# 用户只需配置约 15 行
project:
  name: "GsPDMemo"
  language: "c"

ruleset: "git@github.com:company/guard-rules.git#c"

build:
  command: "./build.sh"

validation:
  test:
    command: "./build.sh test"
  coverage:
    threshold: 80
  asan:
    enabled: true
```

### 9.8 验证项注册机制决策

**问题**：不同语言/项目的动态验证内容不同，如何支持？

**分析**：

| 策略 | 说明 | 问题 |
|-----|------|------|
| **硬编码验证项** | AI Guard 内置 test/coverage/asan | 无法扩展 |
| **用户自定义脚本** | 用户任意编写 | 输出格式不统一 |
| **验证项注册 + 标准格式** | 规则集定义验证项，用户配置启用 | ✅ 最佳 |

**最终决策：验证项注册 + 标准格式**

**机制**：

1. **规则集定义验证项**：声明可用验证项、配置 schema、适配脚本
2. **用户注册验证项**：选择启用哪些验证项，提供命令
3. **适配脚本转换**：将工具输出转换为 AI Guard 标准格式
4. **AI Guard 生成报告**：基于标准格式生成统一报告

**标准格式的好处**：

| 好处 | 说明 |
|-----|------|
| **统一报告** | 所有验证项输出格式一致 |
| **可扩展** | 用户可注册任意验证项 |
| **易于集成** | 上游工具变化只需修改适配脚本 |
| **AI 友好** | AI 可以理解标准格式的报告 |

### 9.9 工具边界决策

**问题**：clang-format 和 clang-tidy 的职责边界？

**澄清**：

| 工具 | 职责 | 是否需要编译 |
|-----|------|------------|
| **clang-format** | 格式化（缩进、空格、换行） | ❌ 不需要 |
| **clang-tidy（命名检查）** | 命名规范检查 | ❌ 不需要 |
| **clang-tidy（完整检查）** | 类型检查、数据流分析、Lint | ✅ 需要 |

**对三层划分的影响**：

| 层级 | 包含 | 执行时机 |
|-----|------|---------|
| **静态检查** | clang-format + clang-tidy（命名） + custom_checks | pre-commit |
| **语义分析** | clang-tidy（完整） | pre-push |
| **动态验证** | test, coverage, asan（注册机制） | pre-push |

### 9.10 custom_checks 定位决策

**问题**：custom_checks 应该做什么？

**定位**：补充工具不支持的检查，而非重复实现工具功能。

| 检查类型 | 工具支持 | 是否需要 custom_checks |
|---------|---------|---------------------|
| 格式化 | clang-format/black/prettier | ❌ |
| 命名规范 | clang-tidy `readability-identifier-naming` | ❌ |
| Lint | clang-tidy/pylint/ESLint | ❌ |
| 文件命名前缀 | 无工具支持 | ✅ 需要 |
| 模块依赖层级（C/C++） | 无成熟工具 | ✅ 需要 |
| Doxygen 注释检查 | 无工具支持 | ✅ 需要 |

---

## 10. 实施路线图

**为什么按这个顺序推进**：

```
Phase 1: CLI + 配置 + 生成器
    ↓ 提供基础框架，可生成规则文档
Phase 2: 拦截器 + PreToolUse
    ↓ 实现行为约束，AI 受控执行
Phase 3: 验证器 + pre-commit + 语言插件
    ↓ 实现代码看护，质量得到保障
Phase 4: 输出层 + update 命令
    ↓ 完善用户体验，系统闭环
```

**依赖关系**：

- Phase 2 依赖 Phase 1 的配置解析
- Phase 3 依赖 Phase 1 的配置解析，但可与 Phase 2 并行
- Phase 4 依赖 Phase 1 的 Generator

**最小可用版本**：Phase 1 完成后即可使用，但仅提供规则文档引导，无强制约束。

### 10.1 Phase 1：CLI 框架 + 配置解析 + Generator

**目标**：实现基础框架，能够生成规则文档。

**工作内容**：

| 任务 | 具体内容 | 依赖 |
|-----|---------|------|
| CLI 框架 | guard 命令入口、参数解析、命令路由 | 无 |
| 配置解析 | YAML 解析、验证、合并逻辑 | CLI 框架 |
| Generator | 规则文档生成逻辑 | 配置解析 |
| Claude Code Adapter | 生成 CLAUDE.md + settings.json | Generator |

**交付物**：

- `guard` CLI 可执行
- `guard init` 创建 guard.yaml
- `guard install --agent claude-code` 生成 CLAUDE.md

### 10.2 Phase 2：Interceptor + PreToolUse Hook

**目标**：实现行为约束的实时拦截。

**工作内容**：

| 任务 | 具体内容 | 依赖 |
|-----|---------|------|
| Interceptor 核心逻辑 | 文件保护检查、命令限制检查、路径访问检查 | 配置解析 |
| PreToolUse Hook 脚本 | enforce_check_system.py | Interceptor |
| Claude Code Hook 安装 | settings.json Hook 配置 | PreToolUse Hook |
| Cursor Adapter | .cursor/hooks.json | PreToolUse Hook |
| OpenCode Plugin | Plugin + interceptor.js | PreToolUse Hook |

**交付物**：

- PreToolUse Hook 可拦截违规操作
- Claude Code / Cursor / OpenCode 行为约束生效

### 10.3 Phase 3：Validator + pre-commit 集成 + 语言插件

**目标**：实现代码看护的静态检查和门禁验证。

**工作内容**：

| 任务 | 具体内容 | 依赖 |
|-----|---------|------|
| Validator 核心逻辑 | 命名检查、文档检查、结构检查 | 配置解析 |
| C 语言插件 | C 特定的命名/文档/结构规则 | Validator |
| Python 语言插件 | Python 特定规则 | Validator |
| TypeScript 语言插件 | TypeScript 特定规则 | Validator |
| pre-commit 集成 | Git Hook 脚本、检查脚本调用 | Validator |
| pre-push 集成 | 门禁验证脚本 | Validator |
| .pre-commit-config.yaml | pre-commit 框架配置 | pre-commit 集成 |

**交付物**：

- pre-commit 执行静态检查
- pre-push 执行质量门禁
- C/Python/TypeScript 语言插件可用

### 10.4 Phase 4：输出层 + update 命令托管块

**目标**：实现完整的输出系统和托管块更新机制。

**工作内容**：

| 任务 | 具体内容 | 依赖 |
|-----|---------|------|
| Content 类型定义 | CheckReport, WarningMessage, InstallSummary | 无 |
| MarkdownRenderer | Markdown 格式渲染 | Content |
| JsonRenderer | JSON 格式渲染 | Content |
| ConsoleChannel | 终端输出 | Renderer |
| FileChannel | 文件写入 | Renderer |
| GitHubChannel | PR 评论发布 | Renderer |
| update 命令 | 托管块识别、内容替换、用户内容保留 | Generator |
| Agent 能力警告 | 不支持 Hook 的 Agent 显示警告 | CLI |

**交付物**：

- `guard update` 更新规则文档，保留用户内容
- 输出层支持 Markdown/JSON，终端/文件/GitHub
- 不支持 Hook 的 Agent 显示警告

---

## 附录

### A. 文件结构总览

```
ai-guard/
├─ cli/
│   ├─ guard.py                  # CLI 入口
│   ├─ commands/
│   │   ├─ init.py
│   │   ├─ install.py
│   │   ├─ update.py
│   │   ├─ check.py
│   │   ├─ verify.py
│   │   ├─ agents.py
│   │   └─ status.py
│
├─ config/
│   ├─ parser.py                 # YAML 解析
│   ├─ validator.py              # 配置验证
│   ├─ merger.py                 # 配置合并
│   ├─ defaults/
│   │   ├─ c.yaml                # C 默认配置
│   │   ├─ python.yaml           # Python 默认配置
│   │   └─ typescript.yaml       # TypeScript 默认配置
│
├─ core/
│   ├─ generator.py              # 规则文档生成
│   ├─ interceptor.py            # 行为拦截
│   ├─ validator.py              # 代码验证
│
├─ plugins/
│   ├─ c.py                      # C 语言插件
│   ├─ python.py                 # Python 语言插件
│   ├─ typescript.py             # TypeScript 语言插件
│
├─ adapters/
│   ├─ base.py                   # Adapter 基类
│   ├─ claude_code.py            # Claude Code 适配
│   ├─ opencode.py               # OpenCode 适配
│   ├─ cursor.py                 # Cursor 适配
│   ├─ kilocode.py               # KiloCode 适配
│   ├─ copilot.py                # GitHub Copilot 适配
│
├─ output/
│   ├─ content/
│   │   ├─ base.py               # Content 基类
│   │   ├─ check_report.py       # 检查报告
│   │   ├─ warning_message.py    # 警告信息
│   │   ├─ install_summary.py    # 安装摘要
│   │   └─ agent_status.py       # Agent 状态
│   ├─ renderer/
│   │   ├─ base.py               # Renderer 基类
│   │   ├─ markdown.py
│   │   ├─ json.py
│   │   └─ html.py               # HTML 渲染器
│   ├─ channel/
│   │   ├─ base.py               # Channel 基类
│   │   ├─ console.py
│   │   ├─ file.py
│   │   ├─ github.py
│   │   └─ webhook.py            # Webhook 通道
│
├─ templates/
│   ├─ claude_md.md              # CLAUDE.md 模板
│   ├─ settings.json             # settings.json 模板
│   ├─ interceptor.py            # PreToolUse Hook 模板
│   ├─ reporter.py               # PostToolUse Hook 模板
│   ├─ pre_commit.sh             # pre-commit Hook 模板
│   ├─ pre_push.sh               # pre-push Hook 模板
│   └─ cursor_hooks.json         # Cursor hooks.json 模板
│
└─ guard.yaml                    # 示例配置
```

### B. Agent 适配文件映射表

| Agent | 规则文档 | Hook 配置 | Hook 脚本 | Git Hooks |
|-------|---------|----------|----------|----------|
| Claude Code | CLAUDE.md | .claude/settings.json | .claude/hooks/*.py | .git/hooks/* |
| OpenCode | .opencode/rules/*.md | .opencode/plugins/ai-guard/plugin.json | .opencode/plugins/ai-guard/*.js | .git/hooks/* |
| Cursor | .cursor/rules/*.mdc | .cursor/hooks.json | scripts/hooks/*.py | .git/hooks/* |
| KiloCode | .kilocode/rules/*.md | 无 | 无 | .git/hooks/* |
| GitHub Copilot | .github/copilot-instructions.md | 无 | 无 | .git/hooks/* |

### C. 违规类型与错误信息模板

| 违规类型 | 错误代码 | 错误信息模板 |
|---------|---------|-------------|
| 文件禁止修改 | `file_protection_forbidden` | `禁止修改 {path}，该路径在 forbidden 清单中` |
| 文件需审批 | `file_protection_approval` | `修改 {path} 需要确认：{message}` |
| 命令禁止执行 | `command_forbidden` | `禁止执行 "{command}"：{message}` |
| 命令不在白名单 | `command_not_allowed` | `命令 "{command}" 不在自动允许清单中，需检查` |
| 命名违规 | `naming_violation` | `{file}:{line}: 命名 "{name}" 不符合 {rule} 规范` |
| 文档缺失 | `documentation_missing` | `{file}:{line}: 函数 "{name}" 缺少文档注释` |
| 依赖违规 | `dependency_violation` | `{file}: 模块 {module} 禁止依赖 {dep_module}` |
| 文件前缀违规 | `file_prefix_violation` | `{file}: 文件名前缀应为 {expected_prefix}` |
| 覆盖率不足 | `coverage_threshold` | `覆盖率 {actual}% 低于阈值 {threshold}%` |
| 测试失败 | `test_failure` | `测试失败：{test_name} - {error_message}` |

---

**文档状态**：✅ 设计完成  
**下一步**：按照实施路线图 Phase 1 开始开发