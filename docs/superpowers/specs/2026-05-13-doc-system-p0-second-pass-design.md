# 文档系统 P0 第二轮收口设计

## 1. 背景

当前文档系统已经完成第一轮分层：

- `README.md` 作为项目总入口
- `docs/blueprint/current.md` 作为当前真相入口
- `docs/blueprint/history.md` 作为阶段演进入口
- `docs/blueprint/roadmap.md` 作为未来规划入口
- `docs/contracts/*.md` 作为正式契约层
- `docs/process/*.md` 作为正式流程层

但 `docs/knowledge/*` 与 `docs/superpowers/*` 仍处于“保留了目录、边界还不够硬”的状态，导致第二轮收口仍有几个问题：

1. `docs/knowledge/*` 已被描述为参考资料，但缺少更明确的准入边界。
2. `docs/superpowers/*` 已被描述为设计与计划层，但其“完成后是否保留”的规则没有在所有关键入口统一。
3. 仓库入口仍存在断链，例如 `README.md` 和开发流程里引用了不存在的 `docs/doc-system.md`。
4. `roadmap` 中的 P0 仍偏方向描述，尚未收敛为接近完成条件的表达。

本设计只处理文档系统第二轮收口，不扩展到性能指标采集或节点平台化预留。

## 2. 设计目标

本轮 P0 的目标是：

1. 固化 `docs/knowledge/*` 的长期定位，使其成为常驻参考层，而不是事实层。
2. 固化 `docs/superpowers/*` 的生命周期规则，使其成为进行中工作区，而不是第二套长期真相源。
3. 清理当前文档入口中的断链与职责混写，让主要入口之间的边界一致。
4. 把 `roadmap` 中的 P0 从“方向”收紧到“可验收目标”。

## 3. 设计原则

- 只收口，不再新增平行总入口。
- 规则优先落到现有正式真相源，不新增一份新的“文档系统总规则文档”。
- `README` 只保留入口级边界，不重新堆细节。
- 长期有效的信息继续回流到 `blueprint / contracts / process / glossary`。
- `knowledge` 与 `superpowers` 都不能与正式真相层竞争入口地位。

## 4. 目标边界

### 4.1 `docs/knowledge/*` 的目标定位

`docs/knowledge/*` 应作为常驻参考层保留，主要回答：

- 为什么做这类选择
- 有哪些已验证的工程经验
- 某类技术方案如何比较
- 某些环境约束或联调现象应如何理解

它可以长期保留以下内容：

- 技术选型背景
- 环境经验
- 联调 Q&A
- 格式转换说明
- 方案对比与决策背景

它不应长期承载以下内容：

- 当前正式运行状态
- 正式控制命令语义
- 正式运行流程
- 必须遵守的契约字段或状态定义
- 未来优先级判断

如果 `knowledge` 中的某条内容已经上升为必须遵守的正式约束，应回流到：

- `docs/blueprint/current.md`
- `docs/contracts/*.md`
- `docs/process/*.md`
- 必要时 `docs/glossary.md`

### 4.2 `docs/superpowers/*` 的目标定位

`docs/superpowers/*` 应作为进行中工作区保留，主要承载：

- 尚未落地的设计展开
- 尚未完成的实施拆分
- 需要阶段性跟踪的临时工作文档

它的默认生命周期应明确为：

- `spec`
  解决“准备怎么设计、为什么这样设计、边界怎么定”
- `plan`
  解决“接下来按什么顺序做、检查点是什么”

默认规则：

- 任务进行中：可继续更新
- 长期有效信息已经形成正式规则：回流到正式层
- `plan` 只服务一次实现时：任务完成并回流后删除
- `spec` 只服务一次设计展开时：回流完成后删除
- 只有跨阶段仍在推进、短期内仍需多次引用的 `spec` 才允许阶段性保留

这意味着 `docs/superpowers/*` 不是长期沉淀库，也不是项目日常总入口。

