interface Props {
  fraction: number | null | undefined;
  label?: string | null;
}

/** Determinate bar when the fraction is known, a shimmer otherwise. */
export function ProgressBar({ fraction, label }: Props) {
  const pct = fraction == null ? null : Math.round(Math.max(0, Math.min(1, fraction)) * 100);
  return (
    <div className="flex min-w-0 items-center gap-2">
      <div
        className="h-1.5 w-28 shrink-0 overflow-hidden rounded-full bg-bark-800"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
        aria-label={label ?? "progress"}
      >
        <div
          className={`h-full rounded-full bg-lamp-500 transition-[width] duration-500 ${pct == null ? "w-1/3 animate-pulse" : ""}`}
          style={pct == null ? undefined : { width: `${pct}%` }}
        />
      </div>
      <span className="truncate text-xs tabular-nums text-bark-300">
        {pct == null ? (label ?? "") : `${pct}%${label ? ` · ${label}` : ""}`}
      </span>
    </div>
  );
}
