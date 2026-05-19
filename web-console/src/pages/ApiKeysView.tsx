import React, {useMemo, useState} from 'react';
import {Copy, Globe, Key, Plus, Trash2} from 'lucide-react';
import {useAppContext, type ApiKeyRow} from '../store';

function formatDate(value: string | null) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function ToggleButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="px-3 py-1 text-xs font-medium border border-slate-300 rounded-md hover:bg-slate-50 transition-colors text-slate-700 bg-white/50 disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function ApiKeysView() {
  const {apiKeys, createApiKey, updateApiKey, deleteApiKey, loading, t, readinessOverview, copyToClipboard} = useAppContext();
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [visibleSecrets, setVisibleSecrets] = useState<Record<number, boolean>>({});

  const [name, setName] = useState('Web Console');
  const [scopeAdmin, setScopeAdmin] = useState(true);
  const [scopeInference, setScopeInference] = useState(true);
  const [rpmLimit, setRpmLimit] = useState('');
  const [concurrencyLimit, setConcurrencyLimit] = useState('');
  const [note, setNote] = useState('');

  const stats = useMemo(() => {
    const total = apiKeys.length;
    const active = apiKeys.filter((item) => item.status === 'active').length;
    const inference = apiKeys.filter((item) => item.scopes.includes('inference')).length;
    const admin = apiKeys.filter((item) => item.scopes.includes('admin')).length;
    return {total, active, inference, admin};
  }, [apiKeys]);

  async function handleCreate() {
    const scopes = [scopeAdmin ? 'admin' : null, scopeInference ? 'inference' : null].filter(Boolean) as string[];
    if (!name.trim() || scopes.length === 0) {
      return;
    }
    setCreating(true);
    try {
      await createApiKey({
        name: name.trim(),
        scopes,
        rpm_limit: rpmLimit.trim() ? Number(rpmLimit) : null,
        concurrency_limit: concurrencyLimit.trim() ? Number(concurrencyLimit) : null,
        note: note.trim() || null,
      });
      setName('Web Console');
      setScopeAdmin(true);
      setScopeInference(true);
      setRpmLimit('');
      setConcurrencyLimit('');
      setNote('');
    } finally {
      setCreating(false);
    }
  }

  async function handleToggle(key: ApiKeyRow) {
    setBusyId(key.id);
    try {
      await updateApiKey(key.id, {status: key.status === 'active' ? 'disabled' : 'active'});
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(key: ApiKeyRow) {
    setBusyId(key.id);
    try {
      await deleteApiKey(key.id);
    } finally {
      setBusyId(null);
    }
  }

  function toggleSecretVisibility(keyId: number) {
    setVisibleSecrets((previous) => ({...previous, [keyId]: !previous[keyId]}));
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 h-full flex flex-col">
      {readinessOverview?.base_urls && (
        <div className="glass-panel p-5">
          <div className="flex items-center gap-2 mb-3">
            <Globe className="w-4 h-4 text-blue-600" />
            <div className="font-semibold text-slate-800">{t('keys.baseUrls')}</div>
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex items-center gap-2 flex-1">
              <span className="text-xs text-slate-500 w-16 shrink-0">{t('keys.local')}</span>
              <code className="flex-1 bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm font-mono text-blue-700">
                {readinessOverview.base_urls.local}
              </code>
              <button onClick={() => void copyToClipboard(readinessOverview.base_urls.local)} className="p-2 text-slate-400 hover:text-blue-600 transition-colors" title={t('keys.copyBase')}>
                <Copy className="w-4 h-4" />
              </button>
            </div>
            <div className="flex items-center gap-2 flex-1">
              <span className="text-xs text-slate-500 w-16 shrink-0">{t('keys.lan')}</span>
              <code className="flex-1 bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm font-mono text-blue-700">
                {readinessOverview.base_urls.lan}
              </code>
              <button onClick={() => void copyToClipboard(readinessOverview.base_urls.lan)} className="p-2 text-slate-400 hover:text-blue-600 transition-colors" title={t('keys.copyBase')}>
                <Copy className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-4">
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">{t('keys.totalKeys')}</div>
          <div className="text-4xl font-bold text-slate-800">{stats.total}</div>
        </div>
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">{t('keys.active')}</div>
          <div className="text-4xl font-bold text-emerald-600">{stats.active}</div>
        </div>
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">{t('keys.inferenceScopes')}</div>
          <div className="text-4xl font-bold text-blue-600">{stats.inference}</div>
        </div>
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">{t('keys.adminScopes')}</div>
          <div className="text-4xl font-bold text-purple-600">{stats.admin}</div>
        </div>
      </div>

      <div className="glass-panel p-5">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_0.9fr_0.9fr_1fr_auto]">
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t('keys.keyName')}
            className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          <input
            type="number"
            value={rpmLimit}
            onChange={(event) => setRpmLimit(event.target.value)}
            placeholder={t('keys.rpmLimit')}
            className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          <input
            type="number"
            value={concurrencyLimit}
            onChange={(event) => setConcurrencyLimit(event.target.value)}
            placeholder={t('keys.concurrency')}
            className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          <input
            type="text"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder={t('keys.optionalNote')}
            className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !name.trim() || (!scopeAdmin && !scopeInference)}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-800 transition-colors shadow-md shadow-slate-900/20 disabled:opacity-60"
          >
            <Plus className="w-4 h-4" />
            {creating ? t('keys.creating') : t('keys.createKey')}
          </button>
        </div>

        <div className="flex flex-wrap gap-3 mt-4">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={scopeAdmin} onChange={() => setScopeAdmin((value) => !value)} />
            {t('keys.scopeAdmin')}
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={scopeInference} onChange={() => setScopeInference((value) => !value)} />
            {t('keys.scopeInference')}
          </label>
        </div>
      </div>

      <div className="glass-panel flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-white/40 flex items-center justify-between gap-4 bg-white/20">
          <div className="font-semibold text-slate-800">{t('keys.keyList')}</div>
          <div className="text-xs text-slate-500">
            {loading.apiKeys ? t('keys.loadingKeys') : t('keys.keysCount', {count: apiKeys.length})}
          </div>
        </div>

        <div className="flex-1 overflow-auto p-0">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-500 uppercase bg-slate-50/50">
              <tr>
                <th className="px-5 py-3 font-medium">{t('keys.name')}</th>
                <th className="px-5 py-3 font-medium">{t('keys.maskedKey')}</th>
                <th className="px-5 py-3 font-medium">{t('keys.status')}</th>
                <th className="px-5 py-3 font-medium">{t('keys.scopes')}</th>
                <th className="px-5 py-3 font-medium">{t('keys.limits')}</th>
                <th className="px-5 py-3 font-medium">{t('keys.usageSummary')}</th>
                <th className="px-5 py-3 font-medium">{t('keys.createdAt')}</th>
                <th className="px-5 py-3 font-medium text-right">{t('keys.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100/50">
              {apiKeys.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-5 py-12 text-center text-slate-500">
                    {loading.apiKeys ? t('keys.loadingKeys') : t('keys.noKeys')}
                  </td>
                </tr>
              ) : (
                apiKeys.map((key) => (
                  <tr key={key.id} className="hover:bg-white/40 transition-colors">
                    <td className="px-5 py-4">
                      <div className="font-medium text-slate-800">{key.name}</div>
                      {key.note && <div className="text-xs text-slate-500 mt-1">{key.note}</div>}
                    </td>
                    <td className="px-5 py-4">
                      <div className="space-y-2">
                        <div className="grid grid-cols-[minmax(0,36ch)_auto_auto] items-center gap-1 max-w-[28rem]">
                          <div
                            data-testid={`api-key-secret-${key.id}`}
                            className="w-[36ch] max-w-full overflow-hidden text-ellipsis whitespace-nowrap font-mono text-xs text-slate-600"
                          >
                            {key.plain_secret && visibleSecrets[key.id] ? key.plain_secret : key.masked_key}
                          </div>
                          <button
                            onClick={() => void copyToClipboard(key.plain_secret || key.masked_key)}
                            className="p-0.5 text-slate-400 hover:text-blue-600 transition-colors"
                            title={key.plain_secret ? t('keys.copySecret') : t('keys.copyMasked')}
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                          {key.plain_secret && (
                            <button
                              onClick={() => toggleSecretVisibility(key.id)}
                              className="w-10 px-1.5 py-0.5 text-[10px] border border-slate-200 rounded text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition-colors"
                            >
                              {visibleSecrets[key.id] ? t('keys.hide') : t('keys.show')}
                            </button>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                          key.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'
                        }`}
                      >
                        {key.status === 'active' ? t('keys.active') : t('keys.disabled')}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex gap-1 flex-wrap">
                        {key.scopes.map((scope) => (
                          <span
                            key={scope}
                            className="px-1.5 py-0.5 bg-blue-50 text-blue-600 border border-blue-100 rounded text-[10px] uppercase font-bold"
                          >
                            {scope}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-xs text-slate-600 font-mono">
                      {key.rpm_limit || '∞'} / {key.concurrency_limit || '∞'}
                    </td>
                    <td className="px-5 py-4 text-xs text-slate-500">
                      {key.usage_summary ? (
                        <div>
                          <div>{t('keys.totalRequests')}: {key.usage_summary.total_requests}</div>
                          <div>{t('keys.totalTokens')}: {key.usage_summary.total_tokens ?? '-'}</div>
                        </div>
                      ) : (
                        <div>-</div>
                      )}
                    </td>
                    <td className="px-5 py-4 text-xs text-slate-500">
                      <div>{formatDate(key.created_at)}</div>
                      <div className="mt-1">
                        {t('keys.lastUsed')}: {formatDate(key.last_used_at)}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        <ToggleButton onClick={() => void handleToggle(key)} disabled={busyId === key.id}>
                          {key.status === 'active' ? t('keys.disable') : t('keys.enable')}
                        </ToggleButton>
                        <button
                          onClick={() => void handleDelete(key)}
                          disabled={busyId === key.id}
                          className="p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors disabled:opacity-50"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
