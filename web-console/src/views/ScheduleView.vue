<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useOverviewStore } from '@/stores/overview'
import type { RuntimeScheduleConfig } from '@/types'

const store = useOverviewStore()
const { snapshot } = storeToRefs(store)

const schedule = computed(() => snapshot.value?.runtime?.schedule ?? null)
const gateway = computed(() => snapshot.value?.runtime?.gateway ?? null)
const agent = computed(() => snapshot.value?.runtime?.agent ?? null)
const saving = ref(false)
const dayOptions = [
  { label: 'Mon', value: 'mon' },
  { label: 'Tue', value: 'tue' },
  { label: 'Wed', value: 'wed' },
  { label: 'Thu', value: 'thu' },
  { label: 'Fri', value: 'fri' },
  { label: 'Sat', value: 'sat' },
  { label: 'Sun', value: 'sun' },
]
const form = reactive<RuntimeScheduleConfig>({
  timezone: 'Asia/Shanghai',
  work_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
  start_time: '09:00',
  end_time: '18:00',
  auto_stop_enabled: true,
  auto_start_enabled: true,
  cooldown_minutes: 10,
})

watch(
  schedule,
  (value) => {
    if (!value) {
      return
    }
    form.timezone = value.timezone
    form.work_days = [...value.work_days]
    form.start_time = value.start_time
    form.end_time = value.end_time
    form.auto_stop_enabled = value.auto_stop_enabled
    form.auto_start_enabled = value.auto_start_enabled
    form.cooldown_minutes = value.cooldown_minutes
  },
  { immediate: true },
)

async function saveSchedule() {
  saving.value = true
  try {
    await store.updateSchedule({
      timezone: form.timezone,
      work_days: [...form.work_days],
      start_time: form.start_time,
      end_time: form.end_time,
      auto_stop_enabled: form.auto_stop_enabled,
      auto_start_enabled: form.auto_start_enabled,
      cooldown_minutes: form.cooldown_minutes,
    })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="page-stack">
    <section class="kpi-grid">
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">时区</span>
        <strong>{{ schedule?.timezone ?? 'Asia/Shanghai' }}</strong>
        <small>默认调度时区</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">工作窗口</span>
        <strong>{{ schedule?.start_time ?? '09:00' }} - {{ schedule?.end_time ?? '18:00' }}</strong>
        <small>{{ (schedule?.work_days ?? []).join(' / ') || 'mon - fri' }}</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">自动启停</span>
        <strong>{{ schedule?.auto_start_enabled ? '开启' : '关闭' }}</strong>
        <small>{{ schedule?.auto_stop_enabled ? '停服开关已启用' : '停服开关已关闭' }}</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">冷却分钟</span>
        <strong>{{ schedule?.cooldown_minutes ?? 10 }}</strong>
        <small>恢复防抖等待时间</small>
      </article>
    </section>

    <section class="chart-grid">
      <article class="surface-card list-card">
        <div class="table-card__head">
          <div>
            <p class="table-card__eyebrow">调度策略</p>
            <h3>当前运行配置</h3>
          </div>
        </div>

        <div class="mini-list">
          <div class="mini-list__item">
            <div>
              <strong>Gateway</strong>
              <p>{{ gateway?.backend_url ?? '未配置' }}</p>
            </div>
            <small>{{ gateway?.queue_limit ?? 0 }} queue</small>
          </div>
          <div class="mini-list__item">
            <div>
              <strong>Agent</strong>
              <p>{{ agent?.host ?? '127.0.0.1' }}:{{ agent?.port ?? 4010 }}</p>
            </div>
            <small>{{ agent?.poll_interval ?? 15 }}s poll</small>
          </div>
          <div class="mini-list__item">
            <div>
              <strong>Auto Recovery</strong>
              <p>{{ agent?.auto_recover ? '开启' : '关闭' }}</p>
            </div>
            <small>threshold {{ agent?.recovery_threshold ?? 2 }}</small>
          </div>
        </div>
      </article>

      <article class="surface-card list-card">
        <div class="table-card__head">
          <div>
            <p class="table-card__eyebrow">调度说明</p>
            <h3>V2 当前行为</h3>
          </div>
        </div>
        <p class="placeholder-card__desc">
          V2 仍以应用内调度为准，工作日默认自动启停；后续如果迁移到 systemd timer，这里的配置会继续沿用。
        </p>
      </article>
    </section>

    <section class="surface-card placeholder-card">
      <div class="table-card__head">
        <div>
          <p class="table-card__eyebrow">调度编辑</p>
          <h3>更新当前计划</h3>
        </div>
      </div>

      <div class="form-grid">
        <el-input v-model="form.timezone" placeholder="Timezone">
          <template #prepend>Timezone</template>
        </el-input>
        <el-input v-model="form.start_time" placeholder="09:00">
          <template #prepend>Start</template>
        </el-input>
        <el-input v-model="form.end_time" placeholder="18:00">
          <template #prepend>End</template>
        </el-input>
        <el-input-number v-model="form.cooldown_minutes" :min="0" :max="240" />
      </div>

      <div class="form-grid">
        <el-select v-model="form.work_days" multiple collapse-tags placeholder="Work days">
          <el-option v-for="item in dayOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <div class="mini-list__item">
          <div>
            <strong>Auto Start</strong>
            <p>工作时间自动拉起</p>
          </div>
          <el-switch v-model="form.auto_start_enabled" />
        </div>
        <div class="mini-list__item">
          <div>
            <strong>Auto Stop</strong>
            <p>非工作时段自动停服</p>
          </div>
          <el-switch v-model="form.auto_stop_enabled" />
        </div>
      </div>

      <div class="form-actions">
        <el-button type="primary" :loading="saving" @click="saveSchedule">保存调度</el-button>
      </div>
    </section>
  </section>
</template>
