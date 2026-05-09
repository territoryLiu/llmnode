import React, {useState} from 'react';
import {Activity, Box, RefreshCw, Terminal} from 'lucide-react';
import {useAppContext} from '../store';

function formatClock(value: string | null | undefined) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function stringifyJson(value: unknown) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return '{}';
  }
}

export function SystemStatusView() {
  const {snapshot, loading, refreshSnapshot, restartBackend} = useAppContext();
  const [isRestarting, setIsRestarting] = useState(false);

  const agentStatus = String(snapshot?.agent_state?.status || 'unknown');
  const backendContainer = snapshot?.backend_container;
  const runtime = snapshot?.runtime;
  const events = snapshot?.events ?? [];
  const schedule = runtime?.schedule;

  async function handleRestart() {
    setIsRestarting(true);
    try {
      await restartBackend();
      await refreshSnapshot();
    } finally {
      setTimeout(() => setIsRestarting(false), 1200);
    }
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-5xl h-full flex flex-col">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
        {[
          {label: 'Node Agent', val: agentStatus, color: agentStatus === 'ready' ? 'text-emerald-600' : 'text-orange-600'},
          {
            label: 'Backend Ready',
            val: snapshot?.backend_ready ? 'True' : 'False',
            color: snapshot?.backend_ready ? 'text-emerald-600' : 'text-red-600',
          },
          {
            label: 'Container',
            val: backendContainer ? 'Exists' : 'N/A',
            color: backendContainer ? 'text-blue-600' : 'text-slate-500',
          },
          {
            label: 'Auto Schedule',
            val: schedule?.auto_start_enabled || schedule?.auto_stop_enabled ? 'Active' : 'Manual',
            color: schedule?.auto_start_enabled || schedule?.auto_stop_enabled ? 'text-purple-600' : 'text-slate-600',
          },
          {label: 'Queue Depth', val: String(snapshot?.queue_length ?? 0), color: 'text-orange-600'},
        ].map((kpi) => (
          <div key={kpi.label} className="glass-panel p-6 flex flex-col justify-between">
            <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">{kpi.label}</div>
            <div className={`text-2xl font-bold ${kpi.color}`}>{kpi.val}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 flex-1">
        <div className="md:col-span-2 flex flex-col gap-6">
          <div className="glass-panel p-6 relative overflow-hidden">
            <div className="absolute top-[-30%] right-[-10%] w-48 h-48 bg-blue-500/20 rounded-full blur-3xl pointer-events-none" />

            <div className="flex items-center justify-between mb-6 relative z-10">
              <h3 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
                <Terminal className="w-5 h-5 text-blue-500" />
                Backend Control
              </h3>

              <button
                onClick={handleRestart}
                disabled={isRestarting}
                className="flex items-center gap-2 px-4 py-2 bg-red-50 hover:bg-red-100 text-red-600 text-sm font-medium rounded-lg border border-red-200 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isRestarting ? 'animate-spin' : ''}`} />
                {isRestarting ? 'Restarting...' : 'Restart Backend'}
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 relative z-10">
              <div className="space-y-4">
                <div>
                  <div className="text-xs font-bold text-slate-500 uppercase mb-1">Gateway URL</div>
                  <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                    {runtime ? `http://${runtime.gateway.host}:${runtime.gateway.port}` : '-'}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-500 uppercase mb-1">Agent Address</div>
                  <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                    {runtime ? `${runtime.agent.host}:${runtime.agent.port}` : '-'}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-500 uppercase mb-1">Backend Model</div>
                  <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                    {runtime?.gateway.backend_model || '-'}
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <div className="text-xs font-bold text-slate-500 uppercase mb-1">Container Image</div>
                  <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60 truncate">
                    {runtime?.vllm.image_name || '-'}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-500 uppercase mb-1">Recovery Threshold</div>
                  <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                    {runtime?.agent.recovery_threshold ?? '-'} failures
                  </div>
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-500 uppercase mb-1">Backend Error</div>
                  <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60 break-all">
                    {snapshot?.backend_error || 'None'}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="glass-panel flex-1 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-white/40 flex items-center justify-between gap-2 bg-white/20">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-purple-500" />
                <h3 className="font-semibold text-slate-800">Agent Events Timeline</h3>
              </div>
              <button
                onClick={() => void refreshSnapshot()}
                className="px-3 py-1.5 text-xs rounded-md border border-slate-300 bg-white/50 hover:bg-white/70 transition-colors"
              >
                刷新
              </button>
            </div>
            <div className="flex-1 p-6 overflow-auto">
              <div className="space-y-6">
                {events.length === 0 ? (
                  <div className="text-sm text-slate-500">{loading.snapshot ? '正在加载事件流...' : '暂无事件记录'}</div>
                ) : (
                  events.map((evt) => (
                    <div
                      key={evt.id}
                      className="relative pl-6 before:content-[''] before:absolute before:left-2 before:top-2 before:bottom-[-24px] before:w-px before:bg-slate-200 last:before:hidden"
                    >
                      <div
                        className={`absolute left-[5px] top-1.5 w-2 h-2 rounded-full border-2 border-white ${
                          evt.status === 'ready'
                            ? 'bg-emerald-500'
                            : evt.status === 'recovering'
                              ? 'bg-orange-500'
                              : 'bg-red-500'
                        }`}
                      />
                      <div className="text-xs font-bold text-slate-400 mb-0.5">{formatClock(evt.created_at)}</div>
                      <div className="text-sm font-semibold capitalize text-slate-800">{evt.status}</div>
                      <div className="text-sm text-slate-600 mt-0.5">{evt.reason || 'no details'}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="glass-panel-dark p-6 flex flex-col h-full relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
          <h3 className="text-lg font-semibold text-slate-200 mb-6 flex items-center gap-2 relative z-10">
            <Box className="w-5 h-5 text-emerald-400" />
            Container Snapshot
          </h3>

          <div className="space-y-4 relative z-10 flex-1">
            <div className="bg-slate-800/50 p-4 rounded-xl border border-slate-700/50">
              <div className="text-xs font-bold text-slate-500 uppercase mb-1">Name</div>
              <div className="font-mono text-sm text-slate-300">
                {runtime?.vllm.container_name || String(backendContainer?.['name'] || 'unknown')}
              </div>
            </div>
            <div className="bg-slate-800/50 p-4 rounded-xl border border-slate-700/50">
              <div className="text-xs font-bold text-slate-500 uppercase mb-1">State</div>
              <div className="flex items-center gap-2">
                <div
                  className={`w-2 h-2 rounded-full ${
                    snapshot?.backend_ready ? 'bg-emerald-500' : 'bg-orange-400'
                  }`}
                />
                <div className="font-mono text-sm text-slate-200">
                  {snapshot?.backend_ready ? 'running' : String(snapshot?.agent_state?.status || 'unknown')}
                </div>
              </div>
            </div>
            <div className="bg-slate-800/50 p-4 rounded-xl border border-slate-700/50 flex-1">
              <div className="text-xs font-bold text-slate-500 uppercase mb-2">Raw Inspect Data</div>
              <pre className="text-[10px] text-slate-400 font-mono overflow-auto opacity-70 whitespace-pre-wrap break-all">
                {stringifyJson(backendContainer || snapshot?.agent_state || {})}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
