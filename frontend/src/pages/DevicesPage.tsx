import React, { useEffect, useState } from 'react';
import {
  Smartphone,
  Router,
  Laptop,
  HelpCircle,
  Edit2,
  ChevronRight,
  X,
  RefreshCw,
} from 'lucide-react';
import { api } from '../services/api';
import type { Device, DeviceDetail } from '../types/api';

interface Props {
  onScan?: () => void;
  scanning?: boolean;
}

export const DevicesPage: React.FC<Props> = ({ onScan, scanning }) => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<DeviceDetail | null>(null);
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const [friendlyNameInput, setFriendlyNameInput] = useState('');
  const [deviceTypeInput, setDeviceTypeInput] = useState('');
  const [loading, setLoading] = useState(true);
  // Default to online-only: matches the router's connected-client count
  // (the router never lists itself; offline devices live on the Offline tab).
  const [statusFilter, setStatusFilter] = useState<'all' | 'online' | 'offline'>('online');

  useEffect(() => {
    loadDevices();
  }, [statusFilter]);

  async function loadDevices() {
    try {
      setLoading(true);
      const data = await api.getDevices(statusFilter === 'all' ? undefined : statusFilter);
      setDevices(data);
    } catch (err) {
      console.error('Failed to load devices:', err);
    } finally {
      setLoading(false);
    }
  }

  async function openDeviceDetail(deviceId: string) {
    try {
      const detail = await api.getDeviceDetail(deviceId);
      setSelectedDevice(detail);
    } catch (err) {
      console.error('Failed to fetch device detail:', err);
    }
  }

  function startEdit(dev: Device) {
    setEditingDevice(dev);
    setFriendlyNameInput(dev.friendly_name || '');
    setDeviceTypeInput(dev.device_type || 'Generic');
  }

  async function saveEdit() {
    if (!editingDevice) return;
    try {
      await api.updateDevice(editingDevice.device_id, {
        friendly_name: friendlyNameInput.trim() || undefined,
        device_type: deviceTypeInput.trim() || undefined,
      });
      setEditingDevice(null);
      await loadDevices();
      if (selectedDevice && selectedDevice.device_id === editingDevice.device_id) {
        openDeviceDetail(editingDevice.device_id);
      }
    } catch (err) {
      alert('Failed to update device: ' + err);
    }
  }

  function localTime(iso: string): string {
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleString(undefined, {
        timeZoneName: 'short',
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
        hour12: false,
      });
    } catch {
      return iso;
    }
  }

  function getDeviceIcon(type: string | null) {
    const t = (type || '').toLowerCase();
    if (t.includes('router') || t.includes('gateway')) return Router;
    if (t.includes('android') || t.includes('ios') || t.includes('phone') || t.includes('tablet')) return Smartphone;
    if (t.includes('pc') || t.includes('laptop') || t.includes('mac') || t.includes('linux')) return Laptop;
    return HelpCircle;
  }

  return (
    <div>
      {/* Top Filter Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {(['all', 'online', 'offline'] as const).map((filter) => (
            <button
              key={filter}
              onClick={() => setStatusFilter(filter)}
              className={`btn btn-sm ${statusFilter === filter ? 'btn-primary' : 'btn-secondary'}`}
              style={{ textTransform: 'capitalize' }}
            >
              {filter}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            {devices.length} devices discovered
          </div>
          {onScan && (
            <button
              onClick={onScan}
              disabled={scanning}
              className="btn btn-secondary btn-sm"
              title="Run fresh device discovery scan"
            >
              <RefreshCw size={14} className={scanning ? 'spin' : ''} />
              {scanning ? 'Scanning...' : 'Scan'}
            </button>
          )}
        </div>
      </div>

      {/* Device Cards Grid */}
      {loading ? (
        <div className="glass-card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
          Loading network devices...
        </div>
      ) : devices.length === 0 ? (
        <div className="glass-card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
          No devices discovered matching filter.
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1.25rem' }}>
          {devices.map((dev) => {
          const Icon = getDeviceIcon(dev.device_type);
          const isOnline = dev.status === 'online';

          return (
            <div key={dev.device_id} className="glass-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '1rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{
                      width: 44,
                      height: 44,
                      borderRadius: 'var(--radius-md)',
                      background: 'rgba(99, 102, 241, 0.12)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--primary-light)',
                    }}>
                      <Icon size={22} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--text-primary)' }}>
                        {dev.friendly_name || dev.device_id}
                      </div>
                      <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                        {dev.device_type || 'Unclassified'} • {dev.vendor || 'Unknown Vendor'}
                        {dev.is_gateway ? (
                          <span className="badge badge-success" style={{ marginLeft: 6, padding: '0.1rem 0.4rem', fontSize: '0.7rem' }}>
                            Gateway
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  <span className={`badge ${isOnline ? 'badge-success' : 'badge-muted'}`}>
                    {isOnline && <span className="status-dot-pulse" style={{ width: 6, height: 6 }} />}
                    {dev.status}
                  </span>
                </div>

                {/* Device Attributes */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Current IP:</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{dev.current_ip || 'None'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>MAC Address:</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                      {dev.primary_mac || 'Unknown'}
                      {dev.mac_is_randomized ? (
                        <span className="badge badge-warning" style={{ marginLeft: 6, padding: '0.1rem 0.4rem', fontSize: '0.7rem' }}>
                          Randomized
                        </span>
                      ) : null}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>DNS Visibility:</span>
                    <span className={`badge ${dev.dns_visibility === 'PARTIAL' ? 'badge-danger' : 'badge-success'}`}>
                      {dev.dns_visibility || 'FULL'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Queries Logged:</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{dev.query_count || 0}</span>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
                <button onClick={() => startEdit(dev)} className="btn btn-secondary btn-sm" style={{ flex: 1 }}>
                  <Edit2 size={13} /> Edit
                </button>
                <button onClick={() => openDeviceDetail(dev.device_id)} className="btn btn-primary btn-sm" style={{ flex: 1 }}>
                  Details <ChevronRight size={13} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
      )}

      {/* Edit Device Modal */}
      {editingDevice && (
        <div className="modal-overlay" onClick={() => setEditingDevice(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <h3 style={{ fontSize: '1.25rem', fontFamily: 'var(--font-display)', fontWeight: 600 }}>
                Edit Device: {editingDevice.device_id}
              </h3>
              <button onClick={() => setEditingDevice(null)} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>

            <div className="form-group">
              <label className="form-label">Friendly Name</label>
              <input
                className="form-input"
                value={friendlyNameInput}
                onChange={(e) => setFriendlyNameInput(e.target.value)}
                placeholder="e.g. Maya's Tablet"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Device Classification</label>
              <select
                className="form-select"
                value={deviceTypeInput}
                onChange={(e) => setDeviceTypeInput(e.target.value)}
              >
                <option value="Android">Android Phone / Tablet</option>
                <option value="iOS">iPhone / iPad</option>
                <option value="PC">Windows / Linux PC</option>
                <option value="Mac">Macintosh</option>
                <option value="SmartTV">Smart TV / Streaming Box</option>
                <option value="GamingConsole">Gaming Console</option>
                <option value="IoT">IoT / Smart Home Device</option>
                <option value="Router">Network Router / AP</option>
                <option value="Generic">Generic / Other</option>
              </select>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '2rem' }}>
              <button onClick={() => setEditingDevice(null)} className="btn btn-secondary">
                Cancel
              </button>
              <button onClick={saveEdit} className="btn btn-primary">
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Device Detail Drawer / Modal */}
      {selectedDevice && (
        <div className="modal-overlay" onClick={() => setSelectedDevice(null)}>
          <div className="modal-card" style={{ maxWidth: 640, maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <div>
                <h3 style={{ fontSize: '1.375rem', fontFamily: 'var(--font-display)', fontWeight: 600 }}>
                  {selectedDevice.friendly_name || selectedDevice.device_id}
                </h3>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                  Device ID: {selectedDevice.device_id} • First seen {localTime(selectedDevice.first_seen)}
                </div>
              </div>
              <button onClick={() => setSelectedDevice(null)} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>

            {/* Top Domains for this Device */}
            <div style={{ marginBottom: '1.75rem' }}>
              <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '0.75rem', color: 'var(--text-primary)' }}>
                Top Domains Queried
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                {selectedDevice.top_domains && selectedDevice.top_domains.length > 0 ? (
                  selectedDevice.top_domains.map((td) => (
                    <div key={td.domain} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'rgba(15, 23, 42, 0.5)', borderRadius: 'var(--radius-sm)', fontSize: '0.8125rem' }}>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{td.domain}</span>
                      <span style={{ color: 'var(--text-muted)' }}>{td.query_count} queries</span>
                    </div>
                  ))
                ) : (
                  <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>No DNS queries recorded yet for this device.</div>
                )}
              </div>
            </div>

            {/* Address History */}
            <div>
              <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '0.75rem', color: 'var(--text-primary)' }}>
                Observed Address History
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {selectedDevice.addresses && selectedDevice.addresses.map((addr) => (
                  <div key={addr.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'rgba(15, 23, 42, 0.4)', borderRadius: 'var(--radius-sm)', fontSize: '0.8125rem' }}>
                    <div>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{addr.ip_address}</span>
                      {addr.hostname && <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>({addr.hostname})</span>}
                    </div>
                    <div style={{ color: 'var(--text-muted)' }}>{addr.observed_at}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
