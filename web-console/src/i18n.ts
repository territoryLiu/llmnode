export type Locale = 'zh' | 'en';

export const DEFAULT_LOCALE: Locale = 'zh';
export const LOCALE_STORAGE_KEY = 'llmnode-console-locale';

export const pageLabels = {
  overview: {zh: '总览', en: 'Overview'},
  usage: {zh: '请求记录', en: 'Usage'},
  keys: {zh: '密钥管理', en: 'API Keys'},
  models: {zh: '模型路由', en: 'Models'},
  schedule: {zh: '调度策略', en: 'Schedule'},
} as const;

export const translations = {
  common: {
    refresh: {zh: '刷新', en: 'Refresh'},
    save: {zh: '保存', en: 'Save'},
    yes: {zh: '是', en: 'Yes'},
    no: {zh: '否', en: 'No'},
    unknown: {zh: '未知', en: 'Unknown'},
    none: {zh: '无', en: 'None'},
  },
  layout: {
    brand: {zh: 'LlmNode', en: 'LlmNode'},
    nav: {
      overview: {zh: '总览', en: 'Overview'},
      usage: {zh: '请求记录', en: 'Usage'},
      keys: {zh: '密钥管理', en: 'API Keys'},
      models: {zh: '模型路由', en: 'Models'},
      schedule: {zh: '调度策略', en: 'Schedule'},
    },
    subtitle: {
      zh: '控制台已接入当前 llmnode 控制面。',
      en: 'Console is connected to the current llmnode control plane.',
    },
    switchToEnglish: {zh: '切换到 English', en: 'Switch to English'},
    switchToChinese: {zh: '切换到中文', en: 'Switch to Chinese'},
    lastUpdated: {zh: '最近更新', en: 'Last updated'},
    snapshotLive: {zh: '实时快照已连接', en: 'Snapshot Live'},
    snapshotReconnecting: {zh: '实时快照重连中', en: 'Snapshot Reconnecting'},
    admin: {zh: '管理员', en: 'Admin'},
    apiKeyPlaceholder: {zh: '输入 sk- 开头的 API 密钥', en: 'Enter an sk- API key'},
    saveApiKey: {zh: '保存密钥', en: 'Save API Key'},
    apiKeyRequired: {zh: '请先输入 API 密钥', en: 'API key is required'},
    apiKeyMissingBanner: {
      zh: '当前未配置 API 密钥。请先用控制命令创建一把 sk- 管理员密钥，然后在这里输入。',
      en: 'No API key configured. Create an sk- admin key first, then enter it here.',
    },
  },
  overview: {
    status: {zh: '状态', en: 'Status'},
    healthy: {zh: '健康', en: 'Healthy'},
    degraded: {zh: '降级', en: 'Degraded'},
    agentGated: {zh: '依赖 Agent 就绪', en: 'Agent gated'},
    directGateway: {zh: '直连网关模式', en: 'Direct gateway'},
    requests: {zh: '请求数', en: 'Requests'},
    requestSummary: {zh: '当前快照中的最近请求数', en: 'Recent requests in the current snapshot'},
    models: {zh: '模型数', en: 'Models'},
    modelSummary: {zh: '已配置逻辑模型路由', en: 'Configured logical model routes'},
    queue: {zh: '队列', en: 'Queue'},
    queueNow: {zh: '实时队列', en: 'Live Queue'},
    queueLimit: {zh: '上限 {count}', en: 'Limit {count}'},
    queueTrend: {zh: '队列与失败趋势', en: 'Queue & Failure Trend'},
    recentSamples: {zh: '最近 {count} 个采样点', en: 'Recent {count} samples'},
    loadingTrend: {zh: '正在加载趋势数据...', en: 'Loading trend data...'},
    noTrend: {zh: '暂时还没有趋势数据', en: 'No trend data yet'},
    modelDistribution: {zh: '模型分布', en: 'Model Distribution'},
    noModelRequests: {zh: '最近没有可统计的模型请求', en: 'No recent model requests to summarize'},
    availableModels: {zh: '当前可访问模型', en: 'Available Models'},
    availableModelsHint: {zh: '下面列出当前已启用模型，复制模型名后可直接切换调用。', en: 'These enabled model IDs are ready to copy and switch to directly.'},
    noAvailableModels: {zh: '当前没有已启用模型', en: 'No enabled models available'},
    copyModel: {zh: '复制模型名', en: 'Copy model name'},
    routeModelName: {zh: '逻辑模型名', en: 'Logical Model'},
    routeBackendModel: {zh: '后端模型', en: 'Backend Model'},
    recentRequests: {zh: '最近请求', en: 'Recent Requests'},
    reqId: {zh: '请求 ID', en: 'Req ID'},
    model: {zh: '模型', en: 'Model'},
    statusColumn: {zh: '状态', en: 'Status'},
    loadingRequests: {zh: '正在拉取请求记录...', en: 'Loading requests...'},
    noRequests: {zh: '还没有请求记录', en: 'No requests yet'},
    quickActions: {zh: '快捷操作', en: 'Quick Actions'},
    restartBackend: {zh: '重启后端', en: 'Restart Backend'},
    restarting: {zh: '重启中...', en: 'Restarting...'},
    editSchedule: {zh: '编辑调度', en: 'Edit Schedule'},
    errors: {zh: '错误与异常', en: 'Errors & Exceptions'},
    noErrors: {zh: '最近样本中没有异常请求。', en: 'No recent errors in sampled requests.'},
    refreshSnapshot: {zh: '刷新快照', en: 'Refresh Snapshot'},
  },
  usage: {
    totalRequests: {zh: '总请求数', en: 'Total Requests'},
    exceptions: {zh: '异常数', en: 'Exceptions'},
    rejected: {zh: '拒绝数', en: 'Rejected'},
    backendType: {zh: '后端类型', en: 'Backend Type'},
    totalTokens: {zh: '总 Token 数', en: 'Total Tokens'},
    cacheReadTokens: {zh: '缓存读取 Token', en: 'Cache Read Tokens'},
    cacheCreationTokens: {zh: '缓存写入 Token', en: 'Cache Creation Tokens'},
    successRate: {zh: '成功率', en: 'Success Rate'},
    noTrendData: {zh: '暂无趋势数据', en: 'No trend data yet'},
    tokensPerDay: {zh: '每日 Token 用量', en: 'Daily Token Usage'},
    backendUsage: {zh: '后端用量分布', en: 'Backend Usage Breakdown'},
    searchPlaceholder: {zh: '搜索请求 ID、模型、IP...', en: 'Search request ID, model, IP...'},
    allStatus: {zh: '全部状态', en: 'All Status'},
    success: {zh: '成功', en: 'Success'},
    error: {zh: '错误', en: 'Error'},
    showing: {zh: '显示 {shown} / {total} 条记录', en: 'Showing {shown} / {total} records'},
    timeId: {zh: '时间 / ID', en: 'Time / ID'},
    protocol: {zh: '协议', en: 'Protocol'},
    model: {zh: '模型', en: 'Model'},
    status: {zh: '状态', en: 'Status'},
    source: {zh: '来源', en: 'Source'},
    clientIp: {zh: '客户端 IP', en: 'Client IP'},
    reason: {zh: '原因', en: 'Reason'},
    userAgent: {zh: '设备 / UA', en: 'Device / UA'},
    loadingLogs: {zh: '正在加载请求日志...', en: 'Loading request logs...'},
    noResults: {zh: '没有符合筛选条件的记录', en: 'No records match the current filters'},
    trendTitle: {zh: '调用趋势', en: 'Usage Trend'},
    trendSubtitle: {zh: '按时间窗口查看输入、输出、缓存与总 Token 用量', en: 'View prompt, completion, cache, and total tokens by time window'},
    recordsTitle: {zh: '调用记录', en: 'Request Records'},
    dateFrom: {zh: '开始时间', en: 'Start Time'},
    dateTo: {zh: '结束时间', en: 'End Time'},
    applyTime: {zh: '应用时间', en: 'Apply Time'},
    resetTime: {zh: '重置', en: 'Reset'},
    exportCsv: {zh: '导出 CSV', en: 'Export CSV'},
    detailTitle: {zh: '请求详情', en: 'Request Detail'},
    detailClose: {zh: '关闭', en: 'Close'},
    latencyMs: {zh: '耗时(ms)', en: 'Latency (ms)'},
    tokensPerSecond: {zh: '输出 TPS', en: 'Output TPS'},
    backendLabel: {zh: '推理后端', en: 'Backend'},
    statusDetail: {zh: '状态详情', en: 'Status Detail'},
    errorMessage: {zh: '错误信息', en: 'Error Message'},
    requestId: {zh: '请求 ID', en: 'Request ID'},
    clickRowHint: {zh: '点击任意记录查看详情', en: 'Click any record to inspect details'},
    pageSize: {zh: '每页', en: 'Page Size'},
    prevPage: {zh: '上一页', en: 'Previous'},
    nextPage: {zh: '下一页', en: 'Next'},
    pageStatus: {zh: '第 {page} / {pages} 页', en: 'Page {page} / {pages}'},
    jumpPage: {zh: '跳到页', en: 'Jump to Page'},
    goPage: {zh: '跳转', en: 'Go'},
    range12h: {zh: '12 小时', en: '12 Hours'},
    rangeDay: {zh: '天', en: 'Day'},
    rangeMonth: {zh: '月', en: 'Month'},
    rangeYear: {zh: '年', en: 'Year'},
    groupByBackend: {zh: '按后端', en: 'By Backend'},
    groupByModel: {zh: '按模型', en: 'By Model'},
    groupByDevice: {zh: '按设备', en: 'By Device'},
    metricPrompt: {zh: '输入 Token', en: 'Prompt Tokens'},
    metricCompletion: {zh: '输出 Token', en: 'Completion Tokens'},
    metricCache: {zh: '缓存 Token', en: 'Cache Tokens'},
    metricTotal: {zh: '总 Token', en: 'Total Tokens'},
    activeGroup: {zh: '当前分组', en: 'Active Group'},
    allGroups: {zh: '全部', en: 'All'},
    noChartData: {zh: '当前时间窗口暂无趋势数据', en: 'No trend data in the selected window'},
    deviceDesktop: {zh: '桌面端', en: 'Desktop'},
    deviceMobile: {zh: '移动端', en: 'Mobile'},
    deviceTool: {zh: '工具', en: 'Tool'},
    deviceUnknown: {zh: '未知设备', en: 'Unknown Device'},
  },
  keys: {
    totalKeys: {zh: '密钥总数', en: 'Total Keys'},
    active: {zh: '启用中', en: 'Active'},
    disabled: {zh: '已禁用', en: 'Disabled'},
    inferenceScopes: {zh: '推理权限数', en: 'Inference Scopes'},
    adminScopes: {zh: '管理权限数', en: 'Admin Scopes'},
    keyName: {zh: '密钥名称', en: 'Key name'},
    rpmLimit: {zh: 'RPM 限制', en: 'RPM limit'},
    concurrency: {zh: '并发限制', en: 'Concurrency'},
    optionalNote: {zh: '可选备注', en: 'Optional note'},
    createKey: {zh: '创建密钥', en: 'Create Key'},
    creating: {zh: '创建中...', en: 'Creating...'},
    scopeAdmin: {zh: '管理权限', en: 'Admin scope'},
    scopeInference: {zh: '推理权限', en: 'Inference scope'},
    copy: {zh: '复制到剪贴板', en: 'Copy to clipboard'},
    copied: {zh: '已复制到剪贴板', en: 'Copied to clipboard'},
    keyList: {zh: '数据库中的 API 密钥', en: 'Database API Keys'},
    loadingKeys: {zh: '正在加载...', en: 'Loading...'},
    keysCount: {zh: '{count} 个密钥', en: '{count} keys'},
    name: {zh: '名称', en: 'Name'},
    status: {zh: '状态', en: 'Status'},
    scopes: {zh: '权限', en: 'Scopes'},
    limits: {zh: '限制 (RPM/并发)', en: 'Limits (RPM/Conc)'},
    createdAt: {zh: '创建时间', en: 'Created At'},
    actions: {zh: '操作', en: 'Actions'},
    noKeys: {zh: '还没有 API Key', en: 'No API keys yet'},
    lastUsed: {zh: '最后使用', en: 'Last used'},
    disable: {zh: '禁用', en: 'Disable'},
    enable: {zh: '启用', en: 'Enable'},
    maskedKey: {zh: '密钥', en: 'Key'},
    liveKey: {zh: '本次明文', en: 'Session Secret'},
    copyMasked: {zh: '复制脱敏密钥', en: 'Copy masked key'},
    copySecret: {zh: '复制真实密钥', en: 'Copy full key'},
    show: {zh: '显示', en: 'Show'},
    hide: {zh: '隐藏', en: 'Hide'},
    usageSummary: {zh: '用量统计', en: 'Usage'},
    totalRequests: {zh: '总请求数', en: 'Total Requests'},
    totalTokens: {zh: '总 Token 数', en: 'Total Tokens'},
    baseUrls: {zh: '服务地址', en: 'Base URLs'},
    local: {zh: '本地地址', en: 'Local'},
    lan: {zh: '局域网地址', en: 'LAN'},
    copyBase: {zh: '复制地址', en: 'Copy address'},
  },
  models: {
    runtimeConfig: {zh: '运行时配置', en: 'Runtime Configuration'},
    singleBackendNotice: {
      zh: '当前运行时仍以单个受控本地后端为主，但每条逻辑模型路由已经可以独立配置外部上游协议。',
      en: 'The runtime still centers on a single managed local backend, but each logical route can now target its own external upstream protocol.',
    },
    backendType: {zh: '后端类型', en: 'Backend Type'},
    gpuMemUtil: {zh: 'GPU 显存利用率', en: 'GPU Mem Util'},
    maxContext: {zh: '最大上下文', en: 'Max Context'},
    serveModel: {zh: '服务模型', en: 'Serve Model'},
    logicalRouting: {zh: '逻辑模型路由', en: 'Logical Model Routing'},
    mappingNotice: {
      zh: '每条路由都可以定义生命周期、上游协议、鉴权方式与能力开关，用于兼容 chat/messages/responses 三类客户端。',
      en: 'Each route can define lifecycle, upstream protocol, auth mode, and capability flags to serve chat/messages/responses clients.',
    },
    logicalModelName: {zh: '逻辑模型名', en: 'Logical Model Name'},
    displayName: {zh: '显示名称', en: 'Display Name'},
    backendModel: {zh: '后端模型', en: 'Backend Model'},
    lifecycleMode: {zh: '生命周期', en: 'Lifecycle'},
    managedLocal: {zh: '本地受控', en: 'Managed Local'},
    external: {zh: '外部上游', en: 'External'},
    upstreamProtocol: {zh: '上游协议', en: 'Upstream Protocol'},
    upstreamBaseUrl: {zh: '上游地址', en: 'Upstream Base URL'},
    upstreamModel: {zh: '上游模型名', en: 'Upstream Model'},
    upstreamAuthKind: {zh: '鉴权方式', en: 'Auth Mode'},
    upstreamAuthRef: {zh: '鉴权引用', en: 'Auth Reference'},
    authNone: {zh: '无', en: 'None'},
    authBearer: {zh: 'Bearer', en: 'Bearer'},
    authXApiKey: {zh: 'X-API-Key', en: 'X-API-Key'},
    capabilities: {zh: '能力开关', en: 'Capabilities'},
    capabilityResponses: {zh: 'Responses', en: 'Responses'},
    capabilityChat: {zh: 'Chat', en: 'Chat'},
    capabilityMessages: {zh: 'Messages', en: 'Messages'},
    capabilityStream: {zh: 'Stream', en: 'Stream'},
    capabilityFunctionTools: {zh: 'Function Tools', en: 'Function Tools'},
    capabilityBuiltinTools: {zh: 'Builtin Tools', en: 'Builtin Tools'},
    capabilityPreviousResponse: {zh: 'Previous Response', en: 'Previous Response'},
    capabilityJsonSchema: {zh: 'JSON Schema', en: 'JSON Schema'},
    enabled: {zh: '启用', en: 'Enabled'},
    actions: {zh: '操作', en: 'Actions'},
    loadingRoutes: {zh: '正在加载路由...', en: 'Loading routes...'},
    noRoutes: {zh: '暂无模型路由', en: 'No model routes yet'},
    saving: {zh: '保存中...', en: 'Saving...'},
    currentConstraint: {zh: '当前约束', en: 'Current Constraint'},
    currentConstraintDesc: {
      zh: 'backend_type 只描述受控本地后端类型；真正请求走哪种协议，由 upstream_protocol 和 lifecycle_mode 决定。',
      en: 'backend_type only describes the managed local backend type; actual request protocol is determined by upstream_protocol and lifecycle_mode.',
    },
  },
  schedule: {
    schedulingBehavior: {zh: 'V2 调度行为', en: 'V2 Scheduling Behavior'},
    schedulingBehaviorDesc: {
      zh: '当前调度直接驱动应用内定时逻辑，这里保存的配置就是系统事实来源。',
      en: 'The scheduler directly drives in-app timing logic, and the configuration saved here is the system source of truth.',
    },
    runtimeStrategy: {zh: '运行时调度策略', en: 'Runtime Scheduling Strategy'},
    timezone: {zh: '时区', en: 'Timezone'},
    startTime: {zh: '开始时间', en: 'Start Time'},
    endTime: {zh: '结束时间', en: 'End Time'},
    cooldownMinutes: {zh: '冷却时间（分钟）', en: 'Cooldown (Minutes)'},
    workDays: {zh: '工作日', en: 'Work Days'},
    autoStart: {zh: '启用自动启动', en: 'Auto Start Enabled'},
    autoStartDesc: {zh: '到开始时间后自动唤起后端实例。', en: 'Automatically wake the backend after the start time.'},
    autoStop: {zh: '启用自动停止', en: 'Auto Stop Enabled'},
    autoStopDesc: {zh: '结束时间后自动关闭后端，节省资源。', en: 'Automatically stop the backend after the end time to save resources.'},
    loadingSchedule: {zh: '正在加载调度配置...', en: 'Loading schedule...'},
    saveHint: {zh: '保存后立即生效', en: 'Changes take effect immediately after saving'},
    applySchedule: {zh: '应用调度', en: 'Apply Schedule'},
    saving: {zh: '保存中...', en: 'Saving...'},
    days: {
      mon: {zh: '周一', en: 'Monday'},
      tue: {zh: '周二', en: 'Tuesday'},
      wed: {zh: '周三', en: 'Wednesday'},
      thu: {zh: '周四', en: 'Thursday'},
      fri: {zh: '周五', en: 'Friday'},
      sat: {zh: '周六', en: 'Saturday'},
      sun: {zh: '周日', en: 'Sunday'},
    },
  },
} as const;

