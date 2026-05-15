import React, {useEffect, useMemo, useState} from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {Search} from 'lucide-react';
import {mapRequestStatus} from '../i18n';
import {useAppContext, type RequestLog, type UsageChartGroup} from '../store';

type ChartWindow = '12h' | 'day' | 'month' | 'year';
type GroupBy = 'backend_type' | 'model_name' | 'device_type';

const TOKEN_LINES = [
  {key: 'prompt_tokens', color: '#2563eb'},
  {key: 'completion_tokens', color: '#0f766e'},
  {key: 'cache_tokens', color: '#d97706'},
  {key: 'total_tokens', color: '#111827'},
] as const;

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function inferDeviceLabel(log: RequestLog, t: (key: string) => string) {
  const agent = (log.user_agent || '').toLowerCase();
  if (agent.includes('iphone') || agent.includes('android') || agent.includes('mobile') || agent.includes('ipad')) {
    return t('usage.deviceMobile');
  }
  if (agent.includes('curl') || agent.includes('postman') || agent.includes('python') || agent.includes('wget')) {
    return t('usage.deviceTool');
  }
  if (agent.includes('mozilla') || agent.includes('chrome') || agent.includes('safari') || agent.includes('firefox')) {
    return t('usage.deviceDesktop');
  }
  return t('usage.deviceUnknown');
}

function metricLabel(t: (key: string) => string, metric: string) {
  const mapping: Record<string, string> = {
    prompt_tokens: t('usage.metricPrompt'),
    completion_tokens: t('usage.metricCompletion'),
    cache_tokens: t('usage.metricCache'),
    total_tokens: t('usage.metricTotal'),
  };
  return mapping[metric] || metric;
}

function groupButtonLabel(t: (key: string) => string, groupBy: GroupBy) {
  if (groupBy === 'backend_type') return t('usage.groupByBackend');
  if (groupBy === 'model_name') return t('usage.groupByModel');
  return t('usage.groupByDevice');
}

