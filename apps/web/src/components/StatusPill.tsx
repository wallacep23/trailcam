import type { JobStatus } from "../lib/api";

const STYLES: Record<JobStatus, string> = {
  queued: "bg-sky-400/10 text-sky-400 ring-sky-400/30",
  running: "bg-lamp-500/15 text-lamp-400 ring-lamp-500/40",
  succeeded: "bg-moss-400/10 text-moss-400 ring-moss-400/30",
  failed: "bg-ember-400/10 text-ember-400 ring-ember-400/30",
  cancelled: "bg-bark-700/40 text-bark-300 ring-bark-500/30",
};

export function StatusPill({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}
    >
      {status === "running" && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
      {status}
    </span>
  );
}
