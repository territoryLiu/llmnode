# P1 性能指标采集设计

## 1. 目标

当前 `docs/blueprint/roadmap.md` 已把“性能指标采集”列为 P1，但代码层仍缺少正式落地点，尤其缺少统一的 `/admin/diagnostics/metrics` 端点。

本设计只解决最小 P1 闭环：

- 不引入 Prometheus、Grafana 等重型监控系统
- 基于现有网关请求链路采集基础性能指标
- 通过 Agent 服务暴露统一只读指标端点
- 用 `models/Qwen/Qwen3.6-27B`、`gpu_memory_utilization: 0.75`、`max_model_len: 262144` 作为本次实测配置

本设计不解决：

- 时间窗口聚合
- 按模型 / 协议 / 状态的多维分组
- GPU 原生利用率的长期采集
- 后端原生 metrics 端口对接

## 2. 设计原则

- 轻量优先：复用现有 `runtime/data/gateway.db`
- 后端无关：采集口径统一放在网关层，不依赖 vLLM 特有接口
- 不影响主链路：指标写入失败不应让推理请求失败
- 口径明确：缺失 `usage` 的请求仍计入请求数与延迟，但不参与 tokens 吞吐统计

## 3. 指标范围

最小 P1 对外提供下面这些指标：

- `request_count`
- `success_count`
- `success_rate`
- `avg_latency_ms`
- `p95_latency_ms`
- `p99_latency_ms`
- `throughput_tokens_per_s`
- `queue_length`
- `tokens_observed_requests`
- `generated_at`

口径约束：

- `request_count` 统计所有已落库请求指标记录
- `success_count` 只统计 `status = ok`
- `success_rate = success_count / request_count`
- 延迟指标以毫秒为单位
- `throughput_tokens_per_s` 只在存在 `completion_tokens` 的样本上统计
- `queue_length` 取网关当前实时等待长度，而不是历史平均值

## 4. 数据来源与边界

### 4.1 采集位置

指标采集统一放在 `gateway-api` 请求处理层。

原因：

- 网关已经掌握请求进入与返回时机
- 网关已经维护队列长度
- 网关能统一覆盖 `openai` 与 `anthropic` 两类协议
- 网关可以直接访问当前逻辑模型名与请求状态

### 4.2 tokens 来源

tokens 统计优先读取后端响应中的 `usage` 字段：

- `prompt_tokens`
- `completion_tokens`
- `total_tokens`

如果响应中没有 `usage`：

- 仍记录请求成功与延迟
- tokens 字段允许为空
- 此类请求不参与 `throughput_tokens_per_s` 计算

## 5. 持久化结构

### 5.1 新增表

新增 `request_metrics` 表，不修改现有 `request_logs` 的审计语义。

建议字段：

- `request_id TEXT PRIMARY KEY`
- `model_name TEXT NOT NULL`
- `protocol TEXT NOT NULL`
- `status TEXT NOT NULL`
- `latency_ms REAL`
- `prompt_tokens INTEGER`
- `completion_tokens INTEGER`
- `total_tokens INTEGER`
- `tokens_per_second REAL`
- `started_at TEXT NOT NULL`
- `finished_at TEXT`
- `created_at TEXT DEFAULT CURRENT_TIMESTAMP`

### 5.2 为什么不直接扩 `request_logs`

`request_logs` 当前主要承担审计与故障定位作用。性能指标和审计日志虽然相关，但职责并不完全相同。

将性能字段全部塞进 `request_logs` 会带来两个问题：

- 表语义继续膨胀，后续维护更容易混乱
- 流式请求和失败请求的度量字段不一定和审计字段同时齐全

因此最小 P1 仍复用同一个数据库，但拆分成单独的 `request_metrics` 表。

## 6. 写入策略

### 6.1 非流式请求

非流式请求处理流程：

1. 进入 handler 时记录 `started_at`
2. 请求成功返回后记录 `finished_at`
3. 计算 `latency_ms`
4. 从响应中提取 `usage`
5. 若存在 `completion_tokens` 且延迟大于 0，计算 `tokens_per_second`
6. 写入一条 `request_metrics`

### 6.2 流式请求

流式请求不能在开始返回流时就拿到完整使用量。

最小 P1 策略：

- 在流结束的 `finally` 中补写最终 metrics
- 若当前流式适配层无法稳定拿到完整 `usage`，则只写：
  - `status`
  - `latency_ms`
  - `started_at`
  - `finished_at`
