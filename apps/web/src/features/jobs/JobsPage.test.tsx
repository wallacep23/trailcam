import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Job } from "../../lib/api";
import { JobsPage } from "./JobsPage";

const NOW = new Date().toISOString();

function job(overrides: Partial<Job>): Job {
  return {
    id: "0190a000-0000-7000-8000-00000000abcd",
    type: "system.selftest",
    status: "queued",
    payload: {},
    priority: 0,
    attempts: 0,
    max_attempts: 3,
    dedupe_key: null,
    error: null,
    progress: null,
    result: null,
    run_after: NOW,
    locked_by: null,
    heartbeat_at: null,
    started_at: null,
    finished_at: null,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

const JOBS = [
  job({ id: "0190a000-0000-7000-8000-000000000001", status: "running", attempts: 1, progress: { done: 5, total: 10, fraction: 0.5, message: "step 5 of 10" } }),
  job({ id: "0190a000-0000-7000-8000-000000000002", status: "failed", attempts: 3, error: "SelfTestError: boom" }),
];

function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("JobsPage", () => {
  const calls: { method: string; url: string }[] = [];

  beforeEach(() => {
    calls.length = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: Request) => {
        const url = new URL(input.url);
        calls.push({ method: input.method, url: url.pathname + url.search });
        if (url.pathname === "/api/v1/jobs/stats") {
          return respond({ counts: { queued: 0, running: 1, succeeded: 0, failed: 1, cancelled: 0 } });
        }
        if (url.pathname === "/api/v1/jobs" && input.method === "GET") {
          return respond({ items: JOBS, total: 2, limit: 100, offset: 0 });
        }
        if (url.pathname.endsWith("/retry")) return respond(job({ status: "queued" }));
        if (url.pathname === "/api/v1/jobs" && input.method === "POST") return respond(job({}), 201);
        return respond({ detail: "not found" }, 404);
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  function renderPage() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <JobsPage />
      </QueryClientProvider>,
    );
  }

  it("lists jobs with status, progress and attempts", async () => {
    renderPage();
    const running = await screen.findByText("running", { selector: "span" });
    const row = running.closest("tr")!;
    expect(within(row).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    expect(within(row).getByText("1/3")).toBeInTheDocument();
    expect(screen.getByText("3/3")).toBeInTheDocument();
  });

  it("retries a failed job through the generated client", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(calls).toContainEqual({ method: "POST", url: "/api/v1/jobs/0190a000-0000-7000-8000-000000000002/retry" });
  });

  it("queues a self-test", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Run self-test" }));
    expect(calls).toContainEqual({ method: "POST", url: "/api/v1/jobs" });
  });

  it("filters by status", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /^failed/ }));
    expect(calls.some((c) => c.url === "/api/v1/jobs?limit=100&status=failed")).toBe(true);
  });
});
