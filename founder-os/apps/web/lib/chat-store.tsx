"use client";

/**
 * Layout-level chat store.
 *
 * Owns every chat session (orchestrator Chat page + per-agent chat panels)
 * and their in-flight runs. Mounted once in the (dashboard) layout, so
 * navigating between tabs never unmounts it: streams keep flowing, state
 * survives, and pages are thin views over this store. The backend also runs
 * orchestrations to completion and persists them even if the browser
 * disconnects entirely (see /api/agents/orchestrate/stream).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@clerk/nextjs";
import { DIRECT_API_URL, apiErrorMessage } from "@/lib/api";

/* ── Types ─────────────────────────────────────────── */

/** Message shape shared by the Chat page and AgentChatPanel. */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  status?: "sending" | "completed" | "error" | "clarification";
  error?: boolean;
  toolsUsed?: string[];
  tokensUsed?: number;
  durationSeconds?: number;
  meta?: {
    model: string;
    tokens: number;
    duration: number;
    agents_used: string[];
    delegations: number;
    tool_calls: number;
    tool_names: string[];
  };
}

/** Intermediate streaming event from the SSE endpoint. */
export interface StreamingEvent {
  type: string;
  tool_name?: string;
  agent?: string;
  is_error?: boolean;
  duration_ms?: number;
  timestamp?: number;
  // done-event fields
  content?: string;
  model?: string;
  tokens_used?: number;
  tool_calls_made?: number;
  tool_names?: string[];
  delegations_made?: number;
  agents_used?: string[];
  duration_seconds?: number;
  stop_reason?: string;
  cost_usd?: number;
  llm_provider?: string;
  pending_approvals?: unknown[];
  error?: string;
}

interface OrchestrationResponse {
  content: string;
  model: string;
  tokens_used: number;
  tool_calls_made: number;
  tool_names: string[];
  delegations_made: number;
  agents_used: string[];
  duration_seconds: number;
  stop_reason: string;
  cost_usd: number;
  llm_provider: string;
  pending_approvals: unknown[];
}

export interface ChatSession {
  agentName: string;
  messages: ChatMessage[];
  /** A run is in flight for this session. */
  pending: boolean;
  /** Live SSE progress events for the in-flight orchestrator run. */
  streamingEvents: StreamingEvent[];
}

export const EMPTY_SESSION: ChatSession = {
  agentName: "",
  messages: [],
  pending: false,
  streamingEvents: [],
};

interface ChatStore {
  sessions: Record<string, ChatSession>;
  /** Load persisted history for a session once (no-op on later calls). */
  ensureHistory: (sessionId: string, agentName: string) => void;
  /** Send a message to the orchestrator (SSE, non-streaming fallback). */
  sendOrchestrator: (sessionId: string, text: string) => Promise<void>;
  /** Send a message to a specific agent (plain JSON endpoint). */
  sendAgentChat: (
    agentName: string,
    sessionId: string,
    text: string
  ) => Promise<void>;
  /** Drop a session's local state (used by "clear chat"). */
  resetSession: (sessionId: string) => void;
  /** True when the orchestrator Chat has a run in flight. */
  orchestratorPending: boolean;
  /** True when any per-agent chat has a run in flight. */
  agentChatPending: boolean;
}

/* ── History mapping ───────────────────────────────── */

function mapHistoryMessage(m: Record<string, unknown>): ChatMessage {
  const role = m.role as "user" | "assistant";
  const msg: ChatMessage = {
    id: (m.id as string) || crypto.randomUUID(),
    role,
    content: m.content as string,
    timestamp: new Date(m.created_at as string),
    status: "completed",
  };
  if (role === "assistant") {
    msg.toolsUsed = (m.tool_names as string[]) || undefined;
    msg.tokensUsed = (m.tokens_used as number) || undefined;
    msg.durationSeconds = (m.duration_seconds as number) || undefined;
    if (m.tokens_used) {
      msg.meta = {
        model: (m.model as string) || "",
        tokens: (m.tokens_used as number) || 0,
        duration: (m.duration_seconds as number) || 0,
        agents_used: (m.agents_used as string[]) || [],
        delegations: (m.delegations_made as number) || 0,
        tool_calls: 0,
        tool_names: (m.tool_names as string[]) || [],
      };
    }
  }
  return msg;
}

/* ── Reload-mid-run polling ────────────────────────── */

// After a full page reload while a run was in flight, history ends on a
// user message with no reply. The run is still finishing server-side, so
// poll history briefly until the assistant message lands.
const POLL_INTERVAL_MS = 4000;
const POLL_MAX_MS = 3 * 60 * 1000;

/* ── Store ─────────────────────────────────────────── */

