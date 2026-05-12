"""临时文档同步脚本，运行后可删除。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        print(f"[skip] {path.name}: pattern not found")
        return
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[ok]   {path.name}")


# ── backend-routing.md ──────────────────────────────────────────────────────
br = ROOT / "docs/contracts/backend-routing.md"

patch(br,
    "- V2 管理面当前不接受非 `vllm` 的 `backend_type`",
    "- `backend_type` 现已正式支持 `vllm / llama.cpp / sglang` 三个值\n"
    "- `/admin/models/{name}` 管理接口已接受三个值（`_VALID_BACKEND_TYPES`）",
)

patch(br,
    "  - V2 对 `backend_type` 的运行时限制",
    "  - `/admin/models` 管理接口的三后端路由支持",
)

patch(br,
    "### 当前正式值\n- `vllm`\n\n### V3 目标值\n- `vllm`\n- `llama_cpp`\n- `sglang`",
    "### 当前正式值\n- `vllm`\n- `llama.cpp`\n- `sglang`",
)

patch(br,
    "  - `llmnode/api/app.py` 的 `/admin/models/{name}` 当前明确拒绝非 `vllm` 值",
    "  - `llmnode/api/app.py` 的 `/admin/models/{name}` 接受 `vllm / llama.cpp / sglang`",
)

patch(br,
    "这些约束意味着：\n\n- 字段层面已经为多后端留口\n- 运行时正式行为仍然只承认 `vllm`",
    "这些约束意味着：\n\n- 字段层面与运行时均已支持三后端\n"
    "- `backend_type` 决定 ContainerSpec、BackendDriver、健康检查和状态展示的全链路行为",
)

patch(br,
    "- 正式可写运行值：`vllm`\n- 正式控制面与网关实现：围绕 `vLLM` 路径",
    "- 正式可写运行值：`vllm / llama.cpp / sglang`\n"
    "- 控制面（`control.py`、`service.py`）与网关管理接口均已完整支持三后端",
)

# 第 7 节结论（中文引号需直接用字符）
old7 = (
    "因此当前结论不是“系统已经正式"
    "支持多后端路由”，而是“正式字"
    "段已经预留了多后端方向，但当前"
    "正式运行值仍然锁定在 `vllm`”。"
)
new7 = (
    "因此当前结论是：字段层面与运行"
    "时均已支持三后端，控制面（`control.py`"
    "、`service.py`）和管理接口均已按 `backend_type` "
    "动态路由。"
)
patch(br, old7, new7)


# ── process/run.md ──────────────────────────────────────────────────────────
run = ROOT / "docs/process/run.md"

patch(run,
    "## 4. 默认启动对象\n\n- `node-agent`\n- `vLLM`\n- `gateway-api`\n- `web-console`",
    "## 4. 默认启动对象\n\n- `node-agent`\n- 推理后端（默认 `vLLM`，可通过 `config/defaults.yaml` 切换为 `llama.cpp` 或 `sglang`）\n- `gateway-api`\n- `web-console`",
)

patch(run,
    "### 5.1 推理后端 ready\n\n至少满足：\n\n- `http://127.0.0.1:8000/v1/models` 返回正常\n\n这说明 `vLLM` 侧已经可服务，但还不等于整个对外入口都已可用。",
    "### 5.1 推理后端 ready\n\n至少满足：\n\n- `http://127.0.0.1:<host_port>/v1/models` 返回正常（默认端口 `8000`）\n\n这说明推理后端已可服务，但还不等于整个对外入口都已可用。",
)

patch(run,
    "- `8000` 正常：后端 ready",
    "- `<host_port>` 正常（默认 `8000`）：后端 ready",
)


# ── contracts/control-plane.md ──────────────────────────────────────────────
cp = ROOT / "docs/contracts/control-plane.md"

patch(cp,
    "### 支持目标\n- `agent`\n- `gateway`\n- `web-console`\n- `vllm`\n- `all`",
    "### 支持目标\n- `agent`\n- `gateway`\n- `web-console`\n- `vllm`（指向当前激活后端的日志，不论 backend_type）\n- `all`",
)


# ── blueprint/current.md ────────────────────────────────────────────────────
cur = ROOT / "docs/blueprint/current.md"

patch(cur,
    "## 10. 当前最该优先补的点\n\n当前最值得继续补厚的方向包括：\n\n- 旧蓝图文档的归档或降权说明\n- 多后端配置与实现之间的一致性收敛\n- 管理台、契约和控制面围绕三后端目标的逐步对齐",
    "## 10. 当前最该优先补的点\n\n当前最值得继续补厚的方向包括：\n\n- 三后端线上联调验证（vLLM / llama.cpp / SGLang 各自跑通推理链路）\n- 管理台与三后端状态展示的对齐\n- 旧蓝图文档的归档或降权说明",
)


# ── blueprint/history.md — 在当前阶段补充三后端控制面落地里程碑 ──────────────
hist = ROOT / "docs/blueprint/history.md"

patch(hist,
    "- 对后续意味着什么：\n  后续重点转向：\n  - 三后端设计与实现对齐\n  - 文档系统继续补厚\n  - 管理台、契约、控制面三者协同收敛",
    "- 对后续意味着什么：\n  后续重点转向：\n  - 三后端线上联调验证（vLLM / llama.cpp / SGLang）\n  - 管理台与三后端状态展示对齐\n  - 文档系统继续补厚\n- 补充里程碑（2026-05）：\n  三后端代码实现全部落地：`ContainerSpec / BackendDriver / service.py / control.py / api/app.py` 均已按 `backend_type` 动态路由；`gpu_memory_utilization` 改为 `0.9`；默认模型目录切换至 `Qwen3.6-35B-A3B`（非 FP8）；GGUF 转换链路（f16 → Q4_K_M）已完成。",
)

print("\ndone.")
