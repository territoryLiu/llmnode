# V3 / V4 平台方向设计展开

## 背景

`docs/blueprintV3.md` 与 `docs/blueprintV4.md` 不再保留为并列蓝图入口。  
它们的未来规划内容已经回流到 `docs/blueprint/roadmap.md`，而更细的设计展开统一收口到 `docs/superpowers/`。

## 当前设计目标

### V3 方向
- 三后端统一抽象：
  - `vLLM`
  - `llama.cpp`
  - `SGLang`
- 每个后端一个 Docker
- 优先复用官方镜像
- 控制面只需要 Python 与 Docker 交互，不再承担本地编译或宿主机原生运行治理
- `node-agent`、`llmnode.control` 与管理台看到的运行对象，默认都应是容器级对象，而不是宿主机进程脚本集合

### V4 方向
- 在三后端控制面稳定后，进一步抽象节点平台化能力
- 明确对象：
  - `Node`
  - `ModelArtifact`
  - `RuntimeProfile`
  - `LogicalModelRoute`
  - `RuntimeInstance`
- 为未来 1~3 节点扩展留接口边界，但当前不进入大规模平台化

## 当前边界

- 本文是设计展开，不是当前真相源
- 当前真相源仍然是：
  - `docs/blueprint/current.md`
  - `docs/contracts/*.md`
  - `docs/process/*.md`
- 当前未来优先级仍然以 `docs/blueprint/roadmap.md` 为准

## 后续实施

如果 V3 / V4 后续进入实施，应继续在 `docs/superpowers/plans/*.md` 中拆解执行顺序、检查点和完成条件。
