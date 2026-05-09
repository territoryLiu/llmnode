export interface AgentStateSnapshot {
  status: string
  backend_ready?: boolean
  failure_count?: number
  checked_at?: string
  last_error?: string
  last_recovery_at?: string
}

export interface RequestLogEntry {
  id: number
  request_id: string
  model_name: string
  status: string
  protocol: string
  error_message?: string | null
  created_at: string
  api_key_id?: number | null
  auth_source?: string | null
  client_ip?: string | null
  user_agent?: string | null
  rejection_reason?: string | null
}

export interface AgentEventEntry {
  id: number
  status: string
  reason?: string | null
  created_at: string
}

export interface ModelEntry {
  id: string
  object: string
  created: number
  owned_by: string
}

export interface RuntimeGatewayConfig {
  host: string
  port: number
  backend_url: string
  backend_model: string
  agent_base_url: string
  agent_status_url: string
  require_agent_ready: boolean
  queue_limit: number
  execution_limit: number
  api_key_configured: boolean
}

export interface RuntimeAgentConfig {
  host: string
  port: number
  state: string
  poll_interval: number
  auto_recover: boolean
  recovery_threshold: number
}

export interface RuntimeScheduleConfig {
  timezone: string
  work_days: string[]
  start_time: string
  end_time: string
  auto_stop_enabled: boolean
  auto_start_enabled: boolean
  cooldown_minutes: number
}

export interface RuntimeVLLMConfig {
  backend_type: string
  container_name: string
  image_name: string
  model_dir: string
  model_name: string
  host_port: number
  gpu_memory_utilization: number
  tensor_parallel_size: number
  max_model_len: number
  max_num_seqs: number
  shm_size: string
  enable_auto_tool_choice: boolean
  reasoning_parser: string
  tool_call_parser: string
}

export interface RuntimeModelRoute {
  name: string
  display_name: string
  backend_model: string
  backend_type: string
  enabled: boolean
}

export interface BackendContainerSnapshot {
  exists: boolean
  running: boolean
  status: string
  name?: string | null
  image?: string | null
}

export interface RuntimeSnapshot {
  gateway: RuntimeGatewayConfig
  agent: RuntimeAgentConfig
  schedule: RuntimeScheduleConfig
  vllm: RuntimeVLLMConfig
  model_routes: RuntimeModelRoute[]
}

export interface AdminSnapshot {
  backend_type: string
  backend_ready: boolean
  backend_error?: string | null
  backend_container?: BackendContainerSnapshot | null
  agent_state: AgentStateSnapshot | null
  require_agent_ready: boolean
  queue_length: number
  models: ModelEntry[]
  logs: RequestLogEntry[]
  events: AgentEventEntry[]
  runtime?: RuntimeSnapshot
}

export interface MetricPoint {
  label: string
  queueLength: number
  failureCount: number
}

export interface AdminApiKeyEntry {
  id: number
  name: string
  status: 'active' | 'disabled'
  scopes: string[]
  rpm_limit: number | null
  concurrency_limit: number | null
  created_at: string
  disabled_at: string | null
  last_used_at: string | null
  note: string | null
}

export interface AdminApiKeyListResponse {
  keys: AdminApiKeyEntry[]
}

export interface AdminApiKeyCreatePayload {
  name: string
  scopes: string[]
  rpm_limit: number | null
  concurrency_limit: number | null
  note: string | null
}

export interface AdminApiKeyUpdatePayload {
  name?: string
  status?: 'active' | 'disabled'
  scopes?: string[]
  rpm_limit?: number | null
  concurrency_limit?: number | null
  note?: string | null
}

export interface AdminApiKeyCreateResponse {
  key: AdminApiKeyEntry
  secret: string
}

export interface AdminApiKeyUpdateResponse {
  key: AdminApiKeyEntry
}

export interface AdminServiceActionResponse {
  accepted: boolean
  service: string
  action: string
  agent_status: string
}
