<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'

import { useOverviewStore } from '@/stores/overview'

const store = useOverviewStore()
const { apiKey, apiBase, snapshot } = storeToRefs(store)

const rows = computed(() => snapshot.value?.logs ?? [])
const statusFilter = ref<'all' | 'ok' | 'rejected' | 'timeout' | 'streaming'>('all')
const protocolFilter = ref<'all' | 'openai' | 'anthropic'>('all')
const rejectionFilter = ref<
  'all' | 'rpm_limit_exceeded' | 'concurrency_limit_exceeded' | 'queue_full' | 'queue_timeout'
>('all')
const keywordFilter = ref('')

const filteredRows = computed(() =>
  rows.value.filter((item) => {
    if (statusFilter.value !== 'all' && item.status !== statusFilter.value) {
      return false
    }
    if (protocolFilter.value !== 'all' && item.protocol !== protocolFilter.value) {
      return false
    }
    if (rejectionFilter.value !== 'all' && item.rejection_reason !== rejectionFilter.value) {
      return false
    }
    const keyword = keywordFilter.value.trim().toLowerCase()
    if (!keyword) {
      return true
    }
    return [
      item.request_id,
      item.model_name,
      item.error_message ?? '',
      item.client_ip ?? '',
      item.user_agent ?? '',
      item.rejection_reason ?? '',
    ].some((value) => value.toLowerCase().includes(keyword))
  }),
)

const errors = computed(() => filteredRows.value.filter((item) => item.status !== 'ok').length)
const rejected = computed(() => filteredRows.value.filter((item) => item.status === 'rejected').length)

function sourceLabel(value: string | null | undefined) {
  if (value === 'bootstrap') {
    return 'bootstrap'
  }
  if (value === 'db') {
    return 'db key'
  }
  return 'unknown'
}

async function refresh() {
  await store.fetchSnapshot()
}

async function reconnect() {
  await store.fetchSnapshot()
  void store.connectStream()
}
</script>

<template>
  <section class="page-stack">
    <section class="kpi-grid">
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">总请求数</span>
        <strong>{{ rows.length }}</strong>
        <small>当前抓取到的审计记录</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">异常请求</span>
        <strong>{{ errors }}</strong>
        <small>非 `ok` 状态</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">拒绝请求</span>
        <strong>{{ rejected }}</strong>
        <small>状态 = rejected</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">后台类型</span>
        <strong>{{ snapshot?.backend_type ?? 'vllm' }}</strong>
        <small>当前唯一运行后端</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">SSE 状态</span>
        <strong>{{ store.streamConnected ? '在线' : '离线' }}</strong>
        <small>实时刷新状态</small>
      </article>
    </section>

    <section class="surface-card filter-card">
      <div class="filter-card__left">
        <el-input v-model="apiKey" show-password placeholder="管理员 API key">
          <template #prepend>API Key</template>
        </el-input>
        <el-input v-model="apiBase" placeholder="API base，默认同源">
          <template #prepend>Base</template>
        </el-input>
      </div>
      <div class="filter-card__right">
        <el-button @click="refresh">刷新</el-button>
        <el-button type="primary" @click="reconnect">重连 SSE</el-button>
      </div>
    </section>

    <section class="surface-card filter-card">
      <div class="filter-card__left">
        <el-select v-model="statusFilter" class="records-filter__field">
          <el-option label="全部状态" value="all" />
          <el-option label="ok" value="ok" />
          <el-option label="rejected" value="rejected" />
          <el-option label="timeout" value="timeout" />
          <el-option label="streaming" value="streaming" />
        </el-select>
        <el-select v-model="protocolFilter" class="records-filter__field">
          <el-option label="全部协议" value="all" />
          <el-option label="openai" value="openai" />
          <el-option label="anthropic" value="anthropic" />
        </el-select>
        <el-select v-model="rejectionFilter" class="records-filter__field">
          <el-option label="全部拒绝原因" value="all" />
          <el-option label="rpm_limit_exceeded" value="rpm_limit_exceeded" />
          <el-option label="concurrency_limit_exceeded" value="concurrency_limit_exceeded" />
          <el-option label="queue_full" value="queue_full" />
          <el-option label="queue_timeout" value="queue_timeout" />
        </el-select>
      </div>
      <div class="filter-card__right records-filter__search">
        <el-input v-model="keywordFilter" clearable placeholder="搜索 request id / model / error / client" />
      </div>
    </section>

    <section class="surface-card table-card">
      <div class="table-card__head">
        <div>
          <p class="table-card__eyebrow">使用记录</p>
          <h3>API 审计明细</h3>
        </div>
        <span>显示 {{ filteredRows.length }} / {{ rows.length }} 条</span>
      </div>

      <el-table :data="filteredRows" height="560">
        <el-table-column prop="created_at" label="时间" min-width="170" />
        <el-table-column prop="request_id" label="Request ID" min-width="180" />
        <el-table-column prop="protocol" label="协议" width="120" />
        <el-table-column prop="model_name" label="模型" min-width="180" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column label="来源" min-width="150">
          <template #default="{ row }">
            <div class="log-meta-cell">
              <strong>{{ sourceLabel(row.auth_source) }}</strong>
              <small>{{ row.api_key_id ?? '—' }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="拒绝原因" min-width="180">
          <template #default="{ row }">
            <span>{{ row.rejection_reason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误" min-width="240" />
        <el-table-column label="客户端" min-width="200">
          <template #default="{ row }">
            <div class="log-meta-cell">
              <strong>{{ row.client_ip || '—' }}</strong>
              <small>{{ row.user_agent || '—' }}</small>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </section>
</template>
