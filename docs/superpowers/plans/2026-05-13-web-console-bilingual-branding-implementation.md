# Web Console 全中文与中英切换改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `web-console` 默认切到全中文，提供整站中英切换按钮，并把左上角品牌替换为 logo + `LlmNode`。

**Architecture:** 在现有 `AppProvider` 中增加全局 `locale` 状态和 `t()` 取词能力，文案集中放入 `web-console/src/i18n.ts`。`Layout` 承接品牌区与语言切换入口，各页面只读取词典和状态映射 helper，不直接散落中英文硬编码。仓库规则要求先完成实现，再统一补测试与验证，因此测试脚本与执行集中放在后半段任务。

**Tech Stack:** React 19, TypeScript, Vite, Vitest, Testing Library, Tailwind CSS

---

### Task 1: 搭建词典与全局语言状态

**Files:**
- Create: `web-console/src/i18n.ts`
- Modify: `web-console/src/store.tsx`
- Modify: `web-console/src/App.tsx`

- [ ] **Step 1: 在 `i18n.ts` 中定义语言类型、词典和取词 helper**

Create `web-console/src/i18n.ts` with:

```ts
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
    loading: {zh: '加载中...', en: 'Loading...'},
    refresh: {zh: '刷新', en: 'Refresh'},
    save: {zh: '保存', en: 'Save'},
    enabled: {zh: '启用', en: 'Enabled'},
    disabled: {zh: '禁用', en: 'Disabled'},
    none: {zh: '无', en: 'None'},
    yes: {zh: '是', en: 'Yes'},
    no: {zh: '否', en: 'No'},
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
    subtitle: {zh: '控制台已接入当前 llmnode 控制面。', en: 'Console is connected to the current llmnode control plane.'},
    switchToEnglish: {zh: '切换到 English', en: 'Switch to English'},
    switchToChinese: {zh: '切换到中文', en: 'Switch to Chinese'},
    connection: {zh: '连接配置', en: 'Connection'},
    apiBase: {zh: 'API 地址', en: 'API Base'},
    apiKey: {zh: 'API 密钥', en: 'API Key'},
    snapshotLive: {zh: '实时快照已连接', en: 'Snapshot Live'},
    snapshotReconnecting: {zh: '实时快照重连中', en: 'Snapshot Reconnecting'},
    lastUpdated: {zh: '最近更新', en: 'Last updated'},
    admin: {zh: '管理员', en: 'Admin'},
  },
  overview: {
    status: {zh: '状态', en: 'Status'},
    healthy: {zh: '健康', en: 'Healthy'},
    degraded: {zh: '降级', en: 'Degraded'},
    agentGated: {zh: '依赖 Agent 就绪', en: 'Agent gated'},
    directGateway: {zh: '直接网关模式', en: 'Direct gateway'},
    requests: {zh: '请求数', en: 'Requests'},
    models: {zh: '模型数', en: 'Models'},
    queue: {zh: '队列', en: 'Queue'},
    queueTrend: {zh: '队列与失败趋势', en: 'Queue & Failure Trend'},
    modelDistribution: {zh: '模型分布', en: 'Model Distribution'},
    recentRequests: {zh: '最近请求', en: 'Recent Requests'},
    quickActions: {zh: '快捷操作', en: 'Quick Actions'},
    restartBackend: {zh: '重启后端', en: 'Restart Backend'},
    restarting: {zh: '重启中...', en: 'Restarting...'},
    editSchedule: {zh: '编辑调度', en: 'Edit Schedule'},
    errors: {zh: '错误与异常', en: 'Errors & Exceptions'},
    noTrend: {zh: '暂时还没有趋势数据', en: 'No trend data yet'},
    loadingTrend: {zh: '正在加载趋势数据...', en: 'Loading trend data...'},
    noRequests: {zh: '还没有请求记录', en: 'No requests yet'},
    loadingRequests: {zh: '正在拉取请求记录...', en: 'Loading requests...'},
    noErrors: {zh: '最近样本中没有异常请求。', en: 'No recent errors in sampled requests.'},
    queueLimit: {zh: '队列上限', en: 'Queue limit'},
    recentSamples: {zh: '最近 {count} 个采样点', en: 'Recent {count} samples'},
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
    source: {zh: '来源', en: 'Source'},
    reason: {zh: '原因', en: 'Reason'},
    noResults: {zh: '没有符合筛选条件的记录', en: 'No records match the current filters'},
    loadingLogs: {zh: '正在加载请求日志...', en: 'Loading request logs...'},
    showing: {zh: '显示 {shown} / {total} 条记录', en: 'Showing {shown} / {total} records'},
    timeId: {zh: '时间 / ID', en: 'Time / ID'},
    protocol: {zh: '协议', en: 'Protocol'},
    model: {zh: '模型', en: 'Model'},
    status: {zh: '状态', en: 'Status'},
    clientIp: {zh: '客户端 IP', en: 'Client IP'},
  },
  keys: {
    totalKeys: {zh: '密钥总数', en: 'Total Keys'},
    active: {zh: '启用中', en: 'Active'},
    inferenceScopes: {zh: '推理权限数', en: 'Inference Scopes'},
    adminScopes: {zh: '管理权限数', en: 'Admin Scopes'},
    keyName: {zh: '密钥名称', en: 'Key name'},
    rpmLimit: {zh: 'RPM 限制', en: 'RPM limit'},
    concurrency: {zh: '并发限制', en: 'Concurrency'},
    optionalNote: {zh: '备注（可选）', en: 'Optional note'},
    createKey: {zh: '创建密钥', en: 'Create Key'},
    creating: {zh: '创建中...', en: 'Creating...'},
    generated: {zh: '密钥已生成', en: 'Key Generated Successfully'},
    copy: {zh: '复制到剪贴板', en: 'Copy to clipboard'},
    copied: {zh: '已复制到剪贴板', en: 'Copied to clipboard'},
    keyList: {zh: '数据库中的 API 密钥', en: 'Database API Keys'},
    loadingKeys: {zh: '正在加载...', en: 'Loading...'},
    noKeys: {zh: '还没有 API Key', en: 'No API keys yet'},
    lastUsed: {zh: '最后使用', en: 'Last used'},
    actions: {zh: '操作', en: 'Actions'},
    limits: {zh: '限制 (RPM/并发)', en: 'Limits (RPM/Conc)'},
    createdAt: {zh: '创建时间', en: 'Created At'},
    name: {zh: '名称', en: 'Name'},
    status: {zh: '状态', en: 'Status'},
    scopes: {zh: '权限', en: 'Scopes'},
    disable: {zh: '禁用', en: 'Disable'},
    enable: {zh: '启用', en: 'Enable'},
    saveSecretWarning: {zh: '请立刻保存这个密钥。关闭后将无法再次查看。', en: 'Save this key now. You will not be able to see it again after closing.'},
  },
  models: {
    runtimeConfig: {zh: '运行时配置', en: 'Runtime Configuration'},
    singleBackendNotice: {zh: '当前版本默认只支持单个 vLLM 后端实例。', en: 'This version currently supports a single vLLM backend instance only.'},
    logicalRouting: {zh: '逻辑模型路由', en: 'Logical Model Routing'},
    mappingNotice: {zh: '映射前端暴露模型名到当前实际服务模型。', en: 'Maps exposed logical model names to the currently served backend model.'},
    loadingRoutes: {zh: '正在加载路由...', en: 'Loading routes...'},
    noRoutes: {zh: '暂无模型路由', en: 'No model routes yet'},
    logicalModelName: {zh: '逻辑模型名', en: 'Logical Model Name'},
    displayName: {zh: '显示名称', en: 'Display Name'},
    backendModel: {zh: '后端模型', en: 'Backend Model'},
    enabled: {zh: '启用', en: 'Enabled'},
    actions: {zh: '操作', en: 'Actions'},
    backendType: {zh: '后端类型', en: 'Backend Type'},
    gpuMemUtil: {zh: 'GPU 显存利用率', en: 'GPU Mem Util'},
    maxContext: {zh: '最大上下文', en: 'Max Context'},
    serveModel: {zh: '服务模型', en: 'Serve Model'},
    saving: {zh: '保存中...', en: 'Saving...'},
    currentConstraint: {zh: '当前约束', en: 'Current Constraint'},
    currentConstraintDesc: {zh: '这版控制台只维护逻辑模型名与单一后端模型的映射，不做多后端分流。', en: 'This console only manages mappings from logical model names to a single backend model and does not split traffic across multiple backends.'},
  },
  schedule: {
    schedulingBehavior: {zh: 'V2 调度行为', en: 'V2 Scheduling Behavior'},
    schedulingBehaviorDesc: {zh: '当前调度直接驱动应用内定时逻辑，这里保存的配置就是系统事实来源。', en: 'The scheduler directly drives in-app timing logic, and the configuration saved here is the system source of truth.'},
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
    inferenceParams: {zh: '推理参数', en: 'Inference Params'},
    gpuInfo: {zh: 'GPU 信息', en: 'GPU Info'},
    modelInfo: {zh: '模型信息', en: 'Model Info'},
    backendControl: {zh: '后端控制', en: 'Backend Control'},
    restartBackend: {zh: '重启后端', en: 'Restart Backend'},
    restarting: {zh: '重启中...', en: 'Restarting...'},
    gatewayUrl: {zh: '网关地址', en: 'Gateway URL'},
    agentAddress: {zh: 'Agent 地址', en: 'Agent Address'},
    containerImage: {zh: '容器镜像', en: 'Container Image'},
    recoveryThreshold: {zh: '恢复阈值', en: 'Recovery Threshold'},
    backendError: {zh: '后端错误', en: 'Backend Error'},
    agentEvents: {zh: 'Agent 事件时间线', en: 'Agent Events Timeline'},
    noEvents: {zh: '暂无事件记录', en: 'No events yet'},
    loadingEvents: {zh: '正在加载事件流...', en: 'Loading events...'},
    containerSnapshot: {zh: '容器快照', en: 'Container Snapshot'},
    rawInspectData: {zh: '原始 Inspect 数据', en: 'Raw Inspect Data'},
    name: {zh: '名称', en: 'Name'},
    state: {zh: '状态', en: 'State'},
    uptime: {zh: '运行时长', en: 'Uptime'},
    restartCount: {zh: '重启次数', en: 'Restart Count'},
    modelName: {zh: '模型名称', en: 'Model Name'},
    modelFormat: {zh: '模型格式', en: 'Model Format'},
    modelType: {zh: '模型类型', en: 'Model Type'},
    layerCount: {zh: '层数', en: 'Layer Count'},
    running: {zh: '运行中', en: 'Running'},
    idle: {zh: '空闲', en: 'Idle'},
    inUse: {zh: '使用中', en: 'In Use'},
    none: {zh: '无', en: 'None'},
  },
} as const;

function isLeaf(value: unknown): value is Record<Locale, string> {
  return Boolean(value) && typeof value === 'object' && 'zh' in (value as Record<string, unknown>) && 'en' in (value as Record<string, unknown>);
}

export function translate(locale: Locale, key: string, vars?: Record<string, string | number>): string {
  const parts = key.split('.');
  let cursor: unknown = translations;
  for (const part of parts) {
    cursor = (cursor as Record<string, unknown>)?.[part];
  }
  if (!isLeaf(cursor)) {
    return key;
  }
  const template = cursor[locale] ?? cursor.zh;
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
  return dict[locale][status as 'ok' | 'error' | 'rejected'] ?? status;
}

export function mapAgentStatus(locale: Locale, status: string): string {
  const dict = {
    zh: {ready: '就绪', recovering: '恢复中', failed: '失败', unknown: '未知', running: '运行中', active: '启用中', disabled: '已禁用', manual: '手动'},
    en: {ready: 'Ready', recovering: 'Recovering', failed: 'Failed', unknown: 'Unknown', running: 'Running', active: 'Active', disabled: 'Disabled', manual: 'Manual'},
  } as const;
  return dict[locale][status as keyof typeof dict.en] ?? status;
}
```

