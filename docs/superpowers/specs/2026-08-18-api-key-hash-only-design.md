# API key hash-only 与运行时文件权限收紧设计

## 1. 背景

安全审查确认三类问题：

1. **明文落库**：`api_keys` 表存在 `plain_secret` 列（`_ensure_columns` 迁移补列），admin 与全部 inference key 的明文都在生产库 `runtime/data/gateway.db` 中。
2. **API 泄漏**：`_sanitize_api_key_row` 把 `plain_secret` 放入响应，导致 `GET /admin/keys`（列表）、`PATCH /admin/keys/{id}`（任意更新回传）、`POST /admin/keys`（响应 `key` 对象冗余）三个端点返回明文。这违反了 `docs/contracts/backend-routing.md §15` 的既有契约（"列表返回 masked_key 脱敏字段，不含 secret 明文"）。
3. **文件权限过宽**：`gateway.db` 为 644、`runtime/data` 为 775，本机其他用户可读全部明文密钥与请求日志。

既有事实：

- gateway 鉴权是 hash-first（`proxy/router.py`：先 `hash_api_key(token)` 再 `get_api_key_by_hash` 查表），`plain_secret` 列完全不参与校验，删除该列对鉴权零影响。
- admin key 目前从 DB 明文读取供 web console dev server 注入（`control.py _ensure_web_console_api_key` → `VITE_API_PROXY_KEY`），这是 hash-only 后必须改造的核心依赖。
- 与 `model_routes.upstream_auth_ref`（secret 不入库、只存引用名）的既有边界先例一致。

## 2. 目标

1. `api_keys` 表移除 `plain_secret` 列（DROP COLUMN + VACUUM 物理清除），密钥仅在创建/轮换当次显示。
2. admin key 落地为独立 600 密钥文件（A1 决策），web console dev server 从文件自动注入。
3. `gateway.db` 权限 600、其父目录（`runtime/data`）700，启动时幂等收紧。
4. 管理 API 任何端点不再返回明文（向 `backend-routing.md §15` 契约收敛）。

## 3. 非目标

- 不轮换存量 5 把 key（A2 决策：hash 不变，客户端无感）。
- 不改 hash 算法（裸 sha256 + 256-bit 随机 secret，离线爆破不可行）。
- 不动 vestigial 的 `last_used_at` 列与死配置 `gateway.api_key`（无消费方，避免扩大 diff 面）。
- 前端功能代码不动（展示逻辑天然兼容 `plain_secret` 缺失），仅同步测试 fixtures。

## 4. 已拍板决策

| 决策 | 内容 |
|---|---|
| A1 | admin key 用独立 600 密钥文件 `runtime/data/admin.key`（跟随 `VLLM_CLAUDE_DB_PATH` 所在目录）：create/rotate-admin-key 时写入，迁移时从旧库抽取（仅文件缺失时），web console dev server 从文件读取注入。`control-plane.md §13` 旧决定"不再落地为 `runtime/data/web-console-admin.key`"更新为新语义：仅允许同目录 `admin.key` 这一种 600 文件落地形式。 |
| A2 | 存量 key 只清除明文、不轮换。客户端（Codex / claude / trae / claude-local）配置不变。 |

本设计新增决策：

- **删列而非置 NULL**：置 NULL 不能物理清除（明文仍在页内空闲区），且列在 = 未来任何 `SELECT *` / 旧代码都能再读出。环境为 SQLite 3.51.1（≥ 3.35 原生 DROP COLUMN），另有表重建兜底。
- **父目录 700**：已评估 `runtime/data/profiles/`（root 属主，docker 容器以 root 运行、CAP_DAC_OVERRIDE 绕过 DAC）与 `benchmarks/` 不受影响；crontab 为空、无其他用户服务消费。若未来有非属主用户需访问，降级 775 即可（显式决策点）。
- **`control migrate` 命令**：显式迁移入口 + 状态展示（列是否已删 / admin.key 存在性 / 权限 / hash 一致性）；迁移逻辑本身在 `init_db` 内，任何进程首次触库即幂等完成。
- **fail-fast 不降级**：迁移与 web console 注入均宁可启动失败并给出可操作文案，不留"明文已丢但 secret 拿不到"的不可感知窗口。

## 5. 方案

### 5.1 db 层（`llmnode/storage/db.py`）

1. `_ensure_columns` 字典删除 `"plain_secret": "TEXT"`（新库从此无此列）。
2. 新增迁移 `_migrate_api_keys_drop_plain_secret(conn, db_path)`，在 `init_db` 末尾、commit 前调用：
   - 幂等守卫：列不存在 → no-op。
   - **抽取先于破坏**：admin 行 `plain_secret IS NOT NULL` 时，先 `write_secret_file` 原子写入 `db_path.parent / "admin.key"`（同目录临时文件 → chmod 0600（硬失败）→ `os.replace` → 回读 hash 校验）；文件已存在但 hash 与 DB admin 行 `key_hash` 不匹配 → fail-fast，提示 `rotate-admin-key` 自愈（不静默覆盖、不自动轮换）。
   - 破坏：`sqlite3.sqlite_version_info >= (3, 35)` → `UPDATE api_keys SET plain_secret = NULL` → `ALTER TABLE api_keys DROP COLUMN plain_secret`；否则表重建兜底。
   - 物理清除：`VACUUM`（仅迁移时一次）；失败 fail-fast 并提示手动 `sqlite3 <db> 'VACUUM'`。
