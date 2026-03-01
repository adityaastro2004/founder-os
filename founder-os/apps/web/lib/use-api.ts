"use client";

import { useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

/**
 * Hook that returns an authenticated API fetcher.
 * Automatically attaches the current Clerk session token.
 *
 * Usage:
 *   const api = useApi();
 *   const data = await api("/api/me");
 */
export function useApi() {
  const { getToken } = useAuth();

  async function fetchWithAuth(path: string, options: RequestInit = {}) {
    const token = await getToken();
    return apiFetch(path, { ...options, token });
  }

  return fetchWithAuth;
}
