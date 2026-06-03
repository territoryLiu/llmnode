import React from 'react';
import {Activity, History, Play, Square, Terminal} from 'lucide-react';
import {useAppContext} from '../store';

function parseTargets(value: string): number[] {
  return value
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item) && item > 0);
}

function statusTone(status: string): string {
  if (status.includes('failed') || status === 'failed') {
    return 'bg-red-50 text-red-700 border-red-200';
  }
  if (status === 'completed') {
    return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  }
  if (status === 'running' || status === 'queued') {
    return 'bg-blue-50 text-blue-700 border-blue-200';
  }
  return 'bg-slate-50 text-slate-600 border-slate-200';
}

export function PerformanceLabView() {
  const {createPerfRun, cancelPerfRun, activePerfRun, perfRuns, t} = useAppContext();
  const [profile, setProfile] = React.useState('vllm_qwen36-27b-nvfp4');
  const [targets, setTargets] = React.useState('4096,32768,65536,131072,176128,262000');
  const [gpuMemoryValues, setGpuMemoryValues] = React.useState('0.55');
  const [submitting, setSubmitting] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const matrixValues = parseTargets(gpuMemoryValues);
    setSubmitting(true);
    try {
      await createPerfRun({
        profile,
        targets: parseTargets(targets),
        max_tokens: 64,
        warmup_runs: 1,
        measure_runs: 3,
        sample_interval: 1,
        concurrency: 1,
        restart_backend: true,
        matrix: matrixValues.length ? {gpu_memory_utilization: matrixValues} : {},
      });
    } finally {
      setSubmitting(false);
    }
  }

  const latestRun = activePerfRun ?? perfRuns[0] ?? null;

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <form
          onSubmit={submit}
          className="glass-panel relative overflow-hidden p-6"
        >
          <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-cyan-400/10 blur-3xl" />
          <div className="absolute -bottom-28 left-10 h-64 w-64 rounded-full bg-slate-900/10 blur-3xl" />
          <div className="relative z-10">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl bg-slate-900 p-3 text-white shadow-lg shadow-slate-900/20">
                <Terminal className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-2xl font-bold text-slate-900">{t('performance.title')}</h2>
                <p className="mt-1 text-sm text-slate-500">{t('performance.hint')}</p>
              </div>
            </div>

            <label className="mt-6 block text-xs font-bold uppercase tracking-wider text-slate-500">
              {t('performance.profile')}
              <input
                aria-label="profile"
                value={profile}
                onChange={(event) => setProfile(event.target.value)}
                className="mt-2 w-full rounded-xl border border-white/80 bg-white/70 px-3 py-2 text-sm font-mono text-slate-800 outline-none focus:ring-2 focus:ring-cyan-500/30"
              />
            </label>

            <label className="mt-4 block text-xs font-bold uppercase tracking-wider text-slate-500">
              {t('performance.targets')}
              <textarea
                aria-label="targets"
                value={targets}
                onChange={(event) => setTargets(event.target.value)}
                className="mt-2 h-28 w-full rounded-xl border border-white/80 bg-white/70 px-3 py-2 text-sm font-mono text-slate-800 outline-none focus:ring-2 focus:ring-cyan-500/30"
              />
            </label>

            <label className="mt-4 block text-xs font-bold uppercase tracking-wider text-slate-500">
              GPU memory utilization matrix
              <input
                aria-label="gpu memory utilization matrix"
                value={gpuMemoryValues}
                onChange={(event) => setGpuMemoryValues(event.target.value)}
                className="mt-2 w-full rounded-xl border border-white/80 bg-white/70 px-3 py-2 text-sm font-mono text-slate-800 outline-none focus:ring-2 focus:ring-cyan-500/30"
              />
            </label>

            <button
              type="submit"
              disabled={submitting || !parseTargets(targets).length || !profile.trim()}
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition-colors hover:bg-slate-800 disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              {t('performance.start')}
            </button>
          </div>
        </form>

        <section className="glass-panel p-6">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl bg-cyan-50 p-3 text-cyan-700">
                <Activity className="h-5 w-5" />
              </div>
              <h3 className="text-xl font-bold text-slate-900">{t('performance.currentRun')}</h3>
            </div>
            {latestRun && (
              <span className={`rounded-full border px-3 py-1 text-xs font-bold ${statusTone(latestRun.status)}`}>
                {latestRun.status}
              </span>
            )}
          </div>

          {latestRun ? (
            <div className="mt-6 space-y-4">
              <div className="rounded-2xl border border-white/70 bg-white/70 p-4">
                <div className="text-xs uppercase tracking-widest text-slate-400">run id</div>
                <div className="mt-1 break-all font-mono text-sm text-slate-800">{latestRun.run_id}</div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-2xl border border-white/70 bg-white/60 p-4">
                  <div className="text-xs uppercase tracking-widest text-slate-400">profile</div>
                  <div className="mt-1 truncate font-mono text-slate-800">{latestRun.request.profile}</div>
                </div>
                <div className="rounded-2xl border border-white/70 bg-white/60 p-4">
                  <div className="text-xs uppercase tracking-widest text-slate-400">targets</div>
                  <div className="mt-1 font-mono text-slate-800">{latestRun.request.targets.length}</div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => cancelPerfRun(latestRun.run_id)}
                disabled={!['queued', 'running', 'cancel_requested'].includes(latestRun.status)}
                className="inline-flex items-center gap-2 rounded-full border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700 transition-colors hover:bg-red-100 disabled:opacity-40"
              >
                <Square className="h-4 w-4" />
                {t('performance.cancel')}
              </button>
            </div>
          ) : (
            <p className="mt-6 rounded-2xl border border-white/70 bg-white/60 p-5 text-sm text-slate-500">
              {t('performance.noRun')}
            </p>
          )}
        </section>
      </div>

      <section className="glass-panel p-6">
        <div className="mb-5 flex items-center gap-3">
          <History className="h-5 w-5 text-slate-500" />
          <h3 className="text-xl font-bold text-slate-900">{t('performance.history')}</h3>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {perfRuns.length === 0 ? (
            <div className="rounded-2xl border border-white/70 bg-white/60 p-5 text-sm text-slate-500">
              {t('performance.noRun')}
            </div>
          ) : (
            perfRuns.map((run) => (
              <div key={run.run_id} className="rounded-2xl border border-white/70 bg-white/70 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="truncate font-mono text-xs text-slate-700">{run.run_id}</div>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold ${statusTone(run.status)}`}>
                    {run.status}
                  </span>
                </div>
                <div className="mt-3 text-xs text-slate-500">{run.request.profile}</div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