## 5. 文档落点设计

本轮不新增新入口，只调整现有文档各自承担的职责。

### 5.1 `docs/process/development-workflow.md`

作为主规则落点，补强以下内容：

- `docs/knowledge/*` 的职责边界
- `docs/superpowers/*` 的生命周期规则
- 什么情况下应回流到正式层
- 什么情况下应删除 `spec / plan`

原因：

- 这份文档本来就负责“需求来了先看哪里、什么时候补 spec/plan、改完后回流哪里”
- 文档生命周期规则放在这里最符合现有分层

### 5.2 `docs/glossary.md`

作为术语压缩定义层，补强：

- `knowledge`
- `spec`
- `plan`

要求：

- 定义简洁
- 强调它们各自回答的问题
- 明确 `spec / plan` 默认不是长期真相源

### 5.3 `docs/knowledge/README.md`

作为参考层目录入口，补强：

- 本目录允许保留什么
- 本目录不应承载什么
- 哪些内容一旦变成正式约束，就必须回流

### 5.4 `README.md`

只做入口级修正：

- 清理对不存在文档的引用
- 保持总入口角色
- 不在这里展开文档系统细则

### 5.5 `docs/blueprint/roadmap.md`

收紧 P0 表达，使其更接近完成定义，例如：

- `docs/knowledge/*` 已固定为常驻参考层
- `docs/superpowers/*` 已固定为进行中工作区
- 入口断链已清理
- 职责混写继续减少

## 6. 不做的事

本轮 P0 不做以下事情：

- 不全面重写全部文档
- 不逐篇清洗所有 `docs/knowledge/*` 内容
- 不在这一轮引入新的文档中心文件
- 不把 `spec / plan` 重新包装成长期设计库
- 不提前推进 P1 性能指标采集
- 不提前推进 P2 节点平台化预留

## 7. 实施顺序

建议顺序如下：

1. 先修主规则：`docs/process/development-workflow.md`
2. 再修术语压缩层：`docs/glossary.md`
3. 再修参考层入口：`docs/knowledge/README.md`
4. 再修总入口断链：`README.md`
5. 最后收紧 `docs/blueprint/roadmap.md` 的 P0 表达

原因：

- 先定主规则，再修入口，避免入口先改而规则仍模糊
- 先修正式层，再回到未来规划层，有利于后续判断 P0 何时移出 roadmap

## 8. 验收标准

本轮设计落地后，至少应满足以下条件：

1. `README.md` 不再引用不存在的文档入口。
2. `README.md`、`current.md`、`development-workflow.md`、`glossary.md` 对目录边界的描述一致。
3. `docs/knowledge/*` 被统一描述为常驻参考层，而不是正式真相层。
4. `docs/superpowers/*` 被统一描述为进行中工作区，而不是长期沉淀库。
5. `spec / plan` 的回流与删除时机在正式流程文档中明确可见。
6. `roadmap` 中的 P0 能被判断为“已完成 / 未完成”，而不再只是方向口号。

## 9. 风险与约束

主要风险：

- 如果规则写得过重，可能把简单文档调整变成高摩擦流程
- 如果规则写得过轻，P0 结束后仍会重新出现边界漂移

因此本设计要求：

- 规则只覆盖职责边界、回流时机、删除时机
- 不增加额外审批层
- 不让 `README` 承担流程细节

## 10. 回流预期

这份设计一旦进入实施，预期会直接影响：

- `README.md`
- `docs/blueprint/roadmap.md`
- `docs/process/development-workflow.md`
- `docs/glossary.md`
- `docs/knowledge/README.md`

如果本轮收口足以改变对“当前最该优先补什么”的描述，也应同步检查：

- `docs/blueprint/current.md`
- 必要时 `docs/blueprint/history.md`

但它们是否更新，应以实施后的实际影响为准，不在本设计中预先强行要求。
