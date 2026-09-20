import React, { useCallback, useEffect, useState } from 'react';
import { Search, Filter, RefreshCw, ChevronLeft, ChevronRight, Globe, X, Copy, Check } from 'lucide-react';
import { api } from '../services/api';
import type { Device, ProxyRequestItem } from '../types/api';

const METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'];

export const WebActivityPage: React.FC = () => {
  const [rows, setRows] = useState<ProxyRequestItem[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchDomain, setSearchDomain] = useState('');
  const [selectedDevice, setSelectedDevice] = useState('');
  const [selectedMethod, setSelectedMethod] = useState('');
  const [hideLocal, setHideLocal] = useState(true);
  const [showSetup, setShowSetup] = useState(false);
  const [inspected, setInspected] = useState<ProxyRequestItem | null>(null);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [coverage, setCoverage] = useState<{ device_id: string; device_name: string; dns_queries: number; proxy_requests: number; has_proxy: boolean }[]>([]);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [data, cov, devs] = await Promise.all([
        api.getProxyRequests({
          domain: searchDomain.trim() || undefined,
          device_id: selectedDevice || undefined,
          method: selectedMethod || undefined,
          hide_local: hideLocal,
          limit,
          offset,
        }),
        api.getProxyCoverage().catch(() => ({ devices: [] as typeof coverage })),
        api.getDevices().catch(() => [] as Device[]),
      ]);
      setRows(data.items);
      setTotal(data.total);
      setDevices(devs);
      setCoverage(cov.devices ?? []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [searchDomain, selectedDevice, selectedMethod, hideLocal, limit, offset]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const deviceLabel = (r: ProxyRequestItem) =>
    r.device_name || devices.find((d) => d.device_id === r.device_id)?.friendly_name || r.device_id || r.client_ip;

  return (
    <div>
      <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Globe size={18} color="var(--primary-light)" />
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>Web Requests</h2>
          </div>
          <button onClick={() => setShowSetup((v) => !v)} className="btn btn-secondary btn-sm">
            {showSetup ? 'Hide setup guide' : 'Proxy setup guide'}
          </button>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginBottom: showSetup ? '1rem' : 0 }}>
          Full request content (method, URL, search keywords, page titles) — only from devices
          whose Wi-Fi proxy points here <span style={{ fontFamily: 'var(--font-mono)' }}>192.168.1.20:8080</span> and
          trust the parental CA. Everyone else stays DNS-only in the Activity Log.
        </p>
        {showSetup && <SetupGuide />}

        {coverage.length > 0 && (
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: showSetup ? '1rem' : '0.75rem' }}>
            {coverage
              .filter((c) => c.dns_queries > 0)
              .map((c) => (
                <span
                  key={c.device_id}
                  className={`badge ${c.has_proxy ? 'badge-success' : 'badge-warning'}`}
                  title={
                    c.has_proxy
                      ? `${c.proxy_requests} proxied requests in 7 days — keywords visible`
                      : `DNS-only — no proxy traffic in 7 days. Enroll this device (setup guide) to see searches.`
                  }
                  style={{ fontSize: '0.75rem', padding: '0.375rem 0.625rem' }}
                >
                  {c.device_name}: {c.has_proxy ? 'Supervised' : 'DNS-only'}
                </span>
              ))}
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            setOffset(0);
            fetchAll();
          }}
          style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center', marginTop: '1rem' }}
        >
          <input
            type="text"
            placeholder="Filter by host (e.g. google, youtube)..."
            value={searchDomain}
            onChange={(e) => setSearchDomain(e.target.value)}
            className="form-input"
            style={{ flex: '1 1 220px' }}
          />
          <select className="form-select" value={selectedDevice} onChange={(e) => { setSelectedDevice(e.target.value); setOffset(0); }} style={{ flex: '1 1 160px' }}>
            <option value="">All Devices</option>
            {devices.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                {d.friendly_name ? `${d.friendly_name} (${d.device_id})` : d.device_id}
              </option>
            ))}
          </select>
          <select className="form-select" value={selectedMethod} onChange={(e) => { setSelectedMethod(e.target.value); setOffset(0); }} style={{ width: '130px' }}>
            <option value="">All Methods</option>
            {METHODS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <button type="submit" className="btn btn-primary btn-sm"><Filter size={14} /> Filter</button>
          <button type="button" onClick={() => fetchAll()} className="btn btn-secondary btn-sm"><RefreshCw size={14} /> Refresh</button>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.8125rem', color: 'var(--text-secondary)', cursor: 'pointer' }} title="Hide router (.1.1), this PC (.20) and loopback destinations">
            <input type="checkbox" checked={hideLocal} onChange={(e) => { setHideLocal(e.target.checked); setOffset(0); }} />
            Hide local network
          </label>
        </form>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Device</th>
              <th>Method</th>
              <th>URL</th>
              <th>Status</th>
              <th>Title</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Loading web requests…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                <div>No proxied requests yet.</div>
                <div style={{ fontSize: '0.8125rem', marginTop: '0.5rem' }}>Point a device&apos;s Wi-Fi proxy at 192.168.1.20:8080 (see setup guide) and browse.</div>
              </td></tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} onClick={() => setInspected(r)} style={{ cursor: 'pointer' }} title="Click to inspect">
                  <td style={{ whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>{new Date(r.occurred_at).toLocaleString()}</td>
                  <td style={{ fontWeight: 600 }}>{deviceLabel(r)}</td>
                  <td><span className={`badge ${r.method === 'GET' ? 'badge-success' : 'badge-warning'}`}>{r.method}</span></td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', maxWidth: '420px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.full_url}</td>
                  <td>{r.status_code == null ? <span className="badge badge-muted">—</span> : <span className={`badge ${r.status_code < 400 ? 'badge-success' : 'badge-danger'}`}>{r.status_code}</span>}</td>
                  <td style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', maxWidth: '260px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.page_title || '—'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.25rem', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
        <span>Showing {offset + 1} - {offset + rows.length} of {total}</span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset === 0} className="btn btn-secondary btn-sm"><ChevronLeft size={16} /> Previous</button>
          <button onClick={() => { if (rows.length >= limit) setOffset(offset + limit); }} disabled={rows.length < limit} className="btn btn-secondary btn-sm">Next <ChevronRight size={16} /></button>
        </div>
      </div>

      {inspected && <WebInspector record={inspected} deviceName={deviceLabel(inspected)} onClose={() => setInspected(null)} />}
    </div>
  );
};

