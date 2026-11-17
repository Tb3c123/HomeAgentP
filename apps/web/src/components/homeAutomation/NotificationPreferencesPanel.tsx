import React, { useEffect, useState } from "react";
import type {
  NotificationEvaluateResponse,
  NotificationPreferences,
  NotificationPreferencesUpdate,
  NotificationSeverity,
} from "../../api/types";
import { StatusBadge } from "../StatusBadge";

interface NotificationPreferencesPanelProps {
  preferences: NotificationPreferences | null;
  isOwner: boolean;
  saveBusy: boolean;
  evaluateBusy: boolean;
  lastEvaluate: NotificationEvaluateResponse | null;
  onSave: (payload: NotificationPreferencesUpdate) => void;
  onEvaluate: () => void;
}

export const NotificationPreferencesPanel: React.FC<NotificationPreferencesPanelProps> = ({
  preferences,
  isOwner,
  saveBusy,
  evaluateBusy,
  lastEvaluate,
  onSave,
  onEvaluate,
}) => {
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [minSeverity, setMinSeverity] = useState<NotificationSeverity>("warning");
  const [notifyOnResolve, setNotifyOnResolve] = useState(true);
  const [cooldownSeconds, setCooldownSeconds] = useState(900);
  const [rateLimitCount, setRateLimitCount] = useState(10);
  const [rateLimitWindowSeconds, setRateLimitWindowSeconds] = useState(300);

  useEffect(() => {
    if (!preferences) return;
    setTelegramEnabled(preferences.telegram_enabled);
    setMinSeverity(preferences.min_severity);
    setNotifyOnResolve(preferences.notify_on_resolve);
    setCooldownSeconds(preferences.cooldown_seconds);
    setRateLimitCount(preferences.rate_limit_count);
    setRateLimitWindowSeconds(preferences.rate_limit_window_seconds);
  }, [preferences]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isOwner) return;
    onSave({
      telegram_enabled: telegramEnabled,
      min_severity: minSeverity,
      notify_on_resolve: notifyOnResolve,
      cooldown_seconds: cooldownSeconds,
      rate_limit_count: rateLimitCount,
      rate_limit_window_seconds: rateLimitWindowSeconds,
    });
  };

  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <div className="section-header">
        <div>
          <h3>Telegram Notification Preferences</h3>
          <p className="muted">
            Outbound-only alert delivery. Bot token and chat IDs are configured via environment only and never exposed.
          </p>
        </div>
        {preferences && (
          <StatusBadge value={preferences.telegram_configured ? "available" : "not_configured"} />
        )}
      </div>

      {!preferences ? (
        <p className="muted">Loading notification preferences...</p>
      ) : (
        <>
          {!preferences.telegram_configured && (
            <div className="banner-notice" role="status" style={{ marginBottom: "0.85rem" }}>
              <strong>Telegram Not Configured / Disabled:</strong> Runtime Telegram delivery is
              disabled or missing a bot token / allowlisted destination chat ID (
              {preferences.destination_count} configured). Local alert history continues normally.
            </div>
          )}

          {!isOwner && (
            <p className="muted" style={{ marginBottom: "0.75rem" }}>
              Viewer role: notification preferences are read-only.
            </p>
          )}

          <form onSubmit={handleSubmit} className="grid" style={{ gap: "0.75rem" }}>
            <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <input
                  type="checkbox"
                  checked={telegramEnabled}
                  disabled={!isOwner}
                  onChange={(e) => setTelegramEnabled(e.target.checked)}
                />
                Enable Telegram Delivery Preference
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <input
                  type="checkbox"
                  checked={notifyOnResolve}
                  disabled={!isOwner}
                  onChange={(e) => setNotifyOnResolve(e.target.checked)}
                />
                Notify on Alert Resolve
              </label>
            </div>

            <div className="grid grid-3" style={{ gap: "0.75rem" }}>
              <div>
                <label htmlFor="notif-min-severity">Minimum Severity</label>
                <select
                  id="notif-min-severity"
                  className="input"
                  value={minSeverity}
                  disabled={!isOwner}
                  onChange={(e) => setMinSeverity(e.target.value as NotificationSeverity)}
                >
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <div>
                <label htmlFor="notif-cooldown">Cooldown (seconds)</label>
                <input
                  id="notif-cooldown"
                  className="input"
                  type="number"
                  min={0}
                  max={86400}
                  value={cooldownSeconds}
                  disabled={!isOwner}
                  onChange={(e) => setCooldownSeconds(Number(e.target.value))}
                />
              </div>
              <div>
                <label htmlFor="notif-rate-limit">Rate Limit (max / window sec)</label>
                <div style={{ display: "flex", gap: "0.4rem" }}>
                  <input
                    id="notif-rate-limit"
                    aria-label="Rate Limit Count"
                    className="input"
                    type="number"
                    min={1}
                    max={200}
                    value={rateLimitCount}
                    disabled={!isOwner}
                    onChange={(e) => setRateLimitCount(Number(e.target.value))}
                  />
                  <input
                    aria-label="Rate Limit Window Seconds"
                    className="input"
                    type="number"
                    min={10}
                    max={86400}
                    value={rateLimitWindowSeconds}
                    disabled={!isOwner}
                    onChange={(e) => setRateLimitWindowSeconds(Number(e.target.value))}
                  />
                </div>
              </div>
            </div>

            {isOwner && (
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <button type="submit" className="btn-primary" disabled={saveBusy}>
                  {saveBusy ? "Saving..." : "Save Preferences"}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={evaluateBusy}
                  onClick={onEvaluate}
                >
                  {evaluateBusy ? "Evaluating..." : "Evaluate Alerts Now"}
                </button>
              </div>
            )}

            {lastEvaluate && (
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                Last evaluation: enqueued {lastEvaluate.enqueued}, cooldown-suppressed{" "}
                {lastEvaluate.suppressed_cooldown}, overflow-suppressed{" "}
                {lastEvaluate.suppressed_overflow}, skipped-disabled {lastEvaluate.skipped_disabled}.
              </p>
            )}
          </form>
        </>
      )}
    </div>
  );
};
