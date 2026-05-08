# API Key Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable V2 API key control plane: database-backed keys, bootstrap admin fallback, admin CRUD, and request-log identity linkage, without pulling V3 or V4 platform scope into the current repo.

**Architecture:** Keep the current FastAPI + SQLite layout. Treat `gateway.api_key` as a long-lived break-glass admin key, persist hashed database keys in `llmnode/storage/db.py`, resolve auth once at request entry, and thread the resolved principal through both admin and inference handlers. Store quota-related fields now for forward compatibility, but do not implement per-key concurrency or RPM enforcement in this phase.

**Tech Stack:** Python 3.11, FastAPI, SQLite, Pydantic, httpx, pytest

---

## Scope Guardrails

- This plan targets **V2 API Key Phase 1** only.
- Follow repo rhythm from `AGENTS.md`: implement first, then add and run tests in one verification block near the end.
- Use `docs/superpowers/specs/2026-05-08-v2-api-key-design.md` as the detailed contract during implementation.
- Keep `GatewayContext.api_key` as the existing bootstrap key field in this slice; do not rename it unless doing so becomes necessary for correctness.
- Prefer focused helpers over broad refactors. `llmnode/api/app.py` is already monolithic; improve it only where API key work directly needs it.

### Phase 1 Includes

- `api_keys` persistence and CRUD
- bootstrap `gateway.api_key` as break-glass admin key
- database-backed auth for `/v1/*` and `/admin/*`
- `admin` / `inference` scope enforcement
- request log linkage with `api_key_id`
- minimal audit source field that distinguishes bootstrap from database-key access

### Deferred to Later Phases

- per-key concurrency enforcement
- precise RPM time-window enforcement
- key rotation or regenerate-secret flow
- richer role hierarchy beyond `admin` and `inference`
- `web-console` API key CRUD page
- soft-delete or audit archive strategy
- PostgreSQL migration

### File Map

- `llmnode/storage/db.py`: SQLite schema, row decoding, API key CRUD helpers, request-log field expansion
- `llmnode/security.py`: secret generation and SHA-256 hashing helpers
- `llmnode/proxy/router.py`: token extraction, auth resolution, scope checks, auth context model
- `llmnode/api/app.py`: endpoint auth wiring, admin API key CRUD endpoints, request log writes
- `README.md`: operator usage examples for bootstrap key and database-backed inference key
- `docs/blueprintV2.md`: V2 status sync after backend work is done
- `tests/test_storage_api_keys.py`: storage CRUD coverage
- `tests/test_auth_api_keys.py`: bootstrap and database-key auth coverage
- `tests/test_admin_api_keys.py`: admin CRUD endpoint coverage
- `tests/test_request_logs_api_keys.py`: request-log identity coverage

### Task 1: Add API key storage primitives

**Files:**
- Modify: `llmnode/storage/db.py`
- Reference: `docs/superpowers/specs/2026-05-08-v2-api-key-design.md`

- [ ] **Step 1: Add the `api_keys` table to `init_db`**

Add this exact table:

```sql
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    scopes TEXT NOT NULL,
    rpm_limit INTEGER,
    concurrency_limit INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    disabled_at TEXT,
    last_used_at TEXT,
    note TEXT
)
```

Keep the existing SQLite setup style used by `request_logs`, `agent_events`, `model_routes`, and `schedule_config`. Do not add migration machinery in this phase.

- [ ] **Step 2: Add an internal row decoder**

Inside `llmnode/storage/db.py`, add one focused helper that converts an `api_keys` row into:

```python
{
    "id": 1,
    "key_hash": "sha256hex",
    "name": "console-admin",
    "status": "active",
    "scopes": ["admin"],
    "rpm_limit": None,
    "concurrency_limit": None,
    "created_at": "2026-05-08 12:00:00",
    "disabled_at": None,
    "last_used_at": None,
    "note": "main console key",
}
```

Rules:
- decode `scopes` from JSON text
- preserve nullable fields as `None`
- do not drop `key_hash` at the storage layer; sanitizing happens later at the API layer

- [ ] **Step 3: Add storage APIs for CRUD and lookup**

Add these functions:

