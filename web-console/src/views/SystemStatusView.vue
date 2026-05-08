<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'

import { useOverviewStore } from '@/stores/overview'

const store = useOverviewStore()
const { snapshot } = storeToRefs(store)

const events = computed(() => snapshot.value?.events ?? [])
const runtime = computed(() => snapshot.value?.runtime ?? null)
const restarting = ref(false)
const restartError = ref('')

async function restartBackend() {
  restarting.value = true
  restartError.value = ''
  try {
    await store.restartService()
    await store.fetchSnapshot()
  } catch (err) {
    restartError.value = err instanceof Error ? err.message : String(err)
  } finally {
    restarting.value = false
  }
}
</script>

<template>
  <section class="page-stack">
    <section class="kpi-grid">
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">节点状态</span>
        <strong>{{ snapshot?.agent_state?.status ?? 'unknown' }}</strong>
        <small>agent state machine</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">后端就绪</span>
        <strong>{{ snapshot?.backend_ready ? '在线' : '离线' }}</strong>
        <small>{{ snapshot?.backend_type ?? 'vllm' }}</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">调度开关</span>
        <strong>{{ snapshot?.require_agent_ready ? '强制' : '宽松' }}</strong>
        <small>request gate policy</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">队列深度</span>
        <strong>{{ snapshot?.queue_length ?? 0 }}</strong>
        <small>waiting requests</small>
      </article>
    </section>

    <section class="chart-grid">
      <article class="surface-card list-card">
        <div class="status-panel__head">
          <div>
            <p class="table-card__eyebrow">运行配置</p>
            <h3>Gateway / Agent / Backend</h3>
          </div>
        </div>
        <div class="mini-list">
          <div class="mini-list__item">
            <div>
              <strong>Gateway</strong>
              <p>{{ runtime?.gateway.backend_url ?? '未配置' }}</p>
            </div>
            <small>{{ runtime?.gateway.queue_limit ?? 0 }} queue</small>
          </div>
          <div class="mini-list__item">
            <div>
              <strong>Agent</strong>
              <p>{{ runtime?.agent.host ?? '127.0.0.1' }}:{{ runtime?.agent.port ?? 4010 }}</p>
            </div>
            <small>{{ runtime?.agent.poll_interval ?? 15 }}s</small>
          </div>
          <div class="mini-list__item">
            <div>
              <strong>VLLM</strong>
              <p>{{ runtime?.vllm.model_name ?? 'qwen36-35b-a3b' }}</p>
            </div>
            <small>{{ runtime?.vllm.host_port ?? 8000 }}</small>
          </div>
        </div>
      </article>

      <article class="surface-card list-card">
        <div class="status-panel__head">
          <div>
            <p class="table-card__eyebrow">恢复参数</p>
            <h3>自动恢复和停服策略</h3>
          </div>
        </div>
        <div class="mini-list">
          <div class="mini-list__item">
            <div>
              <strong>Auto Recover</strong>
              <p>{{ runtime?.agent.auto_recover ? '开启' : '关闭' }}</p>
            </div>
            <small>threshold {{ runtime?.agent.recovery_threshold ?? 2 }}</small>
          </div>
          <div class="mini-list__item">
            <div>
              <strong>Auto Start</strong>
              <p>{{ runtime?.schedule.auto_start_enabled ? '开启' : '关闭' }}</p>
            </div>
            <small>{{ runtime?.schedule.timezone ?? 'Asia/Shanghai' }}</small>
          </div>
          <div class="mini-list__item">
            <div>
              <strong>Auto Stop</strong>
              <p>{{ runtime?.schedule.auto_stop_enabled ? '开启' : '关闭' }}</p>
            </div>
            <small>{{ runtime?.schedule.start_time ?? '09:00' }}-{{ runtime?.schedule.end_time ?? '18:00' }}</small>
          </div>
        </div>
      </article>
    </section>

    <section class="surface-card status-panel">
      <div class="status-panel__head">
        <div>
          <p class="table-card__eyebrow">系统状态</p>
          <h3>节点代理与恢复事件</h3>
        </div>
        <div class="filter-card__right">
          <span>backend: {{ snapshot?.backend_type ?? 'vllm' }}</span>
          <el-button :loading="restarting" type="warning" @click="restartBackend">重启后端</el-button>
        </div>
      </div>

      <div v-if="restartError" class="status-empty">{{ restartError }}</div>

      <div class="status-timeline">
        <div v-for="item in events" :key="item.id" class="status-timeline__item">
          <div class="status-timeline__dot"></div>
          <div>
            <strong>{{ item.status }}</strong>
            <p>{{ item.reason || '无说明' }}</p>
            <small>{{ item.created_at }}</small>
          </div>
        </div>
        <div v-if="events.length === 0" class="status-empty">暂无状态事件。</div>
      </div>
    </section>
  </section>
</template>
