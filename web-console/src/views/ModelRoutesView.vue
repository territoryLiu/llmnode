<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useOverviewStore } from '@/stores/overview'
import type { RuntimeModelRoute } from '@/types'

const store = useOverviewStore()
const { snapshot } = storeToRefs(store)

const models = computed(() => snapshot.value?.runtime?.model_routes ?? [])
const runtime = computed(() => snapshot.value?.runtime?.vllm ?? null)
const savingName = ref('')
const drafts = reactive<Record<string, RuntimeModelRoute>>({})

function ensureDraft(row: RuntimeModelRoute) {
  if (!drafts[row.name]) {
    drafts[row.name] = { ...row }
  }
  return drafts[row.name]
}

watch(
  models,
  (items) => {
    for (const item of items) {
      drafts[item.name] = { ...item }
    }
  },
  { immediate: true },
)

async function saveModel(name: string) {
  const draft = drafts[name]
  if (!draft) {
    return
  }
  savingName.value = name
  try {
    await store.updateModelRoute(name, {
      display_name: draft.display_name,
      backend_model: draft.backend_model,
      enabled: draft.enabled,
    })
  } finally {
    savingName.value = ''
  }
}
</script>

<template>
  <section class="page-stack">
    <section class="kpi-grid">
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">后端类型</span>
        <strong>{{ runtime?.backend_type ?? snapshot?.backend_type ?? 'vllm' }}</strong>
        <small>当前只允许单后端运行</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">模型目录</span>
        <strong>{{ runtime?.model_name ?? 'qwen36-35b-a3b' }}</strong>
        <small>{{ runtime?.model_dir ?? '未配置' }}</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">显存占用策略</span>
        <strong>{{ runtime?.gpu_memory_utilization ?? 0 }}</strong>
        <small>gpu_memory_utilization</small>
      </article>
      <article class="surface-card kpi-card">
        <span class="kpi-card__label">上下文长度</span>
        <strong>{{ runtime?.max_model_len ?? 0 }}</strong>
        <small>max_model_len</small>
      </article>
    </section>

    <section class="surface-card table-card">
      <div class="table-card__head">
        <div>
          <p class="table-card__eyebrow">已注册模型</p>
          <h3>逻辑模型列表</h3>
        </div>
        <span>{{ models.length }} models</span>
      </div>

      <el-table :data="models" height="320">
        <el-table-column prop="name" label="逻辑模型" min-width="220" />
        <el-table-column label="展示名称" min-width="180">
          <template #default="{ row }">
            <el-input v-model="ensureDraft(row).display_name" />
          </template>
        </el-table-column>
        <el-table-column label="后端模型" min-width="180">
          <template #default="{ row }">
            <el-input v-model="ensureDraft(row).backend_model" />
          </template>
        </el-table-column>
        <el-table-column prop="backend_type" label="后端类型" width="140" />
        <el-table-column label="启用" width="100">
          <template #default="{ row }">
            <el-switch v-model="ensureDraft(row).enabled" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="primary" text :loading="savingName === row.name" @click="saveModel(row.name)">
              保存
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </section>
</template>
