export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "unavailable";
  const gib = bytes / (1024 * 1024 * 1024);
  if (gib >= 1) return `${gib.toFixed(2)} GiB`;
  const mib = bytes / (1024 * 1024);
  return `${mib.toFixed(1)} MiB`;
}

export function formatSpeedBps(bytesPerSec: number | null | undefined): string {
  if (bytesPerSec === null || bytesPerSec === undefined) return "unavailable";
  const mib = bytesPerSec / (1024 * 1024);
  if (mib >= 1) return `${mib.toFixed(2)} MiB/s`;
  const kib = bytesPerSec / 1024;
  return `${kib.toFixed(1)} KiB/s`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "unavailable";
  return `${value.toFixed(1)}%`;
}
