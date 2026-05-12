# 后端路由契约

## 0. 文档定位

这份文档只定义逻辑模型如何映射到具体推理后端。  
它回答的是：

1. `backend_type` 的正式语义是什么。
2. 哪些字段属于正式路由契约。
3. 当前已落地和未来目标分别是什么。

它不负责：

- 描述完整系统现状，那是 `docs/blueprint/current.md`
- 描述未来优先级，那是 `docs/blueprint/roadmap.md`
- 展开某一后端的详细启动设计，那是相关 `spec`

## 1. 这份契约服务哪条正式链路

当前它服务的正式链路是：

1. 客户端请求逻辑模型名
2. `gateway-api` 读取当前 `ModelRoute`
3. 路由层根据 `backend_model + backend_type` 决定目标后端
4. 请求被转发到实际推理服务

当前对外暴露的是逻辑模型名；`backend_model` 与 `backend_type` 属于网关、控制面、管理台和存储层共同理解的内部正式字段。

## 2. 目标

- 定义逻辑模型如何映射到具体推理后端
- 保证客户端不需要感知后端差异
- 为管理台、控制面、数据库和网关提供统一字段语义

## 3. 当前契约来源 / 代码锚点

当前正式锚点至少包括：

- `config/models.yaml`
  - 静态模型目录与初始路由来源
- `llmnode/models.py`
  - `ModelRoute` 数据结构
  - `load_model_catalog()` 默认值与加载逻辑
  - `model_routes_for_admin()` 管理台读取视图
- `llmnode/api/app.py`
  - 启动时把模型目录写入运行态
  - `/admin/models` 读取与更新入口
  - `/admin/models` 管理接口的三后端路由支持
- `llmnode/storage/db.py`
  - `model_routes` 表结构与持久化字段

如果这些位置的字段语义不一致，应以代码真实行为为准，并把文档回流补齐。

## 4. 当前状态

- 当前正式运行路径默认仍为 `vLLM`
- 路由配置以 `config/models.yaml` 为主
- `backend_type` 现已正式支持 `vllm / llama.cpp / sglang` 三个值，三后端均已完成线上联调验证（2026-05-12）
- `/admin/models/{name}` 管理接口已接受三个值（`_VALID_BACKEND_TYPES`）

## 5. 正式字段

当前至少包括：

- `name`
- `display_name`
- `backend_model`
- `backend_type`
- `enabled`

后续如果扩展容器与 profile，应继续保证这些字段仍然存在且语义稳定。

字段语义：

- `name`
  - 逻辑模型标识，也是客户端看到的正式模型名
- `display_name`
  - 管理台展示名，不改变正式路由键
- `backend_model`
  - 实际传给后端的模型标识
- `backend_type`
  - 表示这条路由绑定到哪类推理后端
- `enabled`
  - 控制逻辑模型是否对正式 API 暴露

## 6. `backend_type`

### 当前正式值
- `vllm`
- `llama.cpp`
- `sglang`

### 约束
- `backend_type` 是客户端不可见、但网关和控制面必须理解的内部正式字段
- 它决定：
  - 目标后端驱动
  - 请求适配逻辑
  - 健康检查逻辑
  - 管理台状态展示维度

## 7. 当前真实行为

当前真实行为应按下面理解：

- `config/models.yaml` 提供模型目录初值
- `llmnode/models.py` 中 `ModelRoute.backend_type` 默认值是 `vllm`
- 如果配置里未显式写 `backend_type`，加载后会默认落成 `vllm`
- 启动后，模型路由会进入 SQLite 的 `model_routes` 表作为运行态存储
- 管理面可以更新 `display_name / backend_model / backend_type / enabled`
- `/admin/models/{name}` 现已接受 `vllm / llama.cpp / sglang` 三个值（`_VALID_BACKEND_TYPES`）

因此当前结论是：字段层面与运行时均已支持三后端，控制面（`control.py`、`service.py`）和管理接口均已按 `backend_type` 动态路由。

## 8. 运行时约束 / 校验入口

当前至少有这些运行时约束：

- 配置加载约束
  - `llmnode/models.py` 会为缺省路由补 `backend_type="vllm"`
- 存储约束
  - `llmnode/storage/db.py` 中 `model_routes.backend_type` 为 `NOT NULL`
- 管理面约束
  - `llmnode/api/app.py` 的 `/admin/models/{name}` 接受 `vllm / llama.cpp / sglang`
- API 暴露约束
  - `enabled=false` 的逻辑模型不应出现在正式模型列表里

这些约束意味着：

- 字段层面与运行时均已支持三后端
- `backend_type` 决定 ContainerSpec、BackendDriver、健康检查和状态展示的全链路行为

## 9. 路由职责

- `gateway-api` 负责把客户端请求路由到逻辑模型绑定的后端
- 后端差异不应直接暴露给客户端
- 同一逻辑模型在任一时刻应只绑定一个正式后端目标

## 10. 当前与未来的差异

当前正式状态：

- 正式默认后端：`vllm`
- 正式可写运行值：`vllm / llama.cpp / sglang`
- 控制面（`control.py`、`service.py`）与网关管理接口均已完整支持三后端
- 三后端均已完成线上联调验证（2026-05-12）：推理链路打通，`reasoning_content / content` 干净分离已确认

未来仍需补厚的方向：

- 管理台状态展示与三后端类型对齐（当前后端类型、容器状态、推理参数）
- 健康检查和日志采集在三后端下的覆盖面验证

## 11. 长期扩展方向

后续三后端落地后，本契约应继续扩展：

- `container_image`
- `container_name`
- `profile_id`
- `healthcheck_kind`
- `tool_calling_capability`
- `streaming_capability`

## 12. 文档回流要求

如果路由字段或后端类型发生变化，应至少检查是否同步更新：

- `config/models.yaml`
- `llmnode/models.py`
- `llmnode/api/app.py`
- `llmnode/storage/db.py`
- `docs/blueprint/current.md`
- `docs/blueprint/roadmap.md`
- 本文
