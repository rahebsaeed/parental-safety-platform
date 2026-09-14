import React, { useEffect, useState } from 'react';
import {
  Smartphone,
  ShieldAlert,
  Activity,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { api } from '../services/api';
import type {
  AnalyticsOverview,
  CategoryDistributionResponse,
  Device,
  DnsQuery,
  SafetyAlert,
} from '../types/api';
import { EthicalBanner } from '../components/EthicalBanner';

function localTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch {
    return iso;
  }
}

interface Props {
  onNavigate: (tab: 'devices' | 'alerts' | 'activity' | 'analytics' | 'classifications') => void;
}

export const OverviewPage: React.FC<Props> = ({ onNavigate }) => {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [categories, setCategories] = useState<CategoryDistributionResponse | null>(null);
  const [recentQueries, setRecentQueries] = useState<DnsQuery[]>([]);
  const [activeAlerts, setActiveAlerts] = useState<SafetyAlert[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const [ov, cat, act, al, dev] = await Promise.all([
          api.getAnalyticsOverview(),
          api.getCategoryDistribution(),
          api.getActivity({ limit: 8 }),
          api.getAlerts({ status: 'ACTIVE' }),
          api.getDevices(),
        ]);
        setOverview(ov);
        setCategories(cat);
        setRecentQueries(act);
        setActiveAlerts(al);
        setDevices(dev);
      } catch (err) {
        console.error('Failed to load overview data:', err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const onlineDevicesCount = devices.filter((d) => d.status === 'online').length;

  return (
    <div>
      <EthicalBanner text={overview?.disclaimer} />

      {/* Metrics Row */}
      <div className="stats-grid">
        <div className="glass-card" onClick={() => onNavigate('activity')} style={{ cursor: 'pointer' }}>
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Network Query Volume</span>
            <Activity size={18} color="var(--primary-light)" />
          </div>
          <div className="card-value">{loading ? '...' : (overview?.total_queries.toLocaleString() || '0')}</div>
          <div className="card-subtext">Across {overview?.distinct_domains || 0} unique domains</div>
        </div>

        <div className="glass-card" onClick={() => onNavigate('devices')} style={{ cursor: 'pointer' }}>
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Discovered Devices</span>
            <Smartphone size={18} color="var(--success)" />
          </div>
          <div className="card-value">{loading ? '...' : devices.length}</div>
          <div className="card-subtext">{onlineDevicesCount} online now on subnet</div>
        </div>

        <div className="glass-card" onClick={() => onNavigate('alerts')} style={{ cursor: 'pointer' }}>
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Active Safety Alerts</span>
            <ShieldAlert size={18} color={activeAlerts.length > 0 ? 'var(--danger)' : 'var(--success)'} />
          </div>
          <div className="card-value" style={{ color: activeAlerts.length > 0 ? '#f87171' : 'var(--text-primary)' }}>
            {loading ? '...' : activeAlerts.length}
          </div>
          <div className="card-subtext">
            {activeAlerts.length > 0 ? 'Action or triage recommended' : 'No active security concerns'}
          </div>
        </div>

        <div className="glass-card" onClick={() => onNavigate('analytics')} style={{ cursor: 'pointer' }}>
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Dominant Category</span>
            <Layers size={18} color="var(--info)" />
          </div>
          <div className="card-value" style={{ fontSize: '1.5rem', textTransform: 'capitalize' }}>
            {loading ? '...' : overview?.top_category.replace('_', ' ').toLowerCase()}
          </div>
          <div className="card-subtext">Lead category by query count</div>
        </div>
      </div>

      {/* Two Columns: Category Breakdown & Recent DNS Activity */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Category Breakdown Card */}
        <div className="glass-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
            <h2 style={{ fontSize: '1.125rem', fontFamily: 'var(--font-display)', fontWeight: 600 }}>Category Distribution</h2>
            <button onClick={() => onNavigate('analytics')} className="btn btn-secondary btn-sm">
              Full Analytics <ArrowRight size={14} />
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {categories?.categories.slice(0, 5).map((cat) => (
              <div key={cat.category}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                  <span style={{ fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: cat.color }} />
                    {cat.label}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>
                    {cat.query_count} queries ({cat.percentage}%)
                  </span>
                </div>
                <div style={{ height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${cat.percentage}%`, background: cat.color, borderRadius: 3 }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Activity Card */}
        <div className="glass-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
            <h2 style={{ fontSize: '1.125rem', fontFamily: 'var(--font-display)', fontWeight: 600 }}>Recent Query Stream</h2>
            <button onClick={() => onNavigate('activity')} className="btn btn-secondary btn-sm">
              Inspect All <ArrowRight size={14} />
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
            {recentQueries.map((q) => (
              <div
                key={q.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.625rem 0.875rem',
                  background: 'rgba(15, 23, 42, 0.4)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.875rem',
                }}
              >
                <div style={{ minWidth: 0, flex: 1, marginRight: '1rem' }}>
                  <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {q.domain}
                  </div>
<div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {q.device_id || q.source_ip} • {localTime(q.occurred_at)}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className={`badge ${q.response_status === 'NOERROR' ? 'badge-success' : 'badge-warning'}`}>
                    {q.query_type}
                  </span>
                  {q.dns_visibility === 'PARTIAL' && (
                    <span className="badge badge-danger">PARTIAL</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
