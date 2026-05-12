目前市面上**不存在能 100% 无损转换**这三类接口的“万能魔法网关”，因为 `/v1/responses`（OpenAI 新版 Agent）、`/v1/messages`（Anthropic Claude 原生）、`/v1/chat/completions`（事实标准）在底层设计、工具调用逻辑、流式格式上存在**结构性差异**。

但如果你需要**“统一入口、按需路由、格式映射”**，以下是 2026 年最成熟、可落地的方案：

---
### 📊 主流统一转换工具对比

| 工具 | 部署方式 | 支持转换的接口 | 核心优势 | 适用场景 |
|------|----------|----------------|----------|----------|
| **LiteLLM Proxy** | 自托管（Python） | `chat` ↔ `responses` ↔ `messages` ↔ 其他 | 路由/降级/格式映射最全，开源免费 | 企业/开发者自部署、多模型调度 |
| **OneAPI / NewAPI** | 自托管（Go） | 主要统一为 `/v1/chat/completions` | 配额管理、计费、国内生态好 | 团队统一计费、模型池化管理 |
| **OpenRouter** | 云端托管 | 统一暴露 `/v1/chat/completions` | 开箱即用、覆盖 200+ 模型 | 不想运维、快速测试 |
| **Cloudflare Workers / Vercel Edge** | 轻量托管 | 自定义 `chat` ↔ `messages` 映射 | 零成本、延迟极低、完全可控 | 个人开发者、轻量代理 |

---
### 🥇 方案一：LiteLLM Proxy（最推荐，功能最完整）
LiteLLM 是目前唯一明确支持**多协议格式映射 + 智能路由 + 失败降级**的开源网关。

#### ✅ 部署与基础配置
```bash
pip install litellm
litellm --port 4000
```

#### 📝 `config.yaml` 示例（按需适配三种接口）
```yaml
model_list:
  # 1. 标准 OpenAI 兼容模型（走 chat/completions）
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: sk-openai-xxx
      base_url: https://api.openai.com/v1

  # 2. DeepSeek / Qwen（兼容模式）
  - model_name: deepseek-chat
    litellm_params:
      model: openai/deepseek-chat
      api_key: sk-deepseek-xxx
      base_url: https://api.deepseek.com/v1

  # 3. Claude（自动映射 chat → messages）
  - model_name: claude-sonnet-4
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
      api_key: sk-ant-xxx

  # 4. 统一入口：客户端只需调用 /v1/chat/completions
  #    LiteLLM 会根据 model_name 自动转换 payload 并路由
```

#### 🔌 高级能力
- **自动降级**：`fallbacks: ["deepseek-chat", "qwen-turbo"]`
- **协议转换开关**：支持 `custom_llm_provider` 插件处理特殊字段
- **Observability**：内置日志、延迟监控、Token 统计

> 📌 注意：LiteLLM 对 `/v1/responses` 的支持仍在快速迭代，部分高级特性（如内置 `web_search`、多轮状态保持）转换时可能降级为普通工具调用。

---
### ☁️ 方案二：云端统一网关（零运维）
| 服务 | 统一入口 | 转换逻辑 | 备注 |
|------|----------|----------|------|
| **OpenRouter** | `https://openrouter.ai/api/v1/chat/completions` | 后端自动将请求转为对应厂商格式 | 支持 Claude/OpenAI/国产，按 Token 计费 |
| **SiliconFlow / 硅基流动** | `https://api.siliconflow.cn/v1/chat/completions` | 国内合规节点，内置多模型路由 | 适合国内网络，支持 Claude 3.5/4 代理 |

**使用方式**：客户端只需将 `base_url` 改为云端地址，传入 `model: "anthropic/claude-sonnet-4"` 或 `model: "openai/gpt-4o"`，网关自动处理协议差异。

---
### 🛠️ 方案三：轻量级协议适配器（适合特定场景）
如果你只需要 `chat` ↔ `messages` 转换，可用社区开源代理：
- **`openai-to-anthropic-adapter`**（GitHub 搜索）：将 OpenAI 格式转为 Anthropic 原生格式，支持系统提示词分离、`max_tokens` 注入、流式事件重映射。
- **Cloudflare Workers 模板**：约 50 行 JS 即可完成基础字段映射，部署免费，延迟 < 50ms。

