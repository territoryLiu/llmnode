import React, {useMemo, useState} from 'react';
import {Search} from 'lucide-react';
import {useAppContext} from '../store';
import {mapRequestStatus} from '../i18n';

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function UsageRecordsView() {
  const {requestLogs, snapshot, loading, locale, t} = useAppContext();
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');

  const filteredLogs = useMemo(() => {
    return requestLogs.filter((log) => {
      if (filter !== 'all' && log.status !== filter) {
        return false;
      }
      if (!query.trim()) {
        return true;
      }
      const keyword = query.trim().toLowerCase();
      return [log.request_id, log.model_name, log.protocol, log.auth_source, log.client_ip, log.rejection_reason]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [filter, query, requestLogs]);

  const total = requestLogs.length;
  const exceptions = requestLogs.filter((log) => log.error_message).length;
  const rejected = requestLogs.filter((log) => log.status !== 'ok').length;
  const backendType = snapshot?.backend_type?.toUpperCase() || 'VLLM';

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 h-full flex flex-col">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-4">
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
      </div>

      <div className="glass-panel flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-white/40 flex items-center justify-between gap-4 bg-white/20 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
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
          </div>
          <div className="text-xs text-slate-500">
            {t('usage.showing', {shown: filteredLogs.length, total: requestLogs.length})}
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
                <th className="px-5 py-3 font-medium">{t('usage.reason')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100/50">
              {filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-slate-500">
                    {loading.requestLogs ? t('usage.loadingLogs') : t('usage.noResults')}
                  </td>
                </tr>
              ) : (
                filteredLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-white/40 transition-colors">
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
                    <td className="px-5 py-3 text-slate-500 font-mono text-xs max-w-[220px] truncate">
                      {log.rejection_reason || log.error_message || '-'}
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
