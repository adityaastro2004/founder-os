/**
 * Content for `/integrations` and `/integrations/[slug]`.
 *
 * These pages exist because the site already targets queries like "Obsidian AI
 * integration" and "Notion AI sync" in its keywords but had no URL that could
 * rank for them — a keyword with no landing page is a keyword you lose.
 *
 * ⚠️ Status must match the adapters in `apps/api/app/integrations/`:
 *   obsidian        OBSERVE | SYNC | HEALTH   → shipped, two-way
 *   notion          OBSERVE | SYNC | HEALTH   → in progress (OAuth connect landed, ADR-019)
 *   google_calendar OBSERVE | HEALTH          → shipped, read-only
 * The /about page promises that nothing on this site describes a feature that
 * does not exist. `status` is how that promise is kept machine-checkable.
 */

export type IntegrationStatus = "shipped" | "in-progress" | "planned";

export type Integration = {
  slug: string;
  /** Product name as the vendor writes it — this is the head term. */
  name: string;
  status: IntegrationStatus;
  /** Sentence used on the hub card and as the meta description seed. */
  summary: string;
  /** Direction of data flow, in plain words. */
  direction: string;
  /** Search-intent keywords this page is built to answer. */
  keywords: string[];
  /** What Founder OS reads out of the tool. */
  reads: string[];
  /** What Founder OS writes back into the tool. Empty for read-only adapters. */
  writes: string[];
  /** Numbered setup steps — the "how do I connect X" query. */
  setup: string[];
  /** Long-form body paragraphs for the page. */
  body: string[];
};

const statusCopy: Record<IntegrationStatus, string> = {
  shipped: "Available now",
  "in-progress": "In progress",
  planned: "Planned",
};

export function statusLabel(status: IntegrationStatus): string {
  return statusCopy[status];
}

