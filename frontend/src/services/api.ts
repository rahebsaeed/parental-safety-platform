import type {
  AlertSummary,
  AnalyticsOverview,
  CategoryDistributionResponse,
  Device,
  DeviceDetail,
  DnsQuery,
  DomainClassification,
  DomainSecurityResponse,
  DangerousDomain,
  SubjectResponse,
  HealthStatus,
  RouterDnsStatus,
  HourlyActivityItem,
  SafetyAlert,
  TimelineItem,
  SessionInfo,
  OpenRouterCategory,
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
  getHealth: () => fetchJson<HealthStatus>(`${BASE_URL}/health`),
  getDevices: (status?: string) => {
    const params = status ? `?status=${status}` : '';
    return fetchJson<Device[]>(`${BASE_URL}/devices${params}`);
  },
  getDeviceDetail: (deviceId: string) =>
    fetchJson<DeviceDetail>(`${BASE_URL}/devices/${encodeURIComponent(deviceId)}`),
  updateDevice: (deviceId: string, payload: { friendly_name?: string; device_type?: string }) =>
    fetchJson<Device>(`${BASE_URL}/devices/${encodeURIComponent(deviceId)}`, {
      method: 'PATCH', body: JSON.stringify(payload),
    }),
  getActivity: (params: { device_id?: string; domain?: string; visibility?: string; status?: string; limit?: number; offset?: number }) => {
    const qp = new URLSearchParams();
    if (params.device_id) qp.set('device_id', params.device_id);
    if (params.domain) qp.set('domain', params.domain);
    if (params.visibility) qp.set('visibility', params.visibility);
    if (params.status) qp.set('status', params.status);
    if (params.limit) qp.set('limit', String(params.limit));
    if (params.offset) qp.set('offset', String(params.offset));
    return fetchJson<DnsQuery[] | { items: DnsQuery[] }>(`${BASE_URL}/activity?${qp.toString()}`).then(
      (res: unknown): DnsQuery[] => (Array.isArray(res) ? res : ((res as { items?: DnsQuery[] })?.items ?? [])),
    );
  },
  getAlerts: (params?: { status?: string; severity?: string; device_id?: string }) => {
    const qp = new URLSearchParams();
    if (params?.status) qp.set('status', params.status);
    if (params?.severity) qp.set('severity', params.severity);
    if (params?.device_id) qp.set('device_id', params.device_id);
    return fetchJson<SafetyAlert[]>(`${BASE_URL}/alerts?${qp.toString()}`);
  },
  getAlertSummary: () => fetchJson<AlertSummary>(`${BASE_URL}/alerts/summary`),
  updateAlertStatus: (alertId: number, status: string) =>
    fetchJson<SafetyAlert>(`${BASE_URL}/alerts/${alertId}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  triggerScan: (limit = 1000) => fetchJson<{ scanned_queries: number; alerts_created: number; alerts_aggregated: number }>(`${BASE_URL}/alerts/scan?limit=${limit}`, { method: 'POST' }),
  getAnalyticsOverview: (deviceId?: string, startTime?: string, endTime?: string) => {
    const qp = new URLSearchParams();
    if (deviceId) qp.set('device_id', deviceId);
    if (startTime) qp.set('start_time', startTime);
    if (endTime) qp.set('end_time', endTime);
    return fetchJson<AnalyticsOverview>(`${BASE_URL}/analytics/overview${qp.toString() ? '?' + qp.toString() : ''}`);
  },
  getCategoryDistribution: (deviceId?: string, startTime?: string, endTime?: string) => {
    const qp = new URLSearchParams();
    if (deviceId) qp.set('device_id', deviceId);
    if (startTime) qp.set('start_time', startTime);
    if (endTime) qp.set('end_time', endTime);
    return fetchJson<CategoryDistributionResponse>(`${BASE_URL}/analytics/categories${qp.toString() ? '?' + qp.toString() : ''}`);
  },
  getActiveHours: (deviceId?: string, startTime?: string, endTime?: string) => {
    const qp = new URLSearchParams();
    if (deviceId) qp.set('device_id', deviceId);
    if (startTime) qp.set('start_time', startTime);
    if (endTime) qp.set('end_time', endTime);
    return fetchJson<{ disclaimer: string; hourly_distribution: HourlyActivityItem[] }>(`${BASE_URL}/analytics/active-hours${qp.toString() ? '?' + qp.toString() : ''}`);
  },
  getTimeline: (days = 14, deviceId?: string, startTime?: string, endTime?: string) => {
    const qp = new URLSearchParams({ days: String(days) });
    if (deviceId) qp.set('device_id', deviceId);
    if (startTime) qp.set('start_time', startTime);
    if (endTime) qp.set('end_time', endTime);
    return fetchJson<{ disclaimer: string; timeline: TimelineItem[] }>(`${BASE_URL}/analytics/timeline?${qp.toString()}`);
  },
  getClassifications: (category?: string, limit = 100) => {
    const qp = new URLSearchParams({ limit: String(limit) });
    if (category) qp.set('category', category);
    return fetchJson<DomainClassification[]>(`${BASE_URL}/classifications/domains?${qp.toString()}`);
  },
  classifyDomains: (domains: string[]) =>
    fetchJson<{ results: Array<{ domain: string; category: string; rule_type: string | null; pattern: string | null }> }>(`${BASE_URL}/classifications/classify`, { method: 'POST', body: JSON.stringify({ domains }) }),
  syncClassifications: () => fetchJson<{ classified: number; ai_classified: number; still_unknown: number; no_api_key: boolean; message: string }>(`${BASE_URL}/classifications/sync`, { method: 'POST' }),
  aiClassifyDomain: (domain: string) =>
    fetchJson<DomainClassification>(`${BASE_URL}/classifications/ai-classify/${encodeURIComponent(domain)}`, { method: 'POST' }),
  aiSyncClassifications: (limit = 25) => fetchJson<{ considered: number; ai_classified: number; still_unknown: number; no_api_key: boolean }>(`${BASE_URL}/classifications/ai-sync?limit=${limit}`, { method: 'POST' }),
  overrideClassification: (domain: string, category: string, note?: string) =>
    fetchJson<DomainClassification>(`${BASE_URL}/classifications/domains/${encodeURIComponent(domain)}/override`, { method: 'PUT', body: JSON.stringify({ category, note }) }),
  getDomainSecurity: (deviceId?: string, limit = 20, startTime?: string, endTime?: string) => {
    const qp = new URLSearchParams();
    if (deviceId) qp.set('device_id', deviceId);
    if (limit) qp.set('limit', String(limit));
    if (startTime) qp.set('start_date', startTime);
    if (endTime) qp.set('end_date', endTime);
    return fetchJson<DomainSecurityResponse>(`${BASE_URL}/domains/security${qp.toString() ? '?' + qp.toString() : ''}`);
  },
  getDangerousDomains: (deviceId?: string, startTime?: string, endTime?: string) => {
    const qp = new URLSearchParams();
    if (deviceId) qp.set('device_id', deviceId);
    if (startTime) qp.set('start_date', startTime);
    if (endTime) qp.set('end_date', endTime);
    return fetchJson<{ device_id: string | null; total_flagged: number; domains: DangerousDomain[] }>(`${BASE_URL}/domains/dangerous${qp.toString() ? '?' + qp.toString() : ''}`);
  },
  getSubjects: (deviceId?: string, startTime?: string, endTime?: string) => {
    const qp = new URLSearchParams();
    if (deviceId) qp.set('device_id', deviceId);
    if (startTime) qp.set('start_date', startTime);
    if (endTime) qp.set('end_date', endTime);
    return fetchJson<SubjectResponse>(`${BASE_URL}/domains/subjects${qp.toString() ? '?' + qp.toString() : ''}`);
  },
  getTopDomains: (deviceId?: string, limit = 10, startTime?: string, endTime?: string) => {
    const qp = new URLSearchParams();
    if (deviceId) qp.set('device_id', deviceId);
    if (limit) qp.set('limit', String(limit));
    if (startTime) qp.set('start_date', startTime);
    if (endTime) qp.set('end_date', endTime);
    return fetchJson<{ domains: { domain: string; query_count: number }[] }>(`${BASE_URL}/domains/security${qp.toString() ? '?' + qp.toString() : ''}`);
  },
  getOpenRouterCategories: () => fetchJson<{categories: string[]}>(`${BASE_URL}/openrouter/categories`),
  classifyDomainOpenRouter: (domain: string, force = false) => {
    const qp = new URLSearchParams();
    if (force) qp.set('force', 'true');
    return fetchJson<{domain: string; category: string; confidence: number; reason: string; cached: boolean}>(`${BASE_URL}/openrouter/classify/${domain}${qp.toString() ? '?' + qp.toString() : ''}`);
  },
  classifyBatchOpenRouter: (domains: string[]) => fetchJson<{results: Record<string, {category: string; confidence: number; reason: string; cached: boolean}>}>(`${BASE_URL}/openrouter/classify-batch`, { method: 'POST', body: JSON.stringify({ domains }) }),
  getOpenRouterApiKeyStatus: () => fetchJson<{configured: boolean; models?: Array<{model: string; preferred: boolean; cooling: boolean; retry_in: number}>}>(`${BASE_URL}/openrouter/api-key-status`),
  saveOpenRouterApiKey: (key: string) => fetchJson<{message: string}>(`${BASE_URL}/openrouter/api-key`, { method: 'POST', body: JSON.stringify({ key }) }),
  testOpenRouterApiKey: (key?: string) => fetchJson<{ok: boolean; label?: string | null; usage?: number | null; limit?: number | null; error?: string}>(`${BASE_URL}/openrouter/api-key/test`, { method: 'POST', body: JSON.stringify(key ? { key } : {}) }),
  getTopDomainsByCategory: (deviceId?: string, limit = 20) => {
    const qp = new URLSearchParams();
    if (deviceId) qp.set('device_id', deviceId);
    if (limit) qp.set('limit', String(limit));
    return fetchJson<{categories: {category: string; domains: {domain: string; query_count: number}[]; total_queries: number}[]}>(`${BASE_URL}/openrouter/top-domains-by-category${qp.toString() ? '?' + qp.toString() : ''}`);
  },
  login: (password: string) => fetchJson<{ message: string }>(`${BASE_URL}/auth/login`, { method: 'POST', body: JSON.stringify({ password }) }),
  changePassword: (currentPassword: string, newPassword: string) => fetchJson<{ message: string }>(`${BASE_URL}/auth/change-password`, { method: 'PUT', body: JSON.stringify({ currentPassword, newPassword }) }),
  getAuthStatus: () => fetchJson<SessionInfo>(`${BASE_URL}/auth/status`),
  logout: () => fetchJson<{ message: string }>(`${BASE_URL}/auth/logout`, { method: 'POST' }),
  getRouterDnsStatus: () => fetchJson<RouterDnsStatus>(`${BASE_URL}/router-dns/status`),
  setRouterDnsMode: (mode: 'dnsmasq' | 'router') =>
    fetchJson<RouterDnsStatus>(`${BASE_URL}/router-dns/mode`, {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),
};
