import React, { useEffect, useState, useCallback } from 'react';
import {
  Search,
  Filter,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  ShieldAlert,
  Smartphone,
  Globe,
  Radio,
} from 'lucide-react';
import { api } from '../services/api';
import { useRealtime } from '../hooks/useRealtime';
import type { Device, DnsQuery, RealtimeEvent } from '../types/api';

export const ActivityPage: React.FC = () => {
  const [queryList, setQueries] = useState<DnsQuery[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters & Pagination
  const [searchDomain, setSearchDomain] = useState('');
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  const [selectedVisibility, setSelectedVisibility] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

  const fetchDevices = async () => {
    try {
      const data = await api.getDevices();
      setDevices(data);
    } catch {
      // Non-blocking device list fetch
    }
  };

  const fetchQueries = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await api.getActivity({
        domain: searchDomain.trim() || undefined,
        device_id: selectedDevice || undefined,
        visibility: selectedVisibility || undefined,
        status: selectedStatus || undefined,
        limit,
        offset,
      });
      setQueries(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch DNS activity');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [searchDomain, selectedDevice, selectedVisibility, selectedStatus, limit, offset]);

  useEffect(() => {
    fetchDevices();
  }, []);

  useEffect(() => {
    fetchQueries();
  }, [fetchQueries]);

  // Handle incoming live DNS query broadcast
  const handleRealtime = useCallback(
    (event: RealtimeEvent) => {
      if (event.type === 'dns_activity' && offset === 0) {
        const newQuery = event.data as DnsQuery;
        if (selectedDevice && newQuery.device_id !== selectedDevice) return;
        if (searchDomain && !newQuery.domain.toLowerCase().includes(searchDomain.toLowerCase())) return;
        if (selectedVisibility && newQuery.dns_visibility !== selectedVisibility) return;
        if (selectedStatus && newQuery.response_status !== selectedStatus) return;

        setQueries((prev) => [newQuery, ...(Array.isArray(prev) ? prev.slice(0, limit - 1) : [])]);
      }
    },
    [offset, selectedDevice, searchDomain, selectedVisibility, selectedStatus, limit]
  );

  useRealtime({ onEvent: handleRealtime });

  const handleNextPage = () => {
    if (queryList.length === limit) {
      setOffset((prev) => prev + limit);
    }
  };

  const handlePrevPage = () => {
    setOffset((prev) => Math.max(0, prev - limit));
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setOffset(0);
    fetchQueries();
  };

  const getDeviceLabel = (deviceId: string | null) => {
    if (!deviceId) return 'Unassigned';
    const match = devices.find((d) => d.device_id === deviceId);
    return match?.friendly_name || deviceId;
  };

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case 'NOERROR':
        return <span className="badge badge-success">NOERROR</span>;
      case 'NXDOMAIN':
        return <span className="badge badge-warning">NXDOMAIN</span>;
      case 'SERVFAIL':
      case 'REFUSED':
        return <span className="badge badge-danger">{status}</span>;
      default:
        return <span className="badge badge-muted">{status}</span>;
    }
  };

  const getVisibilityBadge = (visibility: string) => {
    if (visibility === 'FULL') {
      return (
        <span className="badge badge-success" title="Attributed to specific device with MAC/IP mapping">
          <ShieldCheck size={12} /> FULL
        </span>
      );
    }
    return (
      <span className="badge badge-warning" title="Attributed via forwarder/gateway without direct client MAC">
        <ShieldAlert size={12} /> PARTIAL
      </span>
    );
  };

  return (
    <div className="activity-page">
      {/* Controls / Filter Bar */}
      <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
            {/* Search Input */}
            <div style={{ position: 'relative', flex: '1 1 280px' }}>
              <Search
                size={16}
                style={{
                  position: 'absolute',
                  left: '0.875rem',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)',
                }}
              />
              <input
                type="text"
                placeholder="Search domain (e.g. youtube, google, adult)..."
                value={searchDomain}
                onChange={(e) => setSearchDomain(e.target.value)}
                className="form-input"
                style={{ paddingLeft: '2.5rem' }}
              />
            </div>

            {/* Device Filter */}
            <div style={{ flex: '1 1 180px' }}>
              <select
                className="form-select"
                value={selectedDevice}
                onChange={(e) => {
                  setSelectedDevice(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">All Devices ({devices.length})</option>
                {devices.map((d) => (
                  <option key={d.device_id} value={d.device_id}>
                    {d.friendly_name ? `${d.friendly_name} (${d.device_id})` : d.device_id}
                  </option>
                ))}
              </select>
            </div>

            {/* Visibility Filter */}
            <div style={{ flex: '1 1 140px' }}>
              <select
                className="form-select"
                value={selectedVisibility}
                onChange={(e) => {
                  setSelectedVisibility(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">All Visibility</option>
                <option value="FULL">FULL (Direct MAC)</option>
                <option value="PARTIAL">PARTIAL (Relayed)</option>
              </select>
            </div>

            {/* Response Status Filter */}
            <div style={{ flex: '1 1 130px' }}>
              <select
                className="form-select"
                value={selectedStatus}
                onChange={(e) => {
                  setSelectedStatus(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">All Statuses</option>
                <option value="NOERROR">NOERROR</option>
                <option value="NXDOMAIN">NXDOMAIN</option>
                <option value="SERVFAIL">SERVFAIL</option>
              </select>
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="submit" className="btn btn-primary btn-sm">
                <Filter size={14} /> Filter
              </button>
              <button
                type="button"
                onClick={() => fetchQueries(true)}
                disabled={refreshing}
                className="btn btn-secondary btn-sm"
              >
                <RefreshCw size={14} className={refreshing ? 'status-dot-pulse' : ''} />
                Refresh
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Query Results Table */}
      {error && (
        <div className="glass-card" style={{ marginBottom: '1.5rem', borderColor: 'var(--danger)', color: '#f87171' }}>
          {error}
        </div>
      )}

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Device</th>
              <th>Source IP</th>
              <th>Domain</th>
              <th>Type</th>
              <th>Status</th>
              <th>Visibility</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                  Loading DNS query activity...
                </td>
              </tr>
            ) : queryList.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                  <Radio size={32} style={{ marginBottom: '0.75rem', opacity: 0.5 }} />
                  <div>No DNS queries matching current criteria.</div>
                </td>
              </tr>
            ) : (
              queryList.map((q) => (
                <tr key={q.id}>
                  <td style={{ whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>
                    {new Date(q.occurred_at).toLocaleString()}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <Smartphone size={14} color="var(--primary-light)" />
                      <span style={{ fontWeight: 600 }}>{getDeviceLabel(q.device_id)}</span>
                    </div>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                    {q.source_ip}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <Globe size={14} color="var(--text-muted)" />
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{q.domain}</span>
                    </div>
                  </td>
                  <td>
                    <span className="badge badge-muted" style={{ fontFamily: 'var(--font-mono)' }}>
                      {q.query_type}
                    </span>
                  </td>
                  <td>{getStatusBadge(q.response_status)}</td>
                  <td>{getVisibilityBadge(q.dns_visibility)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginTop: '1.25rem',
          color: 'var(--text-secondary)',
          fontSize: '0.875rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span>Rows per page:</span>
          <select
            className="form-select"
            value={limit}
            onChange={(e) => {
              setLimit(Number(e.target.value));
              setOffset(0);
            }}
            style={{ width: '80px', padding: '0.25rem 0.5rem' }}
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
          <span>
            Showing queryList {offset + 1} - {offset + queryList.length}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={handlePrevPage}
            disabled={offset === 0 || loading}
            className="btn btn-secondary btn-sm"
          >
            <ChevronLeft size={16} /> Previous
          </button>
          <button
            onClick={handleNextPage}
            disabled={queryList.length < limit || loading}
            className="btn btn-secondary btn-sm"
          >
            Next <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};