const ChatStoreContext = createContext<ChatStore | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const { getToken } = useAuth();
  const getTokenRef = useRef(getToken);
  getTokenRef.current = getToken;

  const [sessions, setSessions] = useState<Record<string, ChatSession>>({});
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  const historyRequested = useRef<Set<string>>(new Set());
  // Sessions the user has interacted with live — polling must never touch these.
  const liveSessions = useRef<Set<string>>(new Set());
  const pollTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const abortControllers = useRef<Map<string, AbortController>>(new Map());

  useEffect(() => {
    const timers = pollTimers.current;
    return () => timers.forEach((t) => clearTimeout(t));
  }, []);

  const update = useCallback(
    (sessionId: string, fn: (s: ChatSession) => ChatSession) => {
      setSessions((prev) => ({
        ...prev,
        [sessionId]: fn(prev[sessionId] ?? EMPTY_SESSION),
      }));
    },
    []
  );

  const stopPolling = useCallback((sessionId: string) => {
    const t = pollTimers.current.get(sessionId);
    if (t) clearTimeout(t);
    pollTimers.current.delete(sessionId);
  }, []);

  const fetchHistory = useCallback(
    async (sessionId: string): Promise<ChatMessage[] | null> => {
      const token = await getTokenRef.current();
      const res = await fetch(
        `${DIRECT_API_URL}/api/history/chat/${encodeURIComponent(sessionId)}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!res.ok) return null;
      const data = await res.json();
      const msgs = Array.isArray(data) ? data : data.messages;
      if (!Array.isArray(msgs)) return null;
      return msgs.map(mapHistoryMessage);
    },
    []
  );

  const pollForReply = useCallback(
    (sessionId: string, startedAt: number) => {
      stopPolling(sessionId);
      const timer = setTimeout(async () => {
        pollTimers.current.delete(sessionId);
        if (liveSessions.current.has(sessionId)) return;
        if (Date.now() - startedAt > POLL_MAX_MS) return;
        try {
          const restored = await fetchHistory(sessionId);
          if (!restored || liveSessions.current.has(sessionId)) return;
          update(sessionId, (s) => ({ ...s, messages: restored }));
          const last = restored[restored.length - 1];
          if (last && last.role === "assistant") return; // reply arrived
        } catch {
          // Transient — keep polling until the deadline.
        }
        pollForReply(sessionId, startedAt);
      }, POLL_INTERVAL_MS);
      pollTimers.current.set(sessionId, timer);
    },
    [fetchHistory, stopPolling, update]
  );

  const ensureHistory = useCallback(
    (sessionId: string, agentName: string) => {
      if (!sessionId || historyRequested.current.has(sessionId)) return;
      historyRequested.current.add(sessionId);
      update(sessionId, (s) => ({ ...s, agentName }));
      (async () => {
        try {
          const restored = await fetchHistory(sessionId);
          if (!restored || restored.length === 0) return;
          const wasUntouched = !liveSessions.current.has(sessionId);
          // Prepend — never clobber messages sent while history was loading.
          update(sessionId, (s) => ({
            ...s,
            messages: [...restored, ...s.messages],
          }));
          const last = restored[restored.length - 1];
          if (wasUntouched && last && last.role === "user") {
            pollForReply(sessionId, Date.now());
          }
        } catch {
          // First load or API unavailable — ignore.
        }
      })();
    },
    [fetchHistory, pollForReply, update]
  );

  const beginSend = useCallback(
    (sessionId: string, agentName: string, text: string): ChatMessage => {
      liveSessions.current.add(sessionId);
      stopPolling(sessionId);
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: new Date(),
      };
      update(sessionId, (s) => ({
        ...s,
        agentName,
        messages: [...s.messages, userMsg],
        pending: true,
        streamingEvents: [],
      }));
      return userMsg;
    },
    [stopPolling, update]
  );

  const appendOrchestratorResult = useCallback(
    (sessionId: string, data: OrchestrationResponse) => {
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.content,
        timestamp: new Date(),
        status: data.stop_reason === "clarification" ? "clarification" : "completed",
        toolsUsed: data.tool_names || [],
        tokensUsed: data.tokens_used,
        durationSeconds: data.duration_seconds,
        meta: {
          model: data.model,
          tokens: data.tokens_used,
          duration: data.duration_seconds,
          agents_used: data.agents_used,
          delegations: data.delegations_made,
          tool_calls: data.tool_calls_made,
          tool_names: data.tool_names || [],
        },
      };
      update(sessionId, (s) => ({
        ...s,
        messages: [...s.messages, assistantMsg],
        streamingEvents: [],
      }));
    },
    [update]
  );

  const sendOrchestrator = useCallback(
    async (sessionId: string, text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sessionsRef.current[sessionId]?.pending) return;

      beginSend(sessionId, "orchestrator", trimmed);

      abortControllers.current.get(sessionId)?.abort();
      const controller = new AbortController();
      abortControllers.current.set(sessionId, controller);

      try {
        const token = await getTokenRef.current();
        const headers = {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        };
        const payload = JSON.stringify({
          message: trimmed,
          session_id: sessionId,
        });

        const res = await fetch(`${DIRECT_API_URL}/api/agents/orchestrate/stream`, {
          method: "POST",
          headers,
          body: payload,
          signal: controller.signal,
        });

        if (!res.ok) {
          // Fallback to the non-streaming endpoint
          const fallback = await fetch(`${DIRECT_API_URL}/api/agents/orchestrate`, {
            method: "POST",
            headers,
            body: payload,
            signal: controller.signal,
          });
          if (!fallback.ok) {
            const body = await fallback.json().catch(() => ({}));
            throw new Error(apiErrorMessage(body, fallback.status));
          }
          appendOrchestratorResult(sessionId, await fallback.json());
          return;
        }

        // Parse SSE stream
        const reader = res.body?.getReader();
        if (!reader) throw new Error("No readable stream");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // Keep incomplete line in buffer

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const event: StreamingEvent = JSON.parse(line.slice(6));

              if (event.type === "done") {
                appendOrchestratorResult(sessionId, {
                  content: event.content || "",
                  model: event.model || "",
                  tokens_used: event.tokens_used || 0,
                  tool_calls_made: event.tool_calls_made || 0,
                  tool_names: event.tool_names || [],
                  delegations_made: event.delegations_made || 0,
                  agents_used: event.agents_used || [],
                  duration_seconds: event.duration_seconds || 0,
                  stop_reason: event.stop_reason || "",
                  cost_usd: event.cost_usd || 0,
                  llm_provider: event.llm_provider || "",
                  pending_approvals: event.pending_approvals || [],
                });
              } else if (event.type === "error") {
                throw new Error(event.error || "Agent error");
              } else if (event.type !== "thinking") {
                // Show intermediate events (tool_call, agent_started, etc.)
                update(sessionId, (s) => ({
                  ...s,
                  streamingEvents: [...s.streamingEvents, event],
                }));
              }
            } catch (parseErr) {
              // Ignore non-JSON SSE lines
              if (parseErr instanceof SyntaxError) continue;
              throw parseErr;
            }
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        const errorMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content:
            err instanceof Error
              ? `Sorry, something went wrong: ${err.message}`
              : "Sorry, something went wrong. Please try again.",
          timestamp: new Date(),
          error: true,
          status: "error",
        };
        update(sessionId, (s) => ({
          ...s,
          messages: [...s.messages, errorMsg],
          streamingEvents: [],
        }));
      } finally {
        update(sessionId, (s) => ({ ...s, pending: false }));
      }
    },
    [appendOrchestratorResult, beginSend, update]
  );

  const sendAgentChat = useCallback(
    async (agentName: string, sessionId: string, text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sessionsRef.current[sessionId]?.pending) return;

      beginSend(sessionId, agentName, trimmed);

      const assistantId = crypto.randomUUID();
      const pendingMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        status: "sending",
      };
      update(sessionId, (s) => ({ ...s, messages: [...s.messages, pendingMsg] }));

      const patchAssistant = (patch: Partial<ChatMessage>) =>
        update(sessionId, (s) => ({
          ...s,
          messages: s.messages.map((m) =>
            m.id === assistantId ? { ...m, ...patch } : m
          ),
        }));

      try {
        const token = await getTokenRef.current();
        const res = await fetch(
          `${DIRECT_API_URL}/api/agents/${encodeURIComponent(agentName)}/chat`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ message: trimmed, session_id: sessionId }),
          }
        );

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `API error ${res.status}`);
        }

        const data = await res.json();
        patchAssistant({
          content: data.reply || data.content || "Done.",
          status:
            data.status === "clarification_needed" ? "clarification" : "completed",
          toolsUsed: data.tool_names || [],
          tokensUsed: data.tokens_used,
          durationSeconds: data.duration_seconds,
        });
      } catch (err) {
        patchAssistant({
          content:
            err instanceof Error ? err.message : "Something went wrong.",
          status: "error",
          error: true,
        });
      } finally {
        update(sessionId, (s) => ({ ...s, pending: false }));
      }
    },
    [beginSend, update]
  );

  const resetSession = useCallback(
    (sessionId: string) => {
      liveSessions.current.add(sessionId);
      stopPolling(sessionId);
      abortControllers.current.get(sessionId)?.abort();
      abortControllers.current.delete(sessionId);
      setSessions((prev) => {
        const next = { ...prev };
        delete next[sessionId];
        return next;
      });
    },
    [stopPolling]
  );

  const { orchestratorPending, agentChatPending } = useMemo(() => {
    let orch = false;
    let agent = false;
    for (const s of Object.values(sessions)) {
      if (!s.pending) continue;
      if (s.agentName === "orchestrator") orch = true;
      else agent = true;
    }
    return { orchestratorPending: orch, agentChatPending: agent };
  }, [sessions]);

  const store = useMemo<ChatStore>(
    () => ({
      sessions,
      ensureHistory,
      sendOrchestrator,
      sendAgentChat,
      resetSession,
      orchestratorPending,
      agentChatPending,
    }),
    [
      sessions,
      ensureHistory,
      sendOrchestrator,
      sendAgentChat,
      resetSession,
      orchestratorPending,
      agentChatPending,
    ]
  );

  return (
    <ChatStoreContext.Provider value={store}>
      {children}
    </ChatStoreContext.Provider>
  );
}

export function useChatStore(): ChatStore {
  const ctx = useContext(ChatStoreContext);
  if (!ctx) {
    throw new Error("useChatStore must be used inside <ChatProvider>");
  }
  return ctx;
}