- tokens 字段允许为空

这保证了流式请求至少能参与请求量、成功率和延迟统计。

### 6.3 失败 / 拒绝请求

以下请求也需要写入 `request_metrics`：

- `queue_full`
- `queue_timeout`
- 鉴权失败以外的已进入 handler 的失败请求
- 后端异常

此类记录：

- 计入 `request_count`
- 不计入 `success_count`
- 一般不带 tokens

这样成功率和延迟分布的分母才完整。

## 7. 聚合逻辑

Agent 新增：

- `GET /admin/diagnostics/metrics`

第一版不支持复杂查询参数，默认返回当前数据库累计结果。

聚合规则：

- `request_count`：`request_metrics` 总数
- `success_count`：`status = ok` 总数
- `success_rate`：`success_count / request_count`
- `avg_latency_ms`：所有有 `latency_ms` 样本的平均值
- `p95_latency_ms`：全部 `latency_ms` 升序后取 95 分位
- `p99_latency_ms`：全部 `latency_ms` 升序后取 99 分位
- `throughput_tokens_per_s`：`sum(completion_tokens) / sum(latency_seconds)`，仅基于有 tokens 的样本
- `queue_length`：实时读取 gateway 当前 `request_gate.waiting`，无法读取时退化为 `0`
- `tokens_observed_requests`：有 `completion_tokens` 的样本数

空库时：

- 返回 200
- 计数型字段返回 `0`
- 延迟与吞吐字段可返回 `0` 或 `null`，实现时应固定一种稳定口径

推荐返回结构：

```json
{
  "request_count": 12,
  "success_count": 10,
  "success_rate": 0.8333,
  "avg_latency_ms": 842.5,
  "p95_latency_ms": 1320.0,
  "p99_latency_ms": 1450.0,
  "throughput_tokens_per_s": 58.4,
  "queue_length": 0,
  "tokens_observed_requests": 8,
  "generated_at": "2026-05-13T10:30:00+00:00"
}
```

## 8. 配置与本次实测参数

本次实测配置收口为：

- `model_dir: models/Qwen/Qwen3.6-27B`
- `model_name` 对齐 27B 模型标识
- `gateway.backend_model` 对齐 27B 逻辑模型
- `config/models.yaml` 对齐 27B 路由
- `gpu_memory_utilization: 0.75`
- `max_model_len: 262144`

本次不再将“35GB 显存占用”写成独立硬约束，统一以 `gpu_memory_utilization: 0.75` 作为配置表达。

## 9. 错误处理

- metrics 写库失败：
  - 主请求仍按原逻辑返回
  - 仅记录告警或日志
- 后端响应缺少 `usage`：
  - 保留延迟与状态记录
  - tokens 字段为空
- 聚合端点读取失败：
  - 应返回明确错误，不伪装成健康状态

核心原则是：指标采集不能成为推理主链路的新失败源。

## 10. 测试与验收

### 10.1 测试范围

最小回归测试包括：

- 存储层：
  - `request_metrics` 建表
  - 单条写入
  - 聚合结果
- API 层：
  - 非流式成功请求写入 metrics
  - 拒绝 / 超时请求写入 metrics
  - 流式请求至少写入状态和延迟
- Agent 层：
  - `/admin/diagnostics/metrics` 返回结构稳定
  - 聚合值符合预期

### 10.2 验收边界

本次验收以以下条件为准：

1. 代码中正式存在 `/admin/diagnostics/metrics`
2. 默认部署切到 `models/Qwen/Qwen3.6-27B`
3. `gpu_memory_utilization: 0.75`
4. `max_model_len: 262144`
5. 至少打通 1 次成功请求后，metrics 中 `request_count > 0`
6. 若后端返回 `usage`，可看到非零 `throughput_tokens_per_s`
7. 若受当前环境 GPU / Docker 权限限制无法完成实机推理，也必须完成代码级与接口级验证，并明确阻塞点

## 11. 后续不在本次范围内的增强

以下内容明确留到后续迭代：

- 时间窗口查询（如最近 5 分钟 / 1 小时）
- 按模型分组聚合
- 按协议分组聚合
- 状态分桶统计
- GPU 显存与利用率历史采样
- 对接 vLLM / SGLang 原生 metrics
