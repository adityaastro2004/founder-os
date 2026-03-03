"use client";

import { useCallback, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

/**
 * Hook that returns a **stable** authenticated API fetcher.
 *
 * The returned function reference never changes between renders,
 * preventing infinite re-fetch loops in useEffect/useCallback deps.
 *
 * Usage:
 *   const api = useApi();
 *   const data = await api("/api/me");
 */
export function useApi() {
  const { getToken } = useAuth();

  // Keep a mutable ref so the callback identity never changes
  const getTokenRef = useRef(getToken);
  getTokenRef.current = getToken;

  const fetchWithAuth = useCallback(
    async (
      path: string,
      options: RequestInit & { direct?: boolean; timeoutMs?: number } = {}
    ) => {
      const token = await getTokenRef.current();
      return apiFetch(path, { ...options, token });
    },
    [] // stable — never changes
  );

  return fetchWithAuth;
}
