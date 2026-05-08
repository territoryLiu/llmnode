# llmnode

本项目是单机本地 LLM 网关，外部同时兼容：

- `POST /v1/chat/completions` for OpenAI clients
- `POST /v1/messages` for Claude Code
- `GET /v1/models`

## 当前状态
- V1：可用原型，单后端 `vLLM`
- V2：平台化控制面，仍只支持 `vLLM`
- V3：预留多后端，新增 `llama.cpp`，面向 Gemma 4 31B 和混合部署

## 架构
- `gateway-api`：鉴权、路由、配额、排队、审计
- `node-agent`：本机 `vLLM` 生命周期、健康检查、恢复
- `web-console`：V2/V3 管理台预留
- `runtime/`：运行产物

## 版本边界
- V1：只要能稳定跑通 Claude Code 和 OpenAI 客户端即可
- V2：补齐平台化能力，但后端仍固定 `vLLM`
- V3：引入 `llama.cpp`，支持高内存 + CPU offload 场景

## 推荐环境
优先使用 `paper2any`：

```bash
conda activate paper2any
cd /proj02/liuheshan/llmnode
```

## 配置
正式配置以 `config/defaults.yaml` 为准。

当前默认模型目录已经统一指向：

- `models/Qwen/Qwen3.6-35B-A3B-FP8`

环境变量仍然可以覆盖运行参数，但它们只是临时覆盖，不再单独维护根目录 `.env.example`。

## 启动

```bash
bash scripts/start_gateway.sh
bash scripts/start_agent.sh
```

## V2 管理前端

前端目录：

```bash
cd /proj02/liuheshan/llmnode/web-console
```

开发模式：

```bash
npm install
npm run dev
```

生产构建：

```bash
npm run build
```

当前首页已经包含：

- 总览状态卡片
- 实时 SSE 面板
- 最近请求表
- 最近节点事件表
- 队列长度 / 失败计数趋势图

## 验证

```bash
curl -H 'Authorization: Bearer dev-key' http://127.0.0.1:4000/v1/models
curl -H 'Authorization: Bearer dev-key' \
  -H 'Content-Type: application/json' \
  -d '{"model":"claude-sonnet-4-5-20250929","messages":[{"role":"user","content":"hello"}],"max_tokens":16}' \
  http://127.0.0.1:4000/v1/chat/completions
curl -H 'Authorization: Bearer dev-key' \
  -H 'Content-Type: application/json' \
  -d '{"model":"claude-sonnet-4-5-20250929","messages":[{"role":"user","content":"hello"}],"max_tokens":16}' \
  http://127.0.0.1:4000/v1/messages
```

## API Key

当前网关同时支持两类 key：

- `gateway.api_key`：长期保留的 break-glass 管理员 key，默认仍是 `dev-key`
- 数据库 key：通过管理接口创建，数据库只保存 `key_hash`

创建一个数据库推理 key：

```bash
curl -X POST http://127.0.0.1:4000/admin/keys \
  -H 'Authorization: Bearer dev-key' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "local-inference",
    "scopes": ["inference"],
    "rpm_limit": null,
    "concurrency_limit": null,
    "note": "local cli"
  }'
```

返回结果中的 `secret` 只会出现一次。拿到后可以直接访问业务接口：

```bash
curl http://127.0.0.1:4000/v1/models \
  -H 'Authorization: Bearer ln_live_your_secret_here'
```

当前数据库 key 已支持：

- `admin` / `inference` scope 校验
- 单 key `rpm_limit` 滑动 60 秒限流
- 单 key `concurrency_limit` 活跃请求并发限制
- 请求日志记录 `api_key_id`、`auth_source`、`client_ip`、`user_agent`、`rejection_reason`

查看数据库 key 列表：

```bash
curl http://127.0.0.1:4000/admin/keys \
  -H 'Authorization: Bearer dev-key'
```

## 测试

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest -q
```

## Claude Code

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:4000",
    "ANTHROPIC_API_KEY": "dev-key"
  }
}
```

如果 `vLLM` 要支持 Claude Code 工具调用，启动参数需要包含：

- `--reasoning-parser qwen3`
- `--enable-auto-tool-choice`
- `--tool-call-parser qwen3_coder`
