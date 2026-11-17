export interface NasPsiWindow {
  avg10: number;
  avg60: number;
  avg300: number;
  total_us: number;
}

export interface NasMountStatus {
  path: string;
  required: boolean;
  status:
    | "mounted"
    | "missing"
    | "unmounted_fallback"
    | "permission_denied"
    | "error"
    | "unavailable";
  is_mounted: boolean;
  is_root_fallback: boolean;
  device: string;
  fstype: string;
  total_bytes: number | null;
  available_bytes: number | null;
  used_bytes: number | null;
  usage_percent: number | null;
  reason: string;
}

export interface NasContainerService {
  name: string;
  status: string;
  state: string;
  memory_bytes: number | null;
  memory_limit_bytes: number | null;
  memory_percent: number | null;
  restart_count: number | null;
  reason: string;
}

export interface NasAlertItem {
  id?: number;
  alert_key: string;
  code?: string;
  severity: "warning" | "critical";
  category: string;
  component?: string;
  target: string;
  message: string;
  metric_value?: number | null;
  threshold_value?: number | null;
  status: string;
  first_seen_at?: string;
  last_seen_at?: string;
  resolved_at?: string | null;
  occurrences?: number;
}

export interface NasStatusResponse {
  status: string;
  adapter_status?: string;
  adapter_enabled: boolean;
  collected_at: string;
  collection_interval_seconds: number;
  history_retention_limit: number;
  reason?: string | null;
  telemetry_boundary?: {
    mode: string;
    source: string;
    schema_version?: string;
    generated_at?: string;
    ttl_seconds?: number;
    age_seconds?: number | null;
    host_verified: boolean;
    fresh: boolean;
    reason?: string | null;
  };
  scheduler?: {
    enabled: boolean;
    running: boolean;
    in_progress?: boolean;
    interval_seconds?: number;
    timeout_seconds?: number;
    last_run_at?: string | null;
    last_success_at?: string | null;
    last_status: string;
    last_error?: string | null;
    run_count?: number;
    skipped_overlap_count?: number;
  };
  thresholds: {
    cpu_warn_percent: number;
    cpu_critical_percent: number;
    ram_warn_percent: number;
    ram_critical_percent: number;
    disk_warn_percent: number;
    disk_critical_percent: number;
    container_mem_warn_percent: number;
    container_mem_critical_percent: number;
  };
  cpu: {
    status: string;
    usage_percent: number | null;
    logical_cores: number | null;
    load_1m: number | null;
    load_5m: number | null;
    load_15m: number | null;
    pressure: {
      status?: string;
      some: NasPsiWindow | null;
      full: NasPsiWindow | null;
    };
    reason?: string | null;
  };
  memory: {
    status: string;
    total_bytes: number | null;
    available_bytes: number | null;
    used_bytes: number | null;
    usage_percent: number | null;
    swap_total_bytes: number | null;
    swap_free_bytes: number | null;
    swap_used_bytes: number | null;
    swap_usage_percent: number | null;
    pressure: {
      status?: string;
      some: NasPsiWindow | null;
      full: NasPsiWindow | null;
    };
    reason?: string | null;
  };
  mounts: Record<string, NasMountStatus>;
  containers: {
    status: string;
    docker_socket_mounted: boolean;
    source: string;
    schema_version?: string | null;
    generated_at?: string | null;
    ttl_seconds?: number;
    age_seconds?: number | null;
    fresh?: boolean;
    collected_at?: string;
    services: Record<string, NasContainerService>;
    reason: string;
  };
  alerts: NasAlertItem[];
  storage_safety: {
    hdd_write_operations: number;
    media_tree_crawled: boolean;
    docker_socket_used: boolean;
  };
}

export interface NasHistoryItem {
  id: number;
  collected_at: string;
  adapter_status: string;
  cpu_usage_percent: number | null;
  load_1m: number | null;
  load_5m: number | null;
  load_15m: number | null;
  ram_total_bytes: number | null;
  ram_available_bytes: number | null;
  ram_used_bytes: number | null;
  ram_usage_percent: number | null;
  swap_total_bytes: number | null;
  swap_used_bytes: number | null;
  swap_usage_percent: number | null;
}
