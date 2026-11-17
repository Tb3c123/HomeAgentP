export interface MediaAlertItem {
  id?: number;
  alert_key: string;
  code: string;
  severity: "warning" | "critical";
  category: string;
  service: string;
  target: string;
  message: string;
  metric_value?: number | null;
  threshold_value?: number | null;
  status: string;
  first_seen_at?: string;
  last_seen_at?: string;
  resolved_at?: string | null;
  occurrences?: number;
  created_at?: string;
}

export interface JellyfinStreamSession {
  session_id: string;
  user_name: string;
  client: string;
  device_name: string;
  item_title: string;
  item_type: string;
  series_name?: string | null;
  play_method: "DirectPlay" | "DirectStream" | "Transcode";
  is_paused: boolean;
  video_codec?: string | null;
  audio_codec?: string | null;
  bitrate?: number | null;
  transcode_reasons: string[];
}

export interface QBittorrentQueueItem {
  hash: string;
  name: string;
  state: string;
  progress_percent: number;
  dlspeed_bytes?: number;
  upspeed_bytes?: number;
  eta_seconds?: number;
  time_active_seconds?: number;
  idle_seconds?: number;
  exceeds_threshold?: boolean;
  error_kind?: string;
  size_bytes?: number;
}

export interface ArrQueueItem {
  id: number;
  title: string;
  status: string;
  tracked_download_status: string;
  tracked_download_state: string;
  error_message: string;
  protocol: string;
  download_client: string;
}

export interface SeerrRecentRequestItem {
  id: number;
  media_type: string;
  status: string;
  requested_by: string;
  tmdb_id: number | null;
  created_at: string;
}

export interface MediaServiceSnapshot<TMetrics = Record<string, unknown>> {
  service: string;
  title: string;
  category: "media" | "downloads";
  enabled: boolean;
  configured: boolean;
  status: string;
  error_code: string | null;
  reason: string;
  latency_ms: number | null;
  version: string | null;
  collected_at: string;
  stale: boolean;
  age_seconds: number;
  consecutive_failures: number;
  read_only_enforced: boolean;
  write_operations_performed: number;
  metrics: TMetrics;
  alerts: MediaAlertItem[];
}

export interface JellyfinMetrics {
  server_name: string | null;
  operating_system: string | null;
  libraries: {
    movies: number | null;
    series: number | null;
    episodes: number | null;
    songs: number | null;
    albums: number | null;
  };
  sessions: {
    active_count: number;
    direct_play_count: number;
    direct_stream_count: number;
    transcoding_count: number;
    paused_count: number;
    streams: JellyfinStreamSession[];
  };
  playback_errors: {
    accessible: boolean;
    count: number;
    recent: Array<{
      name: string;
      type: string;
      severity: string;
      date: string;
      overview: string;
    }>;
  };
}

export interface QBittorrentMetrics {
  webapi_version: string | null;
  connection_status: string;
  dht_nodes: number | null;
  download_speed_bytes: number | null;
  upload_speed_bytes: number | null;
  downloaded_session_bytes: number | null;
  uploaded_session_bytes: number | null;
  counts: {
    total: number;
    downloading: number;
    seeding: number;
    paused: number;
    stalled: number;
    stalled_over_threshold: number;
    queued: number;
    checking: number;
    errored: number;
  };
  stalled_threshold_seconds: number;
  stalled_torrents: QBittorrentQueueItem[];
  errored_torrents: QBittorrentQueueItem[];
  active_queue: QBittorrentQueueItem[];
  credential_scope_notice: string;
}

export interface ArrV3Metrics {
  total_count: number | null;
  monitored_count: number | null;
  available_file_count: number | null;
  size_on_disk_bytes: number | null;
  missing_count: number | null;
  queue_total: number;
  queue_failed_count: number;
  queue_items: ArrQueueItem[];
  failed_imports: ArrQueueItem[];
  health_warnings: Array<{ source: string; type: string; message: string }>;
  diskspace: Array<{
    path: string;
    label: string;
    free_bytes: number | null;
    total_bytes: number | null;
  }>;
}

export interface BazarrMetrics {
  missing_episode_subtitles: number | null;
  missing_movie_subtitles: number | null;
  unhealthy_providers_count: number;
  sonarr_signalr: string | null;
  radarr_signalr: string | null;
  health_issues: Array<{ object: string; issue: string }>;
}

export interface ProwlarrMetrics {
  total_indexers: number | null;
  enabled_indexers: number | null;
  failing_indexers_count: number;
  failing_indexers: Array<{
    indexer_id: number;
    name: string;
    disabled_till: string;
    most_recent_failure: string;
  }>;
  health_warnings: Array<{ source: string; type: string; message: string }>;
}

export interface SeerrMetrics {
  update_available: boolean | null;
  commits_behind: number | null;
  requests: {
    total: number | null;
    movie: number | null;
    tv: number | null;
    pending: number | null;
    approved: number | null;
    processing: number | null;
    available: number | null;
    declined: number | null;
  };
  recent_requests: SeerrRecentRequestItem[];
}

export interface MediaOverviewResponse {
  snapshot_id?: number;
  status: string;
  overall_status: string;
  adapter_enabled: boolean;
  collected_at: string;
  collection_interval_seconds: number;
  history_retention_limit: number;
  failure_threshold: number;
  snapshot_stale_seconds: number;
  reason: string;
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
  summary: {
    configured_services_count: number;
    online_services_count: number;
    jellyfin_active_streams: number;
    jellyfin_direct_play_streams: number;
    jellyfin_transcoding_streams: number;
    qb_download_speed_bytes: number | null;
    qb_upload_speed_bytes: number | null;
    qb_downloading_count: number;
    qb_seeding_count: number;
    qb_stalled_count: number;
    qb_errored_count: number;
    sonarr_queue_count: number;
    sonarr_missing_episodes: number | null;
    radarr_queue_count: number;
    radarr_missing_movies: number | null;
    bazarr_missing_subtitles: number | null;
    prowlarr_failing_indexers: number;
    seerr_pending_requests: number | null;
    seerr_approved_requests: number | null;
  };
  services: {
    jellyfin: MediaServiceSnapshot<JellyfinMetrics>;
    qbittorrent: MediaServiceSnapshot<QBittorrentMetrics>;
    sonarr: MediaServiceSnapshot<ArrV3Metrics>;
    radarr: MediaServiceSnapshot<ArrV3Metrics>;
    bazarr: MediaServiceSnapshot<BazarrMetrics>;
    prowlarr: MediaServiceSnapshot<ProwlarrMetrics>;
    seerr: MediaServiceSnapshot<SeerrMetrics>;
  };
  alerts: MediaAlertItem[];
  safety: {
    read_only_enforced: boolean;
    write_operations_performed: number;
    media_filesystem_mounted: boolean;
    docker_socket_used: boolean;
    ssrf_allowlist_enforced: boolean;
    redirects_blocked: boolean;
    qbittorrent_client_allowlist_only: boolean;
  };
}

export interface MediaHistoryItem {
  id: number;
  collected_at: string;
  overall_status: string;
  jellyfin_active_streams: number;
  jellyfin_transcoding_streams: number;
  qb_dl_speed_bytes: number | null;
  qb_up_speed_bytes: number | null;
  qb_downloading_count: number | null;
  qb_stalled_count: number | null;
  qb_errored_count: number | null;
  sonarr_queue_count: number | null;
  radarr_queue_count: number | null;
  missing_subtitles_count: number | null;
  pending_requests_count: number | null;
}
