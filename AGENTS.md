# Project AGENTS

## 1. 优先级

1. 用户当前明确指令
2. 仓库真相源与项目流程文档
3. 本文件 `AGENTS.md`
4. 外部通用 skill / 通用流程

外部 skill 若与项目流程冲突，以项目流程为准。  
如果 `README.md`、`docs/blueprint/current.md`、`docs/contracts/*.md`、`docs/process/*.md` 与旧设计稿冲突，以当前正式真相源为准。

## 2. 真相源

- `README.md`
- `docs/process/development-workflow.md`
- `docs/blueprint/current.md`
- `docs/blueprint/roadmap.md`
- `docs/blueprint/history.md`
- `docs/contracts/*.md`
- `docs/process/*.md`
- `docs/glossary.md`
- `docs/superpowers/specs/*.md`
- `docs/superpowers/plans/*.md`
- `docs/knowledge/*.md`

## 3. 流程

- 轻流程：文档小修、单文件小改、现有契约下补字段
- 标准流程：一般功能迭代、中等范围 bugfix、单条链路增强
- 重流程：跨层改动、改主链路、改契约、改运行形态、改存储边界、需要迁移顺序或回滚点

不确定时，先看 [docs/process/development-workflow.md](/proj02/liuheshan/llmnode/docs/process/development-workflow.md:1)。

## 4. 回流

改动后判断是否要同步：

- `docs/blueprint/current.md`
- `docs/blueprint/roadmap.md`
- `docs/blueprint/history.md`
- 相关 `docs/contracts/*.md`
- 相关 `docs/process/*.md`
- 相关 `docs/glossary.md`
- 相关 `docs/superpowers/specs/*.md`
- 相关 `docs/superpowers/plans/*.md`

`README.md` 只在下面这些内容变化时才同步：

- 项目总入口
- 最小启动方式
- 文档阅读顺序
- 关键边界说明

## 5. 需求处理判断

- 先用 `docs/blueprint/roadmap.md` 判断这件事是不是当前优先项
- 重流程任务优先看或补 `docs/superpowers/specs/*.md`
- 需要实施拆分、检查点和阶段顺序时，再补 `docs/superpowers/plans/*.md`
- 小改动不要默认补齐整套 `spec / plan`
- `docs/superpowers/specs/*.md` 与 `docs/superpowers/plans/*.md` 默认不是长期真相源，长期有效的信息要回流到 `blueprint / contracts / process`

## 6. 项目硬约束

- 正式控制入口统一为 `python -m llmnode.control`
- 不要恢复 `scripts/control.sh` 或 `scripts/start_*.sh` 作为正式主入口
- 不要再新增 `docs/blueprintV*.md` 这类并列未来蓝图文件
- 未来规划统一写入 `docs/blueprint/roadmap.md`
- 设计展开统一写入 `docs/superpowers/specs/*.md`
- 实施拆分统一写入 `docs/superpowers/plans/*.md`
- 当前正式默认后端仍是 `vLLM`
- 三后端方向统一按 `vLLM / llama.cpp / SGLang` 各自官方 Docker 镜像或官方容器方案推进
- Python 控制面只负责 Docker 编排、状态读取、健康检查、日志与契约治理

## 7. 安全边界

- 不覆盖、回滚、丢弃用户未明确要求的未提交工作
- 大改前先看工作树是否干净
- 优先沿用仓库已有约定
- 如果发现用户已有相关改动，先理解并在其基础上继续

## 8. 开发节奏

- 先完成开发实现
- 开发完成后，再统一编写测试脚本和执行测试
- 不要在开发过程中频繁插入零散测试

## 9. Python 环境

- Python 环境使用 `/home/heshan/.conda/envs/paper2any/bin/python`
- 缺少依赖时，优先用 `https://pypi.tuna.tsinghua.edu.cn/simple` 加速安装
- 如果实际使用了别的环境，必须明确说明

## 10. 验证

- 能验证时尽量验证
- 没验证不要说成“已确认”
- 文档改动至少做结构、引用或关键字回归检查
- 代码改动至少做与本次改动直接相关的命令级验证