```python
def create_api_key(
    conn: sqlite3.Connection,
    *,
    name: str,
    key_hash: str,
    scopes: list[str],
    rpm_limit: int | None = None,
    concurrency_limit: int | None = None,
    status: str = "active",
    note: str | None = None,
) -> dict[str, Any]: ...


def list_api_keys(conn: sqlite3.Connection) -> list[dict[str, Any]]: ...


def get_api_key_by_hash(conn: sqlite3.Connection, key_hash: str) -> dict[str, Any] | None: ...


def get_api_key_by_id(conn: sqlite3.Connection, key_id: int) -> dict[str, Any] | None: ...


def update_api_key(
    conn: sqlite3.Connection,
    key_id: int,
    *,
    name: str | None = None,
    status: str | None = None,
    scopes: list[str] | None = None,
    rpm_limit: int | None = None,
    concurrency_limit: int | None = None,
    note: str | None = None,
) -> dict[str, Any] | None: ...


def delete_api_key(conn: sqlite3.Connection, key_id: int) -> bool: ...
```

Implementation rules:
- `create_api_key` stores `scopes` as JSON text with `ensure_ascii=False`
- `update_api_key` sets `disabled_at` when `status="disabled"`
- `update_api_key` clears `disabled_at` when `status="active"`
- `delete_api_key` returns `True` only when a row was actually removed

- [ ] **Step 4: Keep quota fields storage-only in this phase**

Persist `rpm_limit` and `concurrency_limit`, but do not enforce them yet. The purpose of this task is schema completeness and CRUD support, not runtime quota behavior.

- [ ] **Step 5: Commit**

```bash
git add llmnode/storage/db.py
git commit -m "feat: add api key storage primitives"
```

### Task 2: Resolve auth contexts instead of static string equality

**Files:**
- Create: `llmnode/security.py`
- Modify: `llmnode/proxy/router.py`
- Modify: `llmnode/api/app.py`
- Reference: `docs/superpowers/specs/2026-05-08-v2-api-key-design.md`

- [ ] **Step 1: Add key hashing and secret helpers**

Create `llmnode/security.py` with:

```python
def hash_api_key(secret: str) -> str: ...


def generate_api_key(prefix: str = "ln_live") -> str: ...
```

Implementation rules:
- `hash_api_key` uses SHA-256 hex digest over UTF-8 bytes
- `generate_api_key` returns a high-entropy printable secret such as `ln_live_7e2c3f2b0c1d4a6e9f8a123456789abc`
- do not add reversible encryption or external secret storage

- [ ] **Step 2: Replace `authorize(...)` with auth resolution helpers**

In `llmnode/proxy/router.py`, keep the existing proxy helpers, but replace the current static equality check with:

```python
@dataclass
class AuthContext:
    source: str
    api_key_id: int | None
    name: str
    scopes: list[str]
    rpm_limit: int | None
    concurrency_limit: int | None
```

Add these helpers:

```python
def extract_api_token(auth_header: str | None, x_api_key: str | None) -> str: ...


def resolve_auth_context(
    auth_header: str | None,
    x_api_key: str | None,
    *,
    bootstrap_key: str,
    db: sqlite3.Connection,
) -> AuthContext: ...


def require_scope(auth: AuthContext, scope: str) -> None: ...
```

Behavior:
- missing token => `401`
- bootstrap token match => `AuthContext(source="bootstrap", api_key_id=None, name="bootstrap", scopes=["admin", "inference"], rpm_limit=None, concurrency_limit=None)`
- database token => hash token, query `api_keys`, reject missing rows with `401`
- disabled database key => `401`
- scope mismatch => `403`

- [ ] **Step 3: Keep bootstrap behavior compatible**

Do not remove `gateway.api_key`. In this slice it remains the long-lived break-glass admin key and must:
- access all `/admin/*`
- access all `/v1/*`
- never appear in `/admin/keys`
- log with `api_key_id = null`

- [ ] **Step 4: Thread the resolved auth through request handlers**

In `llmnode/api/app.py`, resolve auth once per request and reuse it for:
- `/v1/models`
- `/v1/chat/completions`
- `/v1/messages`
- `/admin/status`
- `/admin/stream`
- `/admin/request-logs`
- `/admin/models`
- `/admin/schedule`
- the new `/admin/keys` endpoints added in Task 3

