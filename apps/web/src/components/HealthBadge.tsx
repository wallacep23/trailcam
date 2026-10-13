import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

/** Header indicator: API reachable, DB up, extensions installed, schema at head. */
export function HealthBadge() {
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await api.GET("/api/v1/health")).data ?? null,
    refetchInterval: 10_000,
  });
  const status = isError || !data ? "down" : data.status;
  const tone =
    status === "ok" ? "bg-moss-400" : status === "degraded" ? "bg-lamp-500" : "bg-ember-400";
  const failing = data?.checks.filter((c) => !c.ok).map((c) => c.name) ?? [];
  const title =
    status === "ok"
      ? `API ${data?.version} · schema ${data?.schema_revision}`
      : status === "down"
        ? "API or database unreachable"
        : `Degraded: ${failing.join(", ")}`;
  return (
    <span className="flex items-center gap-2 text-xs text-bark-300" title={title}>
      <span className={`size-2 rounded-full ${tone}`} />
      {status === "ok" ? "System OK" : status === "down" ? "Offline" : "Degraded"}
    </span>
  );
}
