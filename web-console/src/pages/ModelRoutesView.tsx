import React, {useEffect, useState} from 'react';
import {AlertCircle, Save} from 'lucide-react';
import {useAppContext, type ModelRouteRow} from '../store';

type DraftRoute = Record<string, ModelRouteRow>;

const capabilityFields: Array<{
  key: keyof ModelRouteRow['capabilities_json'];
  labelKey: string;
  ariaLabel: string;
}> = [
  {key: 'supports_responses', labelKey: 'models.capabilityResponses', ariaLabel: 'Responses'},
  {key: 'supports_chat', labelKey: 'models.capabilityChat', ariaLabel: 'Chat'},
  {key: 'supports_messages', labelKey: 'models.capabilityMessages', ariaLabel: 'Messages'},
  {key: 'supports_stream', labelKey: 'models.capabilityStream', ariaLabel: 'Stream'},
  {key: 'supports_function_tools', labelKey: 'models.capabilityFunctionTools', ariaLabel: 'Function Tools'},
  {key: 'supports_builtin_tools', labelKey: 'models.capabilityBuiltinTools', ariaLabel: 'Builtin Tools'},
  {key: 'supports_previous_response_id_native', labelKey: 'models.capabilityPreviousResponse', ariaLabel: 'Previous Response'},
  {key: 'supports_json_schema', labelKey: 'models.capabilityJsonSchema', ariaLabel: 'JSON Schema'},
];

function normalizeRoute(route: ModelRouteRow): ModelRouteRow {
  return {
    ...route,
    backend_model: route.backend_model ?? '',
    backend_type: route.backend_type ?? 'vllm',
    lifecycle_mode: route.lifecycle_mode ?? 'managed_local',
    upstream_protocol: route.upstream_protocol ?? 'chat',
    upstream_base_url: route.upstream_base_url ?? '',
    upstream_model: route.upstream_model ?? route.backend_model ?? '',
    upstream_auth_kind: route.upstream_auth_kind ?? 'none',
    upstream_auth_ref: route.upstream_auth_ref ?? '',
    capabilities_json: {
      supports_responses: route.capabilities_json?.supports_responses ?? false,
      supports_chat: route.capabilities_json?.supports_chat ?? true,
      supports_messages: route.capabilities_json?.supports_messages ?? false,
      supports_stream: route.capabilities_json?.supports_stream ?? true,
      supports_function_tools: route.capabilities_json?.supports_function_tools ?? true,
      supports_builtin_tools: route.capabilities_json?.supports_builtin_tools ?? false,
      supports_previous_response_id_native: route.capabilities_json?.supports_previous_response_id_native ?? false,
      supports_json_schema: route.capabilities_json?.supports_json_schema ?? false,
    },
  };
}

