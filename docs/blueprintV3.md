# blueprintV3

## 1. 定位
- V3 在 V2 的平台化控制面之上，引入第二种推理后端。
- 目标不是替换 `vLLM`，而是让系统支持两类本机部署路径：
  - `vLLM`：偏 GPU 常驻、服务化、高吞吐
  - `llama.cpp`：偏混合部署、CPU offload、高内存利用、节能
- V3 继续保持外部协议不变，避免影响 Claude Code 和 OpenAI 客户端。

## 2. V3 的新增目标
- 新增 `llama.cpp` 部署方式。
- 支持 Gemma 4 31B 的本地混合部署。
- 继续支持 Qwen 系模型。
- 利用大内存机器，把冷权重放 RAM，显存优先留给热路径和 KV Cache。
- 不负责模型下载；模型由人工准备，系统只做注册、配置和运行控制。

## 3. 对外保持不变
### 3.1 业务接口
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/messages`

### 3.2 兼容要求
- OpenAI 客户端继续走 `/v1/chat/completions`
- Claude Code 继续走 `/v1/messages`
- `gateway-api` 对外契约不因后端类型变化而变化

## 4. 核心变化
### 4.1 新增后端抽象层
- 在 `gateway-api` 和 `node-agent` 之间引入统一后端概念：
  - `backend_type = vllm`
  - `backend_type = llama_cpp`
- 所有逻辑模型最终都映射到：
  - 一个后端类型
  - 一个本地模型目录
  - 一组运行 profile

### 4.2 `gateway-api` 的职责
- 保持不变：
  - 鉴权
  - 配额
  - 排队
  - 审计
  - 双协议兼容
- 新增：
  - 根据模型路由选择目标后端驱动
  - 根据后端类型适配请求参数差异

### 4.3 `node-agent` 的职责
- 保持不变：
  - 启停
  - 健康检查
  - 恢复
  - 遥测
- 新增：
  - 驱动不同后端的本机启动方式
  - 对不同后端执行差异化健康检查和状态采样

## 5. 两类后端定位
### 5.1 `vLLM`
- 适合：
  - GPU 显存较充足
  - 高吞吐
  - 长连接服务
  - OpenAI 风格服务化部署
- 优先模型：
  - Qwen 系
  - 更适合全 GPU 或接近全 GPU 的运行方式

### 5.2 `llama.cpp`
- 适合：
  - 显存有限但 RAM 很大
  - CPU offload
  - MoE 或 dense 模型的混合部署
  - 节能和高内存利用
- 优先模型：
  - Gemma 4 31B
  - 需要依赖高内存、有限显存来落地的大模型

## 6. V3 的部署模型
### 6.1 人工准备模型
- 系统不下载模型。
- 系统不负责从 Hugging Face 拉权重。
- 用户手动准备：
  - 模型目录
  - 权重格式
  - 转换结果

### 6.2 系统负责的内容
- 注册模型路径
- 校验配置合法性
- 管理启动参数
- 启停对应进程
- 跟踪健康和状态

## 7. 运行配置模型
### 7.1 逻辑模型
- 对外展示名
- 协议兼容性
- 默认参数
- 启用状态

### 7.2 后端路由
- `backend_type`
- `backend_name`
- `model_path`
- `profile_id`

### 7.3 运行 profile
- 对 `vllm`：
  - `gpu_memory_utilization`
  - `tensor_parallel_size`
  - `max_model_len`
  - `max_num_seqs`
- 对 `llama.cpp`：
  - `ctx_size`
  - `gpu_layers`
  - `threads`
  - `batch_size`
  - `ubatch_size`
  - `flash_attn`
  - `cache_type`

## 8. Gemma 4 31B 设计要求
- 允许作为 `llama.cpp` 路由目标注册。
- 默认假设：
  - 模型由用户手动下载
  - 需要高 RAM 支撑
  - 不以高并发服务为第一目标
- 推荐定位：
  - 单机开发助手
  - 本地聊天
  - 低显存混合部署

## 9. `llama.cpp` 驱动要求
### 9.1 启动方式
- `node-agent` 需要支持本机进程方式拉起 `llama-server` 或等价服务。
- 不要求一定容器化。
- 如果容器化会增加复杂度，优先支持本机进程部署。

### 9.2 健康检查
- 需要独立于 `vLLM` 的健康检查逻辑。
- 至少检查：
  - 进程是否存在
  - 监听端口是否就绪
  - 基础推理接口是否返回正常

### 9.3 状态采样
- 采样项至少包括：
  - 进程状态
  - 内存占用
  - GPU 占用
  - 上下文配置
  - 最近错误

## 10. 请求适配
- `gateway-api` 不暴露后端差异给客户端。
- 对内需要做参数裁剪和兼容：
  - 某些模型支持 tool calling
  - 某些模型只支持普通聊天
  - 某些后端支持 streaming 的细节不同
- 对 Claude Code：
  - 如果某模型不支持稳定 tool calling，应能明确拒绝或降级

## 11. 观测与审计
- 请求日志需要新增：
  - `backend_type`
  - `profile_id`
  - `runtime_mode`
- 指标需要新增：
  - CPU 内存占用
  - offload 相关状态
  - 后端类型维度的延迟与失败率

## 12. 版本边界
- V3 不做多节点平台。
- V3 不做模型自动下载。
- V3 不做分布式调度。
- V3 不做自动格式转换流水线。
- V3 只解决“单机双后端”的可维护落地。

## 13. 验收标准
- 现有 `vLLM` 路径继续可用。
- `llama.cpp` 路径可被配置、启动、停止、重启。
- Gemma 4 31B 可通过手工准备模型目录后注册并运行。
- OpenAI 客户端仍可通过 `/v1/chat/completions` 调用。
- Claude Code 仍可通过 `/v1/messages` 调用。
- 请求日志可区分 `vllm` 与 `llama_cpp`。
- `node-agent` 能对两种后端分别做健康检查和故障恢复。

## 14. 推荐开发顺序
1. 在 V2 中预留后端抽象，但不实现第二后端。
2. 为 `node-agent` 抽出 `BackendDriver` 接口。
3. 保持 `vllm` 驱动行为不变。
4. 新增 `llama_cpp` 驱动。
5. 加入 Gemma 4 31B 的模型路由和运行 profile。
6. 完成双协议兼容验证和审计验证。
