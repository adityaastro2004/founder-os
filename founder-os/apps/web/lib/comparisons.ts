/**
 * Content for `/compare` and `/compare/[slug]`.
 *
 * Comparison pages capture the highest-intent query a category has — someone
 * typing "X vs Y" has already decided they need the category and is choosing
 * a vendor. The site had no page for any of them.
 *
 * House rule for this file: every comparison carries a `whenOther` section
 * saying plainly when the alternative is the better choice. That is partly
 * honesty (the /about page commits to it) and partly that one-sided comparison
 * pages read as marketing and are treated as such by both readers and Google.
 * Claims about the alternatives are limited to their publicly documented
 * behaviour and stay descriptive rather than disparaging.
 */

export type ComparisonRow = {
  dimension: string;
  founderOs: string;
  other: string;
};

export type Comparison = {
  slug: string;
  /** The thing being compared against, as a reader would name it. */
  other: string;
  /** Page <h1>. */
  title: string;
  /** Meta description seed and hub-card copy. */
  summary: string;
  keywords: string[];
  /** One-sentence answer, placed above the fold for the snippet. */
  verdict: string;
  rows: ComparisonRow[];
  /** When the alternative is genuinely the better pick. Non-negotiable. */
  whenOther: string[];
  body: { heading: string; paragraphs: string[] }[];
};

