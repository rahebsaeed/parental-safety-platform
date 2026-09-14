import React, { useEffect, useState } from 'react';
import {
  Info,
  CheckCircle,
  Play,
  Check,
  Slash,
} from 'lucide-react';
import { api } from '../services/api';
import { useRealtime } from '../hooks/useRealtime';
import type { AlertSummary, SafetyAlert, RealtimeEvent } from '../types/api';

export const AlertsPage: React.FC = () => {
  const [alerts, setAlerts] = useState<SafetyAlert[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ACTIVE');
  const [scanning, setScanning] = useState(false);
  const [loading, setLoading] = useState(true);

  // Live incoming safety alerts
  const handleRealtime = (event: RealtimeEvent) => {
    if (event.type === 'safety_alert') {
      const newAlert = event.data as SafetyAlert;
      if (severityFilter !== 'ALL' && newAlert.severity !== severityFilter) return;
      if (statusFilter !== 'ALL' && newAlert.status !== statusFilter) return;

      setAlerts((prev) => [newAlert, ...prev]);
      setSummary((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          total_alerts: prev.total_alerts + 1,
          active_alerts: prev.active_alerts + 1,
        };
      });
    }
  };

  useRealtime({ onEvent: handleRealtime });

  useEffect(() => {
    loadAlerts();
  }, [severityFilter, statusFilter]);

  async function loadAlerts() {
    try {
      setLoading(true);
      const [alertList, sum] = await Promise.all([
        api.getAlerts({
          severity: severityFilter === 'ALL' ? undefined : severityFilter,
          status: statusFilter === 'ALL' ? undefined : statusFilter,
        }),
        api.getAlertSummary(),
      ]);
      setAlerts(alertList);
      setSummary(sum);
    } catch (err) {
      console.error('Failed to load alerts:', err);
    } finally {
      setLoading(false);
    }
  }

  async function updateStatus(alertId: number, newStatus: string) {
    try {
      await api.updateAlertStatus(alertId, newStatus);
      await loadAlerts();
    } catch (err) {
      alert('Failed to update alert status: ' + err);
    }
  }

  async function triggerScan() {
    try {
      setScanning(true);
      const res = await api.triggerAlertScan(1000);
      alert(`Safety Scan Complete:\n• Queries scanned: ${res.scanned_queries}\n• New alerts: ${res.alerts_created}\n• Aggregated: ${res.alerts_aggregated}`);
      await loadAlerts();
    } catch (err) {
      alert('Failed to run safety scan: ' + err);
    } finally {
      setScanning(false);
    }
  }

  function getSeverityBadge(severity: string) {
    switch (severity) {
      case 'CRITICAL':
        return <span className="badge badge-danger">CRITICAL</span>;
      case 'HIGH':
        return <span className="badge badge-warning">HIGH</span>;
      case 'MEDIUM':
        return <span className="badge badge-info">MEDIUM</span>;
      default:
        return <span className="badge badge-muted">LOW</span>;
    }
  }

  return (
    <div>
      {/* Top Action & Summary Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.25rem', fontWeight: 700 }}>
            Safety Alert Console
          </h2>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            Advisory monitoring of unsafe categories, phishing patterns, and DNS bypass attempts.
          </div>
        </div>

        <button
          onClick={triggerScan}
          className="btn btn-primary btn-sm"
          disabled={scanning}
        >
          <Play size={14} className={scanning ? 'spin' : ''} />
          <span>{scanning ? 'Scanning Queries...' : 'Run Safety Scan'}</span>
        </button>
      </div>

      {/* Metric Counters */}
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="glass-card" style={{ padding: '1.25rem' }}>
          <div className="card-title">Total Alerts Recorded</div>
          <div className="card-value">{summary?.total_alerts || 0}</div>
        </div>
        <div className="glass-card" style={{ padding: '1.25rem' }}>
          <div className="card-title">Active Concerns</div>
          <div className="card-value" style={{ color: (summary?.active_alerts || 0) > 0 ? '#f87171' : 'var(--text-primary)' }}>
            {summary?.active_alerts || 0}
          </div>
        </div>
        <div className="glass-card" style={{ padding: '1.25rem' }}>
          <div className="card-title">Bypass / DoH Probes</div>
          <div className="card-value" style={{ color: '#38bdf8' }}>
            {summary?.by_type?.BYPASS_ATTEMPT || 0}
          </div>
        </div>
        <div className="glass-card" style={{ padding: '1.25rem' }}>
          <div className="card-title">Critical / Unsafe Content</div>
          <div className="card-value" style={{ color: '#f87171' }}>
            {(summary?.by_severity?.CRITICAL || 0) + (summary?.by_severity?.HIGH || 0)}
          </div>
        </div>
      </div>

      {/* Filter Chips */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        {/* Severity Filters */}
        <div style={{ display: 'flex', gap: '0.375rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginRight: '0.375rem' }}>Severity:</span>
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((s) => (
            <button
              key={s}
              onClick={() => setSeverityFilter(s)}
              className={`btn btn-sm ${severityFilter === s ? 'btn-primary' : 'btn-secondary'}`}
              style={{ fontSize: '0.75rem', padding: '0.25rem 0.625rem' }}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Status Filters */}
        <div style={{ display: 'flex', gap: '0.375rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginRight: '0.375rem' }}>Status:</span>
          {['ACTIVE', 'ACKNOWLEDGED', 'DISMISSED', 'RESOLVED', 'ALL'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`btn btn-sm ${statusFilter === st ? 'btn-primary' : 'btn-secondary'}`}
              style={{ fontSize: '0.75rem', padding: '0.25rem 0.625rem' }}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* Alert List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {loading ? (
          <div className="glass-card" style={{ textAlign: 'center', padding: '3rem 1.5rem', color: 'var(--text-muted)' }}>
            <div>Loading safety alerts...</div>
          </div>
        ) : alerts.length === 0 ? (
          <div className="glass-card" style={{ textAlign: 'center', padding: '3rem 1.5rem', color: 'var(--text-muted)' }}>
            <CheckCircle size={40} style={{ margin: '0 auto 1rem', color: 'var(--success)', opacity: 0.8 }} />
            <div style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
              No alerts match your current filter
            </div>
            <div style={{ fontSize: '0.875rem' }}>Your network observation is clear of unhandled safety events.</div>
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className="glass-card"
              style={{
                borderLeft: `4px solid ${
                  alert.severity === 'CRITICAL' ? 'var(--danger)' :
                  alert.severity === 'HIGH' ? 'var(--warning)' : 'var(--info)'
                }`,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  {getSeverityBadge(alert.severity)}
                  <span style={{ fontWeight: 600, fontSize: '1.0625rem', color: 'var(--text-primary)' }}>
                    {alert.title}
                  </span>
                  <span className="badge badge-muted" style={{ textTransform: 'none' }}>
                    Seen {alert.occurrence_count} {alert.occurrence_count === 1 ? 'time' : 'times'}
                  </span>
                </div>

                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  First: {alert.created_at} • Last: {alert.last_seen_at}
                </div>
              </div>

              {/* Target domain and device */}
              <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '0.875rem' }}>
                Target Domain: <strong style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{alert.domain}</strong>
                {alert.device_id && (
                  <span style={{ marginLeft: '1rem' }}>
                    Device: <span style={{ color: 'var(--text-primary)' }}>{alert.device_id}</span>
                  </span>
                )}
              </div>

              {/* Explainability Section (Section 35) */}
              <div style={{
                background: 'rgba(15, 23, 42, 0.6)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '0.75rem 1rem',
                fontSize: '0.8125rem',
                color: 'var(--text-secondary)',
                marginBottom: '1rem',
              }}>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                  <Info size={14} color="var(--primary-light)" />
                  Rule: {alert.rule_matched}
                </div>
                <div>{alert.explanation}</div>
              </div>

              {/* Triage Actions */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)' }}>
                <span className={`badge ${alert.status === 'ACTIVE' ? 'badge-danger' : 'badge-muted'}`}>
                  Status: {alert.status}
                </span>

                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  {alert.status === 'ACTIVE' && (
                    <button
                      onClick={() => updateStatus(alert.id, 'ACKNOWLEDGED')}
                      className="btn btn-secondary btn-sm"
                      title="Mark as acknowledged"
                    >
                      <Check size={12} /> Acknowledge
                    </button>
                  )}
                  {alert.status !== 'DISMISSED' && (
                    <button
                      onClick={() => updateStatus(alert.id, 'DISMISSED')}
                      className="btn btn-secondary btn-sm"
                      title="Dismiss alert"
                    >
                      <Slash size={12} /> Dismiss
                    </button>
                  )}
                  {alert.status !== 'RESOLVED' && (
                    <button
                      onClick={() => updateStatus(alert.id, 'RESOLVED')}
                      className="btn btn-primary btn-sm"
                      title="Mark as resolved"
                    >
                      <CheckCircle size={12} /> Resolve
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
