import React, { useEffect, useState, useCallback } from 'react';
import {
  Download,
  Calendar,
  Clock,
  Layers,
  Smartphone,
  RefreshCw,
  FileSpreadsheet,
  FileCode,
} from 'lucide-react';
import { api } from '../services/api';
import { EthicalBanner } from '../components/EthicalBanner';
import type {
  AnalyticsOverview,
  CategoryDistributionItem,
  Device,
  HourlyActivityItem,
  TimelineItem,
} from '../types/api';

export const AnalyticsPage: React.FC = () => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Analytics states
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [categories, setCategories] = useState<CategoryDistributionItem[]>([]);
  const [hourly, setHourly] = useState<HourlyActivityItem[]>([]);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);

  const fetchDevices = async () => {
    try {
      const data = await api.getDevices();
      setDevices(data);
    } catch {
      // Non-blocking
    }
  };

  const fetchAnalytics = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    const devId = selectedDevice || undefined;

    try {
      const [ovData, catData, hrData, tlData] = await Promise.all([
        api.getAnalyticsOverview(devId),
        api.getCategoryDistribution(devId),
        api.getActiveHours(devId),
        api.getTimeline(14, devId),
      ]);

      setOverview(ovData);
      setCategories(catData.categories || []);
      setHourly(hrData.hourly_distribution || []);
      setTimeline(tlData.timeline || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load network analytics');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedDevice]);

  useEffect(() => {
    fetchDevices();
  }, []);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  const maxHourlyCount = Math.max(...hourly.map((h) => h.query_count), 1);
  const maxTimelineCount = Math.max(...timeline.map((t) => t.query_count), 1);

  const getExportUrl = (format: 'csv' | 'json') => {
    const params = new URLSearchParams();
    if (selectedDevice) params.set('device_id', selectedDevice);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return `/api/analytics/export/${format}${queryString}`;
  };

  return (
    <div className="analytics-page">
      {/* Mandatory Ethical Disclaimer */}
      <EthicalBanner />

      {/* Header Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.75rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Smartphone size={18} color="var(--primary-light)" />
          <select
            className="form-select"
            value={selectedDevice}
            onChange={(e) => setSelectedDevice(e.target.value)}
            style={{ width: '260px' }}
          >
            <option value="">All Network Devices</option>
            {devices.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                {d.friendly_name ? `${d.friendly_name} (${d.device_id})` : d.device_id}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <button
            onClick={() => fetchAnalytics(true)}
            disabled={refreshing}
            className="btn btn-secondary btn-sm"
          >
            <RefreshCw size={14} className={refreshing ? 'status-dot-pulse' : ''} />
            Refresh Data
          </button>
        </div>
      </div>

      {error && (
        <div className="glass-card" style={{ marginBottom: '1.5rem', borderColor: 'var(--danger)', color: '#f87171' }}>
          {error}
        </div>
      )}

      {/* Metric Cards */}
      <div className="stats-grid">
        <div className="glass-card">
          <div className="card-title">Network-Derived Queries</div>
          <div className="card-value">{overview ? overview.total_queries.toLocaleString() : '—'}</div>
          <div className="card-subtext">DNS lookup volume observed</div>
        </div>

        <div className="glass-card">
          <div className="card-title">Distinct Domains</div>
          <div className="card-value">{overview ? overview.distinct_domains.toLocaleString() : '—'}</div>
          <div className="card-subtext">Unique endpoints contacted</div>
        </div>

        <div className="glass-card">
          <div className="card-title">Active Devices</div>
          <div className="card-value">{overview ? overview.active_devices : '—'}</div>
          <div className="card-subtext">With observed DNS telemetry</div>
        </div>

        <div className="glass-card">
          <div className="card-title">Top Traffic Category</div>
          <div className="card-value" style={{ fontSize: '1.375rem', textTransform: 'capitalize' }}>
            {overview?.top_category ? overview.top_category.replace(/_/g, ' ') : 'None'}
          </div>
          <div className="card-subtext">Highest relative request share</div>
        </div>
      </div>

      {/* 24-Hour Activity Histogram */}
      <div className="glass-card" style={{ marginBottom: '1.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
          <Clock size={18} color="var(--primary-light)" />
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
            24-Hour Active Request Hours (00:00 - 23:00)
          </h2>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginBottom: '1.5rem' }}>
          Histogram of network request frequency aggregated by hour of day. Darker and taller bars indicate higher DNS query density.
        </p>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
            Loading hourly telemetry...
          </div>
        ) : (
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-end',
              height: '180px',
              gap: '6px',
              paddingTop: '20px',
              borderBottom: '1px solid var(--border-subtle)',
            }}
          >
            {hourly.map((item) => {
              const heightPercent = Math.max((item.query_count / maxHourlyCount) * 100, 4);
              const isPeak = item.query_count === maxHourlyCount && maxHourlyCount > 0;
              return (
                <div
                  key={item.hour}
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    height: '100%',
                    justifyContent: 'flex-end',
                    position: 'relative',
                  }}
                  title={`${item.hour.toString().padStart(2, '0')}:00 — ${item.query_count} queries`}
                >
                  <div
                    style={{
                      width: '100%',
                      height: `${heightPercent}%`,
                      background: isPeak
                        ? 'linear-gradient(180deg, #ec4899 0%, #8b5cf6 100%)'
                        : item.query_count > 0
                        ? 'linear-gradient(180deg, var(--primary) 0%, rgba(99, 102, 241, 0.4) 100%)'
                        : 'rgba(255, 255, 255, 0.05)',
                      borderRadius: '4px 4px 0 0',
                      transition: 'height 0.3s ease',
                    }}
                  />
                  <span
                    style={{
                      position: 'absolute',
                      bottom: '-24px',
                      fontSize: '0.6875rem',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-muted)',
                    }}
                  >
                    {item.hour % 3 === 0 ? `${item.hour}h` : ''}
                  </span>
                </div>
              );
            })}
          </div>
        )}
        <div style={{ height: '24px' }} />
      </div>

      {/* Grid: Category Breakdown + 14-Day Timeline */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '1.5rem', marginBottom: '1.75rem' }}>
        {/* Category Share */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
            <Layers size={18} color="var(--primary-light)" />
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
              Category Distribution
            </h2>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {categories.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                No category data available yet.
              </div>
            ) : (
              categories.map((cat) => (
                <div key={cat.category}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: '0.8125rem',
                      marginBottom: '0.375rem',
                    }}
                  >
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{cat.label}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      {cat.query_count} queries ({cat.percentage.toFixed(1)}%) • {cat.distinct_domains} domains
                    </span>
                  </div>
                  <div
                    style={{
                      height: '8px',
                      width: '100%',
                      background: 'rgba(255, 255, 255, 0.06)',
                      borderRadius: 'var(--radius-full)',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        height: '100%',
                        width: `${cat.percentage}%`,
                        background: cat.color || 'var(--primary)',
                        borderRadius: 'var(--radius-full)',
                      }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 14-Day Timeline */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
            <Calendar size={18} color="var(--primary-light)" />
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
              14-Day Activity Trend
            </h2>
          </div>

          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginBottom: '1.25rem' }}>
            Daily network query totals across observed devices.
          </p>

          <div
            style={{
              display: 'flex',
              alignItems: 'flex-end',
              height: '180px',
              gap: '8px',
              borderBottom: '1px solid var(--border-subtle)',
            }}
          >
            {timeline.map((day) => {
              const heightPercent = Math.max((day.query_count / maxTimelineCount) * 100, 4);
              return (
                <div
                  key={day.date}
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    height: '100%',
                    justifyContent: 'flex-end',
                    position: 'relative',
                  }}
                  title={`${day.date}: ${day.query_count} queries (${day.active_devices_count} active devices)`}
                >
                  <div
                    style={{
                      width: '100%',
                      height: `${heightPercent}%`,
                      background: 'linear-gradient(180deg, var(--info) 0%, rgba(14, 165, 233, 0.3) 100%)',
                      borderRadius: '4px 4px 0 0',
                    }}
                  />
                  <span
                    style={{
                      position: 'absolute',
                      bottom: '-22px',
                      fontSize: '0.625rem',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-muted)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {day.date.slice(5)}
                  </span>
                </div>
              );
            })}
          </div>
          <div style={{ height: '24px' }} />
        </div>
      </div>

      {/* Data Export & Audit Portability */}
      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <Download size={18} color="var(--primary-light)" />
              <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1rem', fontWeight: 600 }}>
                Data Portability & Export
              </h3>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
              Export sanitized telemetry with mandatory ethical disclaimers for offline inspection, privacy audits, or parent reviews.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <a
              href={getExportUrl('csv')}
              download
              className="btn btn-secondary btn-sm"
              target="_blank"
              rel="noreferrer"
            >
              <FileSpreadsheet size={16} /> Export CSV
            </a>
            <a
              href={getExportUrl('json')}
              download
              className="btn btn-secondary btn-sm"
              target="_blank"
              rel="noreferrer"
            >
              <FileCode size={16} /> Export JSON
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};