const SetupGuide: React.FC = () => (
  <div style={{ background: 'rgba(15, 23, 42, 0.5)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '1rem', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
    <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Per-device setup (2 minutes each, one time only)</div>
    <ol style={{ margin: 0, paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
      <li>On the child&apos;s device, open <span style={{ fontFamily: 'var(--font-mono)' }}>http://192.168.1.20/api/proxy/ca.pem</span> and install the certificate:
        Android → Settings → Security → Install certificate (CA); iPhone → download, then Settings → General → VPN &amp; Device Management → install, then enable full trust under About → Certificate Trust Settings; Windows → double-click → Install Certificate → Trusted Root store.</li>
      <li>Wi-Fi settings → this network → Proxy → Manual → hostname <span style={{ fontFamily: 'var(--font-mono)' }}>192.168.1.20</span>, port <span style={{ fontFamily: 'var(--font-mono)' }}>8080</span>.</li>
      <li>Browse once — requests appear here. Banking/Apple traffic always passes through untouched.</li>
    </ol>
    <div style={{ marginTop: '0.5rem' }}>
      <a href="/api/proxy/ca.pem" download className="btn btn-secondary btn-sm">Download CA certificate</a>
    </div>
  </div>
);

const WebInspector: React.FC<{ record: ProxyRequestItem; deviceName: string; onClose: () => void }> = ({ record, deviceName, onClose }) => {
  const [copied, setCopied] = useState<string | null>(null);

  const copyText = async (key: string, text: string) => {
    const done = () => {
      setCopied(key);
      setTimeout(() => setCopied(null), 1500);
    };
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        done();
        return;
      }
      throw new Error('fallback');
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy') && done();
        document.body.removeChild(ta);
      } catch {
        /* clipboard unavailable */
      }
    }
  };

  const curlCmd = `curl -X ${record.method} ${JSON.stringify(record.full_url)}${record.user_agent ? ` -H ${JSON.stringify(`User-Agent: ${record.user_agent}`)}` : ''}`;
  const recordJson = JSON.stringify(record, null, 2);

  const row = (label: string, value: React.ReactNode) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', padding: '0.375rem 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '0.8125rem' }}>
      <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{label}</span>
      <span style={{ color: 'var(--text-primary)', textAlign: 'right', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(2, 6, 23, 0.7)', zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(520px, 94vw)', background: 'var(--bg-card, #0f172a)', borderLeft: '1px solid var(--border-subtle)', overflowY: 'auto', padding: '1.5rem', zIndex: 61 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: 700 }}>Web Request</h3>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}><X size={20} /></button>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, marginBottom: '1rem', wordBreak: 'break-all' }}>
          <span className={`badge ${record.method === 'GET' ? 'badge-success' : 'badge-warning'}`} style={{ marginRight: '0.5rem' }}>{record.method}</span>
          {record.full_url}
        </div>
        {row('Timestamp', new Date(record.occurred_at).toLocaleString())}
        {row('Device', deviceName)}
        {row('Client IP', record.client_ip)}
        {row('Status', record.status_code ?? '— (connection failed)')}
        {row('Page title', record.page_title || '—')}
        {row('User-Agent', record.user_agent || '—')}
        {row('Referer', record.referer || '—')}
        {row('Request', `${record.req_content_type || '—'} • ${record.req_size} bytes`)}
        {row('Response', `${record.resp_content_type || '—'} • ${record.resp_size} bytes`)}
        <div style={{ fontSize: '0.8125rem', fontWeight: 600, margin: '1rem 0 0.5rem' }}>Copy actions</div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {([['curl', 'Copy as cURL', curlCmd], ['json', 'Copy JSON', recordJson], ['url', 'Copy URL', record.full_url]] as const).map(([key, label, text]) => (
            <button key={key} onClick={() => copyText(key, text)} className="btn btn-secondary btn-sm">
              {copied === key ? <Check size={13} /> : <Copy size={13} />}
              <span style={{ marginLeft: '0.375rem' }}>{copied === key ? 'Copied!' : label}</span>
            </button>
          ))}
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '1rem' }}>
          Bodies, cookies and authorization headers are never stored — only the metadata above, page titles, and search keywords.
        </div>
      </div>
    </div>
  );
};
