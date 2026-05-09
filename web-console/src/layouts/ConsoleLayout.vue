<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute, RouterLink, RouterView } from 'vue-router'

import StatusPill from '@/components/StatusPill.vue'
import { useOverviewStore } from '@/stores/overview'

const route = useRoute()
const store = useOverviewStore()

const navItems = [
  { label: '仪表盘', hint: '实时总览', icon: '仪', path: '/' },
  { label: '使用记录', hint: '请求审计', icon: '记', path: '/usage' },
  { label: 'API 密钥', hint: '认证与限流', icon: '密', path: '/keys' },
  { label: '模型路由', hint: '逻辑到后端', icon: '模', path: '/models' },
  { label: '调度设置', hint: '启停与时段', icon: '时', path: '/schedule' },
  { label: '系统状态', hint: '节点与恢复', icon: '状', path: '/status' },
]

const pageTitle = computed(() => (route.meta.title as string) || '仪表盘')
const pageSubtitle = computed(() => (route.meta.subtitle as string) || 'llmnode 管理控制台')

onMounted(async () => {
  await store.fetchSnapshot()
  void store.connectStream()
})

onBeforeUnmount(() => {
  store.disconnectStream()
})
</script>

<template>
  <div class="console-app">
    <aside class="console-sidebar">
      <div class="brand">
        <div class="brand__mark">LN</div>
        <div class="brand__copy">
          <strong>llmnode</strong>
          <span>Local LLM Control Plane</span>
        </div>
      </div>

      <nav class="nav-list">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
        >
          <span class="nav-item__icon">{{ item.icon }}</span>
          <span class="nav-item__copy">
            <strong>{{ item.label }}</strong>
            <small>{{ item.hint }}</small>
          </span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="sidebar-footer__row">
          <span class="sidebar-footer__dot"></span>
          <span>{{ store.streamConnected ? 'SSE 已连接' : 'SSE 未连接' }}</span>
        </div>
        <div class="sidebar-footer__row">
          <span class="sidebar-footer__label">Backend</span>
          <strong>{{ store.snapshot?.backend_type ?? 'vllm' }}</strong>
        </div>
      </div>
    </aside>

    <section class="console-workspace">
      <header class="topbar">
        <div class="topbar__copy">
          <p class="eyebrow">llmnode · management console</p>
          <h1>{{ pageTitle }}</h1>
          <p>{{ pageSubtitle }}</p>
        </div>

        <div class="topbar__meta">
          <StatusPill :label="store.backendStatus" />
          <div class="topbar__chip">Queue {{ store.snapshot?.queue_length ?? 0 }}</div>
          <div class="topbar__chip">Logs {{ store.requestCount }}</div>
          <div class="topbar__avatar">A</div>
        </div>
      </header>

      <section v-if="store.error || store.snapshot?.backend_error" class="surface-card status-panel">
        <div class="status-panel__head">
          <div>
            <p class="table-card__eyebrow">状态提示</p>
            <h3>当前有异常需要关注</h3>
          </div>
        </div>
        <div class="status-empty">
          {{ store.error || store.snapshot?.backend_error }}
        </div>
      </section>

      <main class="workspace-body">
        <RouterView />
      </main>
    </section>
  </div>
</template>
