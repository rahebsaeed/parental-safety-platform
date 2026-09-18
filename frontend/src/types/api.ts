export interface HealthStatus {
  status: string;
  version: string;
  dns_daemon_alive: boolean;
  database_path: string;
  device_count: number;
  query_count: number;
}

export interface SessionInfo {
  user_id: string | null;
  username: string | null;
  token: string | null;
  expires_at: string | null;
  authenticated: boolean;
  auth_enabled: boolean;
}

export interface Device {
  device_id: string;
  friendly_name: string | null;
  device_type: string | null;
  primary_mac: string | null;
  mac_is_randomized: boolean | number;
  vendor: string | null;
  status: 'online' | 'offline';
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  first_seen: string;
  last_seen: string;
  current_ip?: string;
  query_count?: number;
  dns_visibility?: 'FULL' | 'PARTIAL';
  is_gateway?: boolean;
}

export interface DeviceAddress {
  id: number;
  ip_address: string;
  mac_address: string | null;
  hostname: string | null;
  vendor: string | null;
  observed_at: string;
}

export interface DeviceStatusEvent {
  id: number;
  status: string;
  occurred_at: string;
}

export interface TopDomain {
  domain: string;
  query_count: number;
}

export interface DeviceDetail extends Device {
  addresses: DeviceAddress[];
  status_events: DeviceStatusEvent[];
  top_domains: TopDomain[];
}

export interface DnsQuery {
  id: number;
  occurred_at: string;
  source_ip: string;
  device_id: string | null;
  domain: string;
  query_type: string;
  response_status: string;
  dns_visibility: string;
}

export interface SafetyAlert {
  id: number;
  device_id: string | null;
  domain: string;
  alert_type: 'UNSAFE_CATEGORY' | 'PHISHING_SUSPICIOUS' | 'BYPASS_ATTEMPT' | 'ANOMALOUS_BURST';
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  title: string;
  description: string;
  rule_matched: string;
  explanation: string;
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'DISMISSED' | 'RESOLVED';
  occurrence_count: number;
  created_at: string;
  last_seen_at: string;
}

export interface AlertSummary {
  total_alerts: number;
  active_alerts: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
}

export interface CategoryDistributionItem {
  category: string;
  label: string;
  color: string;
  icon: string;
  query_count: number;
  distinct_domains: number;
  percentage: number;
}

export interface CategoryDistributionResponse {
  disclaimer: string;
  device_id: string | null;
  total_queries: number;
  categories: CategoryDistributionItem[];
}

export interface AnalyticsOverview {
  disclaimer: string;
  device_id: string | null;
  total_queries: number;
  distinct_domains: number;
  active_devices: number;
  top_category: string;
}

export interface HourlyActivityItem {
  hour: number;
  query_count: number;
}

export interface TimelineItem {
  date: string;
  query_count: number;
  active_devices_count: number;
}

export interface DomainClassification {
  domain: string;
  category: string;
  rule_type: string | null;
  pattern: string | null;
  is_override: number;
  note: string | null;
  classified_at: string | null;
}

export interface DomainSecurity {
  domain: string;
  query_count: number;
  unique_devices: number;
  security_level: string;
  security_label: string;
  security_color: string;
  security_icon: string;
  category: string;
  subject: string;
  risk_score: number;
  reason: string;
}

export interface DomainSecurityResponse {
  device_id: string | null;
  total_domains: number;
  domains: DomainSecurity[];
  summary: { safe: number; risky: number; dangerous: number; unknown: number };
}

export interface DangerousDomain {
  domain: string;
  query_count: number;
  security_level: string;
  security_label: string;
  security_color: string;
  category: string;
  subject: string;
  reason: string;
}

export interface SubjectResponse {
  device_id: string | null;
  total_queries: number;
  subjects: { subject: string; query_count: number }[];
}

export interface OpenRouterCategory {
  category: string;
  confidence: number;
  reason: string;
  cached: boolean;
}

export type RouterDnsMode = 'dnsmasq' | 'router' | 'custom' | 'unknown' | 'unreachable';

export interface RouterDnsStatus {
  mode: RouterDnsMode;
  pridns: string | null;
  secdns: string | null;
  dnsmasq_ip: string;
  router_ip: string;
  max_hours: number;
  enabled_at: string | null;
  expires_at: string | null;
  seconds_remaining: number | null;
}

export type RealtimeEventType = 'dns_activity' | 'safety_alert' | 'device_status' | 'connected' | 'pong';

export interface RealtimeEvent<T = any> {
  type: RealtimeEventType;
  timestamp: string;
  data: T;
}

