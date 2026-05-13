# 文档系统 P0 第二轮收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收口 `docs/knowledge/*` 与 `docs/superpowers/*` 的文档边界，修正文档入口断链，并把 `roadmap` 中的 P0 写成可验收目标。

**Architecture:** 本次实现只改正式文档，不改运行代码和契约行为。规则统一以 `docs/process/development-workflow.md` 为主入口，`docs/glossary.md` 负责压缩定义，`docs/knowledge/README.md` 负责参考层准入说明，`README.md` 只做入口级修正，`docs/blueprint/roadmap.md` 收紧 P0 表达，并在最后检查是否需要同步 `current.md`。

**Tech Stack:** Markdown, ripgrep, git diff, 文档结构回归检查

---

### Task 1: 修正文档流程主规则

**Files:**
- Modify: `docs/process/development-workflow.md:44-63`
- Modify: `docs/process/development-workflow.md:145-162`
- Modify: `docs/process/development-workflow.md:260-279`

- [ ] **Step 1: 写出会失败的结构检查**

Run:

```bash
rg -n "docs/doc-system|docs/knowledge/\\*|常驻参考层|进行中工作区" docs/process/development-workflow.md
```

Expected:

```text
- 能看到 `docs/doc-system.md` 的旧引用
- 看不到 `常驻参考层`
- 看不到 `进行中工作区`
```

- [ ] **Step 2: 修改标准阅读顺序，移除不存在入口**

Apply this edit in `docs/process/development-workflow.md`:

