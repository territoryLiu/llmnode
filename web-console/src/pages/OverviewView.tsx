import React, {useMemo, useState} from 'react';
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {AlertTriangle, Copy, Layers, RefreshCcw, ServerCog, Settings, Zap} from 'lucide-react';
import {useAppContext} from '../store';
import {mapRequestStatus} from '../i18n';

function formatClock(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
}

export function OverviewView() {
  const {snapshot, snapshotHistory, refreshSnapshot, loading, setCurrentPage, restartBackend, locale, t} =
    useAppContext();
  const [restarting, setRestarting] = useState(false);

  const recentLogs = snapshot?.logs ?? [];
  const backendLabel = snapshot?.backend_type?.toUpperCase() ?? 'VLLM';
  const modelRoutes = snapshot?.runtime.model_routes ?? [];
  const queueLimit = snapshot?.runtime.gateway.queue_limit ?? 0;
  const errorLogs = recentLogs.filter((log) => log.status !== 'ok');
  const enabledModelRoutes = useMemo(
    () => modelRoutes.filter((route) => route.enabled),
    [modelRoutes],
  );

  async function copyText(value: string) {
    if (!value) {
      return;
    }
    await navigator.clipboard.writeText(value);
  }

  async function handleRestart() {
    setRestarting(true);
    try {
      await restartBackend();
    } finally {
      setTimeout(() => setRestarting(false), 1200);
    }
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-4">
        <div className="glass-panel-dark p-6 flex flex-col justify-between overflow-hidden">
          <div className="absolute top-[-20%] right-[-10%] w-24 h-24 bg-blue-500/40 rounded-full blur-2xl" />
          <div className="flex justify-between items-start mb-4 relative z-10">
            <span className="p-2 bg-slate-800 rounded-lg flex items-center justify-center">
              <ServerCog className="w-5 h-5 text-emerald-400" />
            </span>
            <span className="text-[10px] uppercase tracking-widest font-bold text-white/30">{t('overview.status')}</span>
          </div>
          <h3 className="text-4xl font-bold text-white relative z-10">
            {snapshot?.backend_ready ? t('overview.healthy') : t('overview.degraded')}
          </h3>
          <p className="text-sm text-white/50 mt-1 relative z-10">
            {backendLabel} · {snapshot?.require_agent_ready ? t('overview.agentGated') : t('overview.directGateway')}
          </p>
        </div>

        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="flex justify-between items-start mb-4">
            <span className="p-2 bg-blue-100 rounded-lg flex items-center justify-center">
              <Zap className="w-5 h-5 text-blue-600" />
            </span>
            <span className="text-[10px] uppercase tracking-widest font-bold text-black/30">{t('overview.requests')}</span>
          </div>
          <h3 className="text-4xl font-bold text-slate-800">{recentLogs.length}</h3>
          <p className="text-sm text-black/50 mt-1">{t('overview.requestSummary')}</p>
        </div>

        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="flex justify-between items-start mb-4">
            <span className="p-2 bg-purple-100 rounded-lg flex items-center justify-center">
              <Layers className="w-5 h-5 text-purple-600" />
            </span>
            <span className="text-[10px] uppercase tracking-widest font-bold text-black/30">{t('overview.models')}</span>
          </div>
          <h3 className="text-4xl font-bold text-slate-800">{modelRoutes.length}</h3>
          <p className="text-sm text-black/50 mt-1">{t('overview.modelSummary')}</p>
        </div>

        <div className="glass-panel p-6 flex flex-col justify-between relative overflow-hidden">
          <div className="absolute top-[-20%] right-[-10%] w-24 h-24 bg-orange-500/20 rounded-full blur-2xl" />
          <div className="flex justify-between items-start mb-4 relative z-10">
            <span className="p-2 bg-orange-100 rounded-lg flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-orange-600" />
            </span>
            <span className="text-[10px] uppercase tracking-widest font-bold text-black/30">{t('overview.queueNow')}</span>
          </div>
          <h3 className="text-4xl font-bold text-slate-800 relative z-10">{snapshot?.queue_length ?? 0}</h3>
          <p className="text-sm text-black/50 mt-1 relative z-10">{t('overview.queueLimit', {count: queueLimit})}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="glass-panel lg:col-span-2 overflow-hidden p-6">
          <h4 className="font-bold mb-6 flex flex-wrap justify-between items-center gap-3 text-slate-800">
            <span className="min-w-0">{t('overview.queueTrend')}</span>
            <span className="text-blue-600 text-sm font-normal shrink-0 text-right">
              {t('overview.recentSamples', {count: snapshotHistory.length || 0})}
            </span>
          </h4>
          <div className="h-64 w-full">
            {snapshotHistory.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-500">
                {loading.snapshot ? t('overview.loadingTrend') : t('overview.noTrend')}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={snapshotHistory}>
                  <defs>
                    <linearGradient id="colorQueue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="label" hide />
                  <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                  <RechartsTooltip
                    contentStyle={{
                      borderRadius: '12px',
                      border: 'none',
                      background: 'rgba(255,255,255,0.8)',
                      backdropFilter: 'blur(8px)',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="queueLength"
                    stroke="#3b82f6"
                    strokeWidth={3}
                    fillOpacity={1}
                    fill="url(#colorQueue)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="glass-panel flex flex-col overflow-hidden p-6">
          <h4 className="font-bold mb-2 text-slate-800">{t('overview.availableModels')}</h4>
          <p className="mb-6 text-sm text-slate-500">{t('overview.availableModelsHint')}</p>
          <div className="flex-1 space-y-3">
            {enabledModelRoutes.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white/40 px-4 py-6 text-sm text-slate-500">
                {t('overview.noAvailableModels')}
              </div>
            ) : (
              enabledModelRoutes.map((route) => (
                <div
                  key={route.name}
                  className="rounded-2xl border border-white/60 bg-white/40 px-4 py-3 shadow-sm"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                        {t('overview.routeModelName')}
                      </div>
                      <div className="mt-1 break-all font-mono text-sm text-slate-800">{route.name}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void copyText(route.name)}
                      className="shrink-0 rounded-full border border-slate-200 bg-white/70 p-2 text-slate-500 transition-colors hover:text-blue-600"
                      title={t('overview.copyModel')}
                    >
                      <Copy className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="mt-3">
                    <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                      {t('overview.routeBackendModel')}
                    </div>
                    <div className="mt-1 break-all font-mono text-xs text-slate-600">{route.backend_model}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel overflow-hidden flex flex-col !p-0">
          <div className="p-6 border-b border-black/5 bg-white/30 backdrop-blur-md">
            <h4 className="font-bold text-slate-800">{t('overview.recentRequests')}</h4>
          </div>
          <div className="p-0 flex-1 overflow-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-500 uppercase bg-slate-50/50">
                <tr>
                  <th className="px-6 py-4 font-medium">{t('overview.reqId')}</th>
                  <th className="px-6 py-4 font-medium">{t('overview.model')}</th>
                  <th className="px-6 py-4 font-medium">{t('overview.statusColumn')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {recentLogs.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-6 py-10 text-center text-slate-500">
                      {loading.snapshot ? t('overview.loadingRequests') : t('overview.noRequests')}
                    </td>
                  </tr>
                ) : (
                  recentLogs.slice(0, 8).map((log) => (
                    <tr key={log.id} className="hover:bg-white/40 transition-colors">
                      <td className="px-6 py-3 font-mono text-xs text-slate-600">
                        {log.request_id}
                        <br />
                        <span className="text-[10px] text-slate-400">{formatClock(log.created_at)}</span>
                      </td>
                      <td className="px-6 py-3 text-slate-700">{log.model_name || '-'}</td>
                      <td className="px-6 py-3">
                        <span
                          className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase ${
                            log.status === 'ok' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                          }`}
                        >
                          {mapRequestStatus(locale, log.status)}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="glass-panel overflow-hidden p-6">
          <h4 className="font-bold mb-6 text-slate-800">{t('overview.quickActions')}</h4>
          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={handleRestart}
              disabled={restarting}
              className="flex flex-col items-center justify-center p-6 bg-white/40 border border-white/60 rounded-2xl hover:bg-white/60 hover:shadow-md transition-all cursor-pointer disabled:opacity-60"
            >
              <RefreshCcw className={`w-6 h-6 text-blue-600 mb-2 ${restarting ? 'animate-spin' : ''}`} />
              <span className="text-sm font-medium text-slate-800">
                {restarting ? t('overview.restarting') : t('overview.restartBackend')}
              </span>
            </button>
            <button
              onClick={() => setCurrentPage('schedule')}
              className="flex flex-col items-center justify-center p-6 bg-white/40 border border-white/60 rounded-2xl hover:bg-white/60 hover:shadow-md transition-all cursor-pointer"
            >
              <Settings className="w-6 h-6 text-purple-600 mb-2" />
              <span className="text-sm font-medium text-slate-800">{t('overview.editSchedule')}</span>
            </button>
          </div>

          <div className="mt-8">
            <h4 className="font-bold mb-4 flex items-center gap-2 text-slate-800">
              <AlertTriangle className="w-4 h-4 text-orange-500" />
              {t('overview.errors')}
            </h4>
            <div className="space-y-3">
              {errorLogs.length === 0 ? (
                <div className="p-4 bg-emerald-50/60 border border-emerald-100 rounded-2xl text-sm text-emerald-700">
                  {t('overview.noErrors')}
                </div>
              ) : (
                errorLogs.slice(0, 4).map((err) => (
                  <div key={err.id} className="p-4 bg-red-50/50 border border-red-100 rounded-2xl">
                    <div className="font-mono text-xs text-red-800 font-semibold mb-1">
                      {err.rejection_reason || err.error_message || 'request_failed'}
                    </div>
                    <div className="text-[11px] text-slate-500 flex justify-between gap-4">
                      <span>{err.request_id}</span>
                      <span>{formatClock(err.created_at)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="mt-6 flex justify-end">
            <button
              onClick={() => void refreshSnapshot()}
              className="px-4 py-2 text-sm font-medium border border-slate-300 rounded-lg bg-white/50 hover:bg-white/70 transition-colors text-slate-700"
            >
              {t('overview.refreshSnapshot')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
