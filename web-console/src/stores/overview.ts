import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import type {
  AdminApiKeyCreatePayload,
  AdminApiKeyCreateResponse,
  AdminApiKeyListResponse,
  AdminApiKeyUpdatePayload,
  AdminApiKeyUpdateResponse,
  AdminServiceActionResponse,
  AdminSnapshot,
  MetricPoint,
} from '@/types'
import { consumeSSEStream } from '@/lib/sse'

const MAX_POINTS = 48

function timestampLabel(value: string): string {
  const date = new Date(value)
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(
    date.getSeconds(),
  ).padStart(2, '0')}`
}

export const useOverviewStore = defineStore('overview', () => {
  const snapshot = ref<AdminSnapshot | null>(null)
  const loading = ref(false)
  const streamConnected = ref(false)
  const lastUpdated = ref('')
  const error = ref('')
  const apiBase = ref(localStorage.getItem('vllm-console-api-base') ?? '')
  const apiKey = ref(localStorage.getItem('vllm-console-api-key') ?? 'dev-key')
  const history = ref<MetricPoint[]>([])
  const streamController = ref<AbortController | null>(null)

  const backendStatus = computed(() => snapshot.value?.agent_state?.status ?? 'unknown')
  const recentErrors = computed(() => snapshot.value?.logs.filter((item) => item.status !== 'ok').slice(0, 5) ?? [])
  const requestCount = computed(() => snapshot.value?.logs.length ?? 0)

  function persistSettings() {
    localStorage.setItem('vllm-console-api-base', apiBase.value)
    localStorage.setItem('vllm-console-api-key', apiKey.value)
  }

  function buildUrl(path: string): string {
    const base = apiBase.value.trim()
    if (!base || base === '/') {
      return path
    }
    return `${base.replace(/\/$/, '')}${path}`
  }

  async function sendAdminJson(path: string, method: 'PATCH' | 'POST', payload: unknown) {
    persistSettings()
    const response = await fetch(buildUrl(path), {
      method,
      headers: {
        Authorization: `Bearer ${apiKey.value}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      throw new Error(`${method} ${path} failed: ${response.status}`)
    }
    return response.json()
  }

  async function sendAdminRequest(path: string, method: 'GET' | 'DELETE') {
    persistSettings()
    const response = await fetch(buildUrl(path), {
      method,
      headers: {
        Authorization: `Bearer ${apiKey.value}`,
      },
    })
    if (!response.ok) {
      throw new Error(`${method} ${path} failed: ${response.status}`)
    }
    return response.json()
  }

  async function fetchSnapshot() {
    loading.value = true
    error.value = ''
    persistSettings()
    try {
      const response = await fetch(buildUrl('/admin/status'), {
        headers: {
          Authorization: `Bearer ${apiKey.value}`,
        },
      })
      if (!response.ok) {
        throw new Error(`snapshot request failed: ${response.status}`)
      }
      applySnapshot((await response.json()) as AdminSnapshot)
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  function applySnapshot(payload: AdminSnapshot) {
    snapshot.value = payload
    lastUpdated.value = new Date().toISOString()
    history.value = [
      ...history.value.slice(-(MAX_POINTS - 1)),
      {
        label: timestampLabel(lastUpdated.value),
        queueLength: payload.queue_length,
        failureCount: payload.agent_state?.failure_count ?? 0,
      },
    ]
  }

  async function connectStream() {
    disconnectStream()
    persistSettings()
    streamConnected.value = false
    error.value = ''

    const controller = new AbortController()
    streamController.value = controller

    try {
      const response = await fetch(buildUrl('/admin/stream?interval=2'), {
        headers: {
          Authorization: `Bearer ${apiKey.value}`,
        },
        signal: controller.signal,
      })
      if (!response.ok) {
        throw new Error(`stream request failed: ${response.status}`)
      }

      streamConnected.value = true
      await consumeSSEStream(response, (event) => {
        if (event.event !== 'snapshot') {
          return
        }
        applySnapshot(JSON.parse(event.data) as AdminSnapshot)
      })
      streamConnected.value = false
    } catch (err) {
      if (controller.signal.aborted) {
        return
      }
      error.value = err instanceof Error ? err.message : String(err)
      streamConnected.value = false
    }
  }

  function disconnectStream() {
    streamController.value?.abort()
    streamController.value = null
    streamConnected.value = false
  }

  async function updateModelRoute(name: string, payload: Record<string, unknown>) {
    await sendAdminJson(`/admin/models/${encodeURIComponent(name)}`, 'PATCH', payload)
    await fetchSnapshot()
  }

  async function updateSchedule(payload: Record<string, unknown>) {
    await sendAdminJson('/admin/schedule', 'PATCH', payload)
    await fetchSnapshot()
  }

  async function fetchApiKeys() {
    return (await sendAdminRequest('/admin/keys', 'GET')) as AdminApiKeyListResponse
  }

  async function createApiKey(payload: AdminApiKeyCreatePayload) {
    return (await sendAdminJson('/admin/keys', 'POST', payload)) as AdminApiKeyCreateResponse
  }

  async function updateApiKey(keyId: number, payload: AdminApiKeyUpdatePayload) {
    return (await sendAdminJson(`/admin/keys/${keyId}`, 'PATCH', payload)) as AdminApiKeyUpdateResponse
  }

  async function deleteApiKey(keyId: number) {
    return await sendAdminRequest(`/admin/keys/${keyId}`, 'DELETE')
  }

  async function restartService() {
    return (await sendAdminJson('/admin/services/restart', 'POST', {})) as AdminServiceActionResponse
  }

  return {
    apiBase,
    apiKey,
    backendStatus,
    error,
    history,
    lastUpdated,
    loading,
    recentErrors,
    requestCount,
    snapshot,
    streamConnected,
    applySnapshot,
    connectStream,
    disconnectStream,
    fetchApiKeys,
    fetchSnapshot,
    createApiKey,
    deleteApiKey,
    restartService,
    updateModelRoute,
    updateApiKey,
    updateSchedule,
  }
})