Scope rules:
- `/admin/*` requires `admin`
- `/v1/*` requires `inference`
- `admin` also counts as satisfying `inference`

- [ ] **Step 5: Commit**

```bash
git add llmnode/security.py llmnode/proxy/router.py llmnode/api/app.py
git commit -m "feat: add db-backed api key authentication"
```

### Task 3: Add backend admin API key CRUD endpoints

**Files:**
- Modify: `llmnode/api/app.py`
- Modify: `llmnode/storage/db.py`
- Reference: `docs/superpowers/specs/2026-05-08-v2-api-key-design.md`
- Reference: `docs/blueprintV2.md`

- [ ] **Step 1: Add minimal request validation helpers in `app.py`**

Keep the current repo style and avoid a large schema refactor. Add small local helpers in `llmnode/api/app.py` that validate:
- `name` is a non-empty string
- `scopes` is a non-empty list
- every scope is one of `admin` or `inference`
- `status` is one of `active` or `disabled`
- `rpm_limit` and `concurrency_limit`, when present, are positive integers

Return `400` on invalid admin payloads.

- [ ] **Step 2: Implement `GET /admin/keys`**

Return sanitized rows from `list_api_keys(...)`:

```json
{
  "keys": [
    {
      "id": 1,
      "name": "console-admin",
      "status": "active",
      "scopes": ["admin"],
      "rpm_limit": null,
      "concurrency_limit": null,
      "created_at": "2026-05-08 12:00:00",
      "disabled_at": null,
      "last_used_at": null,
      "note": "main console key"
    }
  ]
}
```

Do not return:
- plaintext secret
- `key_hash`

- [ ] **Step 3: Implement `POST /admin/keys`**

Behavior:
- require `admin` scope
- generate a fresh secret with `generate_api_key()`
- hash it before storage
- create a database row with default `status="active"`
- return the secret exactly once

Example response:

```json
{
  "key": {
    "id": 1,
    "name": "console-admin",
    "status": "active",
    "scopes": ["admin"],
    "rpm_limit": null,
    "concurrency_limit": null,
    "created_at": "2026-05-08 12:00:00",
    "disabled_at": null,
    "last_used_at": null,
    "note": "main console key"
  },
  "secret": "ln_live_7e2c3f2b0c1d4a6e9f8a123456789abc"
}
```

- [ ] **Step 4: Implement `PATCH /admin/keys/{id}` and `DELETE /admin/keys/{id}`**

`PATCH` should support:
- `name`
- `status`
- `scopes`
- `rpm_limit`
- `concurrency_limit`
- `note`

`DELETE` should:
- physically remove the database row in Phase 1
- return `404` when the id does not exist

Do not add:
- key rotation
- bootstrap key deletion
- soft delete
- restore endpoints

- [ ] **Step 5: Keep front-end work out of this slice**

Do not modify `web-console` in this phase. The backend must be usable first via direct admin API calls and the existing bootstrap key.

- [ ] **Step 6: Commit**

```bash
git add llmnode/api/app.py llmnode/storage/db.py
git commit -m "feat: add admin api key crud"
```

### Task 4: Link request logs to API key identity

**Files:**
- Modify: `llmnode/storage/db.py`
- Modify: `llmnode/api/app.py`

- [ ] **Step 1: Extend `request_logs` schema minimally**

Add these columns to the table definition:

```sql
api_key_id INTEGER,
auth_source TEXT,
client_ip TEXT,
user_agent TEXT
```

Do not add token accounting, latency histograms, or quota counters in this phase.

- [ ] **Step 2: Extend the log writer and list APIs**

Update:
- `write_request_log(...)`
- `list_request_logs(...)`

New log fields should include:
- `api_key_id`
- `auth_source`
- `client_ip`
- `user_agent`

Behavior:
- bootstrap requests => `api_key_id=None`, `auth_source="bootstrap"`
- database-key requests => `api_key_id=<row id>`, `auth_source="db"`

- [ ] **Step 3: Pass auth identity from business handlers**

Update all OpenAI and Anthropic request-log write sites in `llmnode/api/app.py` so every success, rejection, timeout, or streaming-start log entry carries:
- resolved `api_key_id`
- resolved `auth_source`
- `request.client.host` when available
- `request.headers.get("user-agent")`

