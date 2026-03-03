"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { useAuth } from "@clerk/nextjs";

const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_MS = 2000;

/**
 * Hook for consuming Server-Sent Events with Clerk auth.
 *
 * Uses raw fetch + ReadableStream instead of native EventSource
 * because EventSource doesn't support custom headers (Authorization).
 *
 * Usage:
 *   const { lastEvent, connected, error } = useEventSource("/api/activity/stream");
 */
export function useEventSource<T = unknown>(
  path: string,
  {
    enabled = true,
    onEvent,
    onError,
  }: {
    enabled?: boolean;
    onEvent?: (event: T) => void;
    onError?: (err: Error) => void;
  } = {}
) {
  const { getToken } = useAuth();
  const [lastEvent, setLastEvent] = useState<T | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout>>(undefined);
  const attemptsRef = useRef(0);
  const onEventRef = useRef(onEvent);
  const onErrorRef = useRef(onError);
  const getTokenRef = useRef(getToken);
  onEventRef.current = onEvent;
  onErrorRef.current = onError;
  getTokenRef.current = getToken;

  const connect = useCallback(async () => {
    // Clean up any existing connection
    abortRef.current?.abort();

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const token = await getTokenRef.current();

      const res = await fetch(path, {
        headers: {
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new Error(`SSE connection failed: ${res.status}`);
      }

      setConnected(true);
      setError(null);
      attemptsRef.current = 0; // reset on successful connection

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No readable stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6)) as T;
              setLastEvent(data);
              onEventRef.current?.(data);
            } catch {
              // Skip malformed JSON (heartbeats, etc.)
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      const e = err instanceof Error ? err : new Error(String(err));
      setError(e);
      setConnected(false);
      onErrorRef.current?.(e);

      // Auto-reconnect with exponential backoff up to MAX_RECONNECT_ATTEMPTS
      if (attemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = Math.min(BASE_RECONNECT_MS * 2 ** attemptsRef.current, 30000);
        attemptsRef.current += 1;
        reconnectTimeout.current = setTimeout(connect, delay);
      }
    }
  }, [path]); // stable — getToken accessed via ref

  useEffect(() => {
    if (!enabled) return;
    attemptsRef.current = 0;
    connect();

    return () => {
      abortRef.current?.abort();
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      setConnected(false);
    };
  }, [enabled, connect]);

  return { lastEvent, connected, error };
}