```md
真正开始开发前，建议至少按下面顺序扫一遍：

1. `README.md`
2. `docs/blueprint/current.md`
3. `docs/blueprint/roadmap.md`
4. 相关 `docs/superpowers/specs/*.md`
5. 相关 `docs/contracts/*.md`
6. 相关 `docs/process/*.md`
7. 必要时看 `docs/knowledge/*.md`

这个顺序的意义是：

- 先确认项目入口和规则
- 再确认当前真相
- 再确认这件事是不是当前优先项
- 再确认有没有现成设计
- 最后才进入契约、流程和实现
```

- [ ] **Step 3: 在文档对象分工中补入 `knowledge` 边界**

Apply this edit in `docs/process/development-workflow.md` under `## 3. 文档对象如何分工`:

```md
- `knowledge`
  解决“为什么这样做、有哪些经验和背景可参考”，但不承担当前状态、正式契约或正式流程真相

默认原则：

- `spec` 与 `plan` 是设计与实施过程文档
- `knowledge` 是常驻参考层，不是正式真相层
- `current / contracts / process` 才是长期真相回流层
- 长期有效的信息最终仍应回流到 `blueprint / contracts / process`
```

- [ ] **Step 4: 收紧 `spec / plan` 生命周期规则**

Replace the `### 6.4 什么时候更新 spec / plan` bullet list with:

```md
对 `docs/superpowers/specs/*.md` 与 `docs/superpowers/plans/*.md`，默认这样处理：

- 如果它们仍承担当前任务的设计或执行真相，就继续更新
- `docs/superpowers/*` 的默认定位是进行中工作区，不是长期沉淀库
- 如果其中有效内容已经沉淀为长期规则，就回流到 `blueprint / contracts / process`
- `plan` 如果只服务一次实现，应在任务完成且正式文档回流后删除
- `spec` 如果只服务一次设计展开，应在回流完成后删除；只有跨阶段仍在推进、短期仍需反复参考时才保留
- 不要强行把 `spec / plan` 升格为长期主入口
```

- [ ] **Step 5: 补 `knowledge` 的回流规则**

Insert this subsection after `### 6.4 什么时候更新 spec / plan`:

```md
### 6.5 什么时候更新 `docs/knowledge/*`

对 `docs/knowledge/*`，默认这样处理：

- 它们用于保留选型背景、环境经验、联调 Q&A、转换说明和对比资料
- 它们可以长期保留，但不承担当前状态、正式契约、正式流程或未来优先级真相
- 如果某条知识已经变成必须遵守的正式约束，应回流到 `current / contracts / process`
- 如果某篇知识文档已经明显过时且没有参考价值，应删除或改写，而不是继续悬挂
```

- [ ] **Step 6: 调整后续节号并保留 README 更新规则**

Make the section that currently starts with `### 6.5 什么时候更新 README.md` become:

```md
### 6.6 什么时候更新 `README.md`

只有下面这些内容发生变化时，才需要同步更新 `README.md`：

- 项目总入口
- 最小启动方式
- 文档阅读顺序
- 关键边界说明
```

- [ ] **Step 7: 运行结构检查确认修正生效**

Run:

```bash
rg -n 'docs/doc-system|常驻参考层|进行中工作区|什么时候更新 `docs/knowledge/\*`' docs/process/development-workflow.md
```

Expected:

```text
- 不再出现 `docs/doc-system`
- 能看到 `常驻参考层`
- 能看到 `进行中工作区`
- 能看到 `什么时候更新 docs/knowledge/*`
```

- [ ] **Step 8: Commit**

```bash
git add docs/process/development-workflow.md
git commit -m "docs: 收紧开发流程文档边界"
```

### Task 2: 收紧术语层定义

**Files:**
- Modify: `docs/glossary.md:6-33`

- [ ] **Step 1: 写出会失败的术语检查**

Run:

```bash
rg -n '^- `knowledge`|不是长期真相源|进行中工作区' docs/glossary.md
```

Expected:

```text
- 看不到 `knowledge`
- 看不到 `不是长期真相源`
- 看不到 `进行中工作区`
```

- [ ] **Step 2: 新增 `knowledge` 术语并收紧 `spec / plan`**

Replace the `## 1. 文档角色` block in `docs/glossary.md` with:

```md
## 1. 文档角色

- `README`
  项目的唯一总入口，回答“这是什么、现在怎么用、先看哪里、怎么启动”。

- `current`
  当前真实状态文档，回答“系统现在是什么”。

- `history`
  阶段演进摘要文档，回答“它怎么演进成现在这样”。

- `roadmap`
  未来规划文档，回答“下一步做什么”。

- `spec`
  设计展开文档，位于 `docs/superpowers/specs/*.md`，回答“准备怎么设计、为什么这样设计、边界如何定义”；默认只服务进行中的设计，不是长期真相源。

- `plan`
  执行计划文档，位于 `docs/superpowers/plans/*.md`，回答“接下来按什么顺序做、检查点是什么”；默认只服务进行中的实施，不是长期真相源。

- `knowledge`
  参考知识文档，位于 `docs/knowledge/*.md`，回答“为什么这样做、有哪些经验和背景可参考”；可以长期保留，但不承担当前状态、正式契约或正式流程真相。

- `contract`
  契约文档，定义正式产物或结构化对象应长什么样。

- `process`
  流程文档，定义如何运行、如何开发、如何部署。

- `legacy`
  仍保留但已经降级的旧内容，只作参考，不再充当主入口。
```

- [ ] **Step 3: 运行术语检查确认更新**

Run:

```bash
rg -n '^- `knowledge`|不是长期真相源|docs/knowledge/\*|进行中的设计|进行中的实施' docs/glossary.md
```

Expected:

```text
- 能看到 `knowledge`
- 能看到 `不是长期真相源`
- 能看到 `docs/knowledge/*`
- 能看到 `进行中的设计`
- 能看到 `进行中的实施`
```

- [ ] **Step 4: Commit**

```bash
git add docs/glossary.md
git commit -m "docs: 收紧术语表中的文档角色定义"
```

### Task 3: 强化知识库入口说明

**Files:**
- Modify: `docs/knowledge/README.md:3-27`

- [ ] **Step 1: 写出会失败的知识库入口检查**

Run:

```bash
rg -n "常驻参考层|不应承载|未来优先级|正式流程|正式契约" docs/knowledge/README.md
```

Expected:

```text
- 看不到 `常驻参考层`
- 看不到 `不应承载`
- 看不到 `未来优先级`
- 看不到 `正式流程`
- 看不到 `正式契约`
```

- [ ] **Step 2: 重写定位说明和使用规则**

Replace the introduction and usage section in `docs/knowledge/README.md` with:

```md
# 知识库索引

本目录存放与 `llmnode` 项目相关的技术选型知识、工程经验和环境说明。

这些文档不是正式契约，也不是当前运行状态说明。  
它们的定位是：**帮助理解“为什么这样做”和“有哪些经验可参考”的常驻参考层**。

---

## 文档列表

| 文件 | 内容摘要 |
|------|----------|
| [api_protocol_reference.md](api_protocol_reference.md) | 三种对外接口协议（/v1/chat/completions、/v1/responses、/v1/messages）的规范对比、字段映射与转换策略 |
| [llm_development.md](llm_development.md) | Dense 与 MoE 模型资源特点、单卡边界与后端框架选型建议 |
| [docker_deployment.md](docker_deployment.md) | 三后端（vLLM / llama.cpp / SGLang）Docker 部署方案与环境约束说明 |
| [model_format_conversion.md](model_format_conversion.md) | safetensors → GGUF 转换流程与量化参数速查 |
| [quantization_comparison.md](quantization_comparison.md) | Q4_K_M vs FP8 量化对比、硬件适配与决策树 |
| [backend_integration_qa.md](backend_integration_qa.md) | 三后端联调验证 Q&A：已知问题、解决方案与验证结果汇总 |

---

## 使用说明

- 这类文档可以长期保留，但默认只承担参考作用，不承担正式真相。
- 本目录适合保留：技术选型背景、环境经验、联调 Q&A、格式转换说明、方案对比资料。
- 本目录不应承载：当前正式状态、正式控制命令语义、正式流程、正式契约字段定义、未来优先级判断。
- 信息以记录为主，不一定实时更新。具体版本号和镜像 tag 以实际验证为准。
- 如果某个知识点已被提升为正式约束，应回流到 `docs/blueprint/current.md`、`docs/contracts/` 或 `docs/process/`。
- 与当前运行状态相关的信息，请以 `docs/blueprint/current.md` 为准。
```

- [ ] **Step 3: 运行入口检查确认边界写入**

Run:

```bash
rg -n "常驻参考层|不应承载|正式流程|正式契约字段定义|未来优先级判断|docs/blueprint/current.md" docs/knowledge/README.md
```

Expected:

```text
- 能看到 `常驻参考层`
- 能看到 `不应承载`
- 能看到 `正式流程`
- 能看到 `正式契约字段定义`
- 能看到 `未来优先级判断`
- 能看到回流到 `docs/blueprint/current.md`
```

- [ ] **Step 4: Commit**

```bash
git add docs/knowledge/README.md
git commit -m "docs: 强化知识库参考层边界"
```

### Task 4: 清理 README 断链并收紧入口说明

**Files:**
- Modify: `README.md:44-53`
- Modify: `README.md:71-80`

- [ ] **Step 1: 写出会失败的 README 检查**

Run:

```bash
rg -n "docs/doc-system|inference_framework_selection" README.md
```

Expected:

```text
- 能看到 `docs/doc-system.md`
- 能看到 `docs/knowledge/inference_framework_selection.md`
```

- [ ] **Step 2: 收紧当前边界说明**

Replace the `## 当前边界` list tail with:

```md
- 当前正式默认后端：`vLLM`
- 默认模型目录：`models/Qwen/Qwen3.6-35B-A3B`
- 当前正式控制入口不再依赖 `scripts/*.sh`
- `docs/blueprint/roadmap.md` 是唯一未来规划入口
- `docs/knowledge/*` 是常驻参考层，不承担正式真相
- `docs/superpowers/*` 负责设计展开与实施计划，默认只服务进行中的工作，不再保留 `docs/blueprintV3.md` / `docs/blueprintV4.md`
```

- [ ] **Step 3: 修正细节索引中的失效链接**

Replace the `## 细节索引` tail with:

```md
- 控制命令、状态输出、`doctor / logs` 语义：
  [docs/contracts/control-plane.md](/proj02/liuheshan/llmnode/docs/contracts/control-plane.md:1)
- 模型路由与 `backend_type` 语义：
  [docs/contracts/backend-routing.md](/proj02/liuheshan/llmnode/docs/contracts/backend-routing.md:1)
- 三后端联调经验与已知问题：
  [docs/knowledge/backend_integration_qa.md](/proj02/liuheshan/llmnode/docs/knowledge/backend_integration_qa.md:1)
- 文档系统开发与回流规则：
  [docs/process/development-workflow.md](/proj02/liuheshan/llmnode/docs/process/development-workflow.md:1)
```

- [ ] **Step 4: 运行 README 检查确认断链已去掉**

Run:

```bash
rg -n "docs/doc-system|inference_framework_selection|常驻参考层|进行中的工作" README.md
```

Expected:

```text
- 不再出现 `docs/doc-system`
- 不再出现 `inference_framework_selection`
- 能看到 `常驻参考层`
- 能看到 `进行中的工作`
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: 修正README文档入口说明"
```

### Task 5: 收紧 roadmap 的 P0 表达并检查 current 是否需要回流

**Files:**
- Modify: `docs/blueprint/roadmap.md:73-85`
- Inspect: `docs/blueprint/current.md:249-253`

- [ ] **Step 1: 写出会失败的 roadmap 检查**

Run:

```bash
rg -n '决定 `docs/knowledge/\*` 的长期定位|规范 `docs/superpowers/\*` 的保留与删除策略|入口断链' docs/blueprint/roadmap.md
```

Expected:

```text
- 能看到 `决定 docs/knowledge/* 的长期定位`
- 能看到 `规范 docs/superpowers/* 的保留与删除策略`
- 看不到 `入口断链`
```

- [ ] **Step 2: 重写 P0 为可验收目标**

Replace the `## 3. P0：文档系统第二轮收口` section body with:

```md
## 3. P0：文档系统第二轮收口

重点：

- 维持“不再保留 `docs/blueprintV3.md` / `docs/blueprintV4.md`”这一入口约束
- 把 `docs/knowledge/*` 固定为常驻参考层，不再与正式真相层混写
- 把 `docs/superpowers/*` 固定为进行中工作区，明确 `spec / plan` 的回流与删除时机
- 清理当前主要文档入口中的断链与职责漂移

完成标志：

- `README.md`、`docs/process/development-workflow.md`、`docs/glossary.md` 对目录边界的表述一致
- `docs/knowledge/README.md` 已明确准入边界和回流规则
- `README.md` 不再引用失效文档入口
- `spec / plan` 默认不是长期真相源这一规则在正式流程层可见

为什么优先：

- 控制面诊断能力已增强完成，当前瓶颈转移到文档治理
- 当前文档系统虽然已分层，但厚度和职责边界还可继续提升
- 如果不继续收口，后续信息会重新散回旧文件
```

- [ ] **Step 3: 检查 `current.md` 是否仍然成立**

Run:

```bash
sed -n '249,253p' docs/blueprint/current.md
```

Expected:

```text
- 仍然保留“文档系统第二轮收口（docs/knowledge/*、docs/superpowers/* 的定位与清理）”
- 如果这里只是方向性描述且未与新边界冲突，本任务不修改 `current.md`
```

- [ ] **Step 4: 运行 roadmap 检查确认完成标志已写入**

Run:

```bash
rg -n "常驻参考层|进行中工作区|完成标志|不再引用失效文档入口|不是长期真相源" docs/blueprint/roadmap.md
```

Expected:

```text
- 能看到 `常驻参考层`
- 能看到 `进行中工作区`
- 能看到 `完成标志`
- 能看到 `不再引用失效文档入口`
- 能看到 `不是长期真相源`
```

- [ ] **Step 5: Commit**

```bash
git add docs/blueprint/roadmap.md
git commit -m "docs: 收紧roadmap中的文档系统P0"
```

### Task 6: 做最终结构回归并决定是否补 history

**Files:**
- Inspect: `README.md`
- Inspect: `docs/process/development-workflow.md`
- Inspect: `docs/glossary.md`
- Inspect: `docs/knowledge/README.md`
- Inspect: `docs/blueprint/roadmap.md`
- Inspect: `docs/blueprint/current.md`
- Optional Modify: `docs/blueprint/history.md`

- [ ] **Step 1: 运行全文档结构回归检查**

Run:

```bash
rg -n "docs/doc-system|inference_framework_selection" README.md docs/process/development-workflow.md docs/blueprint/roadmap.md
```

Expected:

```text
- 没有任何输出
```

- [ ] **Step 2: 运行边界一致性检查**

Run:

```bash
rg -n "常驻参考层|进行中工作区|不是长期真相源|不承担正式真相" README.md docs/process/development-workflow.md docs/glossary.md docs/knowledge/README.md docs/blueprint/roadmap.md
```

Expected:

```text
- 五个文件都能看到与各自职责对应的边界描述
- `README.md` 只保留入口级说明
- `development-workflow.md` 承担主规则
- `glossary.md` 承担压缩定义
- `docs/knowledge/README.md` 承担参考层准入说明
- `roadmap.md` 承担 P0 完成标志
```

- [ ] **Step 3: 运行 Markdown 级别的基础检查**

Run:

```bash
git diff --check
```

Expected:

```text
- 没有 trailing whitespace
- 没有 malformed patch 提示
```

- [ ] **Step 4: 判断是否需要更新 `history.md`**

Use this decision rule:

```text
如果这次改动只是收紧文档边界、清理断链、补齐规则，而没有改变系统阶段判断，则不更新 `docs/blueprint/history.md`。
只有当改动足以改变“项目当前成熟度或阶段认知”时，才补 history。
```

- [ ] **Step 5: Commit**

```bash
git add README.md docs/process/development-workflow.md docs/glossary.md docs/knowledge/README.md docs/blueprint/roadmap.md
git commit -m "docs: 完成文档系统P0第二轮收口"
```
