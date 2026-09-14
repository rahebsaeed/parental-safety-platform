import React, { useEffect, useState, useCallback } from 'react';
import {
  FolderKanban,
  RefreshCw,
  Edit2,
  CheckCircle2,
  Cpu,
  Sparkles,
  X,
  Save,
  Layers,
} from 'lucide-react';
import { api } from '../services/api';
import type { DomainClassification } from '../types/api';

const CATEGORIES = [
  'ALL',
  'UNSAFE',
  'GAMBLING',
  'SOCIAL_MEDIA',
  'STREAMING',
  'GAMING',
  'MESSAGING',
  'NEWS_INFORMATION',
  'PRODUCTIVITY_EDUCATION',
  'SEARCH_PORTAL',
  'INFRASTRUCTURE_SYSTEM',
  'UNKNOWN',
];

export const ClassificationsPage: React.FC = () => {
  const [classifications, setClassifications] = useState<DomainClassification[]>([]);
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Sandbox state
  const [testDomainInput, setTestDomainInput] = useState('');
  const [testResult, setTestResult] = useState<{
    domain: string;
    category: string;
    rule_type: string | null;
    pattern: string | null;
  } | null>(null);
  const [testing, setTesting] = useState(false);

  // Override Modal state
  const [editingDomain, setEditingDomain] = useState<DomainClassification | null>(null);
  const [overrideCategory, setOverrideCategory] = useState('PRODUCTIVITY_EDUCATION');
  const [overrideNote, setOverrideNote] = useState('');
  const [savingOverride, setSavingOverride] = useState(false);

  const fetchClassifications = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const cat = selectedCategory === 'ALL' ? undefined : selectedCategory;
      const data = await api.getClassifications(cat, 200);
      setClassifications(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch classifications');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedCategory]);

  useEffect(() => {
    fetchClassifications();
  }, [fetchClassifications]);

  const handleTestClassifier = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testDomainInput.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.classifyDomains([testDomainInput.trim()]);
      if (res.results && res.results.length > 0) {
        setTestResult(res.results[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Classifier test failed');
    } finally {
      setTesting(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await api.syncClassifications();
      setSyncResult(`Synced successfully! ${res.classified} unclassified domains resolved.`);
      fetchClassifications(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Domain sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const openOverrideModal = (item: DomainClassification) => {
    setEditingDomain(item);
    setOverrideCategory(item.category || 'PRODUCTIVITY_EDUCATION');
    setOverrideNote(item.note || '');
  };

  const handleSaveOverride = async () => {
    if (!editingDomain) return;
    setSavingOverride(true);
    try {
      await api.overrideClassification(editingDomain.domain, overrideCategory, overrideNote);
      setEditingDomain(null);
      fetchClassifications(true);
    } catch (err) {
      alert(`Error saving override: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSavingOverride(false);
    }
  };

  const getCategoryColor = (cat: string) => {
    switch (cat.toUpperCase()) {
      case 'UNSAFE':
      case 'ADULT_EXPLICIT':
        return '#dc2626';
      case 'GAMBLING':
        return '#f97316';
      case 'SOCIAL_MEDIA':
        return '#e91e8c';
      case 'STREAMING':
        return '#e53935';
      case 'GAMING':
        return '#9333ea';
      case 'PRODUCTIVITY_EDUCATION':
        return '#0891b2';
      case 'MESSAGING':
        return '#10b981';
      case 'NEWS_INFORMATION':
        return '#854d0e';
      case 'SEARCH_PORTAL':
        return '#2563eb';
      case 'INFRASTRUCTURE_SYSTEM':
        return '#475569';
      default:
        return '#64748b';
    }
  };

  return (
    <div className="classifications-page">
      {/* Top Banner: Classifier Sandbox & Batch Sync */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
          gap: '1.5rem',
          marginBottom: '2rem',
        }}
      >
        {/* Real-time Domain Classifier Sandbox */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <Sparkles size={18} color="var(--primary-light)" />
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
              Live Classifier Sandbox
            </h2>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginBottom: '1rem' }}>
            Test how the multi-tiered classification engine (exact match, domain suffix, regex keyword) evaluates any domain.
          </p>

          <form onSubmit={handleTestClassifier} style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <input
              type="text"
              placeholder="e.g. tiktok.com, discord.gg, pornhub.com..."
              value={testDomainInput}
              onChange={(e) => setTestDomainInput(e.target.value)}
              className="form-input"
              style={{ flex: 1 }}
            />
            <button type="submit" disabled={testing || !testDomainInput.trim()} className="btn btn-primary btn-sm">
              <Cpu size={14} /> {testing ? 'Testing...' : 'Classify'}
            </button>
          </form>

          {testResult && (
            <div
              style={{
                background: 'rgba(15, 23, 42, 0.7)',
                border: '1px solid var(--border-glass)',
                borderRadius: 'var(--radius-md)',
                padding: '1rem',
                fontSize: '0.8125rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{testResult.domain}</span>
                <span
                  className="badge"
                  style={{
                    backgroundColor: `${getCategoryColor(testResult.category)}22`,
                    color: getCategoryColor(testResult.category),
                    borderColor: `${getCategoryColor(testResult.category)}55`,
                  }}
                >
                  {testResult.category}
                </span>
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Rule Match: <strong style={{ color: 'var(--text-primary)' }}>{testResult.rule_type || 'NONE'}</strong>
                {testResult.pattern && ` (${testResult.pattern})`}
              </div>
            </div>
          )}
        </div>

        {/* Sync & Overview Stats */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <FolderKanban size={18} color="var(--primary-light)" />
              <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', fontWeight: 600 }}>
                Rule Engine Directory
              </h2>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginBottom: '1rem' }}>
              11 comprehensive safety categories covering gaming, adult material, social media, messaging, and system infrastructure.
            </p>
            {syncResult && (
              <div
                style={{
                  background: 'rgba(16, 185, 129, 0.15)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  borderRadius: 'var(--radius-md)',
                  padding: '0.75rem',
                  fontSize: '0.8125rem',
                  color: '#34d399',
                  marginBottom: '1rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <CheckCircle2 size={16} /> {syncResult}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <button
              onClick={handleSync}
              disabled={syncing}
              className="btn btn-secondary btn-sm"
              style={{ flex: 1 }}
            >
              <RefreshCw size={14} className={syncing ? 'status-dot-pulse' : ''} />
              {syncing ? 'Syncing...' : 'Sync Unclassified Domains'}
            </button>
            <button
              onClick={() => fetchClassifications(true)}
              disabled={refreshing}
              className="btn btn-secondary btn-sm"
            >
              <RefreshCw size={14} className={refreshing ? 'status-dot-pulse' : ''} />
            </button>
          </div>
        </div>
      </div>

      {/* Category Filter Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          overflowX: 'auto',
          paddingBottom: '0.75rem',
          marginBottom: '1.5rem',
        }}
      >
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`btn btn-sm ${selectedCategory === cat ? 'btn-primary' : 'btn-secondary'}`}
            style={{
              whiteSpace: 'nowrap',
              fontSize: '0.75rem',
              textTransform: 'capitalize',
            }}
          >
            {cat.toLowerCase().replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {error && (
        <div className="glass-card" style={{ marginBottom: '1.5rem', borderColor: 'var(--danger)', color: '#f87171' }}>
          {error}
        </div>
      )}

      {/* Classifications Table */}
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Domain</th>
              <th>Category</th>
              <th>Rule Type</th>
              <th>Matched Pattern</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                  Loading domain classifications...
                </td>
              </tr>
            ) : classifications.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                  <Layers size={32} style={{ marginBottom: '0.75rem', opacity: 0.5 }} />
                  <div>No classified domains in category "{selectedCategory}".</div>
                </td>
              </tr>
            ) : (
              classifications.map((item) => (
                <tr key={item.domain}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{item.domain}</td>
                  <td>
                    <span
                      className="badge"
                      style={{
                        backgroundColor: `${getCategoryColor(item.category)}22`,
                        color: getCategoryColor(item.category),
                        borderColor: `${getCategoryColor(item.category)}55`,
                      }}
                    >
                      {item.category}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
                    {item.rule_type || 'DEFAULT'}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {item.pattern || '—'}
                  </td>
                  <td>
                    {item.is_override ? (
                      <span className="badge badge-warning" title={item.note || 'Manual parent override'}>
                        OVERRIDE
                      </span>
                    ) : (
                      <span className="badge badge-muted">AUTOMATIC</span>
                    )}
                  </td>
                  <td>
                    <button
                      onClick={() => openOverrideModal(item)}
                      className="btn btn-secondary btn-sm"
                      title="Override category"
                    >
                      <Edit2 size={12} /> Edit
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Override Category Modal */}
      {editingDomain && (
        <div className="modal-overlay" onClick={() => setEditingDomain(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1.25rem', fontWeight: 600 }}>
                Override Classification
              </h3>
              <button
                onClick={() => setEditingDomain(null)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.25rem' }}>
              Assign a customized parent category for <strong style={{ color: 'var(--text-primary)' }}>{editingDomain.domain}</strong>.
            </p>

            <div className="form-group">
              <label className="form-label">Select Category</label>
              <select
                className="form-select"
                value={overrideCategory}
                onChange={(e) => setOverrideCategory(e.target.value)}
              >
                {CATEGORIES.filter((c) => c !== 'ALL').map((cat) => (
                  <option key={cat} value={cat}>
                    {cat.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Note / Rationale (Optional)</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Educational exception approved by parent"
                value={overrideNote}
                onChange={(e) => setOverrideNote(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem' }}>
              <button
                type="button"
                onClick={() => setEditingDomain(null)}
                className="btn btn-secondary"
                disabled={savingOverride}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveOverride}
                className="btn btn-primary"
                disabled={savingOverride}
              >
                <Save size={14} /> {savingOverride ? 'Saving...' : 'Save Override'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
