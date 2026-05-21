import React from 'react';
import {
  Activity,
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  Key,
  LayoutDashboard,
  Network,
  Wifi,
  WifiOff,
} from 'lucide-react';
import logoImage from '../../logo.png';
import {useAppContext} from '../store';
import {cn} from '../lib/utils';
import {Background} from './Background';

export function Layout({children}: {children: React.ReactNode}) {
  const {
    currentPage,
    setCurrentPage,
    locale,
    toggleLocale,
    pageTitle,
    t,
    adminApiKey,
    setAdminApiKey,
    sseConnected,
    globalError,
    copyFeedback,
    lastUpdated,
  } = useAppContext();
  const [draftApiKey, setDraftApiKey] = React.useState(adminApiKey);
  const [showAdminPanel, setShowAdminPanel] = React.useState(false);

  React.useEffect(() => {
    setDraftApiKey(adminApiKey);
  }, [adminApiKey]);

  const navItems = [
    {id: 'overview', label: t('layout.nav.overview'), icon: LayoutDashboard},
    {id: 'usage', label: t('layout.nav.usage'), icon: Activity},
    {id: 'keys', label: t('layout.nav.keys'), icon: Key},
    {id: 'models', label: t('layout.nav.models'), icon: Network},
    {id: 'schedule', label: t('layout.nav.schedule'), icon: CalendarClock},
  ] as const;

  return (
    <div className="relative min-h-screen flex text-slate-800">
      <Background />

      {/* Sidebar - Glassmorphism */}
      <aside className="w-72 fixed inset-y-0 left-0 p-6 flex flex-col z-20 gap-8">
        <div className="flex items-center justify-center px-2">
          <img src={logoImage} alt="LlmNode logo" className="h-36 w-60 object-contain drop-shadow-sm" />
        </div>

        <nav className="flex-1 space-y-2">
          {navItems.map((item) => {
            const isActive = currentPage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setCurrentPage(item.id)}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 text-left cursor-pointer',
                  isActive
                    ? 'bg-white/40 backdrop-blur-md border border-white/40 shadow-sm'
                    : 'hover:bg-white/30 text-[#1a1a1a]/50 hover:text-[#1a1a1a] border border-transparent',
                )}
              >
                <item.icon className={cn('w-5 h-5 shrink-0', isActive ? 'text-blue-600 opacity-80' : 'opacity-50')} />
                <span className={cn('font-medium', isActive ? 'opacity-100' : '')}>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 ml-72 p-6 flex flex-col min-h-screen">
        {/* Top Bar */}
        <header className="mb-8 flex items-center justify-between z-10">
          <div>
            <h1 className="text-3xl font-light text-[#1a1a1a]">
              <span className="font-bold">LlmNode</span> {pageTitle}
            </h1>
            <div className="text-sm text-[#1a1a1a]/60 mt-1">
              {t('layout.subtitle')}
              {lastUpdated && (
                <span className="ml-2">
                  {t('layout.lastUpdated')}:{' '}
                  {lastUpdated.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US')}
                </span>
              )}
            </div>
            {!adminApiKey && (
              <div className="mt-4 max-w-2xl rounded-2xl border border-amber-200 bg-amber-50/90 px-4 py-3">
                <div className="text-sm font-medium text-amber-900">{t('layout.apiKeyMissingBanner')}</div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={toggleLocale}
              className="px-4 py-2 rounded-full border border-white/60 bg-white/40 backdrop-blur-md text-sm font-medium hover:bg-white/60 transition-colors"
            >
              {locale === 'zh' ? t('layout.switchToEnglish') : t('layout.switchToChinese')}
            </button>

            {globalError && (
              <div className="max-w-md flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-100/80 border border-red-200 text-red-600 text-xs font-medium">
                <AlertCircle className="w-4 h-4" />
                <span className="truncate">{globalError}</span>
              </div>
            )}

            <div
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border backdrop-blur-md transition-colors',
                sseConnected
                  ? 'bg-emerald-100/50 border-emerald-200/50 text-emerald-700'
                  : 'bg-red-100/50 border-red-200/50 text-red-700',
              )}
            >
              {sseConnected ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
              {sseConnected ? t('layout.snapshotLive') : t('layout.snapshotReconnecting')}
            </div>

            <div className="relative">
              <button
                type="button"
                aria-label={t('layout.admin')}
                onClick={() => setShowAdminPanel((value) => !value)}
                className="px-4 py-2 rounded-full border border-white/60 bg-white/40 backdrop-blur-md flex items-center gap-3 cursor-pointer"
              >
                <div className="w-6 h-6 rounded-full bg-slate-400"></div>
                <span className="text-sm font-medium">{t('layout.admin')}</span>
              </button>
              {showAdminPanel && (
                <div className="absolute right-0 top-[calc(100%+0.75rem)] z-30 w-[26rem] rounded-2xl border border-amber-200 bg-amber-50/95 p-4 shadow-lg shadow-amber-200/40 backdrop-blur-md">
                  <div className="text-sm font-medium text-amber-900">
                    {adminApiKey ? t('layout.admin') : t('layout.apiKeyMissingBanner')}
                  </div>
                  <div className="mt-3 flex flex-col gap-3">
                    <input
                      aria-label={t('layout.apiKeyPlaceholder')}
                      type="password"
                      value={draftApiKey}
                      onChange={(event) => setDraftApiKey(event.target.value)}
                      placeholder={t('layout.apiKeyPlaceholder')}
                      className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-amber-400/40"
                    />
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setDraftApiKey(adminApiKey);
                          setShowAdminPanel(false);
                        }}
                        className="rounded-full border border-amber-300 bg-white px-3.5 py-2 text-sm text-amber-900 transition-colors hover:bg-amber-100"
                      >
                        {t('layout.closeAdminPanel')}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setAdminApiKey(draftApiKey);
                          setShowAdminPanel(false);
                        }}
                        disabled={!draftApiKey.trim()}
                        className="rounded-full border border-amber-900 bg-amber-900 px-3.5 py-2 text-sm text-white transition-colors hover:bg-amber-800 disabled:opacity-50"
                      >
                        {t('layout.saveApiKey')}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Page Content View */}
        <div className="flex-1 z-10 relative">
          {children}
        </div>
      </main>

      <div className="pointer-events-none fixed right-6 top-6 z-50">
        <div
          role="status"
          aria-live="polite"
          data-testid="copy-toast"
          className={cn(
            'flex items-center gap-3 rounded-2xl border border-emerald-200/80 bg-white/90 px-4 py-3 text-sm font-medium text-emerald-700 shadow-lg shadow-emerald-200/40 backdrop-blur-md transition-all duration-300',
            copyFeedback?.visible ? 'translate-y-0 opacity-100' : '-translate-y-2 opacity-0',
            copyFeedback ? 'visible' : 'invisible',
          )}
        >
          <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" />
          <span className="max-w-xs truncate">{copyFeedback?.message ?? ''}</span>
        </div>
      </div>
    </div>
  );
}
