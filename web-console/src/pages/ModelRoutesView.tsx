import React, {useEffect, useState} from 'react';
import {AlertCircle, Save} from 'lucide-react';
import {useAppContext, type ModelRouteRow} from '../store';

type DraftRoute = Record<string, ModelRouteRow>;

function buildDraft(routes: ModelRouteRow[]): DraftRoute {
  return Object.fromEntries(routes.map((route) => [route.name, {...route}]));
}

export function ModelRoutesView() {
  const {snapshot, modelRoutes, updateModelRoute, loading, t} = useAppContext();
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
          <h3 className="text-lg font-semibold text-slate-800 mb-1">{t('models.runtimeConfig')}</h3>
          <p className="text-sm text-slate-500">{t('models.singleBackendNotice')}</p>
        </div>
        <div className="flex gap-6 relative z-10 flex-wrap">
          <div>
            <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">{t('models.backendType')}</div>
            <div className="font-mono text-sm font-medium text-slate-800 px-2 py-1 bg-slate-100 rounded border border-slate-200">
              {runtime?.backend_type?.toUpperCase() || 'VLLM'}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">{t('models.gpuMemUtil')}</div>
            <div className="font-mono text-sm font-medium text-slate-800 px-2 py-1 bg-slate-100 rounded border border-slate-200">
              {runtime?.gpu_memory_utilization ?? '-'}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">{t('models.maxContext')}</div>
            <div className="font-mono text-sm font-medium text-slate-800 px-2 py-1 bg-slate-100 rounded border border-slate-200">
              {runtime?.max_model_len ?? '-'}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">{t('models.serveModel')}</div>
            <div className="font-mono text-sm font-medium text-slate-800 px-2 py-1 bg-slate-100 rounded border border-slate-200">
              {runtime?.model_name || '-'}
            </div>
          </div>
        </div>
      </div>

      <div className="glass-panel overflow-hidden">
        <div className="p-5 border-b border-white/40 bg-white/20">
          <h3 className="font-semibold text-slate-800">{t('models.logicalRouting')}</h3>
          <p className="text-xs text-slate-500 mt-1">{t('models.mappingNotice')}</p>
        </div>

        <div className="p-0 overflow-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-500 uppercase bg-slate-50/50">
              <tr>
                <th className="px-5 py-4 font-medium w-1/4">{t('models.logicalModelName')}</th>
                <th className="px-5 py-4 font-medium w-1/4">{t('models.displayName')}</th>
                <th className="px-5 py-4 font-medium w-1/3">{t('models.backendModel')}</th>
                <th className="px-5 py-4 font-medium w-24">{t('models.enabled')}</th>
                <th className="px-5 py-4 font-medium text-right">{t('models.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100/50">
              {modelRoutes.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-12 text-center text-slate-500">
                    {loading.modelRoutes ? t('models.loadingRoutes') : t('models.noRoutes')}
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
                          {savingName === route.name ? t('models.saving') : t('common.save')}
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
          <h4 className="text-sm font-semibold text-blue-900">{t('models.currentConstraint')}</h4>
          <p className="text-xs text-blue-700 mt-1">{t('models.currentConstraintDesc')}</p>
        </div>
      </div>
    </div>
  );
}
