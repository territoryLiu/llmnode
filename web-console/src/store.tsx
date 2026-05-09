import React, {createContext, useContext, useEffect, useRef, useState, type ReactNode} from 'react';

export type Page = 'overview' | 'usage' | 'keys' | 'models' | 'schedule' | 'status';

export interface RequestLog {
  id: number;
  request_id: string;
  model_name: string | null;
  status: string;
  protocol: string | null;
  error_message: string | null;
  created_at: string;
  api_key_id: number | null;
  auth_source: string | null;
  client_ip: string | null;
  user_agent: string | null;
  rejection_reason: string | null;
}

export interface AgentEvent {
  id: number;
  status: string;
  reason: string | null;
  created_at: string;
}

export interface ApiKeyRow {
  id: number;
  name: string;
  status: 'active' | 'disabled';
  scopes: string[];
  rpm_limit: number | null;
  concurrency_limit: number | null;
  created_at: string;
  disabled_at: string | null;
  last_used_at: string | null;
  note: string | null;
}

export interface ModelRouteRow {
  name: string;
  display_name: string;
  backend_model: string;
  backend_type: string;
  enabled: boolean;
}

export interface ScheduleConfig {
  timezone: string;
  work_days: string[];
  start_time: string;
  end_time: string;
  auto_stop_enabled: boolean;
  auto_start_enabled: boolean;
  cooldown_minutes: number;
}

export interface SnapshotHistoryPoint {
  label: string;
  queueLength: number;
  failureCount: number;
}

interface RuntimeGatewayConfig {
  host: string;
  port: number;
  backend_url: string;
  backend_model: string;
  agent_base_url: string;
  agent_status_url: string;
  require_agent_ready: boolean;
  queue_limit: number;
  execution_limit: number;
  api_key_configured: boolean;
}

interface RuntimeAgentConfig {
  host: string;
  port: number;
  state: string;
  poll_interval: number;
  auto_recover: boolean;
  recovery_threshold: number;
}

interface RuntimeVllmConfig {
  backend_type: string;
  container_name: string;
  image_name: string;
  model_dir: string;
  model_name: string;
  host_port: number;
  gpu_memory_utilization: number;
  tensor_parallel_size: number;
  max_model_len: number;
  max_num_seqs: number;
  shm_size: string;
  enable_auto_tool_choice: boolean;
  reasoning_parser: string | null;
  tool_call_parser: string | null;
}

export interface AdminSnapshot {
  backend_type: string;
  backend_ready: boolean;
  backend_error: string | null;
  backend_container: Record<string, unknown> | null;
  agent_state: Record<string, unknown> | null;
  require_agent_ready: boolean;
  queue_length: number;
  models: Array<{
    id: string;
    object: string;
    created: number;
    owned_by: string;
  }>;
  logs: RequestLog[];
  events: AgentEvent[];
  runtime: {
    gateway: RuntimeGatewayConfig;
    agent: RuntimeAgentConfig;
    schedule: ScheduleConfig;
    vllm: RuntimeVllmConfig;
    model_routes: ModelRouteRow[];
  };
}

interface CreateApiKeyPayload {
  name: string;
  scopes: string[];
  rpm_limit: number | null;
  concurrency_limit: number | null;
  note: string | null;
}

interface UpdateApiKeyPayload {
  name?: string;
  status?: 'active' | 'disabled';
  scopes?: string[];
  rpm_limit?: number | null;
  concurrency_limit?: number | null;
  note?: string | null;
}

interface UpdateModelRoutePayload {
  display_name?: string;
  backend_model?: string;
  enabled?: boolean;
  backend_type?: string;
}

interface LoadingState {
  snapshot: boolean;
  requestLogs: boolean;
  apiKeys: boolean;
  modelRoutes: boolean;
  schedule: boolean;
}

