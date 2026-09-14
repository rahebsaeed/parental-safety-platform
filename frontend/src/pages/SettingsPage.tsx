import React, { useState, useEffect } from 'react';
import { Lock, Save, AlertCircle, CheckCircle, Key } from 'lucide-react';
import { api } from '../services/api';

export const SettingsPage: React.FC = () => {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [hasSavedKey, setHasSavedKey] = useState<boolean | null>(null);
  const [apiKeyLoading, setApiKeyLoading] = useState(false);
  const [apiKeyMessage, setApiKeyMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [testingKey, setTestingKey] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; label?: string | null; error?: string } | null>(null);
  const [lastVerified, setLastVerified] = useState<string | null>(() => {
    try {
      return localStorage.getItem('openrouter_last_verified');
    } catch {
      return null;
    }
  });

  const [servingModel, setServingModel] = useState<string | null>(null);
  const [coolingCount, setCoolingCount] = useState(0);

  async function fetchApiKeyStatus() {
    try {
      const data = await api.getOpenRouterApiKeyStatus();
      setHasSavedKey(data.configured);
      const models = data.models ?? [];
      const usable = models.find((m) => !m.cooling) ?? null;
      setServingModel(usable ? usable.model : null);
      setCoolingCount(models.filter((m) => m.cooling).length);
    } catch {
      setHasSavedKey(null);
      setServingModel(null);
      setCoolingCount(0);
    }
  }

  async function handleSaveApiKey(e: React.FormEvent) {
    e.preventDefault();
    const key = apiKeyInput.trim();
    if (!key) {
      setApiKeyMessage({ text: 'Enter an API key before saving.', type: 'error' });
      return;
    }
    setApiKeyLoading(true);
    setApiKeyMessage(null);
    setTestResult(null);
    try {
      await api.saveOpenRouterApiKey(key);
      setApiKeyInput('');
      await fetchApiKeyStatus();
      setApiKeyMessage({ text: 'OpenRouter API key saved.', type: 'success' });
    } catch (err: any) {
      setApiKeyMessage({ text: err.message || 'Failed to save API key.', type: 'error' });
    } finally {
      setApiKeyLoading(false);
    }
  }

  async function handleTestApiKey() {
    const key = apiKeyInput.trim();
    setTestingKey(true);
    setTestResult(null);
    setApiKeyMessage(null);
    try {
      const res = await api.testOpenRouterApiKey(key || undefined);
      setTestResult(res);
      if (res.ok) {
        const stamped = new Date().toISOString();
        setLastVerified(stamped);
        try {
          localStorage.setItem('openrouter_last_verified', stamped);
        } catch {
          // Non-blocking (private mode etc.)
        }
      } else {
        setApiKeyMessage({ text: res.error || 'Key test failed.', type: 'error' });
      }
    } catch (err: any) {
      setTestResult({ ok: false, error: err.message || 'Key test failed.' });
      setApiKeyMessage({ text: err.message || 'Key test failed.', type: 'error' });
    } finally {
      setTestingKey(false);
      fetchApiKeyStatus();
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    if (newPassword !== confirmPassword) {
      setMessage({ text: 'Passwords do not match.', type: 'error' });
      return;
    }
    if (newPassword.length < 6) {
      setMessage({ text: 'New password must be at least 6 characters.', type: 'error' });
      return;
    }
    setLoading(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setMessage({ text: 'Password changed successfully. Redirecting to login...', type: 'success' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setTimeout(() => window.location.reload(), 1500);
    } catch (err: any) {
      setMessage({ text: err.message || 'Failed to change password.', type: 'error' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchApiKeyStatus();
  }, []);

  return (
    <div>
      <div style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.5rem', fontFamily: 'var(--font-display)', fontWeight: 600 }}>Settings</h2>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
          Manage your account and platform configuration
        </div>
      </div>

      <div className="glass-card" style={{ maxWidth: 480 }}>
        <form onSubmit={handleChangePassword}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
            <div style={{
              width: 40, height: 40, borderRadius: 'var(--radius-md)',
              background: 'rgba(99, 102, 241, 0.12)', display: 'flex',
              alignItems: 'center', justifyContent: 'center', color: 'var(--primary-light)',
            }}>
              <Lock size={20} />
            </div>
            <div>
              <div style={{ fontWeight: 600 }}>Change Password</div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                Update your parent dashboard password
              </div>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Current Password</label>
            <input
              type="password"
              className="form-input"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Enter current password"
              required
              autoComplete="current-password"
            />
          </div>

          <div className="form-group">
            <label className="form-label">New Password</label>
            <input
              type="password"
              className="form-input"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="At least 6 characters"
              required
              autoComplete="new-password"
            />
          </div>

          <div className="form-group">
            <label className="form-label">Confirm New Password</label>
            <input
              type="password"
              className="form-input"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirm new password"
              required
              autoComplete="new-password"
            />
          </div>

          {message && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)',
              background: message.type === 'success' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
              color: message.type === 'success' ? 'var(--success)' : 'var(--danger)',
              fontSize: '0.875rem', marginBottom: '1rem',
            }}>
              {message.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
              {message.text}
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={loading} style={{ width: '100%' }}>
            <Save size={16} style={{ marginRight: 8 }} />
            {loading ? 'Saving...' : 'Change Password'}
          </button>
        </form>
      </div>

      <div className="glass-card" style={{ maxWidth: 480, marginTop: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
          <Key size={18} color="var(--primary-light)" />
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1rem', fontWeight: 600 }}>
            OpenRouter AI Category Engine
          </h3>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginBottom: '1rem' }}>
          Use OpenRouter's free LLM model to automatically categorize domains. Get a free API key at{' '}
          <a href="https://openrouter.ai" target="_blank" rel="noreferrer" style={{ color: 'var(--primary)' }}>openrouter.ai</a>.
        </p>
        <form onSubmit={handleSaveApiKey}>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <input
              type="password"
              className="form-input"
              placeholder={hasSavedKey ? 'Saved — enter a new key to replace it' : 'Enter OpenRouter API key'}
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              style={{ flex: 1 }}
              autoComplete="off"
            />
            <button type="submit" disabled={apiKeyLoading || !apiKeyInput.trim()} className="btn btn-primary btn-sm">
              <Save size={14} /> {apiKeyLoading ? 'Saving...' : 'Save Key'}
            </button>
            <button
              type="button"
              onClick={handleTestApiKey}
              disabled={testingKey || (!apiKeyInput.trim() && !hasSavedKey)}
              className="btn btn-secondary btn-sm"
              title={apiKeyInput.trim() ? 'Test the key in this field (not saved yet)' : 'Test the saved key'}
            >
              {testingKey ? 'Testing...' : 'Test'}
            </button>
          </div>
        </form>
        {apiKeyMessage && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '0.5rem',
            padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)',
            background: apiKeyMessage.type === 'success' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
            color: apiKeyMessage.type === 'success' ? 'var(--success)' : 'var(--danger)',
            fontSize: '0.875rem', marginTop: '0.75rem',
          }}>
            {apiKeyMessage.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
            {apiKeyMessage.text}
          </div>
        )}
        <div style={{ marginTop: '0.75rem', fontSize: '0.8125rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          {hasSavedKey === null ? (
            <span style={{ color: 'var(--text-muted)' }}>Checking saved key…</span>
          ) : hasSavedKey ? (
            <span style={{ color: '#4caf50' }}><CheckCircle size={14} /> API key saved on server</span>
          ) : (
            <span style={{ color: '#9e9e9e' }}><AlertCircle size={14} /> No API key saved yet</span>
          )}
          {testResult && testResult.ok && (
            <span style={{ color: '#4caf50' }}>
              <CheckCircle size={14} /> Key works{testResult.label ? ` (${testResult.label})` : ''} — classifications will run.
            </span>
          )}
          {servingModel ? (
            <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
              Serving model: {servingModel}{coolingCount > 0 ? ` (${coolingCount} cooling down)` : ''}
            </span>
          ) : hasSavedKey === true ? (
            <span style={{ color: '#ff9800' }}>All free models cooling — retries automatically.</span>
          ) : null}
          {lastVerified && (
            <span style={{ color: 'var(--text-muted)' }}>
              Last verified {new Date(lastVerified).toLocaleString(undefined, { timeZoneName: 'short', hour12: false })}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