Do not add separate admin request auditing yet.

- [ ] **Step 4: Defer `last_used_at` writes**

Keep `last_used_at` in the schema, but do not update it in Phase 1. That keeps this slice focused on authentication, CRUD, and request-log linkage.

- [ ] **Step 5: Commit**

```bash
git add llmnode/storage/db.py llmnode/api/app.py
git commit -m "feat: link request logs to api key identity"
```

### Task 5: Sync project docs to the real Phase 1 outcome

**Files:**
- Modify: `README.md`
- Modify: `docs/blueprintV2.md`
- Reference: `docs/superpowers/specs/2026-05-08-v2-api-key-design.md`

- [ ] **Step 1: Update README usage examples**

Add one concise operator flow:
- use bootstrap key to call `POST /admin/keys`
- receive a one-time database-backed secret
- use the new inference key on `GET /v1/models`

Use current API paths and the project Python environment in examples.

- [ ] **Step 2: Update `docs/blueprintV2.md` status sections**

Sync these sections with the real code state:
- `## 14. 当前已落地`
- `## 15. 当前未完成`
- `## 16. 验收口径`
- `## 16. 验收标准`

Most important alignment points:
- API key CRUD becomes landed
- bootstrap admin key remains intentionally present
- per-key concurrency and RPM stay future work unless they were actually implemented
- front-end API key management page stays future work if untouched

- [ ] **Step 3: Update the detailed spec only if code intentionally diverged**

If the final code differs from `docs/superpowers/specs/2026-05-08-v2-api-key-design.md`, update the spec so it stays authoritative. If code matched the spec closely enough, leave the spec unchanged.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/blueprintV2.md docs/superpowers/specs/2026-05-08-v2-api-key-design.md
git commit -m "docs: sync api key phase1 behavior"
```

### Task 6: Add and run backend tests after implementation

**Files:**
- Create: `tests/test_storage_api_keys.py`
- Create: `tests/test_auth_api_keys.py`
- Create: `tests/test_admin_api_keys.py`
- Create: `tests/test_request_logs_api_keys.py`
- Reference: `tests/test_api_openai.py`
- Reference: `tests/test_api_anthropic.py`
- Reference: `tests/conftest.py`

- [ ] **Step 1: Add storage tests**

Cover at least:
- create and list keys
- lookup by hash
- patch status to `disabled` and back to `active`
- delete key
- `scopes` JSON round-trip

- [ ] **Step 2: Add auth tests**

Cover at least:
- bootstrap key can reach `/admin/status`
- bootstrap key can reach `/v1/models`
- database inference key can reach `/v1/models`
- database inference key gets `403` on `/admin/status`
- disabled database key gets `401`

- [ ] **Step 3: Add admin CRUD tests**

Cover at least:
- admin can create a key and receives one-time `secret`
- `GET /admin/keys` hides `key_hash` and never returns `secret`
- admin can patch `status` and `scopes`
- admin can delete a key
- non-admin key cannot use `/admin/keys`

- [ ] **Step 4: Add request-log identity tests**

Cover at least:
- database-key business request writes its `api_key_id`
- bootstrap-key business request writes `api_key_id is None`
- `auth_source` is `"db"` or `"bootstrap"` as expected

- [ ] **Step 5: Run the targeted backend suite**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest \
  tests/test_storage_api_keys.py \
  tests/test_auth_api_keys.py \
  tests/test_admin_api_keys.py \
  tests/test_request_logs_api_keys.py \
  tests/test_api_openai.py \
  tests/test_api_anthropic.py -q
```

Expected:
- new API key tests pass
- existing OpenAI and Anthropic endpoint tests still pass

- [ ] **Step 6: Run the full backend suite**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest -q
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/test_storage_api_keys.py tests/test_auth_api_keys.py tests/test_admin_api_keys.py tests/test_request_logs_api_keys.py
git commit -m "test: cover api key phase1 flows"
```

## Phase 2 Backlog

Only start the next plan after Phase 1 is implemented and verified.

- per-key concurrency integrated with the current queue semantics
- RPM enforcement with a clear 60-second window rule
- `web-console/src/views/ApiKeysView.vue` real CRUD UI
- per-key usage analytics and richer audit fields
- key rotation or regenerate-secret flow
