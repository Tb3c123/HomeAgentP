export type HaEntityStatus = "online" | "stale" | "unavailable";
export type HaOverviewStatus = "online" | "stale" | "unavailable" | "degraded";

export interface HaEntityStateItem {
  entity_id: string;
  domain: string;
  friendly_name: string;
  state: string;
  attributes: Record<string, string | number | boolean>;
  status: HaEntityStatus;
  last_changed: string | null;
  collected_at: string;
}

export interface HaOverviewResponse {
  status: HaOverviewStatus;
  enabled: boolean;
  reason: string;
  collected_at: string | null;
  entity_count: number;
  entities: HaEntityStateItem[];
}

export type NotificationSeverity = "info" | "warning" | "critical";

export type DeliveryStatus =
  | "pending"
  | "in_flight"
  | "sent"
  | "suppressed_cooldown"
  | "suppressed_rate_limit"
  | "suppressed_overflow"
  | "failed"
  | "dead_letter";

export interface NotificationPreferences {
  telegram_enabled: boolean;
  min_severity: NotificationSeverity;
  notify_on_resolve: boolean;
  cooldown_seconds: number;
  rate_limit_count: number;
  rate_limit_window_seconds: number;
  destination_count: number;
  telegram_configured: boolean;
  updated_by: string;
  updated_at: string;
}

export interface NotificationPreferencesUpdate {
  telegram_enabled: boolean;
  min_severity: NotificationSeverity;
  notify_on_resolve: boolean;
  cooldown_seconds: number;
  rate_limit_count: number;
  rate_limit_window_seconds: number;
}

export interface NotificationDeliveryItem {
  id: number;
  incident_key: string;
  source_domain: "nas" | "media" | "home_assistant" | "system";
  severity: NotificationSeverity;
  channel: "telegram";
  destination_masked: string;
  message_redacted: string;
  status: DeliveryStatus;
  claimed_by: string;
  lease_expires_at: string | null;
  attempt_count: number;
  next_attempt_at: string | null;
  last_error_redacted: string;
  created_at: string;
  sent_at: string | null;
}

export interface NotificationEvaluateResponse {
  enqueued: number;
  suppressed_cooldown: number;
  suppressed_overflow: number;
  skipped_disabled: number;
}