```javascript
// 极简 chat → messages 转换逻辑示例
const anthropicPayload = {
  model: "claude-sonnet-4-20250514",
  max_tokens: body.max_tokens || 4096,
  system: body.messages.find(m => m.role === "system")?.content || "",
  messages: body.messages.filter(m => m.role !== "system"),
  stream: body.stream
};
```

---
### ⚠️ 重要技术边界（避坑指南）
| 特性 | 转换后影响 | 建议 |
|------|------------|------|
| **OpenAI `/v1/responses` 内置工具**（如 `web_search`） | 转为普通函数调用，失去原生优化 | 需客户端显式声明工具定义 |
| **Claude `extended_thinking`** | `chat` 接口不支持，转换会丢失 | 必须直连 `/v1/messages` 或使用 Anthropic SDK |
| **流式事件格式差异** | SSE 字段名不同（`content_block_delta` vs `delta`） | 网关会重映射，但部分 UI 可能断流 |
| **工具调用多轮状态** | `responses` 有原生会话缓存，`chat` 需手动传历史 | 复杂 Agent 建议直连原厂 API |

---
### 💡 选型建议
| 你的需求 | 推荐方案 |
|----------|----------|
| 企业级多模型调度、失败降级、审计日志 | **LiteLLM Proxy** 自托管 |
| 不想运维、快速跑通 Claude + OpenAI + 国产 | **OpenRouter / SiliconFlow** 云端网关 |
| 仅需 Claude 适配、追求低延迟 | **Cloudflare Workers 轻量代理** |
| 团队计费、配额管理为主 | **OneAPI** + 自定义转换插件 |

如果你告诉我：
1. 你主要想给**哪个工具/客户端**提供统一入口？（如 Cursor、Continue、自研平台等）
2. 是否需要支持 **Agent 多轮工具调用** 或 **流式完整保留**？
我可以给你一份**开箱即用的配置模板**或**最小可行代理代码**。


# 🔌 主流编程工具接口标准对比（2026年最新）

你提到的"接口"问题，核心是 **两大标准之争**：`/v1/chat/completions`（旧版通用标准）vs `/v1/responses`（OpenAI新版Agent标准）。下面按工具分类说明：

---

## 📋 接口标准速览表

| 工具/平台 | 默认接口 | 是否支持自定义兼容接口 | 关键说明 |
|-----------|----------|------------------------|----------|
| **OpenAI 官方** | ✅ `/v1/responses`（推荐）+ `/v1/chat/completions`（兼容） | - | Responses 是新Agent原生接口，但旧接口仍可用 [[15]] |
| **Claude (Anthropic)** | ✅ `/v1/messages`（自有标准） | ❌ 不兼容OpenAI格式 | 完全独立的API设计，需专用SDK [[24]] |
| **DeepSeek** | ✅ `/v1/chat/completions`（OpenAI兼容） | ✅ 支持 | 官方文档明确支持用OpenAI SDK调用，只需改base_url [[79]] |
| **Qwen（通义）** | ✅ `/v1/chat/completions`（OpenAI兼容） | ✅ 支持 | 阿里云百炼/通义灵码均提供兼容接口 [[12]] |
| **Cursor** | ⚠️ Agent模式用`/v1/responses`，普通模式用`/v1/chat/completions` | ⚠️ 有限支持 | 自定义API时，Agent模式会强制发Responses格式请求，部分兼容服务商可能失败 [[75]] |
| **Continue插件** | ✅ 可配置（默认`/v1/chat/completions`，o-series/gpt-5用`/v1/responses`） | ✅ 完全支持 | 通过`useResponsesApi: false`可强制降级到旧接口 [[62]] |
| **Cherry Studio** | ✅ `/v1/chat/completions`（OpenAI兼容） | ✅ 完全支持 | 内置多服务商模板，自定义时只需填根地址，自动拼接路径 [[37]] |
| **Claude Code（终端版）** | ✅ `/v1/messages`（Anthropic原生） | ❌ 仅支持Claude系列 | 是Anthropic官方CLI工具，不走OpenAI兼容层 [[8]] |
| **Aider / Cline / Roo Code** | ✅ `/v1/chat/completions` | ✅ 完全支持 | 开源工具普遍优先保障最大兼容性 [[5]] |

