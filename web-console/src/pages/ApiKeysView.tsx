import React, {useMemo, useState} from 'react';
import {CheckCircle2, Copy, Key, Plus, Trash2, X} from 'lucide-react';
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
  const {apiKeys, createApiKey, updateApiKey, deleteApiKey, loading} = useAppContext();
  const [showNewSecret, setShowNewSecret] = useState<string | null>(null);
  const [copyDone, setCopyDone] = useState(false);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

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
      const response = await createApiKey({
        name: name.trim(),
        scopes,
        rpm_limit: rpmLimit.trim() ? Number(rpmLimit) : null,
        concurrency_limit: concurrencyLimit.trim() ? Number(concurrencyLimit) : null,
        note: note.trim() || null,
      });
      setShowNewSecret(response.secret);
      setCopyDone(false);
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

  async function handleCopy() {
    if (!showNewSecret) {
      return;
    }
    await navigator.clipboard.writeText(showNewSecret);
    setCopyDone(true);
    setTimeout(() => setCopyDone(false), 1200);
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

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 h-full flex flex-col">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-4">
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">Total Keys</div>
          <div className="text-4xl font-bold text-slate-800">{stats.total}</div>
        </div>
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">Active</div>
          <div className="text-4xl font-bold text-emerald-600">{stats.active}</div>
        </div>
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">Inference Scopes</div>
          <div className="text-4xl font-bold text-blue-600">{stats.inference}</div>
        </div>
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div className="text-[10px] uppercase font-bold text-black/30 tracking-widest mb-4">Admin Scopes</div>
          <div className="text-4xl font-bold text-purple-600">{stats.admin}</div>
        </div>
      </div>

      <div className="glass-panel p-5">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_0.9fr_0.9fr_1fr_auto]">
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Key name"
            className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          <input
            type="number"
            value={rpmLimit}
            onChange={(event) => setRpmLimit(event.target.value)}
            placeholder="RPM limit"
            className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          <input
            type="number"
            value={concurrencyLimit}
            onChange={(event) => setConcurrencyLimit(event.target.value)}
            placeholder="Concurrency"
            className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          <input
            type="text"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Optional note"
            className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !name.trim() || (!scopeAdmin && !scopeInference)}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-800 transition-colors shadow-md shadow-slate-900/20 disabled:opacity-60"
          >
            <Plus className="w-4 h-4" />
            {creating ? 'Creating...' : 'Create Key'}
          </button>
        </div>

        <div className="flex flex-wrap gap-3 mt-4">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={scopeAdmin} onChange={() => setScopeAdmin((value) => !value)} />
            admin
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={scopeInference} onChange={() => setScopeInference((value) => !value)} />
            inference
          </label>
        </div>
      </div>

      {showNewSecret && (
        <div className="glass-panel-dark overflow-hidden relative border-emerald-500/30">
          <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/20 rounded-full blur-3xl pointer-events-none" />
          <div className="p-6 relative z-10">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-2 text-emerald-400">
                <CheckCircle2 className="w-5 h-5" />
                <h3 className="font-semibold text-lg">Key Generated Successfully</h3>
              </div>
              <button onClick={() => setShowNewSecret(null)} className="text-slate-400 hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-sm text-slate-300 mb-4">
              请立刻保存这个密钥。<strong className="text-red-400 font-bold">关闭后将无法再次查看。</strong>
            </p>

            <div className="flex items-center gap-3">
              <code className="flex-1 bg-slate-950/50 p-3 rounded-lg text-emerald-300 font-mono text-sm border border-emerald-500/20 selection:bg-emerald-500/30 break-all">
                {showNewSecret}
              </code>
              <button
                onClick={() => void handleCopy()}
                className="p-3 bg-emerald-500/20 hover:bg-emerald-500/40 text-emerald-300 rounded-lg border border-emerald-500/50 transition-all"
                title="Copy to clipboard"
              >
                <Copy className="w-5 h-5" />
              </button>
            </div>
            {copyDone && <div className="text-xs text-emerald-300 mt-3">已复制到剪贴板</div>}
          </div>
        </div>
      )}

      <div className="glass-panel flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-white/40 flex items-center justify-between gap-4 bg-white/20">
          <div className="font-semibold text-slate-800">Database API Keys</div>
          <div className="text-xs text-slate-500">{loading.apiKeys ? '正在加载...' : `${apiKeys.length} keys`}</div>
        </div>

        <div className="flex-1 overflow-auto p-0">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-500 uppercase bg-slate-50/50">
              <tr>
                <th className="px-5 py-3 font-medium">Name</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Scopes</th>
                <th className="px-5 py-3 font-medium">Limits (RPM/Conc)</th>
                <th className="px-5 py-3 font-medium">Created At</th>
                <th className="px-5 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100/50">
              {apiKeys.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-slate-500">
                    {loading.apiKeys ? '正在获取密钥列表...' : '还没有 API Key'}
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
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                          key.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'
                        }`}
                      >
                        {key.status}
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
                      <div>{formatDate(key.created_at)}</div>
                      <div className="mt-1">last used: {formatDate(key.last_used_at)}</div>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        <ToggleButton onClick={() => void handleToggle(key)} disabled={busyId === key.id}>
                          {key.status === 'active' ? 'Disable' : 'Enable'}
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