function buildDraft(routes: ModelRouteRow[]): DraftRoute {
  return Object.fromEntries(routes.map((route) => [route.name, normalizeRoute(route)]));
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
    setDrafts((previous) => {
      const base =
        previous[name] ||
        normalizeRoute(
          modelRoutes.find((item) => item.name === name) || {
            name,
            display_name: name,
            backend_model: name,
            backend_type: 'vllm',
            enabled: true,
            lifecycle_mode: 'managed_local',
            upstream_protocol: 'chat',
            upstream_base_url: '',
            upstream_model: name,
            upstream_auth_kind: 'none',
            upstream_auth_ref: '',
            capabilities_json: {
              supports_responses: false,
              supports_chat: true,
              supports_messages: false,
              supports_stream: true,
              supports_function_tools: true,
              supports_builtin_tools: false,
              supports_previous_response_id_native: false,
              supports_json_schema: false,
            },
          },
        );
      return {
        ...previous,
        [name]: {
          ...base,
          ...patch,
          capabilities_json: {
            ...base.capabilities_json,
            ...(patch.capabilities_json || {}),
          },
        },
      };
    });
  }

  function updateCapability(
    name: string,
    key: keyof ModelRouteRow['capabilities_json'],
    value: boolean,
  ) {
    const draft = drafts[name];
    if (!draft) {
      return;
    }
    updateDraft(name, {
      capabilities_json: {
        ...draft.capabilities_json,
        [key]: value,
      },
    });
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
        backend_model: draft.lifecycle_mode === 'managed_local' ? draft.backend_model || null : null,
        enabled: draft.enabled,
        backend_type: draft.lifecycle_mode === 'managed_local' ? draft.backend_type || null : null,
        lifecycle_mode: draft.lifecycle_mode,
        upstream_protocol: draft.upstream_protocol,
        upstream_base_url: draft.upstream_base_url || null,
        upstream_model: draft.upstream_model || null,
        upstream_auth_kind: draft.upstream_auth_kind,
        upstream_auth_ref: draft.upstream_auth_kind === 'none' ? null : draft.upstream_auth_ref || null,
        capabilities_json: draft.capabilities_json,
      });
      setDrafts((previous) => ({...previous, [name]: normalizeRoute(updated)}));
    } finally {
      setSavingName(null);
    }
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-6xl">
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

        <div className="p-5 space-y-5">
          {modelRoutes.length === 0 ? (
            <div className="px-5 py-12 text-center text-slate-500">
              {loading.modelRoutes ? t('models.loadingRoutes') : t('models.noRoutes')}
            </div>
          ) : (
            modelRoutes.map((route) => {
              const draft = drafts[route.name] || normalizeRoute(route);
              return (
                <section key={route.name} className="rounded-2xl border border-slate-200/70 bg-white/60 p-5 space-y-5">
                  <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                    <div className="space-y-2">
                      <div className="font-mono text-xs font-semibold text-slate-700 bg-slate-100 px-2 py-1 rounded inline-flex">
                        {route.name}
                      </div>
                      <div className="flex items-center gap-3">
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            aria-label={`${route.name}-enabled`}
                            type="checkbox"
                            checked={draft.enabled}
                            onChange={(event) => updateDraft(route.name, {enabled: event.target.checked})}
                            className="sr-only peer"
                          />
                          <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600" />
                        </label>
                        <span className="text-xs text-slate-500">{t('models.enabled')}</span>
                      </div>
                    </div>

                    <button
                      onClick={() => void handleSave(route.name)}
                      disabled={savingName === route.name}
                      className="inline-flex items-center justify-center gap-1.5 px-3 py-2 bg-blue-50 hover:bg-blue-100 text-blue-600 text-xs font-medium rounded-md border border-blue-200 transition-colors disabled:opacity-60"
                    >
                      <Save className="w-3.5 h-3.5" />
                      {savingName === route.name ? t('models.saving') : t('common.save')}
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                    <label className="space-y-1.5">
                      <span className="text-xs font-medium text-slate-500">{t('models.displayName')}</span>
                      <input
                        type="text"
                        value={draft.display_name}
                        onChange={(event) => updateDraft(route.name, {display_name: event.target.value})}
                        className="w-full bg-white/70 border border-slate-200 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-medium text-slate-500">{t('models.lifecycleMode')}</span>
                      <select
                        value={draft.lifecycle_mode}
                        onChange={(event) =>
                          updateDraft(route.name, {
                            lifecycle_mode: event.target.value as ModelRouteRow['lifecycle_mode'],
                          })
                        }
                        className="w-full bg-white/70 border border-slate-200 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
                      >
                        <option value="managed_local">{t('models.managedLocal')}</option>
                        <option value="external">{t('models.external')}</option>
                      </select>
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-medium text-slate-500">{t('models.upstreamProtocol')}</span>
                      <select
                        value={draft.upstream_protocol}
                        onChange={(event) =>
                          updateDraft(route.name, {
                            upstream_protocol: event.target.value as ModelRouteRow['upstream_protocol'],
                          })
                        }
                        className="w-full bg-white/70 border border-slate-200 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
                      >
                        <option value="chat">chat</option>
                        <option value="messages">messages</option>
                        <option value="responses">responses</option>
                      </select>
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-medium text-slate-500">{t('models.backendType')}</span>
                      <select
                        value={draft.backend_type || ''}
                        disabled={draft.lifecycle_mode !== 'managed_local'}
                        onChange={(event) => updateDraft(route.name, {backend_type: event.target.value})}
                        className="w-full bg-white/70 border border-slate-200 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30 disabled:bg-slate-100 disabled:text-slate-400"
                      >
                        <option value="vllm">vllm</option>
                        <option value="llama.cpp">llama.cpp</option>
                        <option value="sglang">sglang</option>
                      </select>
                    </label>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                    <label className="space-y-1.5">
                      <span className="text-xs font-medium text-slate-500">{t('models.backendModel')}</span>
                      <input
                        type="text"
                        value={draft.backend_model || ''}
                        disabled={draft.lifecycle_mode !== 'managed_local'}
                        onChange={(event) => updateDraft(route.name, {backend_model: event.target.value})}
                        className="w-full bg-white/70 border border-slate-200 rounded px-3 py-2 text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500/30 disabled:bg-slate-100 disabled:text-slate-400"
                      />
                    </label>
                    <label className="space-y-1.5 md:col-span-2">
                      <span className="text-xs font-medium text-slate-500">{t('models.upstreamBaseUrl')}</span>
                      <input
                        type="text"
                        value={draft.upstream_base_url || ''}
                        onChange={(event) => updateDraft(route.name, {upstream_base_url: event.target.value})}
                        className="w-full bg-white/70 border border-slate-200 rounded px-3 py-2 text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500/30"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-medium text-slate-500">{t('models.upstreamModel')}</span>
                      <input
                        type="text"
                        value={draft.upstream_model || ''}
                        onChange={(event) => updateDraft(route.name, {upstream_model: event.target.value})}
                        className="w-full bg-white/70 border border-slate-200 rounded px-3 py-2 text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500/30"
                      />
                    </label>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                    <label className="space-y-1.5">
                      <span className="text-xs font-medium text-slate-500">{t('models.upstreamAuthKind')}</span>
                      <select
                        value={draft.upstream_auth_kind}
                        onChange={(event) =>
                          updateDraft(route.name, {
                            upstream_auth_kind: event.target.value as ModelRouteRow['upstream_auth_kind'],
                          })
                        }
                        className="w-full bg-white/70 border border-slate-200 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
                      >
                        <option value="none">{t('models.authNone')}</option>
                        <option value="bearer">{t('models.authBearer')}</option>
                        <option value="x_api_key">{t('models.authXApiKey')}</option>
                      </select>
                    </label>
                    <label className="space-y-1.5 md:col-span-2">
                      <span className="text-xs font-medium text-slate-500">{t('models.upstreamAuthRef')}</span>
                      <input
                        type="text"
                        value={draft.upstream_auth_ref || ''}
                        disabled={draft.upstream_auth_kind === 'none'}
                        onChange={(event) => updateDraft(route.name, {upstream_auth_ref: event.target.value})}
                        className="w-full bg-white/70 border border-slate-200 rounded px-3 py-2 text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500/30 disabled:bg-slate-100 disabled:text-slate-400"
                      />
                    </label>
                  </div>

                  <div className="space-y-3">
                    <div className="text-xs font-medium text-slate-500">{t('models.capabilities')}</div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {capabilityFields.map((item) => (
                        <label
                          key={item.key}
                          className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white/70 px-3 py-2 text-sm text-slate-700"
                        >
                          <input
                            aria-label={item.ariaLabel}
                            type="checkbox"
                            checked={draft.capabilities_json[item.key]}
                            onChange={(event) => updateCapability(route.name, item.key, event.target.checked)}
                            className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                          />
                          <span>{t(item.labelKey)}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </section>
              );
            })
          )}
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
