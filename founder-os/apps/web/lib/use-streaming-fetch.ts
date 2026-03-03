"use client";

import { useRef, useCallback, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";

/**
 * Hook for streaming text responses from the API.
 * Uses fetch + ReadableStream for progressive text delivery.
 *
 * For endpoints that return a normal JSON response (not SSE),
 * this collects the full body. For actual streaming endpoints,
 * it progressively yields chunks.
 */
export function useStreamingFetch() {
  const { getToken } = useAuth();
  const abortRef = useRef<AbortController | null>(null);
  const getTokenRef = useRef(getToken);
  getTokenRef.current = getToken;

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // Abort in-flight request on unmount
  useEffect(() => cancel, [cancel]);

  const streamFetch = useCallback(
    async (
      path: string,
      options: {
        method?: string;
        body?: unknown;
        onChunk?: (text: string) => void;
        onDone?: (fullText: string) => void;
        onError?: (err: Error) => void;
      } = {}
    ) => {
      cancel();

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const token = await getTokenRef.current();

        const res = await fetch(path, {
          method: options.method || "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: options.body ? JSON.stringify(options.body) : undefined,
          signal: controller.signal,
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `API error ${res.status}`);
        }

        const contentType = res.headers.get("content-type") || "";

        // If it's JSON, parse and return directly
        if (contentType.includes("application/json")) {
          const json = await res.json();
          const text = json.content || JSON.stringify(json);
          options.onChunk?.(text);
          options.onDone?.(text);
          return json;
        }

        // Stream text/event-stream or text/plain responses
        const reader = res.body?.getReader();
        if (!reader) throw new Error("No readable stream");

        const decoder = new TextDecoder();
        let fullText = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });

          // Handle SSE format
          if (contentType.includes("text/event-stream")) {
            const lines = chunk.split("\n");
            for (const line of lines) {
              if (line.startsWith("data: ")) {
                try {
                  const data = JSON.parse(line.slice(6));
                  const text = data.content || data.text || "";
                  if (text) {
                    fullText += text;
                    options.onChunk?.(fullText);
                  }
                } catch {
                  // Non-JSON SSE line
                }
              }
            }
          } else {
            fullText += chunk;
            options.onChunk?.(fullText);
          }
        }

        options.onDone?.(fullText);
        return fullText;
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        const e = err instanceof Error ? err : new Error(String(err));
        options.onError?.(e);
        throw e;
      }
    },
    [cancel] // stable — getToken accessed via ref
  );

  return { streamFetch, cancel };
}