interface AppState {
  currentPage: Page;
  setCurrentPage: (page: Page) => void;
  apiBase: string;
  setApiBase: (url: string) => void;
  apiKey: string;
  setApiKey: (key: string) => void;
  sseConnected: boolean;
  globalError: string | null;
  setGlobalError: (error: string | null) => void;
  lastUpdated: Date | null;
  snapshot: AdminSnapshot | null;
  snapshotHistory: SnapshotHistoryPoint[];
  requestLogs: RequestLog[];
  apiKeys: ApiKeyRow[];
  modelRoutes: ModelRouteRow[];
  schedule: ScheduleConfig | null;
  loading: LoadingState;
  refreshAll: () => Promise<void>;
  refreshSnapshot: () => Promise<void>;
  refreshRequestLogs: (limit?: number) => Promise<void>;
  refreshApiKeys: () => Promise<void>;
  refreshModelRoutes: () => Promise<void>;
  refreshSchedule: () => Promise<void>;
  createApiKey: (payload: CreateApiKeyPayload) => Promise<{secret: string; key: ApiKeyRow}>;
  updateApiKey: (id: number, payload: UpdateApiKeyPayload) => Promise<ApiKeyRow>;
  deleteApiKey: (id: number) => Promise<void>;
  updateModelRoute: (name: string, payload: UpdateModelRoutePayload) => Promise<ModelRouteRow>;
  updateSchedule: (payload: Partial<ScheduleConfig>) => Promise<ScheduleConfig>;
  restartBackend: () => Promise<void>;
}

const defaultApiBase =
  localStorage.getItem('vllm-console-api-base') ||
  (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:5173');
const defaultApiKey = localStorage.getItem('vllm-console-api-key') || 'dev-key';

const AppContext = createContext<AppState | undefined>(undefined);

function resolveApiBase(apiBase: string): string {
  const normalized = apiBase.trim();
  if (normalized) {
    return normalized.endsWith('/') ? normalized : `${normalized}/`;
  }
  return typeof window !== 'undefined' ? `${window.location.origin}/` : 'http://127.0.0.1:5173/';
}

function buildUrl(apiBase: string, path: string): string {
  return new URL(path, resolveApiBase(apiBase)).toString();
}

function authHeaders(apiKey: string, headers?: HeadersInit): HeadersInit {
  return {
    Accept: 'application/json',
    'x-api-key': apiKey,
    ...headers,
  };
}

function toErrorMessage(error: unknown, fallback = '请求失败'): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  return fallback;
}

function appendHistoryPoint(previous: SnapshotHistoryPoint[], snapshot: AdminSnapshot): SnapshotHistoryPoint[] {
  const point: SnapshotHistoryPoint = {
    label: new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'}),
    queueLength: snapshot.queue_length,
    failureCount: snapshot.logs.filter((log) => log.status !== 'ok').length,
  };
  const next = [...previous, point];
  return next.slice(-48);
}

