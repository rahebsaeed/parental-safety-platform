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
  Shield,
  AlertTriangle,
  CheckCircle,
  Eye,
  Search,
} from 'lucide-react';
import { api } from '../services/api';
import { EthicalBanner } from '../components/EthicalBanner';
import type {
  AnalyticsOverview,
  CategoryDistributionItem,
  Device,
  HourlyActivityItem,
  ProxySearchItem,
  SearchEnginesResponse,
  TimelineItem,
  DomainSecurityResponse,
  DangerousDomain,
  SubjectResponse,
} from '../types/api';

const toLocalDateStr = (d: Date): string => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

/** Default time frame: the last day (yesterday → today). Cleared = all time. */
const defaultStartDate = (): string => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return toLocalDateStr(d);
};

const defaultEndDate = (): string => toLocalDateStr(new Date());

interface Props {
  onInspectDomain?: (domain: string) => void;
}

export const AnalyticsPage: React.FC<Props> = ({ onInspectDomain }) => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  const [startDate, setStartDate] = useState<string>(defaultStartDate);
  const [endDate, setEndDate] = useState<string>(defaultEndDate);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'security' | 'search'>('overview');

  // Analytics states
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [categories, setCategories] = useState<CategoryDistributionItem[]>([]);
  const [hourly, setHourly] = useState<HourlyActivityItem[]>([]);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [analyticsTopDomainList, setTopDomains] = useState<{ domain: string; query_count: number }[]>([]);

  // Domain security states
  const [domainSecurity, setDomainSecurity] = useState<DomainSecurityResponse | null>(null);
  const [dangerousDomains, setDangerousDomains] = useState<DangerousDomain[]>([]);
  const [subjects, setSubjects] = useState<SubjectResponse | null>(null);
  const [aiReady, setAiReady] = useState<boolean | null>(null);

  // Search activity states (per-device search-engine visits)
  const [searchData, setSearchData] = useState<SearchEnginesResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  // Exact typed keywords — only exists for devices on the web proxy
  const [proxySearches, setProxySearches] = useState<ProxySearchItem[]>([]);

  // Day-bounded range: a bare "YYYY-MM-DD" end would exclude that whole day
  // under lexicographic ISO comparison, so pin to full local days.
  const startTime = startDate ? `${startDate}T00:00:00` : undefined;
  const endTime = endDate ? `${endDate}T23:59:59` : undefined;

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
      const [ovData, catData, hrData, tlData, analyticsTopDomainListData] = await Promise.all([
        api.getAnalyticsOverview(devId, startTime, endTime),
        api.getCategoryDistribution(devId, startTime, endTime),
        api.getActiveHours(devId, startTime, endTime),
        api.getTimeline(14, devId, startTime, endTime),
        api.getTopDomains(devId, 10, startTime, endTime),
      ]);

      setOverview(ovData);
      setCategories(catData.categories || []);
      setHourly(hrData.hourly_distribution || []);
      setTimeline(tlData.timeline || []);
      setTopDomains(analyticsTopDomainListData.domains || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load network analytics');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedDevice, startTime, endTime]);

  const fetchDomainSecurity = useCallback(async () => {
    const devId = selectedDevice || undefined;
    try {
      const [secData, dangerData, subjData] = await Promise.all([
        api.getDomainSecurity(devId, 15, startTime, endTime),
        api.getDangerousDomains(devId, startTime, endTime),
        api.getSubjects(devId, startTime, endTime),
      ]);
      setDomainSecurity(secData);
      setDangerousDomains(dangerData.domains || []);
      setSubjects(subjData);
    } catch {
      // Non-blocking
    }
  }, [selectedDevice, startTime, endTime]);

  const fetchAiStatus = useCallback(async () => {
    try {
      const data = await api.getOpenRouterApiKeyStatus();
      setAiReady(data.configured);
    } catch {
      setAiReady(null);
    }
  }, []);

  useEffect(() => {
    fetchDevices();
  }, []);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  useEffect(() => {
    if (activeTab === 'security') {
      fetchDomainSecurity();
      fetchAiStatus();
    }
  }, [activeTab, fetchDomainSecurity, fetchAiStatus]);

  const fetchSearchEngines = useCallback(async () => {
    if (!selectedDevice) {
      setSearchData(null);
      setProxySearches([]);
      return;
    }
    setSearchLoading(true);
    try {
      const [engines, keywords] = await Promise.all([
        api.getSearchEngines(selectedDevice, 7),
        api.getProxySearches(selectedDevice, 30).catch(() => [] as ProxySearchItem[]),
      ]);
      setSearchData(engines);
      setProxySearches(keywords);
    } catch {
      setSearchData(null);
      setProxySearches([]);
    } finally {
      setSearchLoading(false);
    }
  }, [selectedDevice]);

  useEffect(() => {
    if (activeTab === 'search') {
      fetchSearchEngines();
    }
  }, [activeTab, fetchSearchEngines]);

  const maxHourlyCount = Math.max(...hourly.map((h) => h.query_count), 1);
  const maxTimelineCount = Math.max(...timeline.map((t) => t.query_count), 1);

  const getExportUrl = (format: 'csv' | 'json') => {
    const params = new URLSearchParams();
    if (selectedDevice) params.set('device_id', selectedDevice);
    if (startTime) params.set('start_time', startTime);
    if (endTime) params.set('end_time', endTime);
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
          <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            From
            <input
              type="date"
              className="form-select"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={{ width: '140px', marginLeft: '4px' }}
            />
          </label>
          <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            To
            <input
              type="date"
              className="form-select"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={{ width: '140px', marginLeft: '4px' }}
            />
          </label>
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

      {/* Tab toggle */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <button
          onClick={() => setActiveTab('overview')}
          className={`btn btn-sm ${activeTab === 'overview' ? 'btn-primary' : 'btn-secondary'}`}
        >
          <Layers size={14} /> Overview
        </button>
        <button
          onClick={() => setActiveTab('security')}
          className={`btn btn-sm ${activeTab === 'security' ? 'btn-primary' : 'btn-secondary'}`}
        >
          <Shield size={14} /> Domain Security
          {aiReady === true ? (
            <span className="badge badge-success" style={{ marginLeft: 6 }}>AI on</span>
          ) : aiReady === false ? (
            <span className="badge badge-warning" style={{ marginLeft: 6 }}>AI off</span>
          ) : null}
        </button>
        <button
          onClick={() => setActiveTab('search')}
          className={`btn btn-sm ${activeTab === 'search' ? 'btn-primary' : 'btn-secondary'}`}
          title="Which search engines each device used (keywords are not visible at DNS layer)"
        >
          <Search size={14} /> Search Activity
        </button>
      </div>

      {activeTab === 'overview' && (
      <>
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

      {/* Top Domains in Overview */}
      {activeTab === 'overview' && analyticsTopDomainList.length > 0 && (
        <div className="glass-card" style={{ marginBottom: '1.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
            <Eye size={18} color="var(--primary-light)" />
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
              Most Visited Domains
            </h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            {analyticsTopDomainList.slice(0, 10).map((d, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--border-subtle)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', width: '24px' }}>#{i + 1}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>{d.domain}</span>
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>{d.query_count} queries</span>
              </div>
            ))}
          </div>
        </div>
      )}

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
      </>
      )}

      {activeTab === 'security' && (
      <>
      {/* AI status banner — this is how you know the AI is working */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Shield size={18} color="var(--primary-light)" />
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
            AI Categorization
          </h2>
          {aiReady === true ? (
            <span className="badge badge-success">ON</span>
          ) : aiReady === false ? (
            <span className="badge badge-warning">OFF</span>
          ) : (
            <span className="badge badge-muted">checking…</span>
          )}
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginTop: '0.5rem', marginBottom: 0 }}>
          {aiReady === true
            ? 'OpenRouter key is saved — unknown domains below were classified by the AI model.'
            : aiReady === false
            ? 'No OpenRouter key saved — unknown domains stay uncategorized. Add one in Settings → OpenRouter AI Category Engine, then press Test.'
            : 'Checking whether an OpenRouter key is configured…'}
        </p>
      </div>

      {/* Security summary */}
      <div className="stats-grid">
        <div className="glass-card">
          <div className="card-title">Domains Seen</div>
          <div className="card-value">{domainSecurity ? domainSecurity.total_domains.toLocaleString() : '—'}</div>
          <div className="card-subtext">In selected time frame</div>
        </div>

        <div className="glass-card">
          <div className="card-title">Safe</div>
          <div className="card-value" style={{ color: '#4caf50' }}>{domainSecurity ? domainSecurity.summary.safe : '—'}</div>
          <div className="card-subtext"><CheckCircle size={14} /> Benign endpoints</div>
        </div>

        <div className="glass-card">
          <div className="card-title">Risky</div>
          <div className="card-value" style={{ color: '#ff9800' }}>{domainSecurity ? domainSecurity.summary.risky : '—'}</div>
          <div className="card-subtext"><AlertTriangle size={14} /> Review recommended</div>
        </div>

        <div className="glass-card">
          <div className="card-title">Dangerous</div>
          <div className="card-value" style={{ color: '#f44336' }}>{domainSecurity ? domainSecurity.summary.dangerous : '—'}</div>
          <div className="card-subtext"><AlertTriangle size={14} /> Block / discuss</div>
        </div>
      </div>

      {/* Flagged domains */}
      <div className="glass-card" style={{ marginBottom: '1.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
          <AlertTriangle size={18} color="#ff9800" />
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
            Flagged Domains{dangerousDomains.length > 0 ? ` (${dangerousDomains.length})` : ''}
          </h2>
        </div>

        {dangerousDomains.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
            No risky or dangerous domains in this time frame.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {dangerousDomains.map((d) => (
              <div
                key={d.domain}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  gap: '1rem', padding: '0.625rem 0.875rem',
                  background: 'rgba(15, 23, 42, 0.4)', borderRadius: 'var(--radius-md)',
                  fontSize: '0.8125rem',
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {d.domain}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {d.subject} • {d.reason}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', whiteSpace: 'nowrap' }}>
                  <span className="badge" style={{ background: `${d.security_color}22`, color: d.security_color }}>
                    {d.security_label}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{d.query_count}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Subjects */}
      <div className="glass-card" style={{ marginBottom: '1.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
          <Search size={18} color="var(--primary-light)" />
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
            What They Are Exploring
          </h2>
        </div>

        {!subjects || subjects.subjects.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
            No subject data in this time frame.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {subjects.subjects.map((s) => (
              <div key={s.subject}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8125rem', marginBottom: '0.375rem' }}>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{s.subject}</span>
                  <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                    {s.query_count.toLocaleString()} queries
                  </span>
                </div>
                <div style={{ height: '8px', width: '100%', background: 'rgba(255, 255, 255, 0.06)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${subjects.total_queries > 0 ? (s.query_count / subjects.total_queries) * 100 : 0}%`,
                      background: 'var(--primary)',
                      borderRadius: 'var(--radius-full)',
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Top domains by security level */}
      <div className="glass-card" style={{ marginBottom: '1.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
          <Eye size={18} color="var(--primary-light)" />
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
            Top Domains by Security Level
          </h2>
        </div>

        {!domainSecurity || domainSecurity.domains.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
            No domain data in this time frame.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            {domainSecurity.domains.slice(0, 15).map((d, i) => (
              <div key={d.domain} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--border-subtle)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', width: '24px' }}>#{i + 1}</span>
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: d.security_color, flexShrink: 0 }} />
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {d.domain}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', whiteSpace: 'nowrap' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{d.subject}</span>
                  <span className="badge" style={{ background: `${d.security_color}22`, color: d.security_color }}>
                    {d.security_label}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>{d.query_count}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      </>
      )}

      {activeTab === 'search' && (
      <>
      {/* Search Activity — per-device search-engine visits */}
      <div className="glass-card" style={{ marginBottom: '1.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <Search size={18} color="var(--primary-light)" />
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
            Search Activity{selectedDevice ? ` — ${devices.find((d) => d.device_id === selectedDevice)?.friendly_name || selectedDevice}` : ''}
          </h2>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginBottom: '1rem' }}>
          Which search engines this device used, and when. DNS lookups carry
          hostnames only — never the typed keywords — so search terms stay
          private by design; what you see is engine usage over time.
        </p>

        {/* Exact typed keywords — web-proxy devices only */}
        <div style={{ background: 'rgba(15, 23, 42, 0.4)', borderRadius: 'var(--radius-md)', padding: '0.75rem 0.875rem', marginBottom: '1rem' }}>
          <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.5rem' }}>
            Typed search keywords {proxySearches.length > 0 ? `(${proxySearches.length})` : ''}
          </div>
          {proxySearches.length === 0 ? (
            <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              No keywords captured — this device is not on the web proxy yet.
              Open the <strong>Web Requests</strong> tab and follow the 2-minute proxy setup guide.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {proxySearches.slice(0, 30).map((s) => (
                <div key={s.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', padding: '0.375rem 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '0.8125rem' }}>
                  <div style={{ minWidth: 0 }}>
                    <span className="badge badge-info" style={{ marginRight: '0.5rem' }}>{s.engine}</span>
                    <strong>{s.keywords}</strong>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', whiteSpace: 'nowrap' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{new Date(s.occurred_at).toLocaleString()}</span>
                    {onInspectDomain && (
                      <button onClick={() => onInspectDomain(new URL(s.full_url).hostname)} className="btn btn-secondary btn-sm" title="Open in Activity log">
                        Inspect
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {!selectedDevice ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
            Select a child&apos;s device above to see its search-engine activity.
          </div>
        ) : searchLoading ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
            Loading search activity…
          </div>
        ) : !searchData || searchData.engines.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
            No search-engine visits in the last 7 days for this device.
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.25rem' }}>
              {searchData.engines.map((e) => (
                <div key={e.engine} style={{ background: 'rgba(15, 23, 42, 0.4)', borderRadius: 'var(--radius-md)', padding: '0.625rem 0.875rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <span className="badge badge-info" style={{ fontSize: '0.8125rem', padding: '0.375rem 0.75rem' }}>
                      {e.label} • {e.visits} visit{e.visits === 1 ? '' : 's'}
                    </span>
                    {(e.opened_next ?? []).length > 0 && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>then opened:</span>
                    )}
                    {(e.opened_next ?? []).map((n) => (
                      <button
                        key={n.domain}
                        onClick={() => onInspectDomain && onInspectDomain(n.domain)}
                        className="btn btn-secondary btn-sm"
                        title={`Opened after searching on ${e.label} — click to inspect in Activity`}
                        style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}
                      >
                        {n.domain}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {searchData.visits.map((v, i) => (
                <div key={`${v.occurred_at}-${v.domain}-${i}`} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--border-subtle)', gap: '1rem',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
                    <span className="badge badge-muted">{v.label}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {v.domain}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', whiteSpace: 'nowrap' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {new Date(v.occurred_at).toLocaleString()}
                    </span>
                    {onInspectDomain && (
                      <button
                        onClick={() => onInspectDomain(v.domain)}
                        className="btn btn-secondary btn-sm"
                        title="Open these lookups in the Activity log"
                      >
                        Inspect
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
      </>
      )}

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
