import React, { useState } from 'react';
import { Shield } from 'lucide-react';
import { api } from '../services/api';

interface Props {
  onLoginSuccess: () => void;
}

export const LoginPage: React.FC<Props> = ({ onLoginSuccess }) => {
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.login(password);
      onLoginSuccess();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Authentication failed'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <Shield size={48} color="var(--primary-light)" />
          <h1 style={styles.title}>Parental Safety Platform</h1>
          <p style={styles.subtitle}>Enter parent password to continue</p>
        </div>
        <form onSubmit={handleSubmit} style={styles.form}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Parent password"
            style={styles.input}
            autoFocus
            disabled={loading}
            autoComplete="current-password"
          />
          {error && <div style={styles.error}>{error}</div>}
          <button type="submit" style={styles.button} disabled={loading}>
            {loading ? 'Verifying…' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
    background: 'var(--bg-primary, #090d16)',
    fontFamily: 'var(--font-body, Inter, sans-serif)',
  },
  card: {
    width: '100%',
    maxWidth: '400px',
    padding: '2rem',
    background: 'var(--glass, rgba(255,255,255,0.05))',
    borderRadius: 'var(--radius-lg, 16px)',
    boxShadow: 'var(--shadow, 0 8px 32px rgba(0,0,0,0.4))',
  },
  header: {
    textAlign: 'center',
    marginBottom: '2rem',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: 700,
    color: 'var(--text-primary, #e2e8f0)',
    margin: '0.5rem 0 0.25rem',
  },
  subtitle: {
    color: 'var(--text-muted, #94a3b8)',
    fontSize: '0.9rem',
    margin: 0,
  },
  form: { display: 'flex', flexDirection: 'column', gap: '1rem' },
  input: {
    padding: '0.75rem 1rem',
    borderRadius: 'var(--radius, 8px)',
    border: '1px solid var(--border, rgba(255,255,255,0.1))',
    background: 'var(--input-bg, rgba(255,255,255,0.06))',
    color: 'var(--text-primary, #e2e8f0)',
    fontSize: '1rem',
    outline: 'none',
  },
  error: {
    color: '#f87171',
    fontSize: '0.85rem',
    textAlign: 'center',
  },
  button: {
    padding: '0.75rem',
    borderRadius: 'var(--radius, 8px)',
    border: 'none',
    background: 'var(--primary, #6366f1)',
    color: '#fff',
    fontSize: '1rem',
    fontWeight: 600,
    cursor: 'pointer',
  },
};
