import React, {useEffect, useState} from 'react';
import {AlertCircle, Save} from 'lucide-react';
import {useAppContext, type ModelRouteRow} from '../store';

type DraftRoute = Record<string, ModelRouteRow>;

function buildDraft(routes: ModelRouteRow[]): DraftRoute {
  return Object.fromEntries(routes.map((route) => [route.name, {...route}]));
}

export function ModelRoutesView() {
  const {snapshot, modelRoutes, updateModelRoute, loading} = useAppContext();
  const [drafts, setDrafts] = useState<DraftRoute>({});
  const [savingName, setSavingName] = useState<string | null>(null);

  useEffect(() => {
    setDrafts(buildDraft(modelRoutes));
  }, [modelRoutes]);

  const runtime = snapshot?.runtime.vllm;

  function updateDraft(name: string, patch: Partial<ModelRouteRow>) {
    setDrafts((previous) => ({
      ...previous,
      [name]: {
        ...(previous[name] || modelRoutes.find((item) => item.name === name) || {
          name,
          display_name: name,
          backend_model: name,
          backend_type: 'vllm',
          enabled: true,
        }),
        ...patch,
      },
    }));
  }

  async function handleSave(name: string) {
    const draft = drafts[name];
    if (!draft) {
      return;
    }
    setSavingName(name);
    try {
      const updated = await updateModelRoute(name, {
        display_name: draft.display_name,
        backend_model: draft.backend_model,
        enabled: draft.enabled,
        backend_type: draft.backend_type,
      });
      setDrafts((previous) => ({...previous, [name]: updated}));
    } finally {
      setSavingName(null);
    }
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-5xl">
      <div className="glass-panel p-6 flex flex-col md:flex-row gap-6 md:items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-800 mb-1">Runtime Configuration</h3>
          <p className="text-sm text-slate-500">当前版本默认只支持单个 vLLM 后端实例。</p>
        </div>
        <div className="flex gap-6 relative z-10 flex-wrap">
          <div>
            <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">Backend Type</div>
            <div className="font-mono text-sm font-medium text-slate-800 px-2 py-1 bg-slate-100 rounded border border-slate-200">
              {runtime?.backend_type?.toUpperCase() || 'VLLM'}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">GPU Mem Util</div>
            <div className="font-mono text-sm font-medium text-slate-800 px-2 py-1 bg-slate-100 rounded border border-slate-200">
              {runtime?.gpu_memory_utilization ?? '-'}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">Max Context</div>
            <div className="font-mono text-sm font-medium text-slate-800 px-2 py-1 bg-slate-100 rounded border border-slate-200">
              {runtime?.max_model_len ?? '-'}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">Serve Model</div>
            <div className="font-mono text-sm font-medium text-slate-800 px-2 py-1 bg-slate-100 rounded border border-slate-200">
              {runtime?.model_name || '-'}
            </div>
          </div>
        </div>
      </div>

      <div className="glass-panel overflow-hidden">
        <div className="p-5 border-b border-white/40 bg-white/20">
          <h3 className="font-semibold text-slate-800">Logical Model Routing</h3>
          <p className="text-xs text-slate-500 mt-1">映射前端暴露模型名到当前 vLLM 实际服务模型。</p>
        </div>

        <div className="p-0 overflow-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-500 uppercase bg-slate-50/50">
              <tr>
                <th className="px-5 py-4 font-medium w-1/4">Logical Model Name</th>
                <th className="px-5 py-4 font-medium w-1/4">Display Name</th>
                <th className="px-5 py-4 font-medium w-1/3">Backend Model</th>
                <th className="px-5 py-4 font-medium w-24">Enabled</th>
                <th className="px-5 py-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100/50">
              {modelRoutes.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-12 text-center text-slate-500">
                    {loading.modelRoutes ? '正在加载路由...' : '暂无模型路由'}
                  </td>
                </tr>
              ) : (
                modelRoutes.map((route) => {
                  const draft = drafts[route.name] || route;
                  return (
                    <tr key={route.name} className="hover:bg-white/40 transition-colors">
                      <td className="px-5 py-4">
                        <span className="font-mono text-xs font-semibold text-slate-700 bg-slate-100 px-2 py-1 rounded">
                          {route.name}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <input
                          type="text"
                          value={draft.display_name}
                          onChange={(event) => updateDraft(route.name, {display_name: event.target.value})}
                          className="w-full bg-white/50 border border-slate-200 rounded px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
                        />
                      </td>
                      <td className="px-5 py-4">
                        <input
                          type="text"
                          value={draft.backend_model}
                          onChange={(event) => updateDraft(route.name, {backend_model: event.target.value})}
                          className="w-full bg-white/50 border border-slate-200 rounded px-2 py-1.5 text-sm font-mono text-slate-600 outline-none focus:ring-2 focus:ring-blue-500/30"
                        />
                      </td>
                      <td className="px-5 py-4">
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={draft.enabled}
                            onChange={(event) => updateDraft(route.name, {enabled: event.target.checked})}
                            className="sr-only peer"
                          />
                          <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600" />
                        </label>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <button
                          onClick={() => void handleSave(route.name)}
                          disabled={savingName === route.name}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 text-xs font-medium rounded-md border border-blue-200 transition-colors disabled:opacity-60"
                        >
                          <Save className="w-3.5 h-3.5" />
                          {savingName === route.name ? 'Saving...' : 'Save'}
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="glass-panel p-4 flex items-start gap-3 bg-blue-50/50 border-blue-100">
        <AlertCircle className="w-5 h-5 text-blue-500 shrink-0 mt-0.5" />
        <div>
          <h4 className="text-sm font-semibold text-blue-900">当前约束</h4>
          <p className="text-xs text-blue-700 mt-1">
            这版控制台只维护逻辑模型名与单一 vLLM 后端模型的映射，不做多后端分流。
          </p>
        </div>
      </div>
    </div>
  );
}
