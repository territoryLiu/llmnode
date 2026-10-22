# 后端容器端口绑定 127.0.0.1 实施计划

对应 spec：[2026-08-18-backend-port-binding-design.md](../specs/2026-08-18-backend-port-binding-design.md)

## 阶段与文件清单

### 阶段 1.1：spec ports 元组化

`llmnode/agent/docker_control.py`：

- VLLM spec `ports` property（约 :86-88）：`{"8000/tcp": ("127.0.0.1", self.host_port)}`，类型注解 `dict[str, tuple[str, int]]`
- LlamaCpp spec `ports` property（约 :130-132）：`{"8080/tcp": ("127.0.0.1", self.host_port)}`
- SGLang spec `ports` property（约 :181-183）：`{"30000/tcp": ("127.0.0.1", self.host_port)}`
- `_run_new_container` 的 `ports=spec.ports` 不动

检查点：`python -c "from llmnode.agent.docker_control import *"` 导入通过。

### 阶段 1.2：漂移检测纳入 HostIp

`llmnode/agent/docker_control.py`：

- `_normalized_port_bindings`（约 :208-219）：返回值升级为 `dict[container_port, sorted list[(host_ip, host_port)]]`；提取 `HostIp`，缺失或 `"0.0.0.0"` 归一化为 `""`
- `_container_matches_spec`（约 :236-259）：`expected_ports = {str(cp): [(host_ip, str(host_port))] for cp, (host_ip, host_port) in spec.ports.items()}`

检查点：`pytest tests/test_docker_control.py` 全绿（先跑既有测试确认漂移行为符合预期，再补新断言）。

### 阶段 1.3：测试更新

`tests/test_docker_control.py`：

- fake `HostConfig.PortBindings`（约 :38）`HostIp` 更新为 `"127.0.0.1"`
- 新增 `test_ensure_container_running_keeps_loopback_bound_container`：HostIp=127.0.0.1 + 正确端口 + running → `action == "already_running"`，`run_calls == []`
- 新增 `test_ensure_container_running_recreates_legacy_all_interfaces_binding`：HostIp=`""`（含 `"0.0.0.0"` 变体）+ 正确端口 → `action == "recreated"`
- 既有 recreate 测试补显式断言：`containers.run` 收到的 `ports == {"8000/tcp": ("127.0.0.1", 15673)}`
- 新增 spec 级断言：三个 spec 的 `ports` 均为 loopback 元组
- 注意：既有 fake `HostPort=8000` 与 spec 15673 不一致是刻意的漂移构造，不要修正

检查点：`/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_docker_control.py -v` 全绿。

## 生产验证（Step 6）

- 后端重启 / agent 启动后：`docker inspect <container> --format '{{json .HostConfig.PortBindings}}'` 显示 `HostIp: "127.0.0.1"`
- `ss -ltnp | grep 15673` 仅 `127.0.0.1:15673`
- 本机 `curl -sS http://127.0.0.1:15673/v1/models` 200；外部主机 connection refused

## 文档回流

- `docs/contracts/backend-routing.md`：补一行后端容器 PortBindings `HostIp=127.0.0.1` 的契约描述（§15 附近）
- `docs/blueprint/current.md`：补"后端容器端口绑定 127.0.0.1"现状

## 完成条件

- pytest 全绿
- 生产容器 `HostIp=127.0.0.1` 确认
- 文档回流完成
