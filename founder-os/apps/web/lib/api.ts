const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Authenticated fetch wrapper.
 * Passes the Clerk session token as a Bearer token to the FastAPI backend.
 */
export async function apiFetch(
  path: string,
  options: RequestInit & { token?: string | null } = {}
) {
  const { token, headers, ...rest } = options;

  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }

  return res.json();
}