- [ ] **Step 2: 在 `store.tsx` 中加入 `locale`、`setLocale` 和 `t()`**

Modify `web-console/src/store.tsx`:

```ts
import {
  DEFAULT_LOCALE,
  getPageLabel,
  readStoredLocale,
  translate,
  type Locale,
  writeStoredLocale,
} from './i18n';

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
  diagnostics: DiagnosticsStatus | null;
  loading: LoadingState;
  refreshAll: () => Promise<void>;
  refreshSnapshot: () => Promise<void>;
  refreshRequestLogs: (limit?: number) => Promise<void>;
  refreshApiKeys: () => Promise<void>;
  refreshModelRoutes: () => Promise<void>;
  refreshSchedule: () => Promise<void>;
  refreshDiagnostics: () => Promise<void>;
  createApiKey: (payload: CreateApiKeyPayload) => Promise<{secret: string; key: ApiKeyRow}>;
  updateApiKey: (id: number, payload: UpdateApiKeyPayload) => Promise<ApiKeyRow>;
  deleteApiKey: (id: number) => Promise<void>;
  updateModelRoute: (name: string, payload: UpdateModelRoutePayload) => Promise<ModelRouteRow>;
  updateSchedule: (payload: Partial<ScheduleConfig>) => Promise<ScheduleConfig>;
  restartBackend: () => Promise<void>;
}

export function AppProvider({children}: {children: ReactNode}) {
  const [currentPage, setCurrentPage] = useState<Page>('overview');
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale());
  const [apiBase, setApiBase] = useState(defaultApiBase);
  const [apiKey, setApiKey] = useState(defaultApiKey);

  useEffect(() => {
    writeStoredLocale(locale);
  }, [locale]);

  function setLocale(next: Locale) {
    setLocaleState(next);
  }

  function toggleLocale() {
    setLocaleState((previous) => (previous === 'zh' ? 'en' : 'zh'));
  }

  function t(key: string, vars?: Record<string, string | number>) {
    return translate(locale, key, vars);
  }

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
        diagnostics,
        loading,
        refreshAll,
        refreshSnapshot,
        refreshRequestLogs,
        refreshApiKeys,
        refreshModelRoutes,
        refreshSchedule,
        refreshDiagnostics,
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
```

