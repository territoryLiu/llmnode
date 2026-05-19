import React, {createContext, useContext, useEffect, useRef, useState, type ReactNode} from 'react';
import {
  getPageLabel,
  readStoredLocale,
  translate,
  type Locale,
  writeStoredLocale,
} from './i18n';

export type Page = 'overview' | 'usage' | 'keys' | 'models' | 'schedule';

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
  metadata: {
    client_protocol?: string;
    execution_mode?: string;
    adapter_selected?: string | null;
    tool_classes_detected?: string[];
    request_mutation?: boolean;
    mutation_reason?: string | null;
  };
}

export interface RequestLogsResponse {
  logs: RequestLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface RequestMetricDetail {
  request_id: string;
  model_name: string;
  protocol: string;
  status: string;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  tokens_per_second: number | null;
  started_at: string;
  finished_at: string | null;
  backend_type: string | null;
  api_key_id: number | null;
  cache_creation_tokens: number | null;
  cache_read_tokens: number | null;
  cache_miss_tokens: number | null;
  error_code: string | null;
  status_detail: string | null;
}

export interface RequestLogDetail {
  request_id: string;
  log: RequestLog;
  metrics: RequestMetricDetail | null;
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
  masked_key: string;
  plain_secret?: string | null;
  status: 'active' | 'disabled';
  scopes: string[];
  rpm_limit: number | null;
  concurrency_limit: number | null;
  created_at: string;
  disabled_at: string | null;
  last_used_at: string | null;
  note: string | null;
  usage_summary?: {
    total_requests: number;
    total_tokens: number | null;
  };
}

export interface ModelRouteRow {
  name: string;
  display_name: string;
  backend_model: string | null;
  backend_type: string | null;
  enabled: boolean;
  lifecycle_mode: 'managed_local' | 'external';
  upstream_protocol: 'responses' | 'chat' | 'messages';
  upstream_base_url: string | null;
  upstream_model: string | null;
  upstream_auth_kind: 'none' | 'bearer' | 'x_api_key';
  upstream_auth_ref: string | null;
  source_kind: 'profile_seed' | 'manual';
  source_ref: string | null;
  stale: boolean;
  capabilities_json: {
    supports_responses: boolean;
    supports_chat: boolean;
    supports_messages: boolean;
    supports_stream: boolean;
    supports_function_tools: boolean;
    supports_builtin_tools: boolean;
    supports_previous_response_id_native: boolean;
    supports_json_schema: boolean;
  };
  native_protocols_json: string[];
  adapter_policies_json: string[];
  tool_policies_json: {
    openai_function_tools?: boolean;
    anthropic_function_tools?: boolean;
    builtin_tools?: boolean;
  };
  protocol_features_json: {
    stream?: boolean;
    count_tokens?: boolean;
    json_schema?: boolean;
    previous_response_id?: boolean;
  };
  recommended_runtime_semantics?: {
    native_protocols_json: string[];
    adapter_policies_json: string[];
    protocol_features_json: {
      stream?: boolean;
      count_tokens?: boolean;
      json_schema?: boolean;
      previous_response_id?: boolean;
    };
  };
}

export interface ReadinessOverview {
  readiness: Record<string, unknown> | null;
  base_urls: {
    local: string;
    lan: string;
  };
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

export interface UsageSummary {
  request_count: number;
  success_count: number;
  success_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  throughput_tokens_per_s: number;
  tokens_observed_requests: number;
  total_tokens: number | null;
  cache_creation_tokens: number | null;
  cache_read_tokens: number | null;
  cache_miss_tokens: number | null;
  cache_read_observed_requests: number;
}

export interface UsageTrendPoint {
  bucket: string;
  request_count: number;
  total_tokens: number;
  cache_read_tokens: number | null;
  cache_read_observed: number;
}

export interface UsageChartPoint {
  bucket: string;
  label: string;
  request_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  cache_miss_tokens: number;
  cache_tokens: number;
  total_tokens: number;
}

export interface UsageChartGroup {
  group: string;
  label: string;
  totals: Omit<UsageChartPoint, 'bucket' | 'label' | 'request_count'>;
  points: UsageChartPoint[];
}

export interface UsageChart {
  window: '12h' | 'day' | 'month' | 'year';
  group_by: 'backend_type' | 'model_name' | 'device_type';
  totals: Omit<UsageChartPoint, 'bucket' | 'label' | 'request_count'>;
  points: UsageChartPoint[];
  groups: UsageChartGroup[];
}

export interface UsageBreakdownItem {
  group: string | number | null;
  request_count: number;
  total_tokens: number;
  cache_read_tokens: number | null;
  cache_read_observed: number;
}

export interface UsageOverview {
  summary: UsageSummary;
  trend: UsageTrendPoint[];
  breakdown: {
    models: UsageBreakdownItem[];
    backends: UsageBreakdownItem[];
    api_keys: UsageBreakdownItem[];
  };
  chart: UsageChart;
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

export interface DiagnosticsStatus {
  backend_type: string;
  gpu: {
    gpus: Array<{
      index: number;
      name: string;
      memory_total_mb: number;
      memory_used_mb: number;
      utilization_percent: number;
    }>;
    cuda_version: string;
  };
  container: {
    info: {
      status: string;
      running: boolean;
      exit_code: number;
      started_at: string;
      restart_count: number;
      image: string;
      memory_limit: number;
      shm_size: number;
      uptime?: string;
    };
    snapshot: {
      exists: boolean;
      name: string;
      status: string;
      image: string;
    };
  };
  model: {
    model_dir: string;
    model_name: string;
    model_format: string;
    model_config: {
      model_type?: string;
      hidden_size?: number;
      num_hidden_layers?: number;
      vocab_size?: number;
    };
  };
  inference_params: Record<string, string | number | boolean>;
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
  backend_model?: string | null;
  enabled?: boolean;
  backend_type?: string | null;
  lifecycle_mode?: 'managed_local' | 'external';
  upstream_protocol?: 'responses' | 'chat' | 'messages';
  upstream_base_url?: string | null;
  upstream_model?: string | null;
  upstream_auth_kind?: 'none' | 'bearer' | 'x_api_key';
  upstream_auth_ref?: string | null;
  capabilities_json?: ModelRouteRow['capabilities_json'];
  native_protocols_json?: string[];
  adapter_policies_json?: string[];
  tool_policies_json?: ModelRouteRow['tool_policies_json'];
  protocol_features_json?: ModelRouteRow['protocol_features_json'];
}

interface CreateModelRoutePayload {
  name: string;
  display_name: string;
  lifecycle_mode: 'external';
  upstream_protocol: 'responses' | 'chat' | 'messages';
  upstream_base_url: string;
  upstream_model: string;
  upstream_auth_kind?: 'none' | 'bearer' | 'x_api_key';
  upstream_auth_ref?: string | null;
  enabled?: boolean;
  capabilities_json?: ModelRouteRow['capabilities_json'];
  native_protocols_json?: string[];
  adapter_policies_json?: string[];
  tool_policies_json?: ModelRouteRow['tool_policies_json'];
  protocol_features_json?: ModelRouteRow['protocol_features_json'];
}

interface LoadingState {
  snapshot: boolean;
  requestLogs: boolean;
  apiKeys: boolean;
  modelRoutes: boolean;
  schedule: boolean;
  usageOverview: boolean;
}

interface AppState {
  currentPage: Page;
  setCurrentPage: (page: Page) => void;
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  pageTitle: string;
  apiBase: string;
  setApiBase: (url: string) => void;
  sseConnected: boolean;
  globalError: string | null;
  setGlobalError: (error: string | null) => void;
  copyFeedback: {
    message: string;
    visible: boolean;
  } | null;
  copyToClipboard: (value: string, message?: string) => Promise<void>;
  lastUpdated: Date | null;
  snapshot: AdminSnapshot | null;
  snapshotHistory: SnapshotHistoryPoint[];
  requestLogs: RequestLog[];
  requestLogDetail: RequestLogDetail | null;
  requestLogsTotal: number;
  requestLogsLimit: number;
  requestLogsOffset: number;
  apiKeys: ApiKeyRow[];
  modelRoutes: ModelRouteRow[];
  schedule: ScheduleConfig | null;
  diagnostics: DiagnosticsStatus | null;
  readinessOverview: ReadinessOverview | null;
  usageOverview: UsageOverview | null;
  loading: LoadingState;
  refreshAll: () => Promise<void>;
  refreshSnapshot: () => Promise<void>;
  refreshRequestLogs: (options?: {
    limit?: number;
    offset?: number;
    dateFrom?: string | null;
    dateTo?: string | null;
    status?: string | null;
    query?: string | null;
  }) => Promise<void>;
  fetchRequestLogDetail: (requestId: string) => Promise<RequestLogDetail>;
  clearRequestLogDetail: () => void;
  exportRequestLogsCsv: (options?: {
    dateFrom?: string | null;
    dateTo?: string | null;
    status?: string | null;
    query?: string | null;
  }) => Promise<void>;
  refreshApiKeys: () => Promise<void>;
  refreshModelRoutes: () => Promise<void>;
  refreshSchedule: () => Promise<void>;
  refreshDiagnostics: () => Promise<void>;
  refreshReadinessOverview: () => Promise<void>;
  refreshUsageOverview: (options?: {
    granularity?: 'day' | 'month' | 'year';
    window?: '12h' | 'day' | 'month' | 'year';
    groupBy?: 'backend_type' | 'model_name' | 'device_type';
  }) => Promise<void>;
  createApiKey: (payload: CreateApiKeyPayload) => Promise<{secret: string; key: ApiKeyRow}>;
  updateApiKey: (id: number, payload: UpdateApiKeyPayload) => Promise<ApiKeyRow>;
  deleteApiKey: (id: number) => Promise<void>;
  createModelRoute: (payload: CreateModelRoutePayload) => Promise<ModelRouteRow>;
  deleteModelRoute: (name: string) => Promise<void>;
  updateModelRoute: (name: string, payload: UpdateModelRoutePayload) => Promise<ModelRouteRow>;
  updateSchedule: (payload: Partial<ScheduleConfig>) => Promise<ScheduleConfig>;
  restartBackend: () => Promise<void>;
}

function inferDefaultApiBase(): string {
  if (typeof window === 'undefined') {
    return '/';
  }
  return window.location.origin;
}

const defaultApiBase = localStorage.getItem('vllm-console-api-base') || inferDefaultApiBase();

const AppContext = createContext<AppState | undefined>(undefined);

function resolveApiBase(apiBase: string): string {
  const normalized = apiBase.trim();
  if (normalized) {
    return normalized.endsWith('/') ? normalized : `${normalized}/`;
  }
  return `${inferDefaultApiBase()}/`;
}

function buildUrl(apiBase: string, path: string): string {
  return new URL(path, resolveApiBase(apiBase)).toString();
}

function authHeaders(headers?: HeadersInit): HeadersInit {
  return {
    Accept: 'application/json',
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
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale());
  const [apiBase, setApiBase] = useState(defaultApiBase);
  const [sseConnected, setSseConnected] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<{message: string; visible: boolean} | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [snapshot, setSnapshot] = useState<AdminSnapshot | null>(null);
  const [snapshotHistory, setSnapshotHistory] = useState<SnapshotHistoryPoint[]>([]);
  const [requestLogs, setRequestLogs] = useState<RequestLog[]>([]);
  const [requestLogDetail, setRequestLogDetail] = useState<RequestLogDetail | null>(null);
  const [requestLogsTotal, setRequestLogsTotal] = useState(0);
  const [requestLogsLimit, setRequestLogsLimit] = useState(50);
  const [requestLogsOffset, setRequestLogsOffset] = useState(0);
  const [apiKeys, setApiKeys] = useState<ApiKeyRow[]>([]);
  const [modelRoutes, setModelRoutes] = useState<ModelRouteRow[]>([]);
  const [schedule, setSchedule] = useState<ScheduleConfig | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsStatus | null>(null);
  const [readinessOverview, setReadinessOverview] = useState<ReadinessOverview | null>(null);
  const [usageOverview, setUsageOverview] = useState<UsageOverview | null>(null);
  const [loading, setLoading] = useState<LoadingState>({
    snapshot: true,
    requestLogs: true,
    apiKeys: true,
    modelRoutes: true,
    schedule: true,
    usageOverview: true,
  });
  const streamAbortRef = useRef<AbortController | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const copyFeedbackHideTimerRef = useRef<number | null>(null);
  const copyFeedbackClearTimerRef = useRef<number | null>(null);

  useEffect(() => {
    localStorage.setItem('vllm-console-api-base', apiBase);
  }, [apiBase]);

  useEffect(() => {
    writeStoredLocale(locale);
  }, [locale]);

  function setLocale(nextLocale: Locale) {
    setLocaleState(nextLocale);
  }

  function toggleLocale() {
    setLocaleState((previous) => (previous === 'zh' ? 'en' : 'zh'));
  }

  function t(key: string, vars?: Record<string, string | number>) {
    return translate(locale, key, vars);
  }

  async function copyToClipboard(value: string, message?: string) {
    if (!value) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      if (copyFeedbackHideTimerRef.current) {
        window.clearTimeout(copyFeedbackHideTimerRef.current);
      }
      if (copyFeedbackClearTimerRef.current) {
        window.clearTimeout(copyFeedbackClearTimerRef.current);
      }
      setCopyFeedback({message: message ?? t('common.copied'), visible: true});
      copyFeedbackHideTimerRef.current = window.setTimeout(() => {
        setCopyFeedback((previous) => (previous ? {...previous, visible: false} : null));
        copyFeedbackHideTimerRef.current = null;
      }, 1500);
      copyFeedbackClearTimerRef.current = window.setTimeout(() => {
        setCopyFeedback(null);
        copyFeedbackClearTimerRef.current = null;
      }, 1900);
    } catch (error) {
      setGlobalError(toErrorMessage(error, '复制失败'));
      throw error;
    }
  }

