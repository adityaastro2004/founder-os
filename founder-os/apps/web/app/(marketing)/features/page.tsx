import Link from "next/link";
import {
  Bot,
  Brain,
  CalendarCheck,
  Database,
  Plug,
  RefreshCw,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { PageHero } from "../_components/page-hero";
import { CtaBand } from "../_components/cta-band";
import { Section, SectionHeading, Prose } from "../_components/section";
import { pageMetadata } from "../../../lib/site";

export const metadata = pageMetadata({
  title: "Features — company state, agents, memory and integrations",
  description:
    "Every part of Founder OS explained: the Company State Engine, the Orchestrator and specialist agents, four-layer memory, tool adapters, weekly planning and the three-tier approval gate.",
  path: "/features",
  keywords: [
    "Founder OS features",
    "company state engine",
    "multi-agent orchestration",
    "AI long-term memory",
    "Obsidian Notion sync",
    "human in the loop AI approval",
  ],
});

const featureGroups = [
  {
    icon: Database,
    title: "Company State Engine",
    tagline: "The canonical model of your company",
    body: "Goals, projects, tasks, decisions, metrics, people and meetings, all as first-class entities rather than text buried in documents. State arrives three ways — observed from your tools, handed over in the docs you give it, and written by the system as it learns — and each entity carries its provenance so you can always ask where a claim came from.",
    points: [
      "A write gate rejects low-confidence and contradictory updates instead of appending them",
      "The reconciler merges the same project arriving from three tools into one entity",
      "Dedup catches near-identical entities before they multiply",
      "Decay marks entities nothing has touched, so stale work surfaces on its own",
    ],
  },
  {
    icon: Bot,
    title: "One Orchestrator, specialist agents",
    tagline: "You never pick an agent",
    body: "A single entry point analyses your request, decomposes it into subtasks, routes each to the right specialist — Planner, Content, Research, Support — and synthesises one coherent answer. Agents delegate to each other directly, so you are not left hand-wiring a pipeline every time the work spans two domains.",
    points: [
      "Durable orchestration: long runs survive restarts and can be resumed",
      "Background execution with status polling, history and cancellation",
      "Answers cite the state and memories they were built from",
    ],
  },
  {
    icon: Brain,
    title: "Memory that compounds",
    tagline: "August still remembers March",
    body: "Four layers of agent memory sit behind a temporal knowledge graph with typed relationships and entity linking. Composite scoring decides what is worth recalling, and spaced-repetition review keeps important context alive rather than letting recency win by default.",
    points: [
      "Temporal knowledge graph with typed relationships between entities",
      "Composite relevance scoring instead of naive vector similarity alone",
      "Pruning and decay, so the memory stays useful rather than merely large",
    ],
  },
  {
    icon: RefreshCw,
    title: "Two-way tool sync",
    tagline: "Nothing has to migrate",
    body: "Each tool is treated as a synchronisation endpoint: an adapter reads it as a state source, and the renderer writes the reconciled picture back out as ordinary content in that tool. You keep writing where you already write.",
    points: [
      "Obsidian shipped — reads the vault, mirrors state back as plain Markdown",
      "Notion in progress",
      "Google Calendar feeds real capacity into planning",
      "Adapters are pluggable, so a new tool is a new adapter, not a new product",
    ],
  },
  {
    icon: CalendarCheck,
    title: "Automatic weekly planning",
    tagline: "Monday starts with a draft, not a blank page",
    body: "A scheduled job builds next week's plan from live company state — open projects, active goals, unfinished tasks, last week's carry-over — and ranks candidates with ICE scoring against the goals you actually recorded. Calendar load is part of the input, so the plan is built against hours that exist.",
    points: [
      "Generated automatically every Monday morning",
      "ICE (impact, confidence, effort) scoring against recorded goals",
      "Updated in place as tasks close and new commitments are observed",
    ],
  },
  {
    icon: ShieldCheck,
    title: "Human-in-the-loop approval gate",
    tagline: "Autonomy with a brake",
    body: "Every proposed action is classified into one of three risk tiers. Low-risk work runs unattended; medium-risk follows your per-user preferences; anything irreversible or outward-facing is blocked until you explicitly approve it. The gate is enforced by the system, not by agent good behaviour.",
    points: [
      "Three-tier risk classification: low, medium, high",
      "Mandatory gating for irreversible and outward-facing actions",
      "Per-user preferences for what may run unattended",
    ],
  },
  {
    icon: Plug,
    title: "Local-first, provider-pluggable AI",
    tagline: "Your data, your model choice",
    body: "Ollama runs inference locally by default, so the whole system can operate without sending company data to a model vendor. Swap in Anthropic Claude, Google Gemini or any OpenAI-compatible endpoint when you want more capability, with a three-tier fallback chain if a provider is down.",
    points: [
      "Ollama by default — nothing leaves your infrastructure",
      "Claude, Gemini and OpenAI-compatible providers supported",
      "Three-tier fallback so one provider outage is not an outage for you",
    ],
  },
  {
    icon: Workflow,
    title: "Workflows, generated not drawn",
    tagline: "No drag-and-drop canvas to maintain",
    body: "When a request needs a repeatable multi-step process, the Orchestrator generates the workflow rather than making you design it. A self-hosted n8n backend is available if you want a visible, editable flow — it is an execution option, not the differentiator.",
    points: [
      "Workflows generated on the fly from what the company actually needs",
      "Optional n8n execution backend with link-out to the editor",
    ],
  },
];

export default function FeaturesPage() {
  return (
    <>
      <PageHero
        eyebrow="Features"
        title="Everything Founder OS does, and why it is built this way"
        lead="Founder OS is not a chat box with plugins. It is a state engine with agents on top and a hard safety gate in front of anything irreversible. Here is each part in detail."
        crumbs={[{ href: "/features", label: "Features" }]}
      />

      <Section>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {featureGroups.map(({ icon: Icon, title, tagline, body, points }) => (
            <article
              key={title}
              className="flex flex-col rounded-card border border-line bg-surface p-6 md:p-7"
            >
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-control bg-accent-soft">
                  <Icon className="h-4 w-4 text-accent-text" aria-hidden="true" />
                </span>
                <p className="text-[13px] font-medium text-ink-secondary">
                  {tagline}
                </p>
              </div>
              <h2 className="mt-4 font-serif text-xl font-semibold tracking-tight text-ink md:text-2xl">
                {title}
              </h2>
              <p className="mt-3 text-[15px] leading-relaxed text-ink-secondary">
                {body}
              </p>
              <ul className="mt-5 space-y-2 border-t border-line-subtle pt-5">
                {points.map((point) => (
                  <li
                    key={point}
                    className="flex gap-2.5 text-sm leading-relaxed text-ink-secondary"
                  >
                    <span
                      className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent"
                      aria-hidden="true"
                    />
                    {point}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </Section>

      <Section bordered labelledBy="features-next-title">
        <SectionHeading
          id="features-next-title"
          title="Where to go next"
          lead="Features read better with a week attached to them."
        />
        <Prose className="mt-6">
          <ul>
            <li>
              See the parts working together in an{" "}
              <Link href="/case-studies">illustrative scenario</Link> — six tools
              reconciled into one state, a Monday plan that survives the week, or
              support triage with a human on the brake.
            </li>
            <li>
              Check the practical questions on the{" "}
              <Link href="/faq">FAQ</Link> — cost, setup time, self-hosting, and
              what happens to your data.
            </li>
            <li>
              Read who is building this and why on the{" "}
              <Link href="/about">about page</Link>, or{" "}
              <Link href="/contact">ask a direct question</Link>.
            </li>
          </ul>
        </Prose>
      </Section>

      <CtaBand
        title="Connect one tool and see the difference"
        body="The free tier is enough to build your company state from an existing Obsidian vault and ask the Orchestrator a real question about your own company."
      />
    </>
  );
}