- [ ] **Step 3: 保持 `App.tsx` 入口不拆分逻辑，只继续通过 `AppProvider` 包裹**

Modify `web-console/src/App.tsx` only if needed to keep imports clean:

```tsx
export default function App() {
  return (
    <AppProvider>
      <Layout>
        <PageRouter />
      </Layout>
    </AppProvider>
  );
}
```

- [ ] **Step 4: 提交基础词典和语言状态**

```bash
git add web-console/src/i18n.ts web-console/src/store.tsx web-console/src/App.tsx
git commit -m "feat: 增加 web-console 双语状态与词典"
```

### Task 2: 改造布局层品牌区、顶部标题与语言切换入口

**Files:**
- Modify: `web-console/src/components/Layout.tsx`
- Modify: `web-console/src/App.tsx`
- Use existing asset: `web-console/logo.png`

- [ ] **Step 1: 在 `Layout.tsx` 中接入 logo 和 `LlmNode` 品牌**

Modify `web-console/src/components/Layout.tsx` imports and brand block:

```tsx
import logoImage from '../../logo.png';
import {useAppContext} from '../store';

const {
  currentPage,
  setCurrentPage,
  locale,
  toggleLocale,
  t,
  pageTitle,
  sseConnected,
  globalError,
  lastUpdated,
  apiBase,
  setApiBase,
  apiKey,
  setApiKey,
} = useAppContext();

const navItems = [
  {id: 'overview', icon: LayoutDashboard, label: t('layout.nav.overview')},
  {id: 'usage', icon: Activity, label: t('layout.nav.usage')},
  {id: 'keys', icon: Key, label: t('layout.nav.keys')},
  {id: 'models', icon: Network, label: t('layout.nav.models')},
  {id: 'schedule', icon: CalendarClock, label: t('layout.nav.schedule')},
  {id: 'status', icon: Server, label: t('layout.nav.status')},
] as const;

<div className="flex items-center gap-3 px-2">
  <img src={logoImage} alt="LlmNode logo" className="h-11 w-11 rounded-xl object-contain bg-white/60 p-1 shadow-sm" />
  <div>
    <h1 className="text-xl font-bold tracking-tight text-[#1a1a1a]">{t('layout.brand')}</h1>
  </div>
</div>
```

