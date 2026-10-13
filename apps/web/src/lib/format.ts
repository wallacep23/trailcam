/** Short relative time such as "12s ago" or "in 3m". */
export function relativeTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const diffS = Math.round((new Date(iso).getTime() - now) / 1000);
  const abs = Math.abs(diffS);
  const [value, unit] =
    abs < 60 ? [abs, "s"] : abs < 3600 ? [Math.round(abs / 60), "m"] : abs < 86400 ? [Math.round(abs / 3600), "h"] : [Math.round(abs / 86400), "d"];
  if (abs < 2) return "just now";
  return diffS < 0 ? `${value}${unit} ago` : `in ${value}${unit}`;
}

/** Duration between two ISO timestamps, e.g. "2.4s" or "3m 10s". */
export function duration(startIso: string | null | undefined, endIso: string | null | undefined): string {
  if (!startIso || !endIso) return "—";
  const s = (new Date(endIso).getTime() - new Date(startIso).getTime()) / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function shortId(id: string): string {
  return id.slice(-8);
}