  async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(buildUrl(apiBase, path), {
      ...init,
      headers: authHeaders(init?.headers),
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

  async function refreshRequestLogs(options?: {
    limit?: number;
    offset?: number;
    dateFrom?: string | null;
    dateTo?: string | null;
    status?: string | null;
    query?: string | null;
  }) {
    setLoading((previous) => ({...previous, requestLogs: true}));
    try {
      const params = new URLSearchParams();
      params.set('limit', String(options?.limit ?? 200));
      params.set('offset', String(options?.offset ?? 0));
      if (options?.dateFrom) {
        params.set('date_from', options.dateFrom);
      }
      if (options?.dateTo) {
        params.set('date_to', options.dateTo);
      }
      if (options?.status && options.status !== 'all') {
        params.set('status', options.status);
      }
      if (options?.query?.trim()) {
        params.set('query', options.query.trim());
      }
      const payload = await requestJson<RequestLogsResponse>(`/admin/request-logs?${params.toString()}`);
      setRequestLogs(payload.logs);
      setRequestLogsTotal(payload.total);
      setRequestLogsLimit(payload.limit);
      setRequestLogsOffset(payload.offset);
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

  async function refreshDiagnostics() {
    try {
      const agentBase = apiBase.replace(/\/+$/, '').replace(/:\d+$/, ':4010');
      const payload = await fetch(`${agentBase}/admin/diagnostics/status`, {
        headers: authHeaders(),
      });
      if (payload.ok) {
        const data = await payload.json() as DiagnosticsStatus;
        setDiagnostics(data);
      }
    } catch {
      // Silently fail diagnostics fetch
    }
  }

  async function refreshReadinessOverview() {
    try {
      const payload = await requestJson<ReadinessOverview>('/admin/overview/readiness');
      setReadinessOverview(payload);
    } catch {
      // Silently fail readiness overview fetch
    }
  }

  async function refreshUsageOverview(options?: {
    granularity?: 'day' | 'month' | 'year';
    window?: '12h' | 'day' | 'month' | 'year';
    groupBy?: 'backend_type' | 'model_name' | 'device_type';
  }) {
    setLoading((previous) => ({...previous, usageOverview: true}));
    try {
      const granularity = options?.granularity ?? 'day';
      const window = options?.window ?? '12h';
      const groupBy = options?.groupBy ?? 'backend_type';
      const payload = await requestJson<UsageOverview>(
        `/admin/overview/usage?granularity=${encodeURIComponent(granularity)}&window=${encodeURIComponent(window)}&group_by=${encodeURIComponent(groupBy)}`,
      );
      setUsageOverview(payload);
      setGlobalError(null);
      setLastUpdated(new Date());
    } catch (error) {
      const message = toErrorMessage(error, '无法获取用量概览');
      setGlobalError(message);
      throw error;
    } finally {
      setLoading((previous) => ({...previous, usageOverview: false}));
    }
  }

  async function refreshAll() {
    await Promise.allSettled([
      refreshSnapshot(),
      refreshRequestLogs(),
      refreshApiKeys(),
      refreshModelRoutes(),
      refreshSchedule(),
      refreshDiagnostics(),
      refreshReadinessOverview(),
      refreshUsageOverview(),
    ]);
  }

  async function createApiKey(payload: CreateApiKeyPayload) {
    const response = await requestJson<{key: ApiKeyRow; secret: string}>('/admin/keys', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    setApiKeys((previous) => {
      const nextKey = {...response.key, plain_secret: response.secret};
      return [nextKey, ...previous.filter((item) => item.id !== nextKey.id)];
    });
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

  async function createModelRoute(payload: CreateModelRoutePayload) {
    const response = await requestJson<{model: ModelRouteRow}>('/admin/models', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    setModelRoutes((previous) => [...previous, response.model]);
    setLastUpdated(new Date());
    setGlobalError(null);
    void refreshSnapshot();
    return response.model;
  }

  async function deleteModelRoute(name: string) {
    await requestJson<{deleted: boolean; name: string}>(`/admin/models/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
    setModelRoutes((previous) => previous.filter((item) => item.name !== name));
    setLastUpdated(new Date());
    setGlobalError(null);
    void refreshSnapshot();
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

  async function exportRequestLogsCsv(options?: {
    dateFrom?: string | null;
    dateTo?: string | null;
    status?: string | null;
    query?: string | null;
  }) {
    const params = new URLSearchParams();
    if (options?.dateFrom) {
      params.set('date_from', options.dateFrom);
    }
    if (options?.dateTo) {
      params.set('date_to', options.dateTo);
    }
    if (options?.status && options.status !== 'all') {
      params.set('status', options.status);
    }
    if (options?.query?.trim()) {
      params.set('query', options.query.trim());
    }
    const response = await fetch(buildUrl(apiBase, `/admin/request-logs/export?${params.toString()}`), {
      headers: authHeaders(),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const text = await response.text();
    const blob = new Blob([text], {type: 'text/csv;charset=utf-8'});
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = 'request-logs.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }

  async function fetchRequestLogDetail(requestId: string) {
    const payload = await requestJson<RequestLogDetail>(`/admin/request-logs/${encodeURIComponent(requestId)}`);
    setRequestLogDetail(payload);
    return payload;
  }

  function clearRequestLogDetail() {
    setRequestLogDetail(null);
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
          headers: authHeaders(),
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
      if (copyFeedbackHideTimerRef.current) {
        window.clearTimeout(copyFeedbackHideTimerRef.current);
        copyFeedbackHideTimerRef.current = null;
      }
      if (copyFeedbackClearTimerRef.current) {
        window.clearTimeout(copyFeedbackClearTimerRef.current);
        copyFeedbackClearTimerRef.current = null;
      }
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (streamAbortRef.current) {
        streamAbortRef.current.abort();
        streamAbortRef.current = null;
      }
    };
  }, [apiBase]);

  const pageTitle = getPageLabel(currentPage, locale);

  return (
    <AppContext.Provider
      value={{
        currentPage,
        setCurrentPage,
        locale,
        setLocale,
        toggleLocale,
        t,
        pageTitle,
        apiBase,
        setApiBase,
        sseConnected,
        globalError,
        setGlobalError,
        copyFeedback,
        copyToClipboard,
        lastUpdated,
        snapshot,
        snapshotHistory,
        requestLogs,
        requestLogDetail,
        requestLogsTotal,
        requestLogsLimit,
        requestLogsOffset,
        apiKeys,
        modelRoutes,
        schedule,
        diagnostics,
        readinessOverview,
        usageOverview,
        loading,
        refreshAll,
        refreshSnapshot,
        refreshRequestLogs,
        fetchRequestLogDetail,
        clearRequestLogDetail,
        refreshApiKeys,
        refreshModelRoutes,
        refreshSchedule,
        refreshDiagnostics,
        refreshReadinessOverview,
        refreshUsageOverview,
        exportRequestLogsCsv,
        createApiKey,
        updateApiKey,
        deleteApiKey,
        createModelRoute,
        deleteModelRoute,
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
