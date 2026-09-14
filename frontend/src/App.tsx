import React, { useEffect, useState, useCallback } from 'react';
import { Sidebar, NavTab } from './components/Sidebar';
import { Header } from './components/Header';
import { OverviewPage } from './pages/OverviewPage';
import { DevicesPage } from './pages/DevicesPage';
import { AlertsPage } from './pages/AlertsPage';
import { ActivityPage } from './pages/ActivityPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { ClassificationsPage } from './pages/ClassificationsPage';
import { SettingsPage } from './pages/SettingsPage';
import { LoginPage } from './pages/LoginPage';
import { api } from './services/api';
import { useRealtime } from './hooks/useRealtime';
import type { HealthStatus, RealtimeEvent, SessionInfo } from './types/api';

const TAB_METADATA: Record<NavTab, { title: string; subtitle: string }> = {
  overview: { title: 'Platform Overview', subtitle: 'Real-time telemetry, health, and aggregate device safety' },
  devices: { title: 'Device Inventory', subtitle: 'Discovered network nodes, randomized MAC analysis, and hardware profiles' },
  alerts: { title: 'Safety Alerts Console', subtitle: 'Rule-driven explainable warnings with de-duplication and triage' },
  activity: { title: 'DNS Activity Stream', subtitle: 'Filterable network query log with direct vs. relayed visibility indicators' },
  analytics: { title: 'Network-Derived Analytics', subtitle: 'Aggregated request distribution and activity periods (Ethically Labeled)' },
  classifications: { title: 'Domain Rules & Categories', subtitle: '11-category classification engine, testing sandbox, and parent overrides' },
  settings: { title: 'Settings', subtitle: 'Account password and platform configuration' },
};

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>('overview');
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [activeAlertsCount, setActiveAlertsCount] = useState<number>(0);
  const [refreshKey, setRefreshKey] = useState<number>(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);

  const handleRealtimeEvent = useCallback((event: RealtimeEvent) => {
    if (event.type === 'safety_alert') setActiveAlertsCount((prev) => prev + 1);
  }, []);

  const { isConnected } = useRealtime({ onEvent: handleRealtimeEvent });

  const fetchGlobalStatus = useCallback(async () => {
    try {
      const [h, summary] = await Promise.all([
        api.getHealth().catch(() => null),
        api.getAlertSummary().catch(() => null),
      ]);
      if (h) setHealth(h);
      if (summary) setActiveAlertsCount(summary.active_alerts);
    } catch { }
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const info = await api.getAuthStatus();
      setSession(info);
    } catch {
      setSession(null);
    } finally {
      setLoadingSession(false);
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);
  useEffect(() => {
    if (!session?.authenticated) return;
    fetchGlobalStatus();
    const interval = setInterval(fetchGlobalStatus, 30000);
    return () => clearInterval(interval);
  }, [session?.authenticated, fetchGlobalStatus]);

  const handleLoginSuccess = useCallback(() => {
    setSession({ user_id: null, username: null, token: null, expires_at: "", authenticated: true, auth_enabled: true });
    fetchGlobalStatus();
  }, [fetchGlobalStatus]);

  const handleLogout = useCallback(async () => {
    try { await api.logout(); } catch { /* ignore */ }
    setSession({ user_id: null, username: null, token: null, expires_at: "", authenticated: true, auth_enabled: true });
  }, []);

  const handleManualRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await fetchGlobalStatus();
    setRefreshKey((k) => k + 1);
    setTimeout(() => setIsRefreshing(false), 400);
  }, [fetchGlobalStatus]);

  const handleScan = useCallback(async () => {
    setIsScanning(true);
    try {
      await api.triggerScan();
      await fetchGlobalStatus();
      setRefreshKey((k) => k + 1);
    } catch (err) {
      console.error('Scan failed:', err);
    } finally {
      setIsScanning(false);
    }
  }, [fetchGlobalStatus]);

  if (loadingSession) {
    return <div style={{ height: '100vh', background: '#090d16' }} />;
  }

  if (!session || !session.authenticated) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  const meta = TAB_METADATA[activeTab];

  return (
    <div className="app-container">
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        activeAlertsCount={activeAlertsCount}
      />
      <div className="main-wrapper">
        <Header
          title={meta.title}
          subtitle={meta.subtitle}
          isDaemonAlive={health?.dns_daemon_alive ?? true}
          isRealtimeConnected={isConnected}
          onRefresh={handleManualRefresh}
          loading={isRefreshing}
          onLogout={handleLogout}
        />
        <main className="content-viewport" key={refreshKey}>
          {activeTab === 'overview' && <OverviewPage onNavigate={(tab) => setActiveTab(tab as NavTab)} />}
          {activeTab === 'devices' && <DevicesPage onScan={handleScan} scanning={isScanning} />}
          {activeTab === 'alerts' && <AlertsPage />}
          {activeTab === 'activity' && <ActivityPage />}
          {activeTab === 'analytics' && <AnalyticsPage />}
          {activeTab === 'classifications' && <ClassificationsPage />}
          {activeTab === 'settings' && <SettingsPage />}
        </main>
      </div>
    </div>
  );
};
export default App;
