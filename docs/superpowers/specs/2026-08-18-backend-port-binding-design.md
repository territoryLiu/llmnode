# 后端容器端口绑定 127.0.0.1 设计

## 1. 背景

三种后端（vLLM / llama.cpp / SGLang）的 Docker 端口映射通过 `llmnode/agent/docker_control.py` 中三个 spec 的 `ports` property 声明，当前均为 `{"<port>/tcp": host_port}` 的 dict 形式。docker-py 对该形式的语义是绑定宿主机**所有网卡**（`HostIp=""`），导致：

- vLLM 15673、llama.cpp、SGLang 的模型服务端口对 LAN / 外部网络直接暴露；
- 任何能访问该主机的调用方可以绕过 LLM Node gateway 的鉴权、限流、日志与 route 治理，直接调用模型。

本仓库所有消费方（gateway backend client、agent 健康检查、control 命令、perf 脚本、19 个 backend profile）连接后端时已全部使用 `http://127.0.0.1:<port>`，没有任何依赖非本机访问的路径。

## 2. 目标

1. 三种后端的宿主机端口绑定统一限制为 `127.0.0.1`。
2. 容器漂移检测把 `HostIp` 纳入比较：存量 0.0.0.0 绑定的容器在下次 `ensure_container_running` 时被自动判定漂移并重建，完成无手工迁移。
3. 新绑定（127.0.0.1）的容器不被误判漂移，agent 重启不会无谓重建后端。

## 3. 非目标

- gateway 自身 4000 端口的绑定策略不动（对外服务入口，是设计意图；跨机器访问应由 TLS 反代 / VPN / 防火墙解决）。
- 容器内 `--host 0.0.0.0` 监听地址保留（bridge 端口映射要求容器内进程监听所有接口）。
- 客户端 URL、backend profile 的 `host_port`、`backend_url` 全部不动。

## 4. 方案

### 4.1 spec ports 元组化

三个 spec 的 `ports` property 改为元组形式（docker-py 原生支持，转为 `HostIp="127.0.0.1"`）：

```python
@property
def ports(self) -> dict[str, tuple[str, int]]:
    return {"8000/tcp": ("127.0.0.1", self.host_port)}   # VLLM；LlamaCpp 8080 / SGLang 30000 同理
```

`_run_new_container` 的 `ports=spec.ports` 透传不动。

### 4.2 漂移检测纳入 HostIp

`spec.ports` 全仓库只有两个消费点：漂移检测（`_container_matches_spec`）与容器创建（`_run_new_container`）。元组化后若漂移检测不同步改，`str(("127.0.0.1", 15673))` 与归一化值永不相等，每次 agent 启动都会误判漂移重建容器。

- `_normalized_port_bindings` 返回值升级为 `dict[container_port, sorted list[(host_ip, host_port)]]`，提取 `HostIp`，缺失或 `"0.0.0.0"` 归一化为 `""`（不同 docker 版本对全接口绑定的报告不一致）。
- `_container_matches_spec` 的 `expected_ports` 改为 `{str(cp): [(host_ip, str(host_port))] for cp, (host_ip, host_port) in spec.ports.items()}`。

语义：旧 0.0.0.0 容器 → `("", port) != ("127.0.0.1", port)` → 判漂移 → 重建（自动迁移）；新 127.0.0.1 容器 → 相等 → 不漂移。

## 5. 迁移顺序与回滚点

容器无状态（模型目录为 ro bind mount），无数据迁移：

| Step | 操作 | 回滚点 |
|---|---|---|
| 1 | 部署新代码（工作树叠加，不提交） | git 层回到改动前 |
| 2 | 后端下次重启 / agent 启动时漂移检测自动重建容器 | 代码回滚后下次 `ensure_container_running` 反向判漂移、自动重建回 0.0.0.0；无数据风险 |
| 3 | `docker inspect` 确认 `HostIp=127.0.0.1`，`ss -ltnp` 确认仅 `127.0.0.1:<port>` 监听 | 重建失败 = 后端起不来，docker 层面直接排查 |

## 6. 验证标准

- `pytest tests/test_docker_control.py` 全绿，含新增回归：loopback 容器不重建、旧全接口容器重建、`containers.run` 收到元组 ports。
- 生产：`docker inspect <container> --format '{{json .HostConfig.PortBindings}}'` 显示 `HostIp: "127.0.0.1"`；`ss -ltnp | grep <port>` 仅 `127.0.0.1`；本机 `curl http://127.0.0.1:15673/v1/models` 200，外部主机访问 connection refused。
