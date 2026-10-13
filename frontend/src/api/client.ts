/** Thin fetch wrapper for the CancerBioMap REST API (proxied to FastAPI under /api). */

export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
  }
}

export type QueryValue = string | number | boolean | null | undefined;

export function buildQuery(params: Record<string, QueryValue>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    let details: unknown;
    try {
      const body = await res.json();
      message = body?.error?.message ?? message;
      details = body?.error?.details;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message, details);
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string, params: Record<string, QueryValue> = {}, signal?: AbortSignal) {
  return handle<T>(await fetch(`/api${path}${buildQuery(params)}`, { signal }));
}

export async function apiPost<T>(path: string, body?: FormData, params: Record<string, QueryValue> = {},
                                 headers: Record<string, string> = {}) {
  return handle<T>(await fetch(`/api${path}${buildQuery(params)}`, { method: "POST", body, headers }));
}

/** URL for a CSV export; the browser downloads it directly. */
export function exportUrl(dataset: string, params: Record<string, QueryValue> = {}) {
  return `/api/export/${dataset}${buildQuery(params)}`;
}
