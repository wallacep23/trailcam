import createClient from "openapi-fetch";

import type { components, paths } from "../api/schema";

/**
 * Typed API client. Types come from `src/api/schema.d.ts`, which `pnpm gen:api` generates from
 * the backend's OpenAPI document, so the frontend and backend cannot drift (DESIGN §6).
 * Paths are absolute (`/api/v1/...`); Vite proxies `/api` to the API service in development.
 */
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  // Resolve fetch at call time (not import time) so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
});

export type Schemas = components["schemas"];
export type Job = Schemas["JobOut"];
export type JobPage = Schemas["JobPage"];
export type JobStatus = Job["status"];
export type Health = Schemas["Health"];

/** Unwrap an openapi-fetch result, throwing a readable error on failure. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data !== undefined) return result.data;
  const detail =
    result.error && typeof result.error === "object" && "detail" in result.error
      ? String((result.error as { detail: unknown }).detail)
      : result.response.statusText;
  throw new Error(`${result.response.status} ${detail}`);
}