- [ ] **Step 2: 顶部标题、副标题和连接区域改成可切换文案**

Update the top bar in `Layout.tsx`:

```tsx
<header className="mb-8 flex items-center justify-between z-10">
  <div>
    <h1 className="text-3xl font-light text-[#1a1a1a]">
      <span className="font-bold">LlmNode</span> {pageTitle}
    </h1>
    <div className="text-sm text-[#1a1a1a]/60 mt-1">
      {t('layout.subtitle')}
      {lastUpdated && (
        <span className="ml-2">
          {t('layout.lastUpdated')}: {lastUpdated.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US')}
        </span>
      )}
    </div>
  </div>

  <div className="flex items-center gap-4">
    <button
      onClick={toggleLocale}
      className="px-4 py-2 rounded-full border border-white/60 bg-white/40 backdrop-blur-md text-sm font-medium hover:bg-white/60 transition-colors"
    >
      {locale === 'zh' ? t('layout.switchToEnglish') : t('layout.switchToChinese')}
    </button>
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border backdrop-blur-md transition-colors",
        sseConnected
          ? "bg-emerald-100/50 border-emerald-200/50 text-emerald-700"
          : "bg-red-100/50 border-red-200/50 text-red-700",
      )}
    >
      {sseConnected ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
      {sseConnected ? t('layout.snapshotLive') : t('layout.snapshotReconnecting')}
    </div>
    <div className="px-4 py-2 rounded-full border border-white/60 bg-white/40 backdrop-blur-md flex items-center gap-3">
      <div className="w-6 h-6 rounded-full bg-slate-400"></div>
      <span className="text-sm font-medium">{t('layout.admin')}</span>
    </div>
  </div>
</header>
```

