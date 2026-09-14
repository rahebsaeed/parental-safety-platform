import type {
  AlertSummary,
  AnalyticsOverview,
  CategoryDistributionResponse,
  Device,
  DeviceDetail,
  DnsQuery,
  DomainClassification,
  HealthStatus,
  HourlyActivityItem,
  SafetyAlert,
  TimelineItem,
  SessionInfo,
} from '../types/api';

const BASE_URL = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`API Error ${response.status}: ${errorBody || response.statusText}`);
  }

  return response.json();
}

export const api = {
  // Auth
  login: (password: string) =>
    fetchJson<{ authenticated: boolean; token: string; expires_at: string }>(
      `${BASE_URL}/auth/login`,
      {
        method: 'POST',
        body: JSON.stringify({ password }),
      }
    ),
  logout: () =>
    fetchJson<{ authenticated: boolean; message: string }>(
      `${BASE_URL}/auth/logout`,
      { method: 'POST' }
    ),
  getAuthStatus: () =>
    fetchJson<SessionInfo>(`${BASE_URL}/auth/status`),
  changePassword: (current: string, newPassword: string) =>
    fetchJson<{ success: boolean; message: string }>(
      `${BASE_URL}/auth/change-password`,
      {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: newPassword }),
      }
    ),

  // System Health
  getHealth: () => fetchJson<HealthStatus>(`${BASE_URL}/health`),

  // Devices
  getDevices: (status?: string) => {
    const params = status ? `?status=${status}` : '';
    return fetchJson<Device[]>(`${BASE_URL}/devices${params}`);
  },
  getDeviceDetail: (deviceId: string) =>
    fetchJson<DeviceDetail>(`${BASE_URL}/devices/${encodeURIComponent(deviceId)}`),
  updateDevice: (deviceId: string, payload: { friendly_name?: string; device_type?: string }) =>
    fetchJson<Device>(`${BASE_URL}/devices/${encodeURIComponent(deviceId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  triggerScan: () =>
    fetchJson<{ success: boolean; message: string; output: string }>(
      `${BASE_URL}/devices/scan`,
      { method: 'POST' }
    ),

  // DNS Activity (backend returns paginated {total,limit,offset,items})
  getActivity: async (params: {
    device_id?: string;
    domain?: string;
    visibility?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<DnsQuery[]> => {
    const q = new URLSearchParams();
    if (params.device_id) q.set('device_id', params.device_id);
    if (params.domain) q.set('domain', params.domain);
    if (params.visibility) q.set('visibility', params.visibility);
    if (params.status) q.set('status', params.status);
    if (params.limit) q.set('limit', String(params.limit));
    if (params.offset) q.set('offset', String(params.offset));
    const data = await fetchJson<DnsQuery[] | { items: DnsQuery[] }>(`${BASE_URL}/activity?${q.toString()}`);
    return Array.isArray(data) ? data : (data.items ?? []);
  },

  // Safety Alerts
  getAlerts: (params?: { status?: string; severity?: string; device_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.severity) q.set('severity', params.severity);
    if (params?.device_id) q.set('device_id', params.device_id);
    return fetchJson<SafetyAlert[]>(`${BASE_URL}/alerts?${q.toString()}`);
  },
  getAlertSummary: () => fetchJson<AlertSummary>(`${BASE_URL}/alerts/summary`),
  updateAlertStatus: (alertId: number, status: string) =>
    fetchJson<SafetyAlert>(`${BASE_URL}/alerts/${alertId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  triggerAlertScan: (limit = 1000) =>
    fetchJson<{ scanned_queries: number; alerts_created: number; alerts_aggregated: number }>(
      `${BASE_URL}/alerts/scan?limit=${limit}`,
      { method: 'POST' }
    ),

  // Analytics
  getAnalyticsOverview: (deviceId?: string) => {
    const q = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : '';
    return fetchJson<AnalyticsOverview>(`${BASE_URL}/analytics/overview${q}`);
  },
  getCategoryDistribution: (deviceId?: string) => {
    const q = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : '';
    return fetchJson<CategoryDistributionResponse>(`${BASE_URL}/analytics/categories${q}`);
  },
  getActiveHours: (deviceId?: string) => {
    const q = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : '';
    return fetchJson<{ disclaimer: string; hourly_distribution: HourlyActivityItem[] }>(
      `${BASE_URL}/analytics/active-hours${q}`
    );
  },
  getTimeline: (days = 14, deviceId?: string) => {
    const q = new URLSearchParams({ days: String(days) });
    if (deviceId) q.set('device_id', deviceId);
    return fetchJson<{ disclaimer: string; timeline: TimelineItem[] }>(
      `${BASE_URL}/analytics/timeline?${q.toString()}`
    );
  },

  // Domain Classifications
  getClassifications: (category?: string, limit = 100) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (category) q.set('category', category);
    return fetchJson<DomainClassification[]>(`${BASE_URL}/classifications/domains?${q.toString()}`);
  },
  classifyDomains: (domains: string[]) =>
    fetchJson<{ results: Array<{ domain: string; category: string; rule_type: string | null; pattern: string | null }> }>(
      `${BASE_URL}/classifications/classify`,
      { method: 'POST', body: JSON.stringify({ domains }) }
    ),
  syncClassifications: () =>
    fetchJson<{ classified: number; message: string }>(`${BASE_URL}/classifications/sync`, {
      method: 'POST',
    }),
  overrideClassification: (domain: string, category: string, note?: string) =>
    fetchJson<DomainClassification>(`${BASE_URL}/classifications/domains/${encodeURIComponent(domain)}/override`, {
      method: 'PUT',
      body: JSON.stringify({ category, note }),
    }),
};