---

## 🔍 两大接口核心区别

### `/v1/chat/completions`（通用兼容标准）
```json
{
  "model": "gpt-4",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": true
}
```
- ✅ **优势**：生态最广，99%的第三方模型/网关/工具都支持
- ✅ **适用**：常规对话、代码补全、简单工具调用

### `/v1/responses`（OpenAI新版Agent标准）[[15]][[50]]
```json
{
  "model": "gpt-4",
  "input": [{"role": "user", "content": "Hello"}],
  "tools": [{"type": "web_search", ...}],
  "stream": true
}
```
- ✅ **优势**：原生支持多轮推理、内置工具（web_search, code_interpreter）、结构化输出
- ⚠️ **限制**：目前仅OpenAI官方+部分网关完整支持，第三方模型适配中

---

## 🛠️ 各工具配置建议

### ✅ Continue 插件（推荐）
```yaml
# config.yaml
models:
  - name: deepseek-chat
    provider: openai
    model: deepseek-chat
    apiBase: https://api.deepseek.com  # 自动拼接 /v1/chat/completions
    apiKey: sk-xxx
    useResponsesApi: false  # 关键：强制用旧接口，避免兼容问题
```
> 文档明确说明：遇到"organization must be verified"等Responses专属错误时，加此配置即可降级 [[62]]

### ✅ Cherry Studio
1. 设置 → 模型服务 → 添加服务商
2. 类型选 `New API (OpenAI-compatible)`
3. API地址填根地址（如 `https://api.deepseek.com`），**不要**带 `/v1/chat/completions` 后缀
4. 地址末尾加 `#` 可禁用自动拼接（特殊路由时用）[[37]]

### ⚠️ Cursor 自定义API
- 普通聊天模式：基本兼容大多数 `/v1/chat/completions` 接口
- **Agent模式**：会发送 `/v1/responses` 格式请求，若服务商不支持会报错 [[75]]
- ** workaround**：目前只能等待Cursor官方增加"强制兼容模式"，或改用网关中转

### ✅ DeepSeek / Qwen 等国产模型
- 官方均提供 **完全兼容的 `/v1/chat/completions` 接口** [[79]][[82]]
- 调用方式：
  ```python
  from openai import OpenAI
  client = OpenAI(
      api_key="your-key",
      base_url="https://api.deepseek.com"  # 或 https://dashscope.aliyuncs.com/compatible-mode/v1
  )
  response = client.chat.completions.create(...)
  ```

---

## 🔄 如果工具"只认Responses"怎么办？

