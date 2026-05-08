<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { useOverviewStore } from '@/stores/overview'
import type { AdminApiKeyCreatePayload, AdminApiKeyEntry, AdminApiKeyUpdatePayload } from '@/types'

type ApiKeyDraft = {
  name: string
  scopes: string[]
  rpm_limit: number | null
  concurrency_limit: number | null
  note: string
}

const store = useOverviewStore()

const loading = ref(false)
const saving = ref(false)
const actionKeyId = ref<number | null>(null)
const editingKeyId = ref<number | null>(null)
const keys = ref<AdminApiKeyEntry[]>([])
const lastSecret = ref('')
const lastCreatedName = ref('')
const statusFilter = ref<'all' | 'active' | 'disabled'>('all')
const scopeFilter = ref<'all' | 'admin' | 'inference'>('all')
const keywordFilter = ref('')
const sortField = ref<'created_at' | 'status' | 'rpm_limit' | 'concurrency_limit'>('created_at')
const sortDirection = ref<'desc' | 'asc'>('desc')
const drafts = reactive<Record<number, ApiKeyDraft>>({})

const createForm = reactive<AdminApiKeyCreatePayload>({
  name: '',
  scopes: ['inference'],
  rpm_limit: null,
  concurrency_limit: null,
  note: '',
})

const activeCount = computed(() => keys.value.filter((item) => item.status === 'active').length)
const inferenceCount = computed(() => keys.value.filter((item) => item.scopes.includes('inference')).length)
const adminCount = computed(() => keys.value.filter((item) => item.scopes.includes('admin')).length)
const filteredKeys = computed(() => {
  const items = keys.value.filter((item) => {
    if (statusFilter.value !== 'all' && item.status !== statusFilter.value) {
      return false
    }
    if (scopeFilter.value !== 'all' && !item.scopes.includes(scopeFilter.value)) {
      return false
    }
    const keyword = keywordFilter.value.trim().toLowerCase()
    if (!keyword) {
      return true
    }
    return [item.name, item.note ?? ''].some((value) => value.toLowerCase().includes(keyword))
  })

  const direction = sortDirection.value === 'asc' ? 1 : -1
  return [...items].sort((left, right) => {
    switch (sortField.value) {
      case 'status':
        return left.status.localeCompare(right.status) * direction
      case 'rpm_limit':
        return ((left.rpm_limit ?? Number.MAX_SAFE_INTEGER) - (right.rpm_limit ?? Number.MAX_SAFE_INTEGER)) * direction
      case 'concurrency_limit':
        return (
          ((left.concurrency_limit ?? Number.MAX_SAFE_INTEGER) - (right.concurrency_limit ?? Number.MAX_SAFE_INTEGER)) *
          direction
        )
      case 'created_at':
      default:
        return left.created_at.localeCompare(right.created_at) * direction
    }
  })
})

function buildDraft(row: AdminApiKeyEntry): ApiKeyDraft {
  return {
    name: row.name,
    scopes: [...row.scopes],
    rpm_limit: row.rpm_limit,
    concurrency_limit: row.concurrency_limit,
    note: row.note ?? '',
  }
}

function syncDrafts(items: AdminApiKeyEntry[]) {
  const validIds = new Set(items.map((item) => item.id))
  for (const item of items) {
    drafts[item.id] = buildDraft(item)
  }
  for (const key of Object.keys(drafts)) {
    const id = Number(key)
    if (!validIds.has(id)) {
      delete drafts[id]
    }
  }
}

function ensureDraft(row: AdminApiKeyEntry) {
  if (!drafts[row.id]) {
    drafts[row.id] = buildDraft(row)
  }
  return drafts[row.id]
}

function isEditing(row: AdminApiKeyEntry) {
  return editingKeyId.value === row.id
}

async function loadKeys() {
  loading.value = true
  try {
    const response = await store.fetchApiKeys()
    keys.value = response.keys
    syncDrafts(response.keys)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  } finally {
    loading.value = false
  }
}

function resetCreateForm() {
  createForm.name = ''
  createForm.scopes = ['inference']
  createForm.rpm_limit = null
  createForm.concurrency_limit = null
  createForm.note = ''
}

function startEdit(row: AdminApiKeyEntry) {
  drafts[row.id] = buildDraft(row)
  editingKeyId.value = row.id
}

function cancelEdit(row: AdminApiKeyEntry) {
  drafts[row.id] = buildDraft(row)
  if (editingKeyId.value === row.id) {
    editingKeyId.value = null
  }
}

function normalizeNote(value: string) {
  return value.trim() ? value.trim() : null
}

function validateDraft(row: AdminApiKeyEntry) {
  const draft = ensureDraft(row)
  if (!draft.name.trim()) {
    ElMessage.warning('Key 名称不能为空')
    return false
  }
  if (draft.scopes.length === 0) {
    ElMessage.warning('至少选择一个 scope')
    return false
  }
  return true
}

