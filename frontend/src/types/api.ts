export interface HealthStatus {
  status: string;
  version: string;
  dns_daemon_alive: boolean;
  database_path: string;
  device_count: number;
  query_count: number;
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

export interface SessionInfo {
  authenticated: boolean;
  auth_enabled: boolean;
  expires_at: string | null;
}

export interface DevicePrivacy {
  device_id: string;
  visible_in_analytics: boolean;
  reason: string | null;
}

export type RealtimeEventType = 'dns_activity' | 'safety_alert' | 'device_status' | 'connected' | 'pong';

export interface RealtimeEvent<T = any> {
  type: RealtimeEventType;
  timestamp: string;
  data: T;
}

