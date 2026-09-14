import React from 'react';
import { RefreshCw, Radio, LogOut } from 'lucide-react';

interface Props {
  title: string;
  subtitle?: string;
  isDaemonAlive?: boolean;
  isRealtimeConnected?: boolean;
  onRefresh?: () => void;
  loading?: boolean;
  onLogout?: () => void;
}

export const Header: React.FC<Props> = ({
  title,
  subtitle,
  isDaemonAlive = true,
  isRealtimeConnected = false,
  onRefresh,
  loading = false,
  onLogout,
}) => {
  return (
    <header className="top-header">
      <div className="header-title-group">
        <h1>{title}</h1>
        {subtitle && (
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            {subtitle}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        {/* Real-time WebSocket Status */}
        <div
          className="header-status-badge"
          style={{
            backgroundColor: isRealtimeConnected ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255, 255, 255, 0.05)',
            borderColor: isRealtimeConnected ? 'rgba(99, 102, 241, 0.3)' : 'var(--border-subtle)',
          }}
          title={isRealtimeConnected ? 'WebSocket live event streaming active' : 'Connecting to real-time event stream'}
        >
          <Radio size={12} color={isRealtimeConnected ? 'var(--primary-light)' : 'var(--text-muted)'} />
          <span style={{ color: isRealtimeConnected ? 'var(--primary-light)' : 'var(--text-secondary)' }}>
            {isRealtimeConnected ? 'WebSocket Live' : 'Reconnecting...'}
          </span>
        </div>

        {/* DNS Daemon Observer Status */}
        <div className="header-status-badge">
          <span className="status-dot-pulse" />
          <span>{isDaemonAlive ? 'DNS Observer Active' : 'Daemon Standby'}</span>
        </div>

        {onRefresh && (
          <button
            onClick={onRefresh}
            className="btn btn-secondary btn-sm"
            disabled={loading}
            title="Refresh Data"
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
        )}

        {onLogout && (
          <button onClick={onLogout} className="btn btn-secondary btn-sm" title="Sign out">
            <LogOut size={14} />
            <span>Sign Out</span>
          </button>
        )}
      </div>
    </header>
  );
};
