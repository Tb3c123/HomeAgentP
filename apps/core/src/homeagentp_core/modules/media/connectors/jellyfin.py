"""Read-only Jellyfin Media Server connector."""

from __future__ import annotations

from typing import Any, Literal

from homeagentp_core.modules.media.base import (
    MediaMalformedResponseError,
    MediaServiceAdapter,
    SafeMediaHttpClient,
    check_semver_major,
)


def _require_dict(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MediaMalformedResponseError(
            f"Expected JSON object from {context}, got {type(payload).__name__}."
        )
    return payload


def _require_list(payload: Any, context: str) -> list[Any]:
    if not isinstance(payload, list):
        raise MediaMalformedResponseError(
            f"Expected JSON array from {context}, got {type(payload).__name__}."
        )
    return payload


def _opt_dict(val: Any) -> dict[str, Any]:
    return val if isinstance(val, dict) else {}


class JellyfinAdapter(MediaServiceAdapter):
    """Read-only Jellyfin Media Server adapter (/System/Info, /Items/Counts, /Sessions)."""

    service_name = "jellyfin"
    title = "Jellyfin Media Server"
    category: Literal["media", "downloads"] = "media"

    ALLOWED_GET_PREFIXES = (
        "/System/Info",
        "/Items/Counts",
        "/Sessions",
        "/System/ActivityLog/Entries",
    )

    def is_configured(self) -> tuple[bool, str]:
        if not self._settings.jellyfin_url.strip():
            return False, "HOMEAGENTP_JELLYFIN_URL is not configured."
        if not self._settings.jellyfin_api_key.strip():
            return False, "HOMEAGENTP_JELLYFIN_API_KEY is not configured."
        return True, ""

    def _empty_metrics(self) -> dict[str, Any]:
        return {
            "server_name": None,
            "operating_system": None,
            "libraries": {
                "movies": None,
                "series": None,
                "episodes": None,
                "songs": None,
                "albums": None,
            },
            "sessions": {
                "active_count": 0,
                "direct_play_count": 0,
                "direct_stream_count": 0,
                "transcoding_count": 0,
                "paused_count": 0,
                "streams": [],
            },
            "playback_errors": {
                "accessible": False,
                "count": 0,
                "recent": [],
            },
        }

    def _poll_live(
        self, now_iso: str
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        token = self._settings.jellyfin_api_key.strip()
        auth_header = (
            'MediaBrowser Client="HomeAgentP", Device="HomeAgentP-Core", '
            f'DeviceId="homeagentp-core", Version="0.1.0", Token="{token}"'
        )
        client = SafeMediaHttpClient(
            base_url=self._settings.jellyfin_url,
            allowed_hosts=self._settings.media_allowed_hosts,
            timeout_seconds=self._settings.media_http_timeout_seconds,
            max_response_bytes=self._settings.media_max_response_bytes,
            allowed_get_prefixes=self.ALLOWED_GET_PREFIXES,
            default_headers={
                "Authorization": auth_header,
                "X-Emby-Token": token,
                "Accept": "application/json",
            },
            transport=self._transport,
        )

        sys_info = _require_dict(client.get_json("/System/Info"), "Jellyfin /System/Info")
        version = str(sys_info.get("Version") or "").strip()
        if not version:
            raise MediaMalformedResponseError(
                "Jellyfin /System/Info response is missing required 'Version' field."
            )
        check_semver_major(version, min_major=10, service_label="Jellyfin")

        counts = _require_dict(client.get_json("/Items/Counts"), "Jellyfin /Items/Counts")
        if "MovieCount" not in counts and "SeriesCount" not in counts:
            raise MediaMalformedResponseError(
                "Jellyfin /Items/Counts response is missing MovieCount/SeriesCount fields."
            )

        raw_sessions = _require_list(client.get_json("/Sessions"), "Jellyfin /Sessions")
        active_streams: list[dict[str, Any]] = []
        direct_play_cnt = 0
        direct_stream_cnt = 0
        transcode_cnt = 0
        paused_cnt = 0

        for sess in raw_sessions:
            if not isinstance(sess, dict):
                continue
            now_playing = sess.get("NowPlayingItem")
            if not isinstance(now_playing, dict):
                continue

            play_state = _opt_dict(sess.get("PlayState"))
            trans_info = _opt_dict(sess.get("TranscodingInfo"))
            play_method_raw = str(play_state.get("PlayMethod") or "").strip()
            if not play_method_raw:
                play_method_raw = "Transcode" if trans_info else "DirectPlay"

            play_method_lower = play_method_raw.lower()
            if play_method_lower == "transcode":
                transcode_cnt += 1
                normalized_method = "Transcode"
            elif play_method_lower == "directstream":
                direct_stream_cnt += 1
                normalized_method = "DirectStream"
            else:
                direct_play_cnt += 1
                normalized_method = "DirectPlay"

            is_paused = bool(play_state.get("IsPaused", False))
            if is_paused:
                paused_cnt += 1

            reasons_raw = trans_info.get("TranscodeReasons")
            transcode_reasons = (
                [str(r) for r in reasons_raw] if isinstance(reasons_raw, list) else []
            )

            active_streams.append(
                {
                    "session_id": str(sess.get("Id") or ""),
                    "user_name": str(sess.get("UserName") or "unknown"),
                    "client": str(sess.get("Client") or "unknown"),
                    "device_name": str(sess.get("DeviceName") or "unknown"),
                    "item_title": str(now_playing.get("Name") or "Unknown Title"),
                    "item_type": str(now_playing.get("Type") or "Unknown"),
                    "series_name": (
                        str(now_playing["SeriesName"])
                        if now_playing.get("SeriesName")
                        else None
                    ),
                    "play_method": normalized_method,
                    "is_paused": is_paused,
                    "video_codec": (
                        str(trans_info["VideoCodec"])
                        if trans_info.get("VideoCodec")
                        else None
                    ),
                    "audio_codec": (
                        str(trans_info["AudioCodec"])
                        if trans_info.get("AudioCodec")
                        else None
                    ),
                    "bitrate": (
                        int(trans_info["Bitrate"])
                        if isinstance(trans_info.get("Bitrate"), int)
                        else None
                    ),
                    "transcode_reasons": transcode_reasons,
                }
            )

        # Optional ActivityLog inspection for playback/transcode errors if permitted by API key
        playback_errors: list[dict[str, Any]] = []
        activity_accessible = False
        try:
            activity_payload = client.get_json(
                "/System/ActivityLog/Entries", params={"limit": 25}
            )
            if isinstance(activity_payload, dict) and isinstance(
                activity_payload.get("Items"), list
            ):
                activity_accessible = True
                for entry in activity_payload["Items"]:
                    if not isinstance(entry, dict):
                        continue
                    severity_str = str(entry.get("Severity") or "").lower()
                    name_str = str(entry.get("Name") or "")
                    type_str = str(entry.get("Type") or "")
                    if severity_str in {"error", "critical"} or (
                        "failed" in name_str.lower() or "error" in type_str.lower()
                    ):
                        playback_errors.append(
                            {
                                "name": name_str,
                                "type": type_str,
                                "severity": str(entry.get("Severity") or "Error"),
                                "date": str(entry.get("Date") or ""),
                                "overview": str(entry.get("ShortOverview") or ""),
                            }
                        )
        except Exception:
            # Scoped non-admin Jellyfin tokens may not have ActivityLog permissions
            activity_accessible = False

        alerts: list[dict[str, Any]] = []
        svc_status = "online"
        reason = "Jellyfin API online."
        if playback_errors:
            svc_status = "degraded"
            reason = f"Jellyfin reported {len(playback_errors)} recent playback/activity error(s)."
            alerts.append(
                {
                    "alert_key": "jellyfin:playback.error",
                    "code": "playback.error",
                    "severity": "warning",
                    "category": "media",
                    "service": "jellyfin",
                    "target": str(sys_info.get("ServerName") or "jellyfin"),
                    "message": (
                        f"Jellyfin logged {len(playback_errors)} playback/activity error(s): "
                        f"{playback_errors[0]['name']}"
                    ),
                    "metric_value": float(len(playback_errors)),
                    "threshold_value": 1.0,
                    "details": {"recent_errors": playback_errors[:5]},
                    "status": "active",
                    "created_at": now_iso,
                }
            )

        metrics = {
            "server_name": str(sys_info.get("ServerName") or "Jellyfin"),
            "operating_system": str(sys_info.get("OperatingSystem") or "unknown"),
            "libraries": {
                "movies": int(counts.get("MovieCount", 0) or 0),
                "series": int(counts.get("SeriesCount", 0) or 0),
                "episodes": int(counts.get("EpisodeCount", 0) or 0),
                "songs": int(counts.get("SongCount", 0) or 0),
                "albums": int(counts.get("AlbumCount", 0) or 0),
            },
            "sessions": {
                "active_count": len(active_streams),
                "direct_play_count": direct_play_cnt,
                "direct_stream_count": direct_stream_cnt,
                "transcoding_count": transcode_cnt,
                "paused_count": paused_cnt,
                "streams": active_streams,
            },
            "playback_errors": {
                "accessible": activity_accessible,
                "count": len(playback_errors),
                "recent": playback_errors[:5],
            },
        }
        return svc_status, version, metrics, alerts, reason