- [ ] **Step 3: 连接配置面板改成双语标签**

Update the bottom panel labels in `Layout.tsx`:

```tsx
<div className="text-[10px] font-bold text-white/60 mb-2 uppercase tracking-widest">{t('layout.connection')}</div>
<label className="text-[10px] uppercase font-bold text-white/50">{t('layout.apiBase')}</label>
<label className="text-[10px] uppercase font-bold text-white/50">{t('layout.apiKey')}</label>
```

- [ ] **Step 4: 提交布局层品牌和切换入口**

```bash
git add web-console/src/components/Layout.tsx web-console/src/App.tsx web-console/logo.png
git commit -m "feat: 更新 web-console 品牌区与语言切换入口"
```

### Task 3: 把各页面可见 UI 文案统一接到词典

**Files:**
- Modify: `web-console/src/pages/OverviewView.tsx`
- Modify: `web-console/src/pages/UsageRecordsView.tsx`
- Modify: `web-console/src/pages/ApiKeysView.tsx`
- Modify: `web-console/src/pages/ModelRoutesView.tsx`
- Modify: `web-console/src/pages/ScheduleView.tsx`
- Modify: `web-console/src/pages/SystemStatusView.tsx`
- Modify: `web-console/src/i18n.ts`

- [ ] **Step 1: 先改 `OverviewView.tsx`，把卡片、图表、表格和快捷操作文案接到 `t()`**

Modify `web-console/src/pages/OverviewView.tsx`:

```tsx
import {useAppContext} from '../store';

export function OverviewView() {
  const {snapshot, snapshotHistory, refreshSnapshot, loading, setCurrentPage, restartBackend, t, locale} = useAppContext();
  <span className="text-[10px] uppercase tracking-widest font-bold text-white/30">{t('overview.status')}</span>
  <h3 className="text-4xl font-bold text-white relative z-10">
    {snapshot?.backend_ready ? t('overview.healthy') : t('overview.degraded')}
  </h3>
  <p className="text-sm text-white/50 mt-1 relative z-10">
    {backendLabel} · {snapshot?.require_agent_ready ? t('overview.agentGated') : t('overview.directGateway')}
  </p>
  <span>{t('overview.queueTrend')}</span>
  <span className="text-blue-600 text-sm font-normal">{t('overview.recentSamples', {count: snapshotHistory.length || 0})}</span>
  <h4 className="font-bold mb-6 text-slate-800">{t('overview.modelDistribution')}</h4>
  <h4 className="font-bold text-slate-800">{t('overview.recentRequests')}</h4>
  <span className="text-sm font-medium text-slate-800">{restarting ? t('overview.restarting') : t('overview.restartBackend')}</span>
  <span className="text-sm font-medium text-slate-800">{t('overview.editSchedule')}</span>
  <button
    onClick={() => void refreshSnapshot()}
    className="px-4 py-2 text-sm font-medium border border-slate-300 rounded-lg bg-white/50 hover:bg-white/70 transition-colors text-slate-700"
  >
    {t('common.refresh')}
  </button>
```

- [ ] **Step 2: 再改 `UsageRecordsView.tsx` 与 `ApiKeysView.tsx`**

Update `web-console/src/pages/UsageRecordsView.tsx`:

