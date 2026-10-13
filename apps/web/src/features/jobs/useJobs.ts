import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type JobStatus, unwrap } from "../../lib/api";

export const JOBS_KEY = ["jobs"] as const;

export function useJobs(status: JobStatus | null) {
  return useQuery({
    queryKey: [...JOBS_KEY, "list", status],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/jobs", {
          params: { query: { limit: 100, ...(status ? { status: [status] } : {}) } },
        }),
      ),
    refetchInterval: 2000,
  });
}

export function useJobStats() {
  return useQuery({
    queryKey: [...JOBS_KEY, "stats"],
    queryFn: async () => unwrap(await api.GET("/api/v1/jobs/stats")),
    refetchInterval: 2000,
  });
}

export function useJobActions() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: JOBS_KEY });

  const runSelftest = useMutation({
    mutationFn: async (failOnce: boolean) =>
      unwrap(
        await api.POST("/api/v1/jobs", {
          body: {
            type: "system.selftest",
            payload: { steps: 10, sleep_s: 0.4, fail_times: failOnce ? 1 : 0 },
          },
        }),
      ),
    onSuccess: invalidate,
  });
  const retry = useMutation({
    mutationFn: async (jobId: string) =>
      unwrap(await api.POST("/api/v1/jobs/{job_id}/retry", { params: { path: { job_id: jobId } } })),
    onSuccess: invalidate,
  });
  const cancel = useMutation({
    mutationFn: async (jobId: string) =>
      unwrap(await api.POST("/api/v1/jobs/{job_id}/cancel", { params: { path: { job_id: jobId } } })),
    onSuccess: invalidate,
  });
  return { runSelftest, retry, cancel };
}