3. 停止一切读写：5 个 SELECT 去列；`_decode_api_key_row` 删 `plain_secret` 键；`create_api_key` / `update_api_key` 删 `plain_secret` 参数。
4. `init_db` 权限收紧（幂等、每次启动）：父目录 `chmod 0o700`、db 文件 `chmod 0o600`，均 `suppress(OSError)` best-effort（与 `write_secret_file` 的硬失败区分）；只 chmod db 直接父目录，不碰 `runtime/` 本身。

兼容性：新代码 SELECT 不含 `plain_secret` → 新代码 + 旧库（列还在）可运行，部署与迁移可分时段；删列后旧代码不可用 → **单向门**，迁移完成后禁止部署回旧版本。

### 5.2 API 层（`llmnode/api/app.py`）

- `_sanitize_api_key_row` 删除 `plain_secret` 字段 —— 一处修改同时封堵列表 / PATCH 回传 / POST 响应 `key` 对象三处泄漏。
- `POST /admin/keys`：`create_api_key(...)` 停止双写；响应 `"secret": secret` 一次性显示字段**保留**（契约既有语义：创建当次可见）。
- 鉴权链路（`proxy/router.py` hash-first）零改动。

### 5.3 admin key 文件与 CLI（`llmnode/security.py` + `llmnode/control.py`）

- `security.py` 新增 `write_secret_file(path, secret)`：原子写 + 0600（硬失败）+ 回读 hash 校验（失败删临时文件抛错）。db.py 迁移与 control.py 共用。
- 文件规格：`resolve_gateway_db_path().parent / "admin.key"`，单行 `sk-<64hex>\n`，读时 `.strip()`；读时自愈：权限非 600 → chmod 600。
- `_create_admin_key` 只管 DB（删两处 `plain_secret=secret`）；文件写入在 `_create_admin_key_action`（持有 db_path）：DB 成功后写文件，输出增 `key_file` 路径。rotate 走同一路径覆盖写。
- `_ensure_web_console_api_key` 重写：init_db → admin 行缺失 → 现有 "missing" 文案；文件缺失 → 报路径 + rotate 指引；hash 不匹配 → "out of sync" + rotate 指引；**保留 disabled admin 行自动激活逻辑**；返回文件 secret。
- 新增 `control migrate` 命令；`admin-key-status` 增 `key_file` / `key_file_sync` 两行。

### 5.4 web console

- 前端功能代码零改动：`store.tsx` 的 `plain_secret?` 与创建后 merge 保留（仅"当次创建"会话态）；`ApiKeysView` 展示/复制逻辑天然兼容缺失。
- 注入链路不变：`_start_web_console` 的 secret 来源从 DB 变为文件，`VITE_API_PROXY_KEY` 注入与 rotate 后 vite 自动重启机制复用。
- rotate 后在跑的 vite 进程持旧 key 会 401，直到重启 web-console（文档写明）。

## 6. 迁移顺序与回滚点（生产库含 5 把 key 明文）

| Step | 操作 | 回滚点 | 失败行为 |
|---|---|---|---|
| 0 | 备份 `gateway.db`（600） | **R0**：备份本身（含明文，收尾必须删除） | cp 失败即停 |
| 1 | 工作树实现 + pytest 全绿 | git 层回滚（不覆盖用户未提交工作） | — |
| 2 | 停 gateway / agent / web-console（VACUUM 需排他锁；后端容器可不停） | — | — |
| 3 | `python -m llmnode.control migrate`（抽取 → 校验 → NULL → DROP → VACUUM） | **R1**：任一步失败 DB 未被破坏（抽取先于删列 + 回读校验；文件已写但删列失败 = 文件存在 + DB 原样）；回滚 = 备份覆盖 | fail-fast + 可操作文案 |
| 4 | 验证：`PRAGMA table_info` 无列；权限 600/600/700；`grep -F <admin明文> gateway.db` 无匹配；`admin-key-status` 显示 sync=yes | 同 R1 | 不通过即停 |
| 5 | 起服务；`VITE_API_PROXY_KEY` == 文件内容；存量 inference key 请求 200（A2 无感）；admin key 请求 `/admin/keys` 200 且无 plain_secret | **R2**：key 链路异常 → `rotate-admin-key` 自愈；极端回 R1 | fail-fast 文案指引 |
| 6 | 收尾：删除 R0 备份（含明文）；删除一次性 spec/plan | — | — |

## 7. 验证标准

- `pytest tests/` 全绿，含新增 `tests/test_key_migration.py`：迁移删列 + admin.key 0600 + 内容正确 + 5 把 key_hash 不变 + **db 文件字节中不含任何遗留明文**（VACUUM 物理清除断言）+ 幂等 + out-of-sync 中止且列仍在 + init_db 权限 600/700。
- 管理 API 任何端点响应不含 `plain_secret`（列表 / PATCH / POST 三处回归）。
- 生产：`stat` 权限 600/600/700；`grep` 明文无匹配；存量 key 与 admin key 请求均 200。
