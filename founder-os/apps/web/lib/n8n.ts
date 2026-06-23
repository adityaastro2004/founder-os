/**
 * n8n editor link-out (ADR-008, O-5 / O-5-AMEND).
 *
 * v1 surfaces workflow *editing* as a link out to the self-hosted n8n editor —
 * no embed, no SSO. The URL is built from the per-workflow n8n identifier
 * (`n8n_workflow_id`) returned by the backend on push:
 *
 *   `${N8N_BASE_URL}/workflow/${n8n_workflow_id}`
 *
 * The base URL is sourced from the public-env convention this app already uses
 * (see `lib/api.ts` reading `NEXT_PUBLIC_API_URL`): a `NEXT_PUBLIC_*` variable
 * read directly off `process.env` and inlined at build time. Centralised here so
 * there is a single place to change if the convention moves.
 *
 * INTEGRATION FLAG: `NEXT_PUBLIC_N8N_BASE_URL` must be set in the web app's env
 * (documented in `.env.local.example`). The backend's `N8N_BASE_URL` (ADR-008,
 * O-2/O-4 — `config.py`) is server-side only; the dashboard needs its own public
 * mirror to construct the editor link. If these can diverge at deploy time, they
 * should be reconciled to one source during integration.
 */

const N8N_BASE_URL = process.env.NEXT_PUBLIC_N8N_BASE_URL || "";

/**
 * Whether a link-out to the n8n editor can be constructed. False when the public
 * n8n base URL is unset (so the UI hides/disables the affordance instead of
 * rendering a broken link).
 */
export function isN8nEditorConfigured(): boolean {
  return N8N_BASE_URL.length > 0;
}

/**
 * Build the n8n editor URL for a workflow, or `null` if it cannot be built
 * (base URL unset, or the workflow has not been pushed to n8n yet).
 */
export function n8nEditorUrl(
  n8nWorkflowId: string | null | undefined
): string | null {
  if (!N8N_BASE_URL || !n8nWorkflowId) return null;
  const base = N8N_BASE_URL.replace(/\/+$/, "");
  return `${base}/workflow/${encodeURIComponent(n8nWorkflowId)}`;
}
