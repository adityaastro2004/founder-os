/**
 * API URL for server-side calls (direct to FastAPI).
 * Client-side calls use "" so they route through Next.js rewrites proxy.
 */
const API_URL =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : "";

/**
 * Direct URL to FastAPI — bypasses the Next.js rewrite proxy.
 * Use this for long-running requests (>30s) that would timeout through the proxy.
 */
export const DIRECT_API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Authenticated fetch wrapper.
 * Passes the Clerk session token as a Bearer token to the FastAPI backend.
 *
 * Options:
 *  - token: Clerk session token
 *  - direct: if true, bypass the Next.js proxy and call FastAPI directly
 *  - timeoutMs: abort the request after this many milliseconds (0 = no timeout)
 */
export async function apiFetch(
  path: string,
  options: RequestInit & {
    token?: string | null;
    direct?: boolean;
    timeoutMs?: number;
  } = {}
) {
  const { token, headers, direct, timeoutMs, ...rest } = options;

  const base = direct ? DIRECT_API_URL : API_URL;

  // Set up an abort controller for timeout
  let controller: AbortController | undefined;
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  if (timeoutMs && timeoutMs > 0) {
    controller = new AbortController();
    timeoutId = setTimeout(() => controller!.abort(), timeoutMs);
  }

  try {
    // FormData bodies must NOT get a manual Content-Type — the browser sets
    // multipart/form-data with the correct boundary (forcing JSON breaks uploads).
    const isFormData =
      typeof FormData !== "undefined" && rest.body instanceof FormData;

    const res = await fetch(`${base}${path}`, {
      ...rest,
      signal: controller?.signal ?? rest.signal ?? undefined,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `API error ${res.status}`);
    }

    // 204 No Content (e.g. DELETE /api/state/sources/{id}, /api/knowledge/items/{id})
    // has an empty body — res.json() would throw and turn a success into an error.
    if (res.status === 204) return null;
    return res.json();
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(
        "Request timed out — the server is still processing. Check your calendar in a minute."
      );
    }
    throw err;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

/**
 * Raw fetch — returns the Response object (for SSE / streaming).
 */
export async function apiRawFetch(
  path: string,
  options: RequestInit & { token?: string | null } = {}
): Promise<Response> {
  const { token, headers, ...rest } = options;

  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }

  return res;
}