1. **用网关中转**（推荐）  
   部署 [LiteLLM](https://litellm.ai/) 或 [OneAPI](https://github.com/songquanpeng/one-api)，将 `/v1/responses` 请求转换为 `/v1/chat/completions` 转发给目标模型

2. **检查工具配置项**  
   Continue 的 `useResponsesApi: false`、Cherry Studio 的 `#` 地址后缀等，都是为兼容性设计的逃生通道

3. **关注工具更新**  
   Cursor、Windsurf 等商业工具正在快速迭代，新版本可能已增加兼容开关 [[70]]

---

## 💡 一句话总结

> **目前不存在"只有OpenAI和Qwen能用"的协议限制**。  
> 你遇到的兼容问题，99%是**客户端工具的默认行为**（如Cursor Agent模式强制用Responses），而非底层协议封锁。  
> 只要工具支持"自定义OpenAI兼容接口" + 你配置 `useResponsesApi: false` 或用网关中转，**DeepSeek、GLM、MiniMax等模型都能正常使用**。

如果你告诉我具体用的是哪款工具 + 看到的报错信息，我可以给你精确的配置参数或临时解决方案 🔧

为你梳理当前 AI 编程/Agent 生态中三大主流接口的完整协议规范。以下内容基于 **2025-2026 年官方文档与生产环境实践**，可直接用于后端路由层、网关适配或客户端 SDK 开发。

---
## 📐 三大接口核心定位对比
| 接口 | 所属厂商 | 设计定位 | 生态覆盖 | 状态管理 |
|------|----------|----------|----------|----------|
| `/v1/chat/completions` | OpenAI（开源标准） | 通用对话/代码生成事实标准 | 90%+ 开源模型、国产模型、网关 | 无状态，需每次携带完整历史 |
| `/v1/responses` | OpenAI | Agent 原生协议（多轮状态/内置工具/结构化输出） | 仅 OpenAI 官方 + 少数高级网关 | 有状态，支持 `previous_response_id` |
| `/v1/messages` | Anthropic | Claude 专用协议（安全/长上下文/思考模式） | Claude 系列、部分 Claude 代理节点 | 无状态，`system` 独立于对话历史 |

---
## 📦 1. `/v1/chat/completions`（OpenAI 兼容标准）
### 🔹 请求结构
```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "你是一个代码助手"},
    {"role": "user", "content": "写一个快速排序"},
    {"role": "assistant", "content": "..."},
    {"role": "tool", "tool_call_id": "call_1", "content": "{\"status\": \"ok\"}"}
  ],
  "tools": [{
    "type": "function",
    "function": {"name": "run_code", "description": "...", "parameters": {...}}
  }],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 4096
}
```
### 🔹 同步响应
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "以下是快速排序...",
      "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "...", "arguments": "..."}}]
    },
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 120, "completion_tokens": 350, "total_tokens": 470}
}
```
### 🔹 流式响应 (SSE)
```text
data: {"choices":[{"delta":{"role":"assistant"},"index":0,"finish_reason":null}]}
data: {"choices":[{"delta":{"content":"def"},"index":0,"finish_reason":null}]}
data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"run","arguments":"{}"}}]},"index":0}]}
data: [DONE]
```
**特点**：结构扁平、向后兼容极强；工具调用需客户端手动拼接 `tool` 角色消息；流式通过 `choices[0].delta` 推送。

---
## 📦 2. `/v1/responses`（OpenAI Agent 原生协议）
### 🔹 请求结构
```json
{
  "model": "gpt-4o",
  "input": "写一个快速排序并执行测试",
  "tools": [
    {"type": "function", "function": {...}},
    {"type": "web_search"},
    {"type": "code_interpreter"}
  ],
  "stream": true,
  "output_format": {
    "type": "json_schema",
    "schema": {"type": "object", "properties": {"code": {"type": "string"}}}
  }
}
```
> `input` 支持三种形式：纯字符串、消息数组、或 `{"previous_response_id": "resp_xxx"}`（用于恢复多轮状态）

### 🔹 同步响应
```json
{
  "id": "resp_xxx",
  "object": "response",
  "model": "gpt-4o",
  "status": "completed",
  "output": [
    {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "..."}]},
    {"type": "function_call", "call_id": "call_1", "name": "run_code", "arguments": "{}"},
    {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "执行结果：ok"}]}
  ],
  "usage": {"input_tokens": 120, "output_tokens": 350, "total_tokens": 470}
}
```
### 🔹 流式响应 (SSE)
```text
event: response.created
data: {"id": "resp_xxx", "status": "in_progress"}

event: response.output_text.delta
data: {"delta": "def quick_sort", "sequence_number": 0}

event: response.tool_call.arguments.delta
data: {"call_id": "call_1", "delta": "{\"lang\": \"python\"}"}

event: response.completed
data: {"status": "completed", "output": [...], "usage": {...}}
```
**特点**：事件驱动型流式；原生支持内置工具；输出为 `output` 数组（含文本、工具调用、代码执行结果等独立项）；多轮状态通过 `previous_response_id` 维护，无需重复传历史。

---
## 📦 3. `/v1/messages`（Anthropic Claude 原生协议）
### 🔹 请求结构
```json
{
  "model": "claude-sonnet-4-20250514",
  "system": [{"type": "text", "text": "你是一个严谨的代码审查员"}],
  "messages": [
    {"role": "user", "content": "优化这段 Python 代码"},
    {"role": "assistant", "content": "以下是优化方案..."}
  ],
  "max_tokens": 8192,
  "tools": [{
    "name": "file_read",
    "description": "...",
    "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}
  }],
  "tool_choice": {"type": "auto"},
  "stream": true,
  "thinking": {"type": "enabled", "budget_tokens": 2048}
}
```
### 🔹 同步响应
```json
{
  "id": "msg_xxx",
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "我建议使用列表推导式..."},
    {"type": "tool_use", "id": "toolu_01", "name": "file_read", "input": {"path": "main.py"}}
  ],
  "stop_reason": "tool_use",
  "usage": {"input_tokens": 210, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 180, "output_tokens": 420}
}
```
### 🔹 流式响应 (SSE)
```text
event: message_start
data: {"type": "message_start", "message": {"id": "msg_xxx", "role": "assistant", "content": [], "usage": {...}}}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "优化方案如下\n"}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "我需要检查时间复杂度..."}}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": null}, "usage": {"output_tokens": 450}}