async function createKey() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请先填写 key 名称')
    return
  }
  if (createForm.scopes.length === 0) {
    ElMessage.warning('至少选择一个 scope')
    return
  }
  saving.value = true
  try {
    const payload: AdminApiKeyCreatePayload = {
      name: createForm.name.trim(),
      scopes: [...createForm.scopes],
      rpm_limit: createForm.rpm_limit,
      concurrency_limit: createForm.concurrency_limit,
      note: normalizeNote(createForm.note ?? ''),
    }
    const response = await store.createApiKey(payload)
    lastSecret.value = response.secret
    lastCreatedName.value = response.key.name
    resetCreateForm()
    await loadKeys()
    ElMessage.success('API Key 已创建')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  } finally {
    saving.value = false
  }
}

async function saveRow(row: AdminApiKeyEntry) {
  if (!validateDraft(row)) {
    return
  }
  const draft = ensureDraft(row)
  actionKeyId.value = row.id
  try {
    const payload: AdminApiKeyUpdatePayload = {
      name: draft.name.trim(),
      scopes: [...draft.scopes],
      rpm_limit: draft.rpm_limit,
      concurrency_limit: draft.concurrency_limit,
      note: normalizeNote(draft.note),
    }
    await store.updateApiKey(row.id, payload)
    editingKeyId.value = null
    await loadKeys()
    ElMessage.success('Key 配置已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  } finally {
    actionKeyId.value = null
  }
}

async function toggleStatus(row: AdminApiKeyEntry) {
  actionKeyId.value = row.id
  try {
    await store.updateApiKey(row.id, {
      status: row.status === 'active' ? 'disabled' : 'active',
    })
    if (editingKeyId.value === row.id) {
      editingKeyId.value = null
    }
    await loadKeys()
    ElMessage.success(row.status === 'active' ? 'Key 已禁用' : 'Key 已启用')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  } finally {
    actionKeyId.value = null
  }
}

async function removeKey(row: AdminApiKeyEntry) {
  actionKeyId.value = row.id
  try {
    await store.deleteApiKey(row.id)
    if (editingKeyId.value === row.id) {
      editingKeyId.value = null
    }
    await loadKeys()
    ElMessage.success('Key 已删除')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  } finally {
    actionKeyId.value = null
  }
}

async function copySecret() {
  if (!lastSecret.value) {
    return
  }
  try {
    await navigator.clipboard.writeText(lastSecret.value)
    ElMessage.success('secret 已复制到剪贴板')
  } catch {
    ElMessage.warning('当前环境不支持自动复制，请手动复制 secret')
  }
}

onMounted(async () => {
  await loadKeys()
})
</script>

<template>
  <section class="page-stack">
    <section class="kpi-grid">
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">数据库 Key 数</span>
        <strong>{{ keys.length }}</strong>
        <small>不包含 bootstrap 管理员 key</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">活跃 Key</span>
        <strong>{{ activeCount }}</strong>
        <small>status = active</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">推理 Scope</span>
        <strong>{{ inferenceCount }}</strong>
        <small>可访问 `/v1/*`</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">管理 Scope</span>
        <strong>{{ adminCount }}</strong>
        <small>可访问 `/admin/*`</small>
      </article>
    </section>

    <section class="keys-grid">
      <article class="surface-card key-form-card">
        <div class="table-card__head">
          <div>
            <p class="table-card__eyebrow">创建新 Key</p>
            <h3>数据库 API Key</h3>
          </div>
          <span>bootstrap key 不在列表内</span>
        </div>

        <div class="form-grid form-grid--keys">
          <el-input v-model="createForm.name" placeholder="如 console-admin / ci-runner" />
          <el-select v-model="createForm.scopes" multiple collapse-tags placeholder="选择 scope">
            <el-option label="inference" value="inference" />
            <el-option label="admin" value="admin" />
          </el-select>
          <el-input-number v-model="createForm.rpm_limit" :min="1" :step="1" placeholder="RPM" />
          <el-input-number
            v-model="createForm.concurrency_limit"
            :min="1"
            :step="1"
            placeholder="Concurrency"
          />
        </div>

        <div class="form-grid form-grid--keys-secondary">
          <el-input
            v-model="createForm.note"
            placeholder="备注，如 local cli / ops emergency"
          />
          <div class="key-form-card__hint">
            <strong>运行时说明</strong>
            <p>当前 `rpm_limit` 与 `concurrency_limit` 已接入运行时准入，数据库 key 会在全局队列前先做单 key 校验。</p>
          </div>
        </div>

        <div class="form-actions">
          <el-button @click="resetCreateForm">重置</el-button>
          <el-button type="primary" :loading="saving" @click="createKey">创建 Key</el-button>
        </div>
      </article>

      <article class="surface-card secret-card">
        <div class="table-card__head">
          <div>
            <p class="table-card__eyebrow">一次性 Secret</p>
            <h3>最近创建结果</h3>
          </div>
        </div>

        <div v-if="lastSecret" class="secret-card__body">
          <span class="secret-card__label">{{ lastCreatedName }}</span>
          <code class="secret-card__value">{{ lastSecret }}</code>
          <p>明文 secret 只会返回一次。数据库中仅保存 `key_hash`。</p>
          <div class="secret-card__actions">
            <el-button type="primary" plain @click="copySecret">复制 secret</el-button>
            <el-button text @click="lastSecret = ''">清空展示</el-button>
          </div>
        </div>
        <div v-else class="empty-state empty-state--secret">
          创建新 key 后，这里会显示最近一次返回的明文 secret。
        </div>
      </article>
    </section>

    <section class="surface-card table-card table-card--keys">
      <div class="table-card__head">
        <div>
          <p class="table-card__eyebrow">已创建 Key</p>
          <h3>数据库 Key 列表</h3>
        </div>
        <div class="keys-table__meta">
          <span>{{ loading ? '刷新中…' : `${filteredKeys.length} / ${keys.length} keys` }}</span>
          <el-button text @click="loadKeys">刷新</el-button>
        </div>
      </div>

      <div class="keys-filter-bar">
        <el-select v-model="statusFilter" class="keys-filter-bar__field">
          <el-option label="全部状态" value="all" />
          <el-option label="active" value="active" />
          <el-option label="disabled" value="disabled" />
        </el-select>
        <el-select v-model="scopeFilter" class="keys-filter-bar__field">
          <el-option label="全部 scope" value="all" />
          <el-option label="admin" value="admin" />
          <el-option label="inference" value="inference" />
        </el-select>
        <el-input
          v-model="keywordFilter"
          class="keys-filter-bar__search"
          placeholder="搜索名称或备注"
          clearable
        />
        <el-select v-model="sortField" class="keys-filter-bar__field">
          <el-option label="按创建时间" value="created_at" />
          <el-option label="按状态" value="status" />
          <el-option label="按 RPM" value="rpm_limit" />
          <el-option label="按并发" value="concurrency_limit" />
        </el-select>
        <el-select v-model="sortDirection" class="keys-filter-bar__field">
          <el-option label="降序" value="desc" />
          <el-option label="升序" value="asc" />
        </el-select>
      </div>

      <el-table :data="filteredKeys" height="420" v-loading="loading">
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <el-input v-if="isEditing(row)" v-model="ensureDraft(row).name" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" effect="light">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Scopes" min-width="210">
          <template #default="{ row }">
            <el-select
              v-if="isEditing(row)"
              v-model="ensureDraft(row).scopes"
              multiple
              collapse-tags
              class="inline-scope-select"
            >
              <el-option label="inference" value="inference" />
              <el-option label="admin" value="admin" />
            </el-select>
            <div v-else class="scope-badges">
              <span v-for="scope in row.scopes" :key="scope" class="scope-badge">{{ scope }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="RPM" width="120">
          <template #default="{ row }">
            <el-input-number
              v-if="isEditing(row)"
              v-model="ensureDraft(row).rpm_limit"
              :min="1"
              :step="1"
              placeholder="无限制"
            />
            <span v-else>{{ row.rpm_limit ?? '无限制' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="并发" width="120">
          <template #default="{ row }">
            <el-input-number
              v-if="isEditing(row)"
              v-model="ensureDraft(row).concurrency_limit"
              :min="1"
              :step="1"
              placeholder="无限制"
            />
            <span v-else>{{ row.concurrency_limit ?? '无限制' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="170" />
        <el-table-column label="备注" min-width="220">
          <template #default="{ row }">
            <el-input
              v-if="isEditing(row)"
              v-model="ensureDraft(row).note"
              placeholder="备注"
            />
            <span v-else>{{ row.note || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="280" fixed="right">
          <template #default="{ row }">
            <div class="row-actions row-actions--dense">
              <template v-if="isEditing(row)">
                <el-button
                  type="primary"
                  text
                  :loading="actionKeyId === row.id"
                  @click="saveRow(row)"
                >
                  保存
                </el-button>
                <el-button text :disabled="actionKeyId === row.id" @click="cancelEdit(row)">取消</el-button>
              </template>
              <template v-else>
                <el-button
                  type="primary"
                  text
                  :loading="actionKeyId === row.id"
                  @click="startEdit(row)"
                >
                  编辑
                </el-button>
              </template>
              <el-button
                type="primary"
                text
                :loading="actionKeyId === row.id"
                @click="toggleStatus(row)"
              >
                {{ row.status === 'active' ? '禁用' : '启用' }}
              </el-button>
              <el-button
                type="danger"
                text
                :loading="actionKeyId === row.id"
                @click="removeKey(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </section>
</template>