function isLeafNode(value: unknown): value is Record<Locale, string> {
  return (
    typeof value === 'object' &&
    value !== null &&
    'zh' in (value as Record<string, unknown>) &&
    'en' in (value as Record<string, unknown>)
  );
}

export function translate(locale: Locale, key: string, vars?: Record<string, string | number>): string {
  const parts = key.split('.');
  let node: unknown = translations;
  for (const part of parts) {
    node = (node as Record<string, unknown>)?.[part];
  }
  if (!isLeafNode(node)) {
    return key;
  }
  const template = node[locale] ?? node.zh;
  if (!vars) {
    return template;
  }
  return Object.entries(vars).reduce(
    (result, [name, value]) => result.replaceAll(`{${name}}`, String(value)),
    template,
  );
}

export function getPageLabel(page: keyof typeof pageLabels, locale: Locale): string {
  return pageLabels[page][locale];
}

export function readStoredLocale(): Locale {
  if (typeof window === 'undefined') {
    return DEFAULT_LOCALE;
  }
  const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  return stored === 'en' ? 'en' : DEFAULT_LOCALE;
}

export function writeStoredLocale(locale: Locale) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  }
}

export function mapRequestStatus(locale: Locale, status: string): string {
  const dict = {
    zh: {ok: '成功', error: '错误', rejected: '拒绝'},
    en: {ok: 'Success', error: 'Error', rejected: 'Rejected'},
  } as const;
  return dict[locale][status as keyof typeof dict.en] ?? status;
}

export function mapAgentStatus(locale: Locale, status: string): string {
  const dict = {
    zh: {
      ready: '就绪',
      recovering: '恢复中',
      failed: '失败',
      unknown: '未知',
      running: '运行中',
      active: '启用中',
      disabled: '已禁用',
      manual: '手动',
    },
    en: {
      ready: 'Ready',
      recovering: 'Recovering',
      failed: 'Failed',
      unknown: 'Unknown',
      running: 'Running',
      active: 'Active',
      disabled: 'Disabled',
      manual: 'Manual',
    },
  } as const;
  return dict[locale][status as keyof typeof dict.en] ?? status;
}
