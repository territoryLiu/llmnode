<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'

import MetricChart from '@/components/MetricChart.vue'
import ModelDistributionChart from '@/components/ModelDistributionChart.vue'
import StatusPill from '@/components/StatusPill.vue'
import { useOverviewStore } from '@/stores/overview'
import type { RequestLogEntry } from '@/types'

const store = useOverviewStore()
const { snapshot, history, requestCount, recentErrors, streamConnected, lastUpdated } = storeToRefs(store)

const logs = computed(() => snapshot.value?.logs ?? [])
const events = computed(() => snapshot.value?.events ?? [])
const totalModels = computed(() => snapshot.value?.models.length ?? 0)
const readyText = computed(() => (snapshot.value?.backend_ready ? '在线' : '离线'))
const queueText = computed(() => String(snapshot.value?.queue_length ?? 0))

function recentRequestDetail(row: RequestLogEntry) {
  if (row.rejection_reason) {
    return `${row.protocol} · ${row.created_at} · ${row.rejection_reason}`
  }
  return `${row.protocol} · ${row.created_at}`
}

function errorSummaryText(row: RequestLogEntry) {
  if (row.rejection_reason) {
    return row.rejection_reason
  }
  return row.error_message || row.request_id
}
</script>

<template>
  <section class="page-stack">
    <section class="kpi-grid">
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">后端状态</span>
        <strong>{{ readyText }}</strong>
        <small>backend_type: {{ snapshot?.backend_type ?? 'vllm' }}</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">总请求数</span>
        <strong>{{ requestCount }}</strong>
        <small>当前审计记录</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">模型数</span>
        <strong>{{ totalModels }}</strong>
        <small>逻辑模型列表</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">队列长度</span>
        <strong>{{ queueText }}</strong>
        <small>{{ streamConnected ? 'SSE 在线' : 'SSE 离线' }}</small>
      </article>
    </section>

    <section class="toolbar-card surface-card">
      <div class="toolbar-card__left">
        <el-select :model-value="'近 7 天'" style="width: 150px">
          <el-option label="近 7 天" value="近 7 天" />
          <el-option label="今日" value="今日" />
        </el-select>
        <el-select :model-value="'按天'" style="width: 150px">
          <el-option label="按天" value="按天" />
          <el-option label="按小时" value="按小时" />
        </el-select>
      </div>
      <div class="toolbar-card__right">
        <StatusPill :label="snapshot?.agent_state?.status ?? 'unknown'" />
        <span class="toolbar-card__meta">last {{ lastUpdated || 'never' }}</span>
      </div>
    </section>

    <section class="chart-grid">
      <ModelDistributionChart :logs="logs" />
      <MetricChart title="队列与失败趋势" color="#4f7cff" field="queueLength" :points="history" />
    </section>

    <section class="bottom-grid">
      <article class="surface-card list-card">
        <div class="table-card__head">
          <div>
            <p class="table-card__eyebrow">最近使用</p>
            <h3>最新请求和状态</h3>
          </div>
          <span>近 8 条</span>
        </div>

        <div class="mini-list">
          <div v-for="row in logs.slice(0, 8)" :key="row.id" class="mini-list__item">
            <div>
              <strong>{{ row.model_name }}</strong>
              <p>{{ recentRequestDetail(row) }}</p>
            </div>
            <div class="mini-list__right">
              <span class="mini-list__status">{{ row.status }}</span>
              <small>{{ row.request_id }}</small>
            </div>
          </div>
          <div v-if="logs.length === 0" class="empty-state">暂无请求记录。</div>
        </div>
      </article>

      <article class="surface-card list-card">
        <div class="table-card__head">
          <div>
            <p class="table-card__eyebrow">快捷操作</p>
            <h3>管理台入口</h3>
          </div>
        </div>

        <div class="quick-grid">
          <div class="quick-card">
            <span>API 密钥</span>
            <strong>创建 / 禁用 / 删除</strong>
          </div>
          <div class="quick-card">
            <span>模型路由</span>
            <strong>逻辑模型管理</strong>
          </div>
          <div class="quick-card">
            <span>调度</span>
            <strong>工作时段与恢复策略</strong>
          </div>
          <div class="quick-card">
            <span>系统状态</span>
            <strong>节点与 SSE 实时流</strong>
          </div>
        </div>
      </article>
    </section>

    <section class="bottom-grid">
      <article class="surface-card list-card">
        <div class="table-card__head">
          <div>
            <p class="table-card__eyebrow">节点事件</p>
            <h3>最近状态迁移</h3>
          </div>
        </div>
        <div class="mini-list">
          <div v-for="row in events.slice(0, 6)" :key="row.id" class="mini-list__item">
            <div>
              <strong>{{ row.status }}</strong>
              <p>{{ row.reason || '无说明' }}</p>
            </div>
            <small>{{ row.created_at }}</small>
          </div>
          <div v-if="events.length === 0" class="empty-state">暂无节点事件。</div>
        </div>
      </article>

      <article class="surface-card list-card">
        <div class="table-card__head">
          <div>
            <p class="table-card__eyebrow">异常请求</p>
            <h3>错误聚合</h3>
          </div>
          <span>{{ recentErrors.length }}</span>
        </div>
        <div class="mini-list">
          <div v-for="item in recentErrors" :key="item.id" class="mini-list__item">
            <div>
              <strong>{{ item.status }}</strong>
              <p>{{ errorSummaryText(item) }}</p>
            </div>
            <small>{{ item.created_at }}</small>
          </div>
          <div v-if="recentErrors.length === 0" class="empty-state">暂无异常。</div>
        </div>
      </article>
    </section>
  </section>
</template>