event: message_stop
data: {"type": "message_stop"}
```
**特点**：`system` 独立于 `messages` 数组；内容以 `content` 块数组组织（`text`/`tool_use`/`tool_result`）；支持 `thinking` 块输出推理过程；流式严格按 `index` + `type` 分块推送，结构最严谨。

---
## 🔄 协议转换核心难点与适配策略
| 转换方向 | 关键冲突 | 推荐处理方案 |
|----------|----------|--------------|
| `chat` ↔ `messages` | `system` 位置不同；工具调用结构不同（扁平 vs 内容块） | 网关统一映射：`messages` 中 `role: system` 提取为顶层 `system`；工具调用转 `tool_use`/`tool_result` 块 |
| `chat` → `responses` | `messages` → `input`；无状态 → 有状态；流式事件格式完全不同 | 降级处理：将完整 `messages` 拼为 `input` 字符串/数组；忽略 `previous_response_id`；流式重映射为 `response.*` 事件 |
| `responses` → `chat` | `output` 数组需展平为单条 `message`；内置工具需客户端实现 | 提取 `output` 中 `type: message` 的文本拼接为 `content`；`function_call` 转为 `tool_calls` 数组；丢失多轮状态优势 |
| `messages` → `responses` | `thinking` 块无对应字段；`system` 需合并进 `input` | 将 `system` 拼入首条 `user` 消息；忽略 `thinking` 或转为普通文本；工具调用转为 OpenAI 格式 |

### 🛠️ 项目架构建议
1. **内部统一标准**：推荐以 `/v1/chat/completions` 为内部抽象层（生态最广、转换成本最低）
2. **网关分层设计**：
   ```
   客户端 → [协议解析层] → [路由/转换层] → [厂商适配层] → 上游 API
   ```
3. **流式事件统一**：在网关输出端统一封装为 OpenAI 兼容 SSE 格式，前端只需解析 `choices[0].delta`
4. **状态管理隔离**：`/v1/responses` 的 `previous_response_id` 需在网关层自行维护会话映射表，或强制降级为无状态模式

---
## 📌 附：字段速查对照表
| 概念 | `/v1/chat/completions` | `/v1/responses` | `/v1/messages` |
|------|------------------------|-----------------|----------------|
| 对话历史 | `messages` (array) | `input` (string/array) 或 `previous_response_id` | `messages` (array) |
| 系统提示 | `messages[0].role: system` | 合并在 `input` 中 | `system` (顶层字段) |
| 工具定义 | `tools[].function` | `tools[]` (支持 `function`/`web_search` 等) | `tools[]` (无 `type: function` 包装) |
| 工具调用响应 | `message.tool_calls[]` | `output[]` 中 `type: function_call` | `content[]` 中 `type: tool_use` |
| 流式事件前缀 | `data:` (OpenAI 标准) | `event: response.*` + `data:` | `event: message_*` / `content_block_*` + `data:` |
| 结束标记 | `data: [DONE]` | `event: response.completed` | `event: message_stop` |

如果你需要，我可以提供：
- 一份 **TypeScript/Python 协议转换核心代码**（含流式 SSE 事件重映射）
- 针对你项目技术栈的 **网关架构草图**（FastAPI / Cloudflare Worker / LiteLLM 插件）
- 三大接口在 **工具调用多轮对话** 中的完整状态机流程图

告知你的后端语言、是否需要支持 `thinking`/内置工具、以及目标客户端类型，我可直接输出可落地的适配层代码。