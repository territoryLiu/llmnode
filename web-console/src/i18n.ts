export type Locale = 'zh' | 'en';

export const DEFAULT_LOCALE: Locale = 'zh';
export const LOCALE_STORAGE_KEY = 'llmnode-console-locale';

export const pageLabels = {
  overview: {zh: '总览', en: 'Overview'},
  usage: {zh: '请求记录', en: 'Usage'},
  keys: {zh: '密钥管理', en: 'API Keys'},
  models: {zh: '模型路由', en: 'Models'},
  schedule: {zh: '调度策略', en: 'Schedule'},
  status: {zh: '系统状态', en: 'Status'},
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
      status: {zh: '系统状态', en: 'Status'},
    },
    subtitle: {
      zh: '控制台已接入当前 llmnode 控制面。',
      en: 'Console is connected to the current llmnode control plane.',
    },
    switchToEnglish: {zh: '切换到 English', en: 'Switch to English'},
    switchToChinese: {zh: '切换到中文', en: 'Switch to Chinese'},
    connection: {zh: '连接配置', en: 'Connection'},
    apiBase: {zh: 'API 地址', en: 'API Base'},
    apiKey: {zh: 'API 密钥', en: 'API Key'},
    lastUpdated: {zh: '最近更新', en: 'Last updated'},
    snapshotLive: {zh: '实时快照已连接', en: 'Snapshot Live'},
    snapshotReconnecting: {zh: '实时快照重连中', en: 'Snapshot Reconnecting'},
    admin: {zh: '管理员', en: 'Admin'},
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
    queueLimit: {zh: '队列上限 {count}', en: 'Queue limit {count}'},
    queueTrend: {zh: '队列与失败趋势', en: 'Queue & Failure Trend'},
    recentSamples: {zh: '最近 {count} 个采样点', en: 'Recent {count} samples'},
    loadingTrend: {zh: '正在加载趋势数据...', en: 'Loading trend data...'},
    noTrend: {zh: '暂时还没有趋势数据', en: 'No trend data yet'},
    modelDistribution: {zh: '模型分布', en: 'Model Distribution'},
    noModelRequests: {zh: '最近没有可统计的模型请求', en: 'No recent model requests to summarize'},
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
    loadingLogs: {zh: '正在加载请求日志...', en: 'Loading request logs...'},
    noResults: {zh: '没有符合筛选条件的记录', en: 'No records match the current filters'},
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
    generated: {zh: '密钥生成成功', en: 'Key Generated Successfully'},
    saveSecretWarning: {
      zh: '请立刻保存这个密钥。关闭后将无法再次查看。',
      en: 'Save this key now. You will not be able to see it again after closing.',
    },
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
  },
  models: {
    runtimeConfig: {zh: '运行时配置', en: 'Runtime Configuration'},
    singleBackendNotice: {
      zh: '当前版本默认只支持单个 vLLM 后端实例。',
      en: 'This version currently supports a single vLLM backend instance only.',
    },
    backendType: {zh: '后端类型', en: 'Backend Type'},
    gpuMemUtil: {zh: 'GPU 显存利用率', en: 'GPU Mem Util'},
    maxContext: {zh: '最大上下文', en: 'Max Context'},
    serveModel: {zh: '服务模型', en: 'Serve Model'},
    logicalRouting: {zh: '逻辑模型路由', en: 'Logical Model Routing'},
    mappingNotice: {
      zh: '映射前端暴露模型名到当前 vLLM 实际服务模型。',
      en: 'Maps exposed logical model names to the currently served vLLM model.',
    },
    logicalModelName: {zh: '逻辑模型名', en: 'Logical Model Name'},
    displayName: {zh: '显示名称', en: 'Display Name'},
    backendModel: {zh: '后端模型', en: 'Backend Model'},
    enabled: {zh: '启用', en: 'Enabled'},
    actions: {zh: '操作', en: 'Actions'},
    loadingRoutes: {zh: '正在加载路由...', en: 'Loading routes...'},
    noRoutes: {zh: '暂无模型路由', en: 'No model routes yet'},
    saving: {zh: '保存中...', en: 'Saving...'},
    currentConstraint: {zh: '当前约束', en: 'Current Constraint'},
    currentConstraintDesc: {
      zh: '这版控制台只维护逻辑模型名与单一 vLLM 后端模型的映射，不做多后端分流。',
      en: 'This console only manages mappings from logical model names to a single vLLM backend model and does not split traffic across multiple backends.',
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
  status: {
    nodeAgent: {zh: '节点代理', en: 'Node Agent'},
    backendReady: {zh: '后端就绪', en: 'Backend Ready'},
    backendType: {zh: '后端类型', en: 'Backend Type'},
    autoSchedule: {zh: '自动调度', en: 'Auto Schedule'},
    queueDepth: {zh: '队列深度', en: 'Queue Depth'},
    active: {zh: '启用中', en: 'Active'},
    manual: {zh: '手动', en: 'Manual'},
    containerInfo: {zh: '容器信息', en: 'Container Info'},
    containerName: {zh: '容器名称', en: 'Container Name'},
    state: {zh: '状态', en: 'State'},
    uptime: {zh: '运行时长', en: 'Uptime'},
    restartCount: {zh: '重启次数', en: 'Restart Count'},
    inferenceParams: {zh: '推理参数', en: 'Inference Params'},
    gpuInfo: {zh: 'GPU 信息', en: 'GPU Info'},
    memory: {zh: '显存', en: 'Memory'},
    utilization: {zh: '利用率', en: 'Utilization'},
    gpuState: {zh: '状态', en: 'State'},
    inUse: {zh: '使用中', en: 'In Use'},
    idle: {zh: '空闲', en: 'Idle'},
    modelInfo: {zh: '模型信息', en: 'Model Info'},
    modelName: {zh: '模型名称', en: 'Model Name'},
    modelFormat: {zh: '模型格式', en: 'Model Format'},
    modelType: {zh: '模型类型', en: 'Model Type'},
    layerCount: {zh: '层数', en: 'Layer Count'},
    backendControl: {zh: '后端控制', en: 'Backend Control'},
    restartBackend: {zh: '重启后端', en: 'Restart Backend'},
    restarting: {zh: '重启中...', en: 'Restarting...'},
    gatewayUrl: {zh: '网关地址', en: 'Gateway URL'},
    agentAddress: {zh: 'Agent 地址', en: 'Agent Address'},
    backendModel: {zh: '后端模型', en: 'Backend Model'},
    containerImage: {zh: '容器镜像', en: 'Container Image'},
    recoveryThreshold: {zh: '恢复阈值', en: 'Recovery Threshold'},
    failuresUnit: {zh: '次失败', en: 'failures'},
    backendError: {zh: '后端错误', en: 'Backend Error'},
    agentEvents: {zh: 'Agent 事件时间线', en: 'Agent Events Timeline'},
    loadingEvents: {zh: '正在加载事件流...', en: 'Loading events...'},
    noEvents: {zh: '暂无事件记录', en: 'No events yet'},
    noDetails: {zh: '无详情', en: 'No details'},
    containerSnapshot: {zh: '容器快照', en: 'Container Snapshot'},
    name: {zh: '名称', en: 'Name'},
    rawInspectData: {zh: '原始 Inspect 数据', en: 'Raw Inspect Data'},
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