```tsx
const {requestLogs, snapshot, loading, t, locale} = useAppContext();
{[
  {label: t('usage.totalRequests'), val: String(total)},
  {label: t('usage.exceptions'), val: String(exceptions), color: 'text-red-600'},
  {label: t('usage.rejected'), val: String(rejected), color: 'text-orange-600'},
  {label: t('usage.backendType'), val: backendType},
].map((kpi) => (
  <div key={kpi.label} className="glass-panel p-6 flex flex-col justify-between">
    <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">{kpi.label}</div>
    <div className={`text-4xl font-bold ${kpi.color || 'text-slate-800'}`}>{kpi.val}</div>
  </div>
))}
placeholder={t('usage.searchPlaceholder')}
<option value="all">{t('usage.allStatus')}</option>
<option value="ok">{t('usage.success')}</option>
<option value="rejected">{t('usage.rejected')}</option>
<option value="error">{t('usage.error')}</option>
<div className="text-xs text-slate-500">{t('usage.showing', {shown: filteredLogs.length, total: requestLogs.length})}</div>
```

Update `web-console/src/pages/ApiKeysView.tsx`:

```tsx
const {apiKeys, createApiKey, updateApiKey, deleteApiKey, loading, t} = useAppContext();
const [name, setName] = useState('Web Console');
<div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">{t('keys.totalKeys')}</div>
placeholder={t('keys.keyName')}
placeholder={t('keys.rpmLimit')}
placeholder={t('keys.concurrency')}
placeholder={t('keys.optionalNote')}
{creating ? t('keys.creating') : t('keys.createKey')}
<h3 className="font-semibold text-lg">{t('keys.generated')}</h3>
title={t('keys.copy')}
{copyDone && <div className="text-xs text-emerald-300 mt-3">{t('keys.copied')}</div>}
<div className="font-semibold text-slate-800">{t('keys.keyList')}</div>
```

- [ ] **Step 3: 再改 `ModelRoutesView.tsx`、`ScheduleView.tsx` 和 `SystemStatusView.tsx`**

Update `web-console/src/pages/ModelRoutesView.tsx`:

```tsx
const {snapshot, modelRoutes, updateModelRoute, loading, t} = useAppContext();
<h3 className="text-lg font-semibold text-slate-800 mb-1">{t('models.runtimeConfig')}</h3>
<p className="text-sm text-slate-500">{t('models.singleBackendNotice')}</p>
<h3 className="font-semibold text-slate-800">{t('models.logicalRouting')}</h3>
<p className="text-xs text-slate-500 mt-1">{t('models.mappingNotice')}</p>
{savingName === route.name ? t('models.saving') : t('common.save')}
```

Update `web-console/src/pages/ScheduleView.tsx`:

```tsx
const {schedule, updateSchedule, loading, t} = useAppContext();
const DAYS = [
  {id: 'mon', key: 'schedule.days.mon'},
  {id: 'tue', key: 'schedule.days.tue'},
  {id: 'wed', key: 'schedule.days.wed'},
  {id: 'thu', key: 'schedule.days.thu'},
  {id: 'fri', key: 'schedule.days.fri'},
  {id: 'sat', key: 'schedule.days.sat'},
  {id: 'sun', key: 'schedule.days.sun'},
] as const;
<h4 className="text-sm font-semibold text-orange-900">{t('schedule.schedulingBehavior')}</h4>
<p className="text-xs text-orange-800 mt-1">{t('schedule.schedulingBehaviorDesc')}</p>
<label className="block text-xs font-bold text-slate-500 uppercase mb-2">{t('schedule.timezone')}</label>
<span className="text-xs font-medium text-blue-900">{t(day.key)}</span>
{saving ? t('schedule.saving') : t('schedule.applySchedule')}
```

Update `web-console/src/pages/SystemStatusView.tsx`:

```tsx
const {snapshot, diagnostics, loading, refreshSnapshot, refreshDiagnostics, restartBackend, t, locale} = useAppContext();
{[
  {label: t('status.nodeAgent'), val: mapAgentStatus(locale, agentStatus), color: agentStatus === 'ready' ? 'text-emerald-600' : 'text-orange-600'},
  {label: t('status.backendReady'), val: snapshot?.backend_ready ? t('common.yes') : t('common.no'), color: snapshot?.backend_ready ? 'text-emerald-600' : 'text-red-600'},
  {label: t('status.backendType'), val: getBackendTypeBadge(), color: 'text-blue-600'},
  {label: t('status.autoSchedule'), val: schedule?.auto_start_enabled || schedule?.auto_stop_enabled ? t('status.active') : t('status.manual'), color: schedule?.auto_start_enabled || schedule?.auto_stop_enabled ? 'text-purple-600' : 'text-slate-600'},
  {label: t('status.queueDepth'), val: String(snapshot?.queue_length ?? 0), color: 'text-orange-600'},
].map((kpi) => (
  <div key={kpi.label} className="glass-panel p-6 flex flex-col justify-between">
    <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">{kpi.label}</div>
    <div className={`text-2xl font-bold ${kpi.color}`}>{typeof kpi.val === 'string' ? kpi.val : kpi.val}</div>
  </div>
))}
<h3 className="text-lg font-semibold text-slate-800">{t('status.containerInfo')}</h3>
<h3 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
  <Terminal className="w-5 h-5 text-blue-500" />
  {t('status.backendControl')}
</h3>
{isRestarting ? t('status.restarting') : t('status.restartBackend')}
```

