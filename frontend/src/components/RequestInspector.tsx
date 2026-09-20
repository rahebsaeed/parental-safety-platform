import React, { useEffect, useState } from 'react';
import { X, Copy, Check, Globe, ShieldAlert } from 'lucide-react';
import { api } from '../services/api';
import type { DnsQuery, SafetyAlert } from '../types/api';

interface Props {
  record: DnsQuery | null;
  deviceLabel: (deviceId: string | null) => string;
  onClose: () => void;
}

/**
 * DNS-record inspector drawer.
 *
 * Shows the COMPLETE stored record for one observed lookup — and nothing
 * else. This platform captures DNS metadata only (domain, query type,
 * client IP, response, timestamp). There are no URLs, HTTP methods,
 * headers, bodies, or cookies to display, by architectural design
 * (no TLS interception, no payload collection) — the boundary note below
 * says so explicitly instead of faking those sections.
 */
const TYPE_DESCRIPTIONS: Record<string, string> = {
  A: 'IPv4 address lookup — the everyday "what IP is this name?" question.',
  AAAA: 'IPv6 address lookup.',
  HTTPS: 'HTTPS/SVCB service binding — may advertise HTTP/3 (h3) support via ALPN.',
  CNAME: 'Canonical-name alias — the answer is another domain name.',
  MX: 'Mail exchanger — the answer names the domain\u2019s mail server.',
  TXT: 'Free-form text record (SPF, verification tokens, …).',
  PTR: 'Reverse lookup — IP address back to hostname.',
  SRV: 'Service locator (chat, VoIP, game servers, …).',
  NS: 'Authoritative name servers for the zone.',
  SOA: 'Zone authority / serial record.',
};

const TAG_TOOLTIPS: Record<string, string> = {
  DoH: 'Query went to a known encrypted-DNS endpoint. The lookup is visible, but anything resolved through it afterwards is not.',
  VPN: 'First contact with commercial VPN infrastructure — tunneled traffic bypasses local observation.',
  Tor: 'Contact with Tor anonymity infrastructure — intentionally untraceable.',
  SafeSearch: 'Forced SafeSearch / Restricted-mode hostname — filtering enforced at the provider.',
};

export const RequestInspector: React.FC<Props> = ({ record, deviceLabel, onClose }) => {
  const [alerts, setAlerts] = useState<SafetyAlert[]>([]);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    if (!record) return;
    api
      .getAlerts({ domain: record.domain })
      .then(setAlerts)
      .catch(() => setAlerts([]));
  }, [record]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!record) return null;

  const copyText = async (key: string, text: string) => {
    const done = () => {
      setCopied(key);
      setTimeout(() => setCopied(null), 1500);
    };
    try {
      // Async clipboard needs a secure context — this dashboard is served
      // over plain LAN HTTP, so fall back to the classic textarea trick.
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        done();
        return;
      }
      throw new Error('async clipboard unavailable');
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        if (document.execCommand('copy')) {
          done();
        } else {
          setCopied(`${key}-failed`);
          setTimeout(() => setCopied(null), 1500);
        }
        document.body.removeChild(ta);
      } catch {
        setCopied(`${key}-failed`);
        setTimeout(() => setCopied(null), 1500);
      }
    }
  };

  const digCommand = `dig @192.168.1.20 ${record.domain} ${record.query_type}`;
  const recordJson = JSON.stringify(record, null, 2);

  const copyBtn = (key: string, label: string, text: string) => (
    <button
      key={key}
      onClick={() => copyText(key, text)}
      className="btn btn-secondary btn-sm"
      title={label}
    >
      {copied === key ? <Check size={13} /> : <Copy size={13} />}
      <span style={{ marginLeft: '0.375rem' }}>
        {copied === key ? 'Copied!' : copied === `${key}-failed` ? 'Copy failed — select manually' : label}
      </span>
    </button>
  );

  const row = (label: string, value: React.ReactNode) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', padding: '0.375rem 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '0.8125rem' }}>
      <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{label}</span>
      <span style={{ color: 'var(--text-primary)', textAlign: 'right', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(2, 6, 23, 0.7)', zIndex: 60 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(480px, 94vw)',
          background: 'var(--bg-card, #0f172a)', borderLeft: '1px solid var(--border-subtle)',
          overflowY: 'auto', padding: '1.5rem', zIndex: 61,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Globe size={18} color="var(--primary-light)" /> Request Inspector
          </h3>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
            <X size={20} />
          </button>
        </div>

        <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, marginBottom: '1rem', wordBreak: 'break-all' }}>
          {record.domain}
        </div>

        {row('Timestamp', new Date(record.occurred_at).toLocaleString())}
        {row('Device', record.device_name || deviceLabel(record.device_id))}
        {row('Client IP', <span style={{ fontFamily: 'var(--font-mono)' }}>{record.source_ip}</span>)}
        {row('Query type', <span className="badge badge-muted" style={{ fontFamily: 'var(--font-mono)' }}>{record.query_type}</span>)}
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '0.25rem 0 0.5rem' }}>
          {TYPE_DESCRIPTIONS[record.query_type] ?? 'DNS resource record lookup.'}
        </div>
        {row('Response', record.response_status)}
        {row('Answer', record.resolved_addresses ? <span style={{ fontFamily: 'var(--font-mono)' }}>{record.resolved_addresses}</span> : <span style={{ color: 'var(--text-muted)' }}>—</span>)}
        {row('Visibility', record.dns_visibility)}
        {row('Category', record.category ?? 'Unclassified')}

        {(record.tags?.length ?? 0) > 0 && (
          <div style={{ margin: '0.75rem 0' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.375rem' }}>Traffic tags</div>
            <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
              {(record.tags ?? []).map((t) => (
                <span key={t} className="badge badge-warning" title={TAG_TOOLTIPS[t] ?? t}>{t}</span>
              ))}
            </div>
          </div>
        )}

        <div style={{ fontSize: '0.8125rem', fontWeight: 600, margin: '1rem 0 0.5rem' }}>
          Related safety alerts ({alerts.length})
        </div>
        {alerts.length === 0 ? (
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>No alerts reference this domain.</div>
        ) : (
          alerts.slice(0, 5).map((a) => (
            <div key={a.id} style={{ fontSize: '0.8125rem', padding: '0.5rem', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', marginBottom: '0.5rem' }}>
              <span className="badge badge-danger" style={{ marginRight: '0.5rem' }}>{a.severity}</span>
              {a.title}
              <div style={{ color: 'var(--text-muted)', marginTop: '0.25rem' }}>{a.rule_matched} • seen {a.occurrence_count}×</div>
            </div>
          ))
        )}

        <div style={{ fontSize: '0.8125rem', fontWeight: 600, margin: '1rem 0 0.5rem' }}>Copy actions</div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {copyBtn('dig', 'Copy as dig', digCommand)}
          {copyBtn('json', 'Copy JSON', recordJson)}
          {copyBtn('domain', 'Copy domain', record.domain)}
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem', wordBreak: 'break-all' }}>
          {digCommand}
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', background: 'rgba(56, 189, 248, 0.08)', border: '1px solid rgba(56, 189, 248, 0.25)', borderRadius: 'var(--radius-md)', padding: '0.75rem', marginTop: '1rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
          <ShieldAlert size={14} style={{ flexShrink: 0, marginTop: '0.125rem' }} />
          <span>
            DNS-layer boundary: this platform never sees URLs, HTTP methods,
            headers, cookies, or bodies — those would require breaking TLS on
            your family&apos;s devices, which this system will not do. What you
            see above is the complete stored record.
          </span>
        </div>
      </div>
    </div>
  );
};
