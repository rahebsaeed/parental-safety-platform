import React from 'react';
import {
  LayoutDashboard,
  Smartphone,
  ShieldAlert,
  Activity,
  BarChart3,
  FolderKanban,
  Shield,
  Settings,
} from 'lucide-react';

export type NavTab = 'overview' | 'devices' | 'alerts' | 'activity' | 'analytics' | 'classifications' | 'settings';

interface Props {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  activeAlertsCount?: number;
}

export const Sidebar: React.FC<Props> = ({
  activeTab,
  onTabChange,
  activeAlertsCount = 0,
}) => {
  const navItems = [
    { id: 'overview' as NavTab, label: 'Overview', icon: LayoutDashboard },
    { id: 'devices' as NavTab, label: 'Devices', icon: Smartphone },
    {
      id: 'alerts' as NavTab,
      label: 'Safety Alerts',
      icon: ShieldAlert,
      badge: activeAlertsCount > 0 ? activeAlertsCount : undefined,
    },
    { id: 'activity' as NavTab, label: 'Activity Log', icon: Activity },
    { id: 'analytics' as NavTab, label: 'Analytics', icon: BarChart3 },
    { id: 'classifications' as NavTab, label: 'Domain Rules', icon: FolderKanban },
    { id: 'settings' as NavTab, label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="sidebar" aria-label="Sidebar Navigation">
      <div className="sidebar-header">
        <div className="sidebar-logo-icon">
          <Shield size={20} />
        </div>
        <span className="sidebar-logo-title">Parental Safety</span>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`nav-item ${isActive ? 'active' : ''}`}
            >
              <div className="nav-item-left">
                <Icon size={18} />
                <span>{item.label}</span>
              </div>
              {item.badge !== undefined && (
                <span className="nav-badge">{item.badge}</span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div>Platform v0.1.0</div>
        <div style={{ color: 'var(--text-muted)' }}>Local Observer • 192.168.1.20</div>
      </div>
    </aside>
  );
};