- [ ] **Step 4: 用关键字回归搜索检查英文硬编码和旧品牌是否还残留**

Run:

```bash
rg -n "Nexus|Dashboard|Usage|Create Key|Restart Backend|Apply Schedule|Queue & Failure Trend|Model Distribution|Container Snapshot" web-console/src -S
```

Expected:

```text
No matches found
```

- [ ] **Step 5: 提交页面双语化改造**

```bash
git add web-console/src/pages/OverviewView.tsx \
  web-console/src/pages/UsageRecordsView.tsx \
  web-console/src/pages/ApiKeysView.tsx \
  web-console/src/pages/ModelRoutesView.tsx \
  web-console/src/pages/ScheduleView.tsx \
  web-console/src/pages/SystemStatusView.tsx \
  web-console/src/i18n.ts
git commit -m "feat: 完成 web-console 页面双语化"
```

### Task 4: 补前端测试脚手架并为语言切换增加最小回归

**Files:**
- Modify: `web-console/package.json`
- Modify: `web-console/vite.config.ts`
- Create: `web-console/src/test/setup.ts`
- Create: `web-console/src/i18n.test.ts`
- Create: `web-console/src/components/Layout.test.tsx`

- [ ] **Step 1: 在 `package.json` 中加入 Vitest 和 Testing Library**

