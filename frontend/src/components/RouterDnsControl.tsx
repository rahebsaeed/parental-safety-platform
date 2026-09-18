import React, { useCallback, useEffect, useState } from 'react';
import { ShieldCheck, ShieldAlert, HelpCircle, ArrowLeftRight } from 'lucide-react';
import { api } from '../services/api';
import type { RouterDnsStatus } from '../types/api';

const POLL_INTERVAL_MS = 30000;

/**
 * Router DNS badge + manual switch, shown in the app header.
 *
 * MANUAL-ONLY model: no boot/suspend/shutdown/WiFi automation changes the
 * router — only this button (POST /api/router-dns/mode). Enabling filtered
 * DNS starts a failsafe deadline (default 3h); the revert timer flips the
 * router back to default automatically. The badge always reflects the
 * router's *actual* reported DNS (polled every 30s) plus the countdown.
 */
export const RouterDnsControl: React.FC = () => {
  const [status, setStatus] = useState<RouterDnsStatus | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getRouterDnsStatus();
      setStatus(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Router unreachable');
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const handleSwitch = async (extend = false) => {
    if (!status || switching) return;
    // Extend = re-enable filtered DNS to restart the failsafe clock.
    const target = extend ? 'dnsmasq' : status.mode === 'dnsmasq' ? 'router' : 'dnsmasq';
    const confirmMsg =
      target === 'dnsmasq'
        ? `Route the whole LAN through this PC for filtering (auto-reverts to Router DNS after ~${status.max_hours ?? 3}h)?`
        : 'Fall back to Router DNS now (unfiltered)?';
    if (!window.confirm(confirmMsg)) return;
    setSwitching(true);
    setError(null);
    try {
      const data = await api.setRouterDnsMode(target);
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Switch failed');
    } finally {
      setSwitching(false);
    }
  };

  const formatRemaining = (secs: number | null | undefined): string | null => {
    if (secs === null || secs === undefined) return null;
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    if (h > 0) return `${h}h ${m}m left`;
    if (m > 0) return `${m}m left`;
    return `<1m left`;
  };

  const mode = status?.mode ?? 'unknown';
  const isDnsmasq = mode === 'dnsmasq';
  const isRouter = mode === 'router';

  const Icon = isDnsmasq ? ShieldCheck : isRouter ? ShieldAlert : HelpCircle;
  const iconColor = isDnsmasq ? '#4caf50' : isRouter ? '#ff9800' : 'var(--text-muted)';
  const label = isDnsmasq
    ? `DNS: rosa-PC (${status?.pridns})`
    : isRouter
    ? `DNS: Router (${status?.pridns})`
    : 'DNS: ?';

  const remaining = formatRemaining(status?.seconds_remaining);
  const tooltip = isDnsmasq
    ? `Router points at this PC — filtered + logged. Auto-reverts to Router DNS ${remaining ? `in ${remaining}` : `after ~${status?.max_hours ?? 3}h`} if you forget. Click to fall back now.`
    : isRouter
    ? `Router points at itself — UNFILTERED. Click to filter through this PC (auto-reverts after ~${status?.max_hours ?? 3}h).`
    : 'Could not read router DNS. Check the router is reachable, then retry.';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <div
        className="header-status-badge"
        style={{
          backgroundColor: isDnsmasq
            ? 'rgba(76, 175, 80, 0.15)'
            : isRouter
            ? 'rgba(255, 152, 0, 0.15)'
            : 'rgba(255, 255, 255, 0.05)',
          borderColor: isDnsmasq
            ? 'rgba(76, 175, 80, 0.3)'
            : isRouter
            ? 'rgba(255, 152, 0, 0.3)'
            : 'var(--border-subtle)',
        }}
        title={error ?? tooltip}
      >
        <Icon size={12} color={iconColor} />
        <span style={{ color: iconColor }}>{label}</span>
      </div>

      {isDnsmasq && remaining && (
        <span style={{ color: iconColor, fontSize: '0.8rem', whiteSpace: 'nowrap' }} title={`Auto-reverts at ${status?.expires_at ?? 'deadline'}`}>
          ⏳ {remaining}
        </span>
      )}

      <button
        onClick={() => handleSwitch(false)}
        disabled={switching || (!isDnsmasq && !isRouter)}
        className="btn btn-secondary btn-sm"
        title={tooltip}
      >
        <ArrowLeftRight size={14} className={switching ? 'spin' : ''} />
        <span>{switching ? 'Switching...' : isDnsmasq ? 'Use Router DNS' : 'Use rosa-PC DNS'}</span>
      </button>

      {isDnsmasq && (
        <button
          onClick={() => handleSwitch(true)}
          disabled={switching}
          className="btn btn-secondary btn-sm"
          title={`Restart the ~${status?.max_hours ?? 3}h failsafe clock from now`}
        >
          <span>+{status?.max_hours ?? 3}h</span>
        </button>
      )}
    </div>
  );
};