export function AppProvider({children}: {children: ReactNode}) {
  const [currentPage, setCurrentPage] = useState<Page>('overview');
  const [apiBase, setApiBase] = useState(defaultApiBase);
  const [apiKey, setApiKey] = useState(defaultApiKey);
  const [sseConnected, setSseConnected] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [snapshot, setSnapshot] = useState<AdminSnapshot | null>(null);
  const [snapshotHistory, setSnapshotHistory] = useState<SnapshotHistoryPoint[]>([]);
  const [requestLogs, setRequestLogs] = useState<RequestLog[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKeyRow[]>([]);
  const [modelRoutes, setModelRoutes] = useState<ModelRouteRow[]>([]);
  const [schedule, setSchedule] = useState<ScheduleConfig | null>(null);
  const [loading, setLoading] = useState<LoadingState>({
    snapshot: true,
    requestLogs: true,
    apiKeys: true,
    modelRoutes: true,
    schedule: true,
  });
  const streamAbortRef = useRef<AbortController | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);

  useEffect(() => {
    localStorage.setItem('vllm-console-api-base', apiBase);
  }, [apiBase]);

  useEffect(() => {
    localStorage.setItem('vllm-console-api-key', apiKey);
  }, [apiKey]);

  async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(buildUrl(apiBase, path), {
      ...init,
      headers: authHeaders(apiKey, init?.headers),
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const payload = await response.json();
        if (typeof payload?.detail === 'string' && payload.detail.trim()) {
          detail = payload.detail;
        }
      } catch {
        // ignore non-json error bodies
      }
      throw new Error(detail);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  }

  function applySnapshot(nextSnapshot: AdminSnapshot) {
    setSnapshot(nextSnapshot);
    setModelRoutes(nextSnapshot.runtime.model_routes);
    setSchedule(nextSnapshot.runtime.schedule);
    setSnapshotHistory((previous) => appendHistoryPoint(previous, nextSnapshot));
    setLastUpdated(new Date());
    setGlobalError(null);
  }

  async function refreshSnapshot() {
    setLoading((previous) => ({...previous, snapshot: true}));
    try {
      const payload = await requestJson<AdminSnapshot>('/admin/status');
      applySnapshot(payload);
      if (requestLogs.length === 0 && payload.logs.length > 0) {
        setRequestLogs(payload.logs);
      }
    } catch (error) {
      const message = toErrorMessage(error, '无法获取系统快照');
      setGlobalError(message);
      throw error;
    } finally {
      setLoading((previous) => ({...previous, snapshot: false}));
    }
  }

  async function refreshRequestLogs(limit = 200) {
    setLoading((previous) => ({...previous, requestLogs: true}));
    try {
      const payload = await requestJson<{logs: RequestLog[]}>(`/admin/request-logs?limit=${limit}`);
      setRequestLogs(payload.logs);
      setGlobalError(null);
      setLastUpdated(new Date());
    } catch (error) {
      const message = toErrorMessage(error, '无法获取请求日志');
      setGlobalError(message);
      throw error;
    } finally {
      setLoading((previous) => ({...previous, requestLogs: false}));
    }
  }

  async function refreshApiKeys() {
    setLoading((previous) => ({...previous, apiKeys: true}));
    try {
      const payload = await requestJson<{keys: ApiKeyRow[]}>('/admin/keys');
      setApiKeys(payload.keys);
      setGlobalError(null);
      setLastUpdated(new Date());
    } catch (error) {
      const message = toErrorMessage(error, '无法获取 API Key 列表');
      setGlobalError(message);
      throw error;
    } finally {
      setLoading((previous) => ({...previous, apiKeys: false}));
    }
  }

  async function refreshModelRoutes() {
    setLoading((previous) => ({...previous, modelRoutes: true}));
    try {
      const payload = await requestJson<{models: ModelRouteRow[]}>('/admin/models');
      setModelRoutes(payload.models);
      setGlobalError(null);
      setLastUpdated(new Date());
    } catch (error) {
      const message = toErrorMessage(error, '无法获取模型路由');
      setGlobalError(message);
      throw error;
    } finally {
      setLoading((previous) => ({...previous, modelRoutes: false}));
    }
  }

  async function refreshSchedule() {
    setLoading((previous) => ({...previous, schedule: true}));
    try {
      const payload = await requestJson<{schedule: ScheduleConfig}>('/admin/schedule');
      setSchedule(payload.schedule);
      setGlobalError(null);
      setLastUpdated(new Date());
    } catch (error) {
      const message = toErrorMessage(error, '无法获取调度配置');
      setGlobalError(message);
      throw error;
    } finally {
      setLoading((previous) => ({...previous, schedule: false}));
    }
  }

  async function refreshAll() {
    await Promise.allSettled([
      refreshSnapshot(),
      refreshRequestLogs(),
      refreshApiKeys(),
      refreshModelRoutes(),
      refreshSchedule(),
    ]);
  }

  async function createApiKey(payload: CreateApiKeyPayload) {
    const response = await requestJson<{key: ApiKeyRow; secret: string}>('/admin/keys', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    setApiKeys((previous) => [response.key, ...previous]);
    setLastUpdated(new Date());
    setGlobalError(null);
    return response;
  }

  async function updateApiKey(id: number, payload: UpdateApiKeyPayload) {
    const response = await requestJson<{key: ApiKeyRow}>(`/admin/keys/${id}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    setApiKeys((previous) => previous.map((item) => (item.id === id ? response.key : item)));
    setLastUpdated(new Date());
    setGlobalError(null);
    return response.key;
  }

  async function deleteApiKey(id: number) {
    await requestJson<{deleted: boolean; id: number}>(`/admin/keys/${id}`, {
      method: 'DELETE',
    });
    setApiKeys((previous) => previous.filter((item) => item.id !== id));
    setLastUpdated(new Date());
    setGlobalError(null);
  }

  async function updateModelRoute(name: string, payload: UpdateModelRoutePayload) {
    const response = await requestJson<{model: ModelRouteRow}>(`/admin/models/${encodeURIComponent(name)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    setModelRoutes((previous) => previous.map((item) => (item.name === name ? response.model : item)));
    setLastUpdated(new Date());
    setGlobalError(null);
    void refreshSnapshot();
    return response.model;
  }

  async function updateSchedule(payload: Partial<ScheduleConfig>) {
    const response = await requestJson<{schedule: ScheduleConfig}>('/admin/schedule', {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    setSchedule(response.schedule);
    setLastUpdated(new Date());
    setGlobalError(null);
    void refreshSnapshot();
    return response.schedule;
  }

  async function restartBackend() {
    await requestJson('/admin/services/restart', {
      method: 'POST',
    });
    setLastUpdated(new Date());
    setGlobalError(null);
    window.setTimeout(() => {
      void refreshSnapshot();
    }, 1500);
  }

  useEffect(() => {
    let disposed = false;

    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (streamAbortRef.current) {
      streamAbortRef.current.abort();
      streamAbortRef.current = null;
    }

    const readStream = async () => {
      const controller = new AbortController();
      streamAbortRef.current = controller;

      try {
        const response = await fetch(buildUrl(apiBase, '/admin/stream?interval=3'), {
          headers: authHeaders(apiKey),
          signal: controller.signal,
          cache: 'no-store',
        });

        if (!response.ok || !response.body) {
          throw new Error(`实时流连接失败 (${response.status})`);
        }

        setSseConnected(true);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (!disposed) {
          const {done, value} = await reader.read();
          if (done) {
            throw new Error('实时流已断开');
          }

          buffer += decoder.decode(value, {stream: true});
          let splitIndex = buffer.indexOf('\n\n');
          while (splitIndex >= 0) {
            const rawEvent = buffer.slice(0, splitIndex);
            buffer = buffer.slice(splitIndex + 2);
            splitIndex = buffer.indexOf('\n\n');

            const dataLines = rawEvent
              .split('\n')
              .filter((line) => line.startsWith('data:'))
              .map((line) => line.slice(5).trimStart());

            if (dataLines.length === 0) {
              continue;
            }

            try {
              const payload = JSON.parse(dataLines.join('\n')) as AdminSnapshot;
              applySnapshot(payload);
              setSseConnected(true);
            } catch {
              // ignore malformed chunks
            }
          }
        }
      } catch (error) {
        if (disposed || controller.signal.aborted) {
          return;
        }
        setSseConnected(false);
        setGlobalError(toErrorMessage(error, '实时连接已中断，正在重连'));
        try {
          await refreshSnapshot();
        } catch {
          // ignore snapshot refresh errors during reconnect
        }
        reconnectTimerRef.current = window.setTimeout(() => {
          void readStream();
        }, 3000);
      }
    };

    void refreshAll();
    void readStream();

    return () => {
      disposed = true;
      setSseConnected(false);
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (streamAbortRef.current) {
        streamAbortRef.current.abort();
        streamAbortRef.current = null;
      }
    };
  }, [apiBase, apiKey]);

  return (
    <AppContext.Provider
      value={{
        currentPage,
        setCurrentPage,
        apiBase,
        setApiBase,
        apiKey,
        setApiKey,
        sseConnected,
        globalError,
        setGlobalError,
        lastUpdated,
        snapshot,
        snapshotHistory,
        requestLogs,
        apiKeys,
        modelRoutes,
        schedule,
        loading,
        refreshAll,
        refreshSnapshot,
        refreshRequestLogs,
        refreshApiKeys,
        refreshModelRoutes,
        refreshSchedule,
        createApiKey,
        updateApiKey,
        deleteApiKey,
        updateModelRoute,
        updateSchedule,
        restartBackend,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return context;
}