Modify `web-console/package.json`:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "clean": "rm -rf dist",
    "lint": "tsc --noEmit",
    "test": "vitest run"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/express": "^4.17.21",
    "@types/node": "^22.14.0",
    "autoprefixer": "^10.4.21",
    "jsdom": "^25.0.1",
    "tailwindcss": "^4.1.14",
    "tsx": "^4.21.0",
    "typescript": "~5.8.2",
    "vite": "^6.2.3",
    "vitest": "^2.1.8",
    "keep all existing dependency versions unchanged for entries not shown here"
  }
}
```

- [ ] **Step 2: 在 `vite.config.ts` 中加入测试环境配置**

Modify `web-console/vite.config.ts`:

```ts
export default defineConfig(({mode}) => {
  return {
    plugins: [react(), tailwindcss()],
    define: {
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/test/setup.ts',
      css: true,
    },
    server: {
      hmr: process.env.DISABLE_HMR !== 'true',
      proxy: {
        '/admin': {
          target: proxyTarget,
          changeOrigin: true,
        },
        '/health': {
          target: proxyTarget,
          changeOrigin: true,
        },
        '/v1': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
```

- [ ] **Step 3: 加测试 setup 与最小回归用例**

Create `web-console/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

Create `web-console/src/i18n.test.ts`:

```ts
import {describe, expect, it} from 'vitest';
import {mapAgentStatus, mapRequestStatus, translate} from './i18n';

describe('i18n helpers', () => {
  it('returns Chinese by default and interpolates variables', () => {
    expect(translate('zh', 'overview.recentSamples', {count: 3})).toBe('最近 3 个采样点');
  });

  it('maps request and agent status for English', () => {
    expect(mapRequestStatus('en', 'ok')).toBe('Success');
    expect(mapAgentStatus('en', 'recovering')).toBe('Recovering');
  });
});
```

Create `web-console/src/components/Layout.test.tsx`:

```tsx
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {describe, expect, it, vi} from 'vitest';
import App from '../App';

const emptySnapshot = {
  backend_type: 'vllm',
  backend_ready: true,
  backend_error: null,
  backend_container: null,
  agent_state: {status: 'ready'},
  require_agent_ready: true,
  queue_length: 0,
  models: [],
  logs: [],
  events: [],
  runtime: {
    gateway: {
      host: '127.0.0.1',
      port: 4000,
      backend_url: 'http://127.0.0.1:8000',
      backend_model: 'Qwen',
      agent_base_url: 'http://127.0.0.1:4010',
      agent_status_url: 'http://127.0.0.1:4010/admin/status',
      require_agent_ready: true,
      queue_limit: 8,
      execution_limit: 1,
      api_key_configured: true,
    },
    agent: {
      host: '127.0.0.1',
      port: 4010,
      state: 'ready',
      poll_interval: 3,
      auto_recover: true,
      recovery_threshold: 3,
    },
    schedule: {
      timezone: 'Asia/Shanghai',
      work_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
      start_time: '09:00',
      end_time: '18:00',
      auto_stop_enabled: true,
      auto_start_enabled: true,
      cooldown_minutes: 10,
    },
    vllm: {
      backend_type: 'vllm',
      container_name: 'llmnode-vllm',
      image_name: 'vllm/vllm-openai:latest',
      model_dir: 'models/Qwen',
      model_name: 'Qwen',
      host_port: 8000,
      gpu_memory_utilization: 0.75,
      tensor_parallel_size: 1,
      max_model_len: 32768,
      max_num_seqs: 8,
      shm_size: '8g',
      enable_auto_tool_choice: false,
      reasoning_parser: null,
      tool_call_parser: null,
    },
    model_routes: [],
  },
};

vi.stubGlobal(
  'fetch',
  vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/admin/status')) {
      return Promise.resolve(new Response(JSON.stringify(emptySnapshot), {status: 200, headers: {'Content-Type': 'application/json'}}));
    }
    if (url.includes('/admin/request-logs')) {
      return Promise.resolve(new Response(JSON.stringify({logs: []}), {status: 200, headers: {'Content-Type': 'application/json'}}));
    }
    if (url.includes('/admin/keys')) {
      return Promise.resolve(new Response(JSON.stringify({keys: []}), {status: 200, headers: {'Content-Type': 'application/json'}}));
    }
    if (url.includes('/admin/models')) {
      return Promise.resolve(new Response(JSON.stringify({models: []}), {status: 200, headers: {'Content-Type': 'application/json'}}));
    }
    if (url.includes('/admin/schedule')) {
      return Promise.resolve(new Response(JSON.stringify({schedule: emptySnapshot.runtime.schedule}), {status: 200, headers: {'Content-Type': 'application/json'}}));
    }
    if (url.includes('/admin/stream')) {
      return Promise.resolve(new Response('', {status: 200}));
    }
    return Promise.resolve(new Response('{}', {status: 200, headers: {'Content-Type': 'application/json'}}));
  }),
);

describe('Layout locale switch', () => {
  it('renders Chinese by default and switches to English', async () => {
    render(<App />);

    expect(screen.getByText('LlmNode')).toBeInTheDocument();
    expect(screen.getByText('总览')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', {name: '切换到 English'}));

    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Switch to 中文'})).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: 提交测试脚手架和最小回归**

```bash
git add web-console/package.json web-console/vite.config.ts \
  web-console/src/test/setup.ts web-console/src/i18n.test.ts \
  web-console/src/components/Layout.test.tsx
git commit -m "test: 增加 web-console 双语切换回归"
```

### Task 5: 统一执行验证并收尾

**Files:**
- Verify only: `web-console/src/**`
- Verify only: `docs/superpowers/specs/2026-05-13-web-console-bilingual-branding-design.md`

- [ ] **Step 1: 运行类型检查**

Run:

```bash
cd web-console && npm run lint
```

Expected:

```text
exit code 0
```

- [ ] **Step 2: 运行前端测试**

Run:

```bash
cd web-console && npm test
```

Expected:

```text
all tests passed
```

- [ ] **Step 3: 运行生产构建**

Run:

```bash
cd web-console && npm run build
```

Expected:

```text
vite build completed successfully
```

- [ ] **Step 4: 最终回归搜索整站是否仍残留旧品牌或明显英文硬编码**

Run:

```bash
rg -n "Nexus Console|Nexus |Dashboard|Queue & Failure Trend|Restart Backend|Create Key|Apply Schedule" web-console/src web-console/index.html -S
```

Expected:

```text
No matches found
```

- [ ] **Step 5: 汇总改动并提交**

```bash
git add web-console/src web-console/package.json web-console/vite.config.ts
git commit -m "feat: 完成 web-console 全中文与中英切换改造"
```
