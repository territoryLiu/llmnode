import React, {useState, useEffect} from 'react';
import {Activity, Box, RefreshCw, Terminal, Cpu, HardDrive} from 'lucide-react';
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
  const {snapshot, diagnostics, loading, refreshSnapshot, refreshDiagnostics, restartBackend} = useAppContext();
  const [isRestarting, setIsRestarting] = useState(false);

  useEffect(() => {
    void refreshDiagnostics();
    const interval = setInterval(() => {
      void refreshDiagnostics();
    }, 10000);
    return () => clearInterval(interval);
  }, [refreshDiagnostics]);

  const agentStatus = String(snapshot?.agent_state?.status || 'unknown');
  const backendContainer = snapshot?.backend_container;
  const backendType = snapshot?.backend_type || diagnostics?.backend_type || 'vllm';
  const runtime = snapshot?.runtime;
  const events = snapshot?.events ?? [];
  const schedule = runtime?.schedule;

  const getBackendTypeBadge = () => {
    const badges: Record<string, {label: string; color: string}> = {
      vllm: {label: 'vLLM', color: 'bg-blue-500/20 text-blue-600 border-blue-300'},
      'llama.cpp': {label: 'llama.cpp', color: 'bg-green-500/20 text-green-600 border-green-300'},
      sglang: {label: 'SGLang', color: 'bg-purple-500/20 text-purple-600 border-purple-300'},
    };
    const badge = badges[backendType] || {label: backendType, color: 'bg-gray-500/20 text-gray-600 border-gray-300'};
    return (
      <span className={`px-2 py-1 rounded text-xs font-medium border ${badge.color}`}>
        {badge.label}
      </span>
    );
  };

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
            label: 'Backend Type',
            val: getBackendTypeBadge(),
            color: 'text-blue-600',
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
            <div className={`text-2xl font-bold ${kpi.color}`}>{typeof kpi.val === 'string' ? kpi.val : kpi.val}</div>
          </div>
        ))}
      </div>

      {/* 容器详细信息 */}
      {diagnostics?.container && (
        <div className="glass-panel p-6">
          <div className="flex items-center gap-2 mb-4">
            <Box className="w-5 h-5 text-blue-500" />
            <h3 className="text-lg font-semibold text-slate-800">容器信息</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs font-bold text-slate-500 uppercase mb-1">容器名称</div>
              <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60 truncate">
                {diagnostics.container.snapshot.name || 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-xs font-bold text-slate-500 uppercase mb-1">状态</div>
              <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                {diagnostics.container.info.running ? (
                  <span className="text-green-600">运行中</span>
                ) : (
                  <span className="text-gray-600">{diagnostics.container.info.status}</span>
                )}
              </div>
            </div>
            <div>
              <div className="text-xs font-bold text-slate-500 uppercase mb-1">运行时长</div>
              <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                {diagnostics.container.info.uptime || 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-xs font-bold text-slate-500 uppercase mb-1">重启次数</div>
              <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                {diagnostics.container.info.restart_count > 0 ? (
                  <span className="text-orange-600">{diagnostics.container.info.restart_count}</span>
                ) : (
                  <span className="text-green-600">0</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 推理参数 */}
      {diagnostics?.inference_params && Object.keys(diagnostics.inference_params).length > 0 && (
        <div className="glass-panel p-6">
          <div className="flex items-center gap-2 mb-4">
            <Terminal className="w-5 h-5 text-purple-500" />
            <h3 className="text-lg font-semibold text-slate-800">推理参数</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(diagnostics.inference_params).map(([key, value]) => (
              <div key={key}>
                <div className="text-xs font-bold text-slate-500 uppercase mb-1">{key}</div>
                <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                  {typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* GPU 信息 */}
      {diagnostics?.gpu && diagnostics.gpu.gpus.length > 0 && (
        <div className="glass-panel p-6">
          <div className="flex items-center gap-2 mb-4">
            <Cpu className="w-5 h-5 text-green-500" />
            <h3 className="text-lg font-semibold text-slate-800">GPU 信息</h3>
            <span className="text-xs text-slate-500 ml-auto">CUDA {diagnostics.gpu.cuda_version}</span>
          </div>
          <div className="space-y-3">
            {diagnostics.gpu.gpus.map((gpu) => {
              const memUsedGB = (gpu.memory_used_mb / 1024).toFixed(1);
              const memTotalGB = (gpu.memory_total_mb / 1024).toFixed(0);
              const memPercent = ((gpu.memory_used_mb / gpu.memory_total_mb) * 100).toFixed(0);
              return (
                <div key={gpu.index} className="bg-white/50 border border-white/60 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="font-semibold text-slate-800">GPU {gpu.index}</div>
                    <div className="text-sm text-slate-600">{gpu.name}</div>
                  </div>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <div className="text-xs text-slate-500">显存</div>
                      <div className="font-mono text-slate-700">
                        {memUsedGB} / {memTotalGB} GB
                      </div>
                      <div className="text-xs text-slate-500">({memPercent}%)</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">利用率</div>
                      <div className="font-mono text-slate-700">{gpu.utilization_percent}%</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">状态</div>
                      <div className="font-mono text-slate-700">
                        {gpu.utilization_percent > 0 ? (
                          <span className="text-green-600">使用中</span>
                        ) : (
                          <span className="text-slate-500">空闲</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 模型信息 */}
      {diagnostics?.model && (
        <div className="glass-panel p-6">
          <div className="flex items-center gap-2 mb-4">
            <HardDrive className="w-5 h-5 text-orange-500" />
            <h3 className="text-lg font-semibold text-slate-800">模型信息</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div>
              <div className="text-xs font-bold text-slate-500 uppercase mb-1">模型名称</div>
              <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60 truncate">
                {diagnostics.model.model_name}
              </div>
            </div>
            <div>
              <div className="text-xs font-bold text-slate-500 uppercase mb-1">模型格式</div>
              <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                {diagnostics.model.model_format}
              </div>
            </div>
            {diagnostics.model.model_config.model_type && (
              <div>
                <div className="text-xs font-bold text-slate-500 uppercase mb-1">模型类型</div>
                <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                  {diagnostics.model.model_config.model_type}
                </div>
              </div>
            )}
            {diagnostics.model.model_config.num_hidden_layers && (
              <div>
                <div className="text-xs font-bold text-slate-500 uppercase mb-1">层数</div>
                <div className="font-mono text-sm text-slate-700 bg-white/50 px-3 py-2 rounded border border-white/60">
                  {diagnostics.model.model_config.num_hidden_layers}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

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
