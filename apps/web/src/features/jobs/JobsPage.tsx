import { useState } from "react";

import { ProgressBar } from "../../components/ProgressBar";
import { StatusPill } from "../../components/StatusPill";
import type { Job, JobStatus } from "../../lib/api";
import { duration, relativeTime, shortId } from "../../lib/format";
import { useJobActions, useJobStats, useJobs } from "./useJobs";

const FILTERS: (JobStatus | null)[] = [null, "queued", "running", "succeeded", "failed", "cancelled"];

/** Jobs page (NFR-11): live queue state, progress, errors, retry. */
export function JobsPage() {
  const [filter, setFilter] = useState<JobStatus | null>(null);
  const [failOnce, setFailOnce] = useState(false);
  const jobs = useJobs(filter);
  const stats = useJobStats();
  const { runSelftest, retry, cancel } = useJobActions();

  return (
    <section className="mx-auto max-w-6xl">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Jobs</h1>
          <p className="mt-1 text-sm text-bark-300">
            Pipeline work queued by the API and run by the worker. Refreshes every 2 seconds.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-bark-300">
            <input
              type="checkbox"
              className="accent-lamp-500"
              checked={failOnce}
              onChange={(e) => setFailOnce(e.target.checked)}
            />
            fail first attempt
          </label>
          <button
            type="button"
            onClick={() => runSelftest.mutate(failOnce)}
            disabled={runSelftest.isPending}
            className="rounded-md bg-lamp-500 px-3 py-1.5 text-sm font-medium text-bark-950 hover:bg-lamp-400 disabled:opacity-50"
          >
            Run self-test
          </button>
        </div>
      </header>

      <nav className="mt-6 flex flex-wrap gap-1.5" aria-label="Filter by status">
        {FILTERS.map((f) => {
          const count = f ? stats.data?.counts[f] : undefined;
          const active = f === filter;
          return (
            <button
              key={f ?? "all"}
              type="button"
              aria-pressed={active}
              onClick={() => setFilter(f)}
              className={`rounded-full px-3 py-1 text-xs ring-1 ring-inset ${
                active
                  ? "bg-bark-100 text-bark-950 ring-bark-100"
                  : "text-bark-300 ring-bark-700 hover:text-bark-100"
              }`}
            >
              {f ?? "all"}
              {count !== undefined && <span className="ml-1.5 tabular-nums opacity-70">{count}</span>}
            </button>
          );
        })}
      </nav>

      {(runSelftest.error ?? retry.error ?? cancel.error) && (
        <p role="alert" className="mt-4 rounded-md bg-ember-400/10 px-3 py-2 text-sm text-ember-400">
          {String((runSelftest.error ?? retry.error ?? cancel.error)?.message)}
        </p>
      )}

      <div className="mt-4 overflow-x-auto rounded-lg ring-1 ring-bark-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-bark-900 text-xs uppercase tracking-wider text-bark-500">
            <tr>
              <th className="px-3 py-2 font-medium">Job</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Progress</th>
              <th className="px-3 py-2 font-medium">Attempts</th>
              <th className="px-3 py-2 font-medium">Created</th>
              <th className="px-3 py-2 font-medium">Took</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-bark-800">
            {jobs.isLoading && <EmptyRow text="Loading…" />}
            {jobs.isError && <EmptyRow text={`Could not load jobs: ${jobs.error.message}`} />}
            {jobs.data?.items.length === 0 && (
              <EmptyRow text="No jobs yet. Run a self-test to see the queue at work." />
            )}
            {jobs.data?.items.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                onRetry={() => retry.mutate(job.id)}
                onCancel={() => cancel.mutate(job.id)}
              />
            ))}
          </tbody>
        </table>
      </div>
      {jobs.data && jobs.data.total > jobs.data.items.length && (
        <p className="mt-2 text-xs text-bark-500">
          Showing {jobs.data.items.length} of {jobs.data.total}.
        </p>
      )}
    </section>
  );
}

function EmptyRow({ text }: { text: string }) {
  return (
    <tr>
      <td colSpan={7} className="px-3 py-10 text-center text-bark-500">
        {text}
      </td>
    </tr>
  );
}

function JobRow({ job, onRetry, onCancel }: { job: Job; onRetry: () => void; onCancel: () => void }) {
  const [open, setOpen] = useState(false);
  const canRetry = job.status === "failed" || job.status === "cancelled";
  return (
    <>
      <tr className="align-middle hover:bg-bark-900/60">
        <td className="px-3 py-2">
          <div className="font-mono text-xs text-bark-100">{job.type}</div>
          <div className="font-mono text-[11px] text-bark-500">{shortId(job.id)}</div>
        </td>
        <td className="px-3 py-2">
          <StatusPill status={job.status} />
        </td>
        <td className="px-3 py-2">
          {job.progress ? (
            <ProgressBar fraction={job.progress.fraction} label={job.progress.message} />
          ) : job.status === "queued" && job.attempts > 0 ? (
            <span className="text-xs text-bark-300">retry {relativeTime(job.run_after)}</span>
          ) : (
            <span className="text-xs text-bark-500">—</span>
          )}
        </td>
        <td className="px-3 py-2 tabular-nums text-bark-300">
          {job.attempts}/{job.max_attempts}
        </td>
        <td className="px-3 py-2 text-xs text-bark-300">{relativeTime(job.created_at)}</td>
        <td className="px-3 py-2 text-xs tabular-nums text-bark-300">
          {duration(job.started_at, job.finished_at)}
        </td>
        <td className="space-x-2 whitespace-nowrap px-3 py-2 text-right">
          {job.error && (
            <button type="button" className="text-xs text-bark-300 hover:text-bark-100" onClick={() => setOpen(!open)}>
              {open ? "hide error" : "error"}
            </button>
          )}
          {canRetry && (
            <button type="button" className="text-xs font-medium text-lamp-400 hover:text-lamp-500" onClick={onRetry}>
              Retry
            </button>
          )}
          {job.status === "queued" && (
            <button type="button" className="text-xs text-bark-300 hover:text-ember-400" onClick={onCancel}>
              Cancel
            </button>
          )}
        </td>
      </tr>
      {open && job.error && (
        <tr>
          <td colSpan={7} className="bg-bark-900 px-3 py-2">
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-ember-400">
              {job.error}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}