export const integrations: Integration[] = [
  {
    slug: "obsidian",
    name: "Obsidian",
    status: "shipped",
    summary:
      "Read your vault as a state source and mirror the reconciled company state back into it as ordinary Markdown.",
    direction: "Two-way — Founder OS reads the vault and writes back to it",
    keywords: [
      "Obsidian AI integration",
      "Obsidian AI assistant",
      "sync Obsidian vault with AI",
      "Obsidian second brain automation",
    ],
    reads: [
      "Markdown notes, including frontmatter and wiki-links",
      "Goals, projects, tasks and decisions expressed as ordinary prose",
      "Meeting notes and daily notes, with their dates",
      "Backlinks, used as evidence when the reconciler merges entities",
    ],
    writes: [
      "A mirrored view of company state as plain Markdown files",
      "Project and goal pages that stay current as state changes",
      "Links back into the notes each fact was derived from",
    ],
    setup: [
      "Sign up and open Apps in the dashboard.",
      "Add Obsidian as a state source and point it at your vault directory.",
      "Run the first observe pass — the engine reads existing notes and builds your initial company state.",
      "Review what it extracted; the write gate has already rejected anything it was not confident about.",
      "Turn on mirroring, and the reconciled state is written back into the vault as Markdown you can read without Founder OS.",
    ],
    body: [
      "Obsidian is the state source Founder OS shipped first, and it is the cleanest illustration of the adapter model: your vault is not imported, migrated, or locked in. It is read where it already lives. Founder OS parses the notes you write anyway — daily notes, meeting notes, project pages — and lifts the goals, projects, tasks, decisions and people out of them as first-class entities in the Company State Engine.",
      "The interesting half is the return trip. Once state is reconciled across every source you have connected, the renderer writes it back into the vault as ordinary Markdown. Nothing proprietary, nothing that needs Founder OS running to read. If you cancel tomorrow, the vault is still a vault — the mirrored pages just stop updating.",
      "Because everything is plain text, the hygiene layer matters more here than anywhere else. The same project written as \"Q3 launch\", \"launch\" and \"the launch\" across three months of notes is one entity after reconciliation, not three. The write gate rejects updates it cannot support from what the notes actually say, and decay surfaces the project you stopped writing about six weeks ago instead of leaving it looking active forever.",
    ],
  },
  {
    slug: "notion",
    name: "Notion",
    status: "in-progress",
    summary:
      "Connect a Notion workspace over OAuth, read databases and pages as state, and mirror company state back into Notion.",
    direction: "Two-way — in progress; OAuth connect is live",
    keywords: [
      "Notion AI integration",
      "Notion AI alternative",
      "sync Notion with AI agent",
      "Notion database automation",
    ],
    reads: [
      "Databases mapped onto goals, projects, tasks and meetings",
      "Page content and properties, with their last-edited timestamps",
      "Relations between databases, used as reconciliation evidence",
    ],
    writes: [
      "Reconciled state mirrored into the databases you nominate",
      "Status and progress updates written as ordinary Notion properties",
    ],
    setup: [
      "Open Apps in the dashboard and choose Notion.",
      "Authorise the workspace through Notion's OAuth flow — Founder OS never asks for your password, and the grant is scoped to what you select.",
      "Pick which databases map to goals, projects, tasks and meetings.",
      "Run the first observe pass and review the extracted state.",
      "Enable mirroring for the databases you want kept in sync.",
    ],
    body: [
      "Notion is the second adapter, and it is honestly described as in progress: the OAuth connect flow is live, the adapter and the database mapper are built, and the two-way sync is being hardened. It is listed here because the shape is decided, not because the work is finished — see the roadmap for where it stands today.",
      "The design question with Notion is mapping. A vault is prose, but a Notion workspace is already structured — and structured differently in every company. So the adapter does not assume a schema. You nominate which databases mean goals, projects, tasks and meetings, and the mapper translates between your properties and the canonical entities. Relations between your databases become evidence the reconciler uses when deciding whether two records are the same thing.",
      "If you are comparing this with Notion AI, the distinction is worth stating plainly: Notion AI works on the contents of Notion. Founder OS works on the contents of your company, of which Notion is one source. The reconciled picture spans your vault, your calendar and your workspace at once, and Notion is one of the places that picture is written back to.",
    ],
  },
  {
    slug: "google-calendar",
    name: "Google Calendar",
    status: "shipped",
    summary:
      "Feed real calendar capacity into weekly planning, so the Monday plan is built against hours that actually exist.",
    direction: "One-way — Founder OS reads your calendar",
    keywords: [
      "Google Calendar AI planning",
      "AI weekly planner calendar",
      "calendar capacity planning tool",
    ],
    reads: [
      "Events and their durations across the coming week",
      "Meeting load, used to compute the hours genuinely available",
      "Recurring commitments, so they are not double-counted as free time",
    ],
    writes: [],
    setup: [
      "Open Apps in the dashboard and connect Google Calendar over OAuth.",
      "Grant read access to the calendars you want counted as capacity.",
      "The Monday planner picks it up on the next run — no further configuration.",
    ],
    body: [
      "Most planning tools ask what you intend to do this week and take the answer at face value. The result is a plan sized for a week you do not have, which is why it is abandoned by Wednesday. Founder OS treats the calendar as a hard input: before ranking anything, it works out how many hours are genuinely unclaimed after the meetings you have already committed to.",
      "That number then constrains the plan. Candidate work is ranked by ICE — impact, confidence, effort — against the goals actually recorded in your company state, and the plan is cut to fit real capacity rather than to fill an idealised week. A week with eleven hours of calls produces a visibly smaller plan than a week with none, automatically.",
      "The adapter is read-only on purpose. Founder OS observes your calendar and reports health; it does not create, move or delete events. Writing to a calendar is an outward-facing action, and outward-facing actions belong behind the approval gate rather than inside a scheduled background job.",
    ],
  },
];

export function getIntegration(slug: string): Integration | undefined {
  return integrations.find((integration) => integration.slug === slug);
}
