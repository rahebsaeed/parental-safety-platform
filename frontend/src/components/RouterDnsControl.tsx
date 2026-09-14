import React, { useCallback, useEffect, useState } from 'react';
import { ShieldCheck, ShieldAlert, HelpCircle, ArrowLeftRight } from 'lucide-react';
import { api } from '../services/api';
import type { RouterDnsStatus } from '../types/api';

const POLL_INTERVAL_MS = 30000;

/**
 * Router DNS badge + manual switch, shown in the app header.
 *
 * The badge always reflects the router's *actual* reported DNS (polled),
 * so suspend/shutdown automation, the WiFi dispatcher, or a change made
 * from another device can never leave the UI lying about the current mode.
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

  const handleSwitch = async () => {
    if (!status || switching) return;
    const target = status.mode === 'dnsmasq' ? 'router' : 'dnsmasq';
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

  const tooltip = isDnsmasq
    ? 'Router points at this PC — traffic is filtered and logged. Click to fall back to the router (unfiltered).'
    : isRouter
    ? 'Router points at itself — traffic is UNFILTERED. Click to route through this PC (filtered + logged).'
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

      <button
        onClick={handleSwitch}
        disabled={switching || (!isDnsmasq && !isRouter)}
        className="btn btn-secondary btn-sm"
        title={tooltip}
      >
        <ArrowLeftRight size={14} className={switching ? 'spin' : ''} />
        <span>{switching ? 'Switching...' : isDnsmasq ? 'Use Router DNS' : 'Use rosa-PC DNS'}</span>
      </button>
    </div>
  );
};
