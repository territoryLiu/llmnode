import React, {useEffect, useState} from 'react';
import {Calendar, Check, Clock, Power, ShieldAlert} from 'lucide-react';
import {useAppContext, type ScheduleConfig} from '../store';

const DAYS = [
  {id: 'mon', key: 'schedule.days.mon'},
  {id: 'tue', key: 'schedule.days.tue'},
  {id: 'wed', key: 'schedule.days.wed'},
  {id: 'thu', key: 'schedule.days.thu'},
  {id: 'fri', key: 'schedule.days.fri'},
  {id: 'sat', key: 'schedule.days.sat'},
  {id: 'sun', key: 'schedule.days.sun'},
] as const;

const EMPTY_SCHEDULE: ScheduleConfig = {
  timezone: 'Asia/Shanghai',
  work_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
  start_time: '09:00',
  end_time: '18:00',
  auto_stop_enabled: true,
  auto_start_enabled: true,
  cooldown_minutes: 10,
};

export function ScheduleView() {
  const {schedule, updateSchedule, loading, t} = useAppContext();
  const [draft, setDraft] = useState<ScheduleConfig>(schedule || EMPTY_SCHEDULE);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (schedule) {
      setDraft(schedule);
    }
  }, [schedule]);

  function toggleDay(dayId: string) {
    setDraft((previous) => ({
      ...previous,
      work_days: previous.work_days.includes(dayId)
        ? previous.work_days.filter((item) => item !== dayId)
        : [...previous.work_days, dayId],
    }));
  }

  async function handleSave() {
    setSaving(true);
    try {
      const updated = await updateSchedule(draft);
      setDraft(updated);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-4xl">
      <div className="flex items-center gap-4 p-4 glass-panel bg-orange-50/50 border-orange-200">
        <ShieldAlert className="w-6 h-6 text-orange-500 shrink-0" />
        <div>
          <h4 className="text-sm font-semibold text-orange-900">{t('schedule.schedulingBehavior')}</h4>
          <p className="text-xs text-orange-800 mt-1">{t('schedule.schedulingBehaviorDesc')}</p>
        </div>
      </div>

      <div className="glass-panel p-6 relative overflow-hidden">
        <div className="absolute -bottom-20 -right-20 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -top-20 -left-20 w-64 h-64 bg-pink-500/10 rounded-full blur-3xl pointer-events-none" />

        <h3 className="text-lg font-semibold text-slate-800 mb-6 relative z-10 flex items-center gap-2">
          <Calendar className="w-5 h-5 text-blue-500" />
          {t('schedule.runtimeStrategy')}
        </h3>

        <form
          className="space-y-8 relative z-10"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSave();
          }}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase mb-2">{t('schedule.timezone')}</label>
                <select
                  value={draft.timezone}
                  onChange={(event) => setDraft((previous) => ({...previous, timezone: event.target.value}))}
                  className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30 text-slate-700"
                >
                  <option value="Asia/Shanghai">Asia/Shanghai</option>
                  <option value="UTC">UTC</option>
                  <option value="America/New_York">America/New_York</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase mb-2">{t('schedule.startTime')}</label>
                  <div className="relative">
                    <Clock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      type="time"
                      value={draft.start_time}
                      onChange={(event) => setDraft((previous) => ({...previous, start_time: event.target.value}))}
                      className="w-full pl-9 pr-3 py-2 text-sm bg-white/60 border border-white/80 rounded-lg outline-none focus:ring-2 focus:ring-blue-500/30"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase mb-2">{t('schedule.endTime')}</label>
                  <div className="relative">
                    <Clock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      type="time"
                      value={draft.end_time}
                      onChange={(event) => setDraft((previous) => ({...previous, end_time: event.target.value}))}
                      className="w-full pl-9 pr-3 py-2 text-sm bg-white/60 border border-white/80 rounded-lg outline-none focus:ring-2 focus:ring-blue-500/30"
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase mb-2">{t('schedule.cooldownMinutes')}</label>
                <input
                  type="number"
                  min={0}
                  value={draft.cooldown_minutes}
                  onChange={(event) =>
                    setDraft((previous) => ({...previous, cooldown_minutes: Number(event.target.value || 0)}))
                  }
                  className="w-full bg-white/60 border border-white/80 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/30 font-mono"
                />
              </div>
            </div>

            <div className="space-y-6">
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase mb-3">{t('schedule.workDays')}</label>
                <div className="flex flex-wrap gap-2">
                  {DAYS.map((day) => (
                    <label
                      key={day.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-blue-200 bg-blue-50/50 cursor-pointer hover:bg-blue-100 transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={draft.work_days.includes(day.id)}
                        onChange={() => toggleDay(day.id)}
                        className="w-3.5 h-3.5 text-blue-600 rounded border-slate-300 focus:ring-blue-500"
                      />
                      <span className="text-xs font-medium text-blue-900">{t(day.key)}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="space-y-4 pt-4 border-t border-slate-200/50">
                <label className="flex items-start gap-3 cursor-pointer group">
                  <div className="mt-0.5 relative flex items-center justify-center w-5 h-5 rounded border border-slate-300 bg-white group-hover:border-blue-400 transition-colors">
                    <input
                      type="checkbox"
                      checked={draft.auto_start_enabled}
                      onChange={(event) =>
                        setDraft((previous) => ({...previous, auto_start_enabled: event.target.checked}))
                      }
                        className="opacity-0 absolute inset-0 z-10 cursor-pointer peer"
                    />
                    <Check className="w-3.5 h-3.5 text-blue-600 opacity-0 peer-checked:opacity-100 transition-opacity" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-800">{t('schedule.autoStart')}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{t('schedule.autoStartDesc')}</div>
                  </div>
                </label>

                <label className="flex items-start gap-3 cursor-pointer group">
                  <div className="mt-0.5 relative flex items-center justify-center w-5 h-5 rounded border border-slate-300 bg-white group-hover:border-blue-400 transition-colors">
                    <input
                      type="checkbox"
                      checked={draft.auto_stop_enabled}
                      onChange={(event) =>
                        setDraft((previous) => ({...previous, auto_stop_enabled: event.target.checked}))
                      }
                        className="opacity-0 absolute inset-0 z-10 cursor-pointer peer"
                    />
                    <Check className="w-3.5 h-3.5 text-blue-600 opacity-0 peer-checked:opacity-100 transition-opacity" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-800">{t('schedule.autoStop')}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{t('schedule.autoStopDesc')}</div>
                  </div>
                </label>
              </div>
            </div>
          </div>

          <div className="pt-6 border-t border-white/60 flex items-center justify-between">
            <div className="text-xs text-slate-500">{loading.schedule ? t('schedule.loadingSchedule') : t('schedule.saveHint')}</div>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 px-6 py-2.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors shadow-lg shadow-slate-900/20 font-medium text-sm disabled:opacity-60"
            >
              <Power className="w-4 h-4" />
              {saving ? t('schedule.saving') : t('schedule.applySchedule')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
