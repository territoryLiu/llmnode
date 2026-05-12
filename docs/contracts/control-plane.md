# 控制面契约

## 0. 文档定位

这份文档只定义 `python -m llmnode.control` 这套正式控制入口应稳定提供什么。  
它回答的是：

1. 正式控制面有哪些命令。
2. 每类命令至少应输出什么信息。
3. 单服务控制和整栈控制的边界是什么。
4. 什么属于正式行为，什么只是当前实现细节。

它不负责：

- 描述当前系统整体状态，那是 `docs/blueprint/current.md`
- 描述未来多后端规划，那是 `docs/blueprint/roadmap.md`
- 展开具体实现代码结构，那是相关 `spec / plan`

## 1. 正式入口

正式入口统一为：

```bash
python -m llmnode.control <action>
```

当前控制面不再依赖 shell 脚本层。

## 2. 命令集合

控制面当前正式命令包括：

- `start`
- `stop`
- `restart`
- `status`
- `env`
- `doctor`
- `logs`

如果后续新增命令，应同步更新：

- 本文
- `docs/process/run.md`
- `docs/blueprint/current.md`
- 相关测试

只有当控制面的最小启动方式、总入口或关键边界发生变化时，才需要同步更新 `README.md`。

## 3. 总体输出要求

- 输出优先服务终端直接阅读
- 结构应以标题块和摘要块为主
- 关键状态不应只藏在日志里
- 同一类信息应尽量稳定出现在同一段落
- 诊断输出应优先帮助定位“下一步该做什么”

## 4. `start`

### 职责
- 启动正式整栈运行路径

### 默认目标
- `node-agent`
- 推理后端
- `gateway-api`
- `web-console`

### 输出要求
- 显示启动阶段
- 显示关键地址
- 显示关键日志路径
- 启动失败时应能给出错误信息和清理行为

## 5. `stop`

### 职责
- 有序停止整栈

### 输出要求
- 显示停止阶段
- 显示各组件停止结果
- 最后给出整栈停止摘要

## 6. `restart`

### 职责
- 对整栈执行 stop + start

### 输出要求
- 保留完整阶段输出
- 明确告诉用户当前执行的是重启路径

## 7. `status`

### 职责
- 输出当前控制面视角下的运行状态摘要

### 必须提供
- 当前项目路径
- 当前 Python 环境
- 当前后端摘要
- 关键 HTTP 健康状态
- 关键进程摘要
- 总结态：
  - `ready`
  - `warming`
  - `partial`
  - `stopped`

## 8. `env`

### 职责
- 输出当前运行环境和关键路径

### 必须提供
- 项目路径
- Python 解释器
- runtime/log/run 目录
- 模型目录
- 关键服务 URL
- 前端目录

## 9. `doctor`

### 职责
- 提供系统级体检与建议动作

### 必须提供
- Python / Docker / npm / `ss` 可用性
- 模型目录与前端目录检查
- 端口检查
- HTTP 健康检查
- 运行产物检查
- Docker 容器 / 镜像检查
- 下一步建议动作

### 输出目标
- 用户不需要再自己把检查结果翻译成命令
- 应尽量直接告诉用户下一步最值得执行什么

## 10. `logs`

### 职责
- 提供统一日志查看入口

### 支持目标
- `agent`
- `gateway`
- `web-console`
- `vllm`（固定别名，指向当前激活的推理后端日志，不论实际 `backend_type` 是 `vllm / llama.cpp / sglang`）
- `all`

### 必须提供
- 日志目标
- 日志文件路径
- 最近若干行内容

### 当前原则
- 默认更适合“快速定位和预览”
- 不是长时间驻留式日志查看器

## 11. 单服务控制

当前控制面应支持单服务控制：

```bash
python -m llmnode.control start --service gateway --daemon
python -m llmnode.control start --service agent --daemon
python -m llmnode.control start --service vllm --daemon
python -m llmnode.control stop --service gateway
python -m llmnode.control stop --service agent
python -m llmnode.control stop --service vllm
```

当前边界：

- `gateway / agent` 支持前台与后台运行
- `vllm` 当前更偏 daemon 风格

## 12. 命令变更后的回流要求

如果控制面发生变化，至少要检查是否同步更新：

- 本文
- `docs/process/run.md`
- `docs/blueprint/current.md`
- `tests/test_control.py`

如果变化已经影响项目总入口、最小启动方式或关键边界，再额外同步 `README.md`。
