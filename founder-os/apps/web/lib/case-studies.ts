/**
 * Case-study content.
 *
 * IMPORTANT — these are **illustrative scenarios**, not real customer accounts.
 * Founder OS has no publicly referenceable customers yet, so every page built
 * from this data renders a visible disclaimer (see the `<Disclaimer>` in
 * `app/(marketing)/case-studies/_components/`) and deliberately contains no
 * invented metrics, testimonials, company names or logos. When real customers
 * agree to be named, replace an entry wholesale and drop the disclaimer for it.
 */

export type CaseStudy = {
  slug: string;
  /** Card + <h1> title. */
  title: string;
  /** Short label above the title. */
  persona: string;
  /** Meta description + card summary. */
  description: string;
  /** The stack the scenario assumes. */
  stack: string[];
  /** "Before" — what the day looked like. */
  situation: string;
  friction: string[];
  /** "What Founder OS does" — ordered walkthrough. */
  steps: { heading: string; body: string }[];
  /** "After" — behavioural outcomes only, never invented numbers. */
  outcomes: string[];
  /** Which product surface the scenario leans on most. */
  featureFocus: string;
};

export const caseStudies: CaseStudy[] = [
  {
    slug: "solo-saas-founder",
    title: "Six tools, one company state",
    persona: "Solo SaaS founder",
    description:
      "How a one-person SaaS keeps goals, tasks and decisions consistent across Obsidian, GitHub, Stripe and Calendar without a weekly manual clean-up.",
    stack: ["Obsidian", "GitHub", "Stripe", "Google Calendar", "Slack"],
    situation:
      "A single founder ships a B2B SaaS alone. The roadmap lives in Obsidian, issues in GitHub, revenue in Stripe, commitments in Calendar, and customer promises in Slack DMs. Nothing is wrong in any one tool — but no tool knows the company, so every planning session starts with twenty minutes of re-reading five apps.",
    friction: [
      "The same project exists under three different names in three tools.",
      "Decisions made in Slack never reach the roadmap doc, so the roadmap quietly goes stale.",
      "Promises to customers live in DMs and are remembered only when someone follows up.",
      "Weekly planning is done from memory, so whatever was loudest last wins.",
    ],
    steps: [
      {
        heading: "Connect the tools as state sources, not as chat plugins",
        body: "Obsidian is connected first as a state source. Founder OS reads the vault, extracts goals, projects, tasks, decisions and people, and writes them into the Company State Engine as `observed` entities — the vault is never treated as a pile of text to summarise on demand.",
      },
      {
        heading: "Reconcile the duplicates instead of stacking them",
        body: "The reconciler matches the same project arriving from three sources into one canonical entity, and the write gate rejects low-confidence or contradictory updates rather than letting the model happily create a fourth copy.",
      },
      {
        heading: "Mirror the unified picture back into Obsidian",
        body: "The renderer writes the reconciled state back into the vault as ordinary Markdown. The founder keeps working in Obsidian — the difference is that the notes now agree with GitHub, Stripe and Calendar.",
      },
      {
        heading: "Ask the Orchestrator, not five apps",
        body: "“What slipped this week and what did it cost us?” goes to one Orchestrator, which decomposes the question, pulls from state and memory, delegates research or drafting to specialist agents, and returns one answer with its sources.",
      },
    ],
    outcomes: [
      "Planning starts from a written state of the company rather than from recall.",
      "A decision recorded once shows up wherever that project is described.",
      "Stale projects surface on their own, because state decay marks entities nothing has touched.",
      "The founder stays in Obsidian; the reconciliation happens underneath.",
    ],
    featureFocus: "Company State Engine + Obsidian adapter",
  },
  {
    slug: "three-person-agency",
    title: "A Monday plan that survives the week",
    persona: "Three-person agency",
    description:
      "How a tiny agency turns scattered client commitments into one ICE-scored weekly plan that is generated automatically every Monday morning.",
    stack: ["Notion", "Google Calendar", "Slack", "Gmail"],
    situation:
      "Three people, nine active clients. Every Monday the team spends the first hour rebuilding a shared plan from Notion pages, inboxes and last week's leftovers — and by Wednesday the plan no longer matches reality, so it gets abandoned.",
    friction: [
      "Client commitments arrive by email and Slack and never make it into the plan.",
      "Priorities are argued from opinion because nothing scores the work.",
      "Calendar load is invisible while planning, so the week is over-committed by Tuesday.",
      "The plan is a document, so nothing notices when it goes out of date.",
    ],
    steps: [
      {
        heading: "Let the planner run before anyone is awake",
        body: "A scheduled job generates the weekly plan every Monday at 08:00 from current company state — open projects, live goals, unfinished tasks and last week's carry-over — so the week starts with a draft instead of a blank page.",
      },
      {
        heading: "Score the work instead of debating it",
        body: "Candidate tasks are ranked with ICE (impact, confidence, effort) against the goals actually recorded in state. Disagreement moves from “what matters more” to “is this score right”, which is a much shorter conversation.",
      },
      {
        heading: "Plan against real calendar capacity",
        body: "The Google Calendar source feeds meetings and blocks into state, so the plan is built against the hours that actually exist rather than an imaginary empty week.",
      },
      {
        heading: "Keep the plan alive after Monday",
        body: "As tasks close and new commitments are observed, the plan is updated in place and mirrored back into Notion. Nothing needs to be re-typed for the plan to stay true.",
      },
    ],
    outcomes: [
      "Monday starts with a reviewable draft plan, not an empty document.",
      "Prioritisation is explicit and reproducible instead of loudest-voice-wins.",
      "Over-commitment is visible at planning time, not on Thursday.",
      "The plan and the client tools stop drifting apart mid-week.",
    ],
    featureFocus: "Weekly planner + Notion and Calendar sources",
  },
  {
    slug: "indie-developer-support",
    title: "Support triage without a support team",
    persona: "Indie developer",
    description:
      "How one developer handles a growing support load with agents that draft, classify and escalate — while every irreversible action still waits for a human.",
    stack: ["Gmail", "GitHub", "Obsidian"],
    situation:
      "A paid developer tool crosses a few hundred users. Support is now a real job: bug reports, billing questions and feature requests all land in one inbox, and answering them eats the hours meant for building.",
    friction: [
      "Every reply is written from scratch, including the twentieth identical one.",
      "Bug reports are answered but never turn into tracked issues.",
      "Recurring complaints are felt but not measured, so the roadmap does not react to them.",
      "Refunds and account changes are the scary part — nothing should touch those unattended.",
    ],
    steps: [
      {
        heading: "Classify before drafting",
        body: "Incoming messages are classified by intent and linked to the project, release or customer they concern in company state, so a reply is drafted with the actual context rather than generic politeness.",
      },
      {
        heading: "Draft, don't send",
        body: "The Support agent produces a draft answer with its reasoning and sources. Low-risk replies can be approved in one click; nothing is sent silently.",
      },
      {
        heading: "Gate anything irreversible",
        body: "The three-tier approval gate classifies each proposed action as low, medium or high risk. Refunds, deletions and outbound commitments are high risk and are blocked until a human explicitly approves them — the gate is not bypassable by an agent.",
      },
      {
        heading: "Turn support signal into roadmap input",
        body: "Repeated reports are reconciled into the same canonical issue in state, so the third occurrence is visible as a pattern instead of as three unrelated emails, and it competes for roadmap space on evidence.",
      },
    ],
    outcomes: [
      "Repetitive replies become review-and-send instead of write-from-scratch.",
      "Support conversations leave a trace in company state rather than only in the inbox.",
      "Recurring pain is counted, so the roadmap can answer it.",
      "Irreversible actions still require a human, by design.",
    ],
    featureFocus: "Specialist agents + human-in-the-loop approval gate",
  },
];

export function getCaseStudy(slug: string): CaseStudy | undefined {
  return caseStudies.find((study) => study.slug === slug);
}