export function UsageRecordsView() {
  const {
    requestLogs,
    requestLogDetail,
    requestLogsTotal,
    requestLogsLimit,
    requestLogsOffset,
    snapshot,
    usageOverview,
    loading,
    locale,
    t,
    refreshUsageOverview,
    refreshRequestLogs,
    exportRequestLogsCsv,
    fetchRequestLogDetail,
    clearRequestLogDetail,
  } = useAppContext();
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [window, setWindow] = useState<ChartWindow>('12h');
  const [groupBy, setGroupBy] = useState<GroupBy>('backend_type');
  const [activeGroup, setActiveGroup] = useState<string>('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [pageSize, setPageSize] = useState(25);
  const [pageInput, setPageInput] = useState('1');

  useEffect(() => {
    void refreshUsageOverview({
      granularity: window === 'year' ? 'year' : window === 'month' ? 'month' : 'day',
      window,
      groupBy,
    });
  }, [groupBy, window]);

  useEffect(() => {
    setActiveGroup('all');
  }, [groupBy, window]);

  const currentPage = Math.floor(requestLogsOffset / Math.max(requestLogsLimit, 1)) + 1;
  const totalPages = Math.max(1, Math.ceil(requestLogsTotal / Math.max(requestLogsLimit, 1)));

  useEffect(() => {
    setPageInput(String(currentPage));
  }, [currentPage]);

  async function applyLogFilters(nextOffset = 0) {
    await refreshRequestLogs({
      limit: pageSize,
      offset: nextOffset,
      dateFrom: dateFrom || null,
      dateTo: dateTo || null,
      status: filter,
      query,
    });
  }

  useEffect(() => {
    void applyLogFilters(0);
  }, [pageSize]);

  const total = usageOverview?.summary.request_count ?? (requestLogsTotal || requestLogs.length);
  const successRate = usageOverview?.summary.success_rate ?? null;
  const totalTokens = usageOverview?.summary.total_tokens ?? null;
  const cacheReadTokens = usageOverview?.summary.cache_read_tokens ?? null;
  const backendType = snapshot?.backend_type?.toUpperCase() || 'VLLM';
  const chart = usageOverview?.chart;
  const chartGroups = chart?.groups ?? [];
  const selectedGroup = activeGroup === 'all'
    ? null
    : chartGroups.find((group) => group.group === activeGroup) ?? null;
  const chartPoints = selectedGroup?.points ?? chart?.points ?? [];
  const groupTotals = selectedGroup?.totals ?? chart?.totals ?? null;

  const topGroups = useMemo(() => {
    return chartGroups.slice(0, 6);
  }, [chartGroups]);

  const summaryTiles = [
    {
      label: t('usage.metricPrompt'),
      value: groupTotals?.prompt_tokens ?? 0,
      tone: 'text-blue-700 bg-blue-100/80 border-blue-200',
    },
    {
      label: t('usage.metricCompletion'),
      value: groupTotals?.completion_tokens ?? 0,
      tone: 'text-teal-700 bg-teal-100/80 border-teal-200',
    },
    {
      label: t('usage.metricCache'),
      value: groupTotals?.cache_tokens ?? 0,
      tone: 'text-amber-700 bg-amber-100/80 border-amber-200',
    },
    {
      label: t('usage.metricTotal'),
      value: groupTotals?.total_tokens ?? 0,
      tone: 'text-slate-800 bg-slate-200/80 border-slate-300',
    },
  ];

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 h-full flex flex-col">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-4">
        {[
          {label: t('usage.totalRequests'), val: String(total)},
          {
            label: t('usage.successRate'),
            val: successRate === null ? '-' : `${(successRate * 100).toFixed(1)}%`,
            color: 'text-emerald-600',
          },
          {label: t('usage.totalTokens'), val: totalTokens ?? '-'},
          {label: t('usage.backendType'), val: backendType},
        ].map((kpi) => (
          <div key={kpi.label} className="glass-panel p-6 flex flex-col justify-between">
            <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">{kpi.label}</div>
            <div className={`text-4xl font-bold ${kpi.color || 'text-slate-800'}`}>{kpi.val}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.9fr_0.95fr]">
        <div className="glass-panel overflow-hidden">
          <div className="relative border-b border-white/50 bg-[radial-gradient(circle_at_top_left,_rgba(217,119,87,0.14),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(59,130,246,0.14),_transparent_26%),linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.68))] px-6 py-6">
            <div className="flex flex-col gap-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase font-bold text-black/30 tracking-[0.22em] mb-2">{t('usage.trendTitle')}</div>
                  <div className="text-2xl font-semibold text-slate-900">{selectedGroup?.label || t('usage.allGroups')}</div>
                  <div className="mt-1 text-sm text-slate-500">{t('usage.trendSubtitle')}</div>
                </div>
                <div className="flex flex-wrap gap-2 rounded-full border border-white/80 bg-[#f7f2e9] p-1">
                  {([
                    ['12h', t('usage.range12h')],
                    ['day', t('usage.rangeDay')],
                    ['month', t('usage.rangeMonth')],
                    ['year', t('usage.rangeYear')],
                  ] as const).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setWindow(value)}
                      className={`px-3.5 py-2 rounded-full text-sm transition-colors ${
                        window === value ? 'bg-[#1f1d1a] text-[#fffdf7] shadow-[0_10px_18px_rgba(31,29,26,0.18)]' : 'text-[#6a6459] hover:bg-white/80'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {([
                  'backend_type',
                  'model_name',
                  'device_type',
                ] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setGroupBy(value)}
                    className={`rounded-full border px-3.5 py-2 text-sm transition-colors ${
                      groupBy === value
                        ? 'border-[#1f1d1a] bg-[#1f1d1a] text-[#fffdf7]'
                        : 'border-white/80 bg-white/70 text-slate-600 hover:bg-white'
                    }`}
                  >
                    {groupButtonLabel(t, value)}
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {summaryTiles.map((tile) => (
                  <div key={tile.label} className={`rounded-2xl border px-4 py-3 ${tile.tone}`}>
                    <div className="text-[10px] uppercase tracking-[0.18em] opacity-75">{tile.label}</div>
                    <div className="mt-2 text-2xl font-semibold">{tile.value}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="p-6">
            <div className="h-80">
              {chartPoints.length === 0 ? (
                <div className="h-full flex items-center justify-center text-sm text-slate-500">
                  {loading.usageOverview ? t('usage.loadingLogs') : t('usage.noChartData')}
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartPoints} margin={{top: 12, right: 12, left: 4, bottom: 8}}>
                    <CartesianGrid stroke="rgba(148,163,184,0.22)" strokeDasharray="3 3" />
                    <XAxis dataKey="label" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                    <RechartsTooltip
                      formatter={(value: number, name: string) => [value, metricLabel(t, name)]}
                      labelFormatter={(label) => `${label}`}
                      contentStyle={{
                        borderRadius: '18px',
                        border: '1px solid rgba(231,225,214,0.9)',
                        background: 'rgba(255,253,248,0.96)',
                        boxShadow: '0 16px 32px rgba(24,22,17,0.08)',
                      }}
                    />
                    <Legend formatter={(value) => metricLabel(t, String(value))} />
                    {TOKEN_LINES.map((line) => (
                      <Line
                        key={line.key}
                        type="monotone"
                        dataKey={line.key}
                        stroke={line.color}
                        strokeWidth={2.5}
                        dot={false}
                        activeDot={{r: 4}}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>

        <div className="glass-panel p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <div className="text-[10px] uppercase font-bold text-black/30 tracking-[0.22em] mb-2">{t('usage.activeGroup')}</div>
              <div className="text-lg font-semibold text-slate-900">{groupButtonLabel(t, groupBy)}</div>
            </div>
            <div className="rounded-full border border-white/80 bg-[#f7f2e9] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-500">
              Top {topGroups.length || 0}
            </div>
          </div>
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => setActiveGroup('all')}
              className={`w-full text-left rounded-[1.7rem] border p-4 transition-all ${
                activeGroup === 'all'
                  ? 'border-[#1f1d1a] bg-[#1f1d1a] text-[#fffdf7] shadow-[0_18px_28px_rgba(31,29,26,0.18)]'
                  : 'border-white/70 bg-white/70 hover:bg-white'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold">{t('usage.allGroups')}</div>
                <div className={`text-[10px] uppercase tracking-[0.18em] ${activeGroup === 'all' ? 'text-white/55' : 'text-slate-400'}`}>
                  Focus
                </div>
              </div>
              <div className={`mt-3 text-xs ${activeGroup === 'all' ? 'text-white/70' : 'text-slate-500'}`}>
                {t('usage.metricTotal')}: {chart?.totals.total_tokens ?? 0}
              </div>
            </button>

            {topGroups.map((group: UsageChartGroup) => (
              <button
                key={group.group}
                type="button"
                onClick={() => setActiveGroup(group.group)}
                className={`w-full text-left rounded-[1.7rem] border p-4 transition-all ${
                  activeGroup === group.group
                    ? 'border-[#d97757] bg-[linear-gradient(135deg,#d97757,#f1bf42)] text-white shadow-[0_18px_30px_rgba(217,119,87,0.24)]'
                    : 'border-white/70 bg-white/70 hover:bg-white'
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold text-sm">{group.label}</div>
                  <div className={`text-xs ${activeGroup === group.group ? 'text-white/80' : 'text-slate-500'}`}>
                    {group.totals.total_tokens}
                  </div>
                </div>
                <div className={`mt-3 grid grid-cols-2 gap-2 text-xs ${activeGroup === group.group ? 'text-white/80' : 'text-slate-500'}`}>
                  <div>{t('usage.metricPrompt')}: {group.totals.prompt_tokens}</div>
                  <div>{t('usage.metricCompletion')}: {group.totals.completion_tokens}</div>
                  <div>{t('usage.metricCache')}: {group.totals.cache_tokens}</div>
                  <div>{t('usage.metricTotal')}: {group.totals.total_tokens}</div>
                </div>
              </button>
            ))}

            <div className="rounded-[1.7rem] border border-white/70 bg-[#faf8f2]/90 p-4 text-sm text-slate-600">
              <div className="font-semibold text-slate-800 mb-2">
                {selectedGroup?.label || t('usage.allGroups')}
              </div>
              <div className="space-y-1">
                <div>{t('usage.metricPrompt')}: {groupTotals?.prompt_tokens ?? 0}</div>
                <div>{t('usage.metricCompletion')}: {groupTotals?.completion_tokens ?? 0}</div>
                <div>{t('usage.metricCache')}: {groupTotals?.cache_tokens ?? 0}</div>
                <div>{t('usage.metricTotal')}: {groupTotals?.total_tokens ?? 0}</div>
                <div>{t('usage.cacheReadTokens')}: {cacheReadTokens ?? 0}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="glass-panel flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-white/40 flex items-center justify-between gap-4 bg-white/20 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="font-semibold text-slate-800 mr-2">{t('usage.recordsTitle')}</div>
            <div className="text-xs text-slate-500">{t('usage.clickRowHint')}</div>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <span>{t('usage.dateFrom')}</span>
              <input
                aria-label={t('usage.dateFrom')}
                type="datetime-local"
                value={dateFrom}
                onChange={(event) => setDateFrom(event.target.value)}
                className="rounded-lg border border-white/70 bg-white/70 px-3 py-1.5 text-sm outline-none"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <span>{t('usage.dateTo')}</span>
              <input
                aria-label={t('usage.dateTo')}
                type="datetime-local"
                value={dateTo}
                onChange={(event) => setDateTo(event.target.value)}
                className="rounded-lg border border-white/70 bg-white/70 px-3 py-1.5 text-sm outline-none"
              />
            </label>
            <button
              type="button"
              onClick={() => void applyLogFilters(0)}
              className="rounded-full border border-slate-900 bg-slate-900 px-3.5 py-2 text-sm text-white transition-colors hover:bg-slate-800"
            >
              {t('usage.applyTime')}
            </button>
            <button
              type="button"
              onClick={() => {
                setDateFrom('');
                setDateTo('');
                setFilter('all');
                setQuery('');
                void refreshRequestLogs({limit: pageSize, offset: 0});
              }}
              className="rounded-full border border-white/80 bg-white/70 px-3.5 py-2 text-sm text-slate-600 transition-colors hover:bg-white"
            >
              {t('usage.resetTime')}
            </button>
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t('usage.searchPlaceholder')}
                className="pl-9 pr-4 py-1.5 text-sm rounded-lg bg-white/50 border border-white/60 focus:ring-2 focus:ring-blue-500/30 outline-none w-64"
              />
            </div>
            <select
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              className="px-3 py-1.5 text-sm rounded-lg bg-white/50 border border-white/60 outline-none text-slate-700"
            >
              <option value="all">{t('usage.allStatus')}</option>
              <option value="ok">{t('usage.success')}</option>
              <option value="rejected">{t('usage.rejected')}</option>
              <option value="error">{t('usage.error')}</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <span>{t('usage.pageSize')}</span>
              <select
                value={pageSize}
                onChange={(event) => setPageSize(Number(event.target.value))}
                className="px-3 py-1.5 text-sm rounded-lg bg-white/50 border border-white/60 outline-none text-slate-700"
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
            <button
              type="button"
              onClick={() => void exportRequestLogsCsv({
                dateFrom: dateFrom || null,
                dateTo: dateTo || null,
                status: filter,
                query,
              })}
              className="rounded-full border border-white/80 bg-white/70 px-3.5 py-2 text-sm text-slate-600 transition-colors hover:bg-white"
            >
              {t('usage.exportCsv')}
            </button>
          </div>
          <div className="text-xs text-slate-500">
            {t('usage.showing', {shown: requestLogs.length, total: requestLogsTotal || requestLogs.length})}
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          <table className="w-full text-sm text-left whitespace-nowrap">
            <thead className="text-xs text-slate-500 uppercase bg-slate-50/50 sticky top-0 backdrop-blur-md">
              <tr>
                <th className="px-5 py-3 font-medium">{t('usage.timeId')}</th>
                <th className="px-5 py-3 font-medium">{t('usage.protocol')}</th>
                <th className="px-5 py-3 font-medium">{t('usage.model')}</th>
                <th className="px-5 py-3 font-medium">{t('usage.status')}</th>
                <th className="px-5 py-3 font-medium">{t('usage.source')}</th>
                <th className="px-5 py-3 font-medium">{t('usage.clientIp')}</th>
                <th className="px-5 py-3 font-medium">{t('usage.userAgent')}</th>
                <th className="px-5 py-3 font-medium">{t('usage.reason')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100/50">
              {requestLogs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-5 py-12 text-center text-slate-500">
                    {loading.requestLogs ? t('usage.loadingLogs') : t('usage.noResults')}
                  </td>
                </tr>
              ) : (
                requestLogs.map((log) => (
                  <tr
                    key={log.id}
                    className="hover:bg-white/40 transition-colors cursor-pointer"
                    onClick={() => void fetchRequestLogDetail(log.request_id)}
                  >
                    <td className="px-5 py-3">
                      <div className="font-mono text-xs text-slate-600">{log.request_id}</div>
                      <div className="text-[10px] text-slate-400">{formatDate(log.created_at)}</div>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{log.protocol || '-'}</td>
                    <td className="px-5 py-3 text-slate-700">{log.model_name || '-'}</td>
                    <td className="px-5 py-3">
                      <span
                        className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase ${
                          log.status === 'ok'
                            ? 'bg-emerald-100 text-emerald-700'
                            : log.status === 'error'
                              ? 'bg-red-100 text-red-700'
                              : 'bg-orange-100 text-orange-700'
                        }`}
                      >
                        {mapRequestStatus(locale, log.status)}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-600">
                      <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-xs border border-slate-200">
                        {log.auth_source || '-'}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-500 font-mono text-xs">{log.client_ip || '-'}</td>
                    <td className="px-5 py-3 text-slate-500 text-xs max-w-[260px]">
                      <div className="font-medium text-slate-700">{inferDeviceLabel(log, t)}</div>
                      <div className="truncate font-mono">{log.user_agent || '-'}</div>
                    </td>
                    <td className="px-5 py-3 text-slate-500 font-mono text-xs max-w-[220px] truncate">
                      {log.rejection_reason || log.error_message || '-'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="border-t border-white/40 bg-white/20 px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
          <div className="text-xs text-slate-500">
            {t('usage.pageStatus', {page: currentPage, pages: totalPages})}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <span>{t('usage.jumpPage')}</span>
              <input
                type="number"
                min={1}
                max={totalPages}
                value={pageInput}
                onChange={(event) => setPageInput(event.target.value)}
                className="w-20 rounded-lg border border-white/70 bg-white/70 px-3 py-1.5 text-sm outline-none"
              />
            </label>
            <button
              type="button"
              onClick={() => {
                const nextPage = Math.min(totalPages, Math.max(1, Number(pageInput) || 1));
                void applyLogFilters((nextPage - 1) * pageSize);
              }}
              className="rounded-full border border-white/80 bg-white/70 px-3.5 py-2 text-sm text-slate-600 transition-colors hover:bg-white"
            >
              {t('usage.goPage')}
            </button>
            <button
              type="button"
              disabled={requestLogsOffset <= 0}
              onClick={() => void applyLogFilters(Math.max(0, requestLogsOffset - pageSize))}
              className="rounded-full border border-white/80 bg-white/70 px-3.5 py-2 text-sm text-slate-600 transition-colors hover:bg-white disabled:opacity-50"
            >
              {t('usage.prevPage')}
            </button>
            <button
              type="button"
              disabled={currentPage >= totalPages}
              onClick={() => void applyLogFilters(requestLogsOffset + pageSize)}
              className="rounded-full border border-white/80 bg-white/70 px-3.5 py-2 text-sm text-slate-600 transition-colors hover:bg-white disabled:opacity-50"
            >
              {t('usage.nextPage')}
            </button>
          </div>
        </div>
      </div>

      {requestLogDetail && (
        <div
          data-testid="request-detail-drawer"
          aria-label={t('usage.detailTitle')}
          className="fixed inset-y-0 right-0 z-40 w-full max-w-xl bg-white/95 backdrop-blur-xl border-l border-white/70 shadow-2xl"
        >
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">{t('usage.detailTitle')}</div>
              <div className="mt-2 text-xl font-semibold text-slate-900">{requestLogDetail.log.model_name || '-'}</div>
            </div>
            <button
              type="button"
              onClick={clearRequestLogDetail}
              className="rounded-full border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-600 hover:bg-slate-50"
            >
              {t('usage.detailClose')}
            </button>
          </div>

          <div className="h-full overflow-auto px-6 py-5 pb-24">
            <div className="grid grid-cols-2 gap-3">
              {[
                [t('usage.requestId'), requestLogDetail.request_id],
                [t('usage.status'), requestLogDetail.log.status],
                [t('usage.protocol'), requestLogDetail.log.protocol || '-'],
                [t('usage.backendLabel'), requestLogDetail.metrics?.backend_type || '-'],
                [t('usage.source'), requestLogDetail.log.auth_source || '-'],
                [t('usage.clientIp'), requestLogDetail.log.client_ip || '-'],
                [t('usage.totalTokens'), requestLogDetail.metrics?.total_tokens ?? '-'],
                [t('usage.latencyMs'), requestLogDetail.metrics?.latency_ms ?? '-'],
                [t('usage.metricPrompt'), requestLogDetail.metrics?.prompt_tokens ?? '-'],
                [t('usage.metricCompletion'), requestLogDetail.metrics?.completion_tokens ?? '-'],
                [t('usage.metricCache'), (requestLogDetail.metrics?.cache_creation_tokens || 0) + (requestLogDetail.metrics?.cache_read_tokens || 0) + (requestLogDetail.metrics?.cache_miss_tokens || 0)],
                [t('usage.tokensPerSecond'), requestLogDetail.metrics?.tokens_per_second ?? '-'],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">{label}</div>
                  <div className="mt-2 break-all text-sm font-medium text-slate-800">{String(value)}</div>
                </div>
              ))}
            </div>

            <div className="mt-5 space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">{t('usage.userAgent')}</div>
                <div className="mt-2 text-sm text-slate-700 break-all">{requestLogDetail.log.user_agent || '-'}</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">{t('usage.statusDetail')}</div>
                <div className="mt-2 text-sm text-slate-700 break-all">{requestLogDetail.metrics?.status_detail || requestLogDetail.log.rejection_reason || '-'}</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">{t('usage.errorMessage')}</div>
                <div className="mt-2 text-sm text-slate-700 break-all">{requestLogDetail.log.error_message || '-'}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
