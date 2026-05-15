/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import React from 'react';
import { AppProvider, useAppContext } from './store';
import { Layout } from './components/Layout';
import { OverviewView } from './pages/OverviewView';
import { UsageRecordsView } from './pages/UsageRecordsView';
import { ApiKeysView } from './pages/ApiKeysView';
import { ModelRoutesView } from './pages/ModelRoutesView';
import { ScheduleView } from './pages/ScheduleView';

function PageRouter() {
  const { currentPage } = useAppContext();
  
  switch (currentPage) {
    case 'overview': return <OverviewView />;
    case 'usage': return <UsageRecordsView />;
    case 'keys': return <ApiKeysView />;
    case 'models': return <ModelRoutesView />;
    case 'schedule': return <ScheduleView />;
    default: return <OverviewView />;
  }
}

export default function App() {
  return (
    <AppProvider>
      <Layout>
        <PageRouter />
      </Layout>
    </AppProvider>
  );
}
