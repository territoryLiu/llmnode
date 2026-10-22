# API key hash-only 与文件权限收紧实施计划

对应 spec：[2026-08-18-api-key-hash-only-design.md](../specs/2026-08-18-api-key-hash-only-design.md)

## 阶段与文件清单（严格分层，db 层是地基）

### 阶段 2.1：db 层

`llmnode/storage/db.py`：

1. `_ensure_columns`（约 :189-197）字典删除 `"plain_secret": "TEXT"`
2. 新增 `_migrate_api_keys_drop_plain_secret(conn, db_path)`（init_db 末尾、commit 前调用）：
   - 幂等守卫：列不存在 → no-op
   - 抽取先于破坏：admin 行 `plain_secret IS NOT NULL` → `write_secret_file(db_path.parent / "admin.key", secret)`；文件已存在但 hash 不匹配 → fail-fast 提示 rotate
   - 破坏：SQLite ≥ 3.35 → NULL + `DROP COLUMN`；否则表重建兜底
   - 物理清除：`VACUUM`（仅迁移时一次，失败 fail-fast）
3. 停止一切读写：5 个 SELECT（约 :806/:819/:830/:842/:854）去列；`_decode_api_key_row`（约 :51-65）删 `plain_secret` 键；`create_api_key`（约 :773-813）/ `update_api_key`（约 :863-925）删 `plain_secret` 参数
4. `init_db`（约 :79）权限收紧：父目录 `chmod 0o700`、db 文件 `chmod 0o600`（`suppress(OSError)` best-effort，每次启动幂等）

`llmnode/security.py`：

- 新增 `write_secret_file(path, secret)`：同目录临时文件 → `os.chmod(0o600)`（**硬失败**）→ `os.replace` → 回读 hash 校验（失败删临时文件抛错）

检查点：手工建一个带 `plain_secret` 的旧库 → `init_db` → 列消失、admin.key 生成、VACUUM 后文件字节无明文。

### 阶段 2.2：API 层

`llmnode/api/app.py`（注意：本文件有 226 行未提交 SSE diff，用函数名锚点编辑）：

- `_sanitize_api_key_row`（约 :818-832）删除 `plain_secret` 字段（一处封堵三处泄漏）
- `POST /admin/keys`（约 :1731-1756）：`create_api_key(...)` 去掉 `plain_secret=secret`；响应 `"secret": secret` 保留

检查点：`pytest tests/test_admin_api_keys.py tests/test_auth_api_keys.py`（此阶段允许部分断言失败——明文断言在 2.5 统一改）。

### 阶段 2.3：admin key 文件 + CLI

`llmnode/control.py`：

- `_create_admin_key`（约 :235-261）：删两处 `plain_secret=secret`（函数只管 DB）
- `_create_admin_key_action`（约 :307-323）：DB 成功后 `write_secret_file(db_path.parent / "admin.key", secret)`，输出增 `key_file` 路径
- `_ensure_web_console_api_key`（约 :222-232）重写：init_db → admin 行（缺失 → 现有文案）→ 读文件（缺失 → 报路径 + rotate 指引）→ hash 校验（不匹配 → "out of sync" + rotate 指引）→ 保留 disabled 自动激活 → 返回文件 secret；读时自愈：权限非 600 → chmod 600
- `_create_inference_key`（约 :264-304）：删 `plain_secret=secret`（inference key 从不落文件，仅 CLI 一次性打印）
- 新增 `control migrate` 命令（`build_parser` choices + dispatch → `_migrate_action`）：`init_db` 触发迁移，打印列 / admin.key 存在性 / 权限 / hash 一致性
- `_admin_key_status_action`（约 :326 起）：增 `key_file` / `key_file_sync` 两行

检查点：CLI 手工 `create-admin-key` / `rotate-admin-key`（测试库）→ admin.key 内容正确、0600；`control migrate` 状态输出正确。

### 阶段 2.4：web console

- 功能代码零改动（`_start_web_console` 的 secret 来源自动变为文件，`VITE_API_PROXY_KEY` 注入与 vite 自动重启机制复用）
- 前端仅改 `web-console/src/pages/ConsoleViews.test.tsx` fixtures：删列表响应中的 `plain_secret`；"复制真实密钥"测试改"复制脱敏密钥"语义（vitest 本机未装，代码同步改、不本地跑）

### 阶段 2.5：统一测试（实现完成后统一写）

- `tests/test_storage_api_keys.py`：删 `plain_secret` 实参与断言，改 `assert "plain_secret" not in rows[0]`
- `tests/test_admin_api_keys.py`：:47 改 `"plain_secret" not in key_row`；POST 区补 `body["key"]` 无明文；PATCH 测试补无明文断言
- **新增 `tests/test_key_migration.py`**：
  - `_build_legacy_db(path)` 工具（raw SQL 建旧表 + 5 行）
  - 迁移删列 + admin.key 0600 + 内容正确 + 5 把 key_hash 不变 + db 字节无 `sk-legacy-*`（VACUUM 断言）
  - 幂等（两次 init_db）；out-of-sync → 抛错且列仍在；新库从无该列；init_db 权限 600/700
- `tests/test_control_web_console.py`：:45 重构为读文件语义；新增文件被删 / 内容被篡改 / disabled 行 + 有效文件
- `tests/test_control.py`：create/rotate 语义保持；新增 admin.key 内容 == secret、rotate 后 == 新 secret

检查点：`/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/ -q` 全绿。

### 阶段 2.6：文档回流

- `docs/contracts/control-plane.md` §12 / §13：:338 旧句改新语义（admin.key 600 文件）；新增 `migrate` 命令说明；§12 输出补 `key_file`
- `docs/process/run.md` §8：补 admin key 文件与 `control migrate` 用法、600/700 边界
- `docs/blueprint/current.md`：:233 更新新语义；补"api_keys 表已移除 plain_secret 列"与"后端容器端口绑定 127.0.0.1"
- `docs/contracts/backend-routing.md` §15：基本不改（与修复后一致），微调一句"创建响应仅当次返回 secret"

## 生产迁移（Step 2-5，停服务后执行）

```bash
PY=/home/heshan/.conda/envs/paper2any/bin/python
# Step 2: 停 gateway / agent / web-console
# Step 3:
$PY -m llmnode.control migrate
# Step 4:
sqlite3 runtime/data/gateway.db "PRAGMA table_info(api_keys);" | grep plain_secret   # 期望无输出
grep -cF '<已知admin明文>' runtime/data/gateway.db                                    # 期望 0
stat -c '%a %n' runtime/data/gateway.db runtime/data/admin.key runtime/data           # 600 600 700
$PY -m llmnode.control admin-key-status                                               # key_file_sync=yes
# Step 5: 起服务，存量 inference key 与 admin key 请求均 200，/admin/keys 响应无 plain_secret
# Step 6: 删除 R0 备份（含明文）；删除本 spec/plan
```

## 完成条件

- pytest 全绿
- 生产库 `plain_secret` 列已删、字节无明文、权限 600/600/700
- web console 自动注入走文件链路
- 文档回流完成，一次性 spec/plan 删除
