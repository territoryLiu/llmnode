import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useOverviewStore } from './overview'

const storageState = new Map<string, string>()

vi.stubGlobal('localStorage', {
  getItem(key: string) {
    return storageState.has(key) ? storageState.get(key)! : null
  },
  setItem(key: string, value: string) {
    storageState.set(key, value)
  },
  removeItem(key: string) {
    storageState.delete(key)
  },
  clear() {
    storageState.clear()
  },
})

describe('overview store api key helpers', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('fetches api key list from admin endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        keys: [
          {
            id: 1,
            name: 'demo',
            status: 'active',
            scopes: ['inference'],
            rpm_limit: null,
            concurrency_limit: null,
            created_at: '2026-05-08 12:00:00',
            disabled_at: null,
            last_used_at: null,
            note: null,
          },
        ],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useOverviewStore()
    const result = await store.fetchApiKeys()

    expect(fetchMock).toHaveBeenCalledWith('/admin/keys', {
      method: 'GET',
      headers: {
        Authorization: 'Bearer dev-key',
      },
    })
    expect(result.keys[0].name).toBe('demo')
  })

  it('creates api key via admin endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        key: {
          id: 2,
          name: 'ci',
          status: 'active',
          scopes: ['inference'],
          rpm_limit: null,
          concurrency_limit: null,
          created_at: '2026-05-08 12:00:00',
          disabled_at: null,
          last_used_at: null,
          note: null,
        },
        secret: 'ln_live_demo',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useOverviewStore()
    const payload = {
      name: 'ci',
      scopes: ['inference'],
      rpm_limit: null,
      concurrency_limit: null,
      note: null,
    }
    const result = await store.createApiKey(payload)

    expect(fetchMock).toHaveBeenCalledWith('/admin/keys', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer dev-key',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
    expect(result.secret).toBe('ln_live_demo')
  })

  it('updates api key via patch endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        key: {
          id: 2,
          name: 'ci',
          status: 'disabled',
          scopes: ['inference'],
          rpm_limit: null,
          concurrency_limit: null,
          created_at: '2026-05-08 12:00:00',
          disabled_at: '2026-05-08 12:30:00',
          last_used_at: null,
          note: null,
        },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useOverviewStore()
    const result = await store.updateApiKey(2, { status: 'disabled' })

    expect(fetchMock).toHaveBeenCalledWith('/admin/keys/2', {
      method: 'PATCH',
      headers: {
        Authorization: 'Bearer dev-key',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ status: 'disabled' }),
    })
    expect(result.key.status).toBe('disabled')
  })

  it('sends full editable payload for api key patch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        key: {
          id: 3,
          name: 'ops-console',
          status: 'active',
          scopes: ['admin', 'inference'],
          rpm_limit: 120,
          concurrency_limit: 2,
          created_at: '2026-05-08 12:00:00',
          disabled_at: null,
          last_used_at: null,
          note: 'ops',
        },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useOverviewStore()
    const payload = {
      name: 'ops-console',
      scopes: ['admin', 'inference'],
      rpm_limit: 120,
      concurrency_limit: 2,
      note: 'ops',
    }
    await store.updateApiKey(3, payload)

    expect(fetchMock).toHaveBeenCalledWith('/admin/keys/3', {
      method: 'PATCH',
      headers: {
        Authorization: 'Bearer dev-key',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
  })

  it('deletes api key via delete endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ deleted: true, id: 2 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useOverviewStore()
    const result = await store.deleteApiKey(2)

    expect(fetchMock).toHaveBeenCalledWith('/admin/keys/2', {
      method: 'DELETE',
      headers: {
        Authorization: 'Bearer dev-key',
      },
    })
    expect(result).toEqual({ deleted: true, id: 2 })
  })

  it('sends restart command to the admin services endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        accepted: true,
        service: 'backend',
        action: 'restart',
        agent_status: 'recovering',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useOverviewStore()
    const result = await store.restartService()

    expect(fetchMock).toHaveBeenCalledWith('/admin/services/restart', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer dev-key',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({}),
    })
    expect(result.accepted).toBe(true)
    expect(result.agent_status).toBe('recovering')
  })

  it('stores backend error from admin snapshot payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        backend_type: 'vllm',
        backend_ready: false,
        backend_error: 'ReadError: backend down',
        agent_state: { status: 'degraded' },
        require_agent_ready: false,
        queue_length: 0,
        models: [],
        logs: [],
        events: [],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useOverviewStore()
    await store.fetchSnapshot()

    expect(store.snapshot?.backend_error).toBe('ReadError: backend down')
  })

  it('stores backend container snapshot from admin snapshot payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        backend_type: 'vllm',
        backend_ready: true,
        backend_error: null,
        backend_container: {
          exists: true,
          running: true,
          status: 'running',
          name: 'qwen36-vllm',
        },
        agent_state: { status: 'ready' },
        require_agent_ready: false,
        queue_length: 0,
        models: [],
        logs: [],
        events: [],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useOverviewStore()
    await store.fetchSnapshot()

    expect(store.snapshot?.backend_container?.status).toBe('running')
    expect(store.snapshot?.backend_container?.name).toBe('qwen36-vllm')
  })
})