export const comparisons: Comparison[] = [
  {
    slug: "founder-os-vs-chatgpt",
    other: "ChatGPT",
    title: "Founder OS vs ChatGPT for running a company",
    summary:
      "ChatGPT is a general assistant you prompt. Founder OS is a system that maintains a canonical model of your company and acts on it in the background. Where each one wins, honestly.",
    keywords: [
      "Founder OS vs ChatGPT",
      "ChatGPT alternative for founders",
      "ChatGPT for business operations",
      "AI assistant with long-term memory",
    ],
    verdict:
      "Use ChatGPT for isolated tasks you can describe in a prompt. Use Founder OS when the expensive part is not writing the answer but reassembling the context the answer needs.",
    rows: [
      {
        dimension: "Where context comes from",
        founderOs:
          "A Company State Engine fed passively from the tools you connect, plus four layers of long-term memory",
        other: "What you paste into the prompt, plus whatever memory the product retains",
      },
      {
        dimension: "When it runs",
        founderOs:
          "Continuously — five loops keep cycling, and a weekly plan is generated whether or not you open anything",
        other: "When you open it and type",
      },
      {
        dimension: "Acting in your tools",
        founderOs:
          "Pluggable adapters read your tools as state sources and mirror the reconciled picture back into them",
        other: "Via connectors and custom integrations you configure per task",
      },
      {
        dimension: "Multi-step work",
        founderOs:
          "One Orchestrator decomposes the request and delegates to Planner, Content, Research and Support agents",
        other: "One assistant, with tools; you drive the decomposition",
      },
      {
        dimension: "Safety on irreversible actions",
        founderOs:
          "Three-tier risk classification enforced by the system; anything irreversible waits for explicit approval",
        other: "Per-tool confirmation, configured by whoever built the integration",
      },
      {
        dimension: "Running it privately",
        founderOs:
          "Local-first — Ollama by default, so prompts need never leave your infrastructure; self-hosting supported",
        other: "Hosted service",
      },
      {
        dimension: "Breadth",
        founderOs:
          "Narrow on purpose: running a small company. Weak outside that",
        other: "Very broad — writing, coding, analysis, images, general knowledge",
      },
    ],
    whenOther: [
      "You want one answer to one question and you can describe the whole context in a paragraph. That is a prompt, not a system.",
      "The work is outside company operations — general research, drafting, coding help, learning something new. Founder OS is deliberately narrow and will be worse at all of it.",
      "You are not willing to connect any tool. Founder OS without state sources is a worse chat window.",
      "You want the frontier model itself. Founder OS is provider-pluggable and can call Claude or Gemini, but it is not competing on raw model quality.",
    ],
    body: [
      {
        heading: "The difference is state, not model quality",
        paragraphs: [
          "It is tempting to frame this as a model comparison, and it is not one. Founder OS can call the same class of model — it is provider-pluggable across Anthropic, Google and any OpenAI-compatible endpoint, with Ollama running locally by default. If you gave both systems identical context, you would get comparable answers.",
          "The difference is that they never have identical context. A general assistant starts from what you remembered to paste. Founder OS starts from a canonical model of your company that was assembled while you were doing something else: goals, projects, tasks, decisions, metrics, people and meetings, reconciled across every tool you connected and kept current by a hygiene layer that rejects low-confidence updates, merges duplicate entities and decays what has gone stale.",
          "So the honest comparison is not \"which one writes better\" but \"how much of your day goes into telling it what is going on\". If that number is near zero, a chat box is fine. If it is most of the interaction, the chat box is the wrong shape.",
        ],
      },
      {
        heading: "One assistant versus one Orchestrator",
        paragraphs: [
          "The second structural difference is who does the decomposition. With a general assistant, a request that spans research, planning and drafting is your job to break apart — you run three conversations and stitch the results together.",
          "Founder OS gives you a single entry point. The Orchestrator analyses the request, splits it into subtasks, routes each to the specialist that should handle it, and synthesises one answer. Long-running work continues on a background queue with status, history and cancellation, and survives a restart rather than dying with the tab.",
        ],
      },
      {
        heading: "Autonomy needs a brake",
        paragraphs: [
          "A system that acts on its own schedule needs a different safety model from one that acts only when prompted. Founder OS classifies every proposed action into three risk tiers. Low-risk work runs unattended, medium-risk follows your preferences, and anything irreversible or outward-facing — sending a message, issuing a refund, deleting something — is blocked until you approve it explicitly. The gate is enforced by the system, not left to agent good behaviour.",
        ],
      },
    ],
  },
  {
    slug: "founder-os-vs-notion-ai",
    other: "Notion AI",
    title: "Founder OS vs Notion AI for company knowledge",
    summary:
      "Notion AI works on what is inside Notion. Founder OS works on what is true about your company across every tool, and treats Notion as one source among several.",
    keywords: [
      "Founder OS vs Notion AI",
      "Notion AI alternative",
      "AI across all my tools",
      "company knowledge base AI",
    ],
    verdict:
      "If your company genuinely lives inside one Notion workspace, Notion AI is the shorter path. If it is spread across a vault, a tracker, a calendar and a workspace that quietly disagree, that spread is the problem Founder OS is built for.",
    rows: [
      {
        dimension: "Scope of knowledge",
        founderOs:
          "Every connected source, reconciled into one canonical company state",
        other: "The contents of your Notion workspace",
      },
      {
        dimension: "Conflicting information",
        founderOs:
          "A reconciler merges the same entity arriving from different tools; a write gate rejects contradictory updates",
        other: "Both versions exist as pages; resolution is manual",
      },
      {
        dimension: "Structure",
        founderOs:
          "Goals, projects, tasks, decisions, metrics, people and meetings as first-class typed entities with provenance",
        other: "Whatever database schema you designed",
      },
      {
        dimension: "Runs on its own",
        founderOs:
          "Yes — continuous observation plus an automatic Monday plan built against real calendar capacity",
        other: "Invoked in a page or a chat",
      },
      {
        dimension: "Relationship to Notion",
        founderOs:
          "Notion is a state source and a mirror target — the adapter is in progress",
        other: "It is Notion",
      },
      {
        dimension: "Where inference runs",
        founderOs: "Local by default via Ollama; hosted providers optional",
        other: "Hosted",
      },
    ],
    whenOther: [
      "Your whole company really is in Notion, and no meaningful state lives anywhere else. Adding a layer above one tool buys you nothing.",
      "You want AI inside the editor while you write — drafting, summarising and rewriting in place. That is Notion AI's home ground and Founder OS does not compete there.",
      "You need it working this afternoon with zero setup. The Founder OS Notion adapter is still in progress, and the useful state builds over the first week.",
      "You are not looking for autonomy. If \"acts on a schedule\" sounds like a risk rather than a feature, the simpler tool is the right call.",
    ],
    body: [
      {
        heading: "Working on a tool versus working on a company",
        paragraphs: [
          "Notion AI is scoped to Notion, and that is a coherent design: it can see your pages and databases, so it answers well about them. The limit is the same as the scope. It cannot tell you that the launch date in your project database contradicts the commitment you made in a meeting note in your vault, because it cannot see the vault.",
          "Founder OS is built one level up. Each tool is a state source; the Company State Engine reconciles what they each know into a single canonical model with provenance attached, so you can always ask where a claim came from. Notion is one input to that model and one of the places the reconciled picture is written back to.",
        ],
      },
      {
        heading: "Structured entities, not structured pages",
        paragraphs: [
          "Both systems have structure, but at different layers. In Notion the structure is the schema you designed, and it is per-workspace — a project means whatever your project database says it means. In Founder OS the entity types are fixed and canonical: goal, project, task, decision, metric, person, meeting. Your Notion databases are mapped onto them rather than replacing them.",
          "That is what makes cross-tool reconciliation possible at all. Once \"the Q3 launch\" from your vault, your tracker and your workspace resolve to one entity, dedup, decay and the write gate have something coherent to operate on. Without a canonical type system underneath, three tools produce three parallel truths and a human to arbitrate them.",
        ],
      },
      {
        heading: "Nothing has to migrate",
        paragraphs: [
          "The usual objection to a layer above your tools is that it becomes another place to maintain. The adapter model is the answer: Founder OS reads the tool as a state source and the renderer writes the reconciled picture back out as ordinary content in that tool. You keep working where you already work. If you stop using Founder OS, your Notion is still your Notion — the mirrored content just stops updating.",
        ],
      },
    ],
  },
  {
    slug: "founder-os-vs-virtual-assistant",
    other: "a virtual assistant",
    title: "Founder OS vs hiring a virtual assistant",
    summary:
      "A VA brings judgement, accountability and the ability to handle anything. Founder OS brings continuous coverage, perfect recall and a cost that does not scale with hours. Where each one earns its keep.",
    keywords: [
      "AI virtual assistant for founders",
      "alternative to hiring a virtual assistant",
      "AI chief of staff",
      "solo founder operations tool",
    ],
    verdict:
      "A virtual assistant is better at anything requiring judgement, relationships or physical-world follow-through. Founder OS is better at the part that is really an information problem — knowing what is true across your tools and keeping it that way.",
    rows: [
      {
        dimension: "Cost shape",
        founderOs: "A flat subscription from $0; does not scale with hours worked",
        other: "Hourly or monthly retainer; scales directly with hours",
      },
      {
        dimension: "Coverage",
        founderOs: "Continuous, including nights and weekends",
        other: "Their working hours, in their timezone",
      },
      {
        dimension: "Recall",
        founderOs:
          "Four-layer memory and a temporal knowledge graph — a decision from March is still available in August",
        other: "As good as their notes, and it leaves when they do",
      },
      {
        dimension: "Onboarding",
        founderOs:
          "Connect a tool; useful state builds over the first week as it reads existing history",
        other: "Weeks of explaining context, repeated for each new hire",
      },
      {
        dimension: "Judgement calls",
        founderOs:
          "Deliberately gated — anything irreversible or outward-facing waits for your approval",
        other: "Independent judgement, which is the main reason to hire one",
      },
      {
        dimension: "Accountability",
        founderOs: "A system you own and audit; provenance on every claim",
        other: "A person who is answerable to you",
      },
    ],
    whenOther: [
      "The work needs judgement about people — negotiating, hiring, handling an upset customer, deciding what to say when the honest answer is awkward.",
      "It requires acting in the physical world, or inside systems that have no API and no intention of getting one.",
      "You need someone accountable for an outcome, not a system that proposes one. Software cannot own a result.",
      "The bottleneck is genuinely hours of execution rather than fragmented context. Founder OS reduces the reassembly cost; it does not do the work of a second person.",
    ],
    body: [
      {
        heading: "These are not really the same job",
        paragraphs: [
          "Founders comparing these two are usually looking at one budget line and two ways to spend it, but the jobs barely overlap. What you hire a VA for is judgement plus hands: someone to chase the supplier, handle the awkward email, and make a sensible call when the instructions run out. What Founder OS handles is the part that was always an information problem — knowing what is actually going on across six tools that each hold a fragment of it.",
          "In most solo companies the second problem is the larger one and the less visible one, because it does not look like work. It looks like a morning spent re-reading five apps to reconstruct where things stand. That is the cost the Company State Engine removes, and no amount of delegated hours removes it, because the context is in your head rather than written down anywhere a helper could read.",
        ],
      },
      {
        heading: "What continuous coverage actually buys",
        paragraphs: [
          "A VA works their hours. Founder OS runs five loops continuously — observe, remember, understand, execute, learn — so state stays current between your sessions rather than at them. The practical output is that Monday starts with a plan rather than a blank page: an ICE-ranked draft generated from live company state, sized against the hours your calendar says you genuinely have.",
          "Memory is the other asymmetry. A VA's recall is as good as their notes and it leaves with them. Founder OS keeps four layers of long-term memory over a temporal knowledge graph with composite scoring and entity linking, so the decision recorded in March is still there in August with its provenance attached — and it stays there when anything else changes.",
        ],
      },
      {
        heading: "The honest limit",
        paragraphs: [
          "Founder OS is explicitly not autonomous where autonomy is dangerous. Every proposed action is risk-classified, and anything irreversible or outward-facing is held until you approve it. That is the right default, and it is also the clearest boundary against a human helper: a VA can be trusted to send the email. Founder OS drafts it and waits.",
          "Many founders end up with both, and the split settles in the same place — the system holds the truth and prepares the work; the person handles the judgement and the conversations.",
        ],
      },
    ],
  },
];

export function getComparison(slug: string): Comparison | undefined {
  return comparisons.find((comparison) => comparison.slug === slug);
}
