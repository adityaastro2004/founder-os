import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Brain,
  CalendarCheck,
  Database,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { CtaLink } from "./_components/cta-link";
import { CtaBand } from "./_components/cta-band";
import { FaqSection } from "./_components/faq-section";
import { Container, Section, SectionHeading, Prose } from "./_components/section";
import { caseStudies } from "../../lib/case-studies";
import { homeFaqs } from "../../lib/faq";
import { pageMetadata } from "../../lib/site";

export const metadata = pageMetadata({
  title: "AI operating system for solo founders",
  description:
    "Founder OS is an AI operating system for solo founders: autonomous agents, long-term memory, and a Company State Engine that keeps one source of truth across Obsidian, Notion, GitHub and your calendar.",
  path: "/",
  keywords: [
    "AI operating system for founders",
    "AI co-founder",
    "solo founder productivity tool",
    "multi-agent AI assistant",
    "company knowledge base AI",
    "Obsidian AI integration",
  ],
});

const loops = [
  {
    name: "Observe",
    body: "Passively read the tools you already use — docs, issues, calendar, conversations — without asking you to file anything twice.",
  },
  {
    name: "Remember",
    body: "Write what matters into company state and four layers of long-term memory, deduplicated and linked to the right project.",
  },
  {
    name: "Understand",
    body: "Score the current state of the company against the goals you actually recorded, and surface what has quietly gone stale.",
  },
  {
    name: "Execute",
    body: "Decompose the request, delegate to specialist agents, and act — with irreversible steps held at the approval gate.",
  },
  {
    name: "Learn",
    body: "Compile what worked into reusable skills, decay what no longer matters, and get better at your company over time.",
  },
];

const features = [
  {
    icon: Database,
    title: "Company State Engine",
    body: "One canonical model of goals, projects, tasks, decisions, metrics, people and meetings — reconciled, deduplicated and write-gated.",
  },
  {
    icon: Bot,
    title: "One Orchestrator, many agents",
    body: "You never pick an agent. The Orchestrator decomposes your request, delegates to Planner, Content, Research or Support, and synthesises one answer.",
  },
  {
    icon: Brain,
    title: "Memory that compounds",
    body: "Four-layer agent memory plus a temporal knowledge graph, with composite scoring and entity linking — so last month's context is still there.",
  },
  {
    icon: RefreshCw,
    title: "Two-way tool sync",
    body: "Pluggable adapters read your tools as state sources and mirror the unified picture back. Obsidian today, Notion in progress.",
  },
  {
    icon: CalendarCheck,
    title: "Automatic weekly planning",
    body: "An ICE-scored plan generated every Monday morning from live company state and real calendar capacity — not from memory.",
  },
  {
    icon: ShieldCheck,
    title: "Human-in-the-loop by design",
    body: "Three-tier risk classification. Low-risk work runs unattended; anything irreversible waits for your explicit approval.",
  },
];

export default async function Home() {
  const { userId } = await auth();

  // Signed-in visitors get the product, not the pitch.
  if (userId) {
    redirect("/dashboard");
  }

  return (
    <>
      {/* ── Hero — the primary CTA sits above the fold on a 360px phone ── */}
      <Container className="pt-10 pb-14 md:pt-16 md:pb-20">
        <div className="max-w-3xl">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-[13px] font-medium text-ink-secondary">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
            The tireless co-founder for solo founders
          </p>

          <h1 className="font-serif text-[2rem] font-semibold leading-[1.12] tracking-tight text-ink sm:text-5xl md:text-6xl">
            One system that knows your whole company
          </h1>

          <p className="mt-5 max-w-xl text-base leading-relaxed text-ink-secondary md:text-lg">
            Slack knows the conversation. GitHub knows the code. Stripe knows the
            revenue. Nothing knows the company — so you app-switch all day,
            reassembling context by hand. Founder OS keeps one canonical company
            state and puts autonomous agents on top of it.
          </p>

          <div className="mt-8 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
            <CtaLink href="/sign-up" size="lg">
              Start for free
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </CtaLink>
            <CtaLink href="/features" variant="secondary" size="lg">
              See how it works
            </CtaLink>
          </div>

          <p className="mt-5 text-[13px] text-ink-secondary">
            Free tier · no credit card · runs locally on Ollama if you prefer
          </p>
        </div>
      </Container>

      {/* ── Five loops ─────────────────────────────────────────────── */}
      <Section bordered labelledBy="loops-title">
        <SectionHeading
          id="loops-title"
          eyebrow="How it works"
          title="Five loops, running whether or not you are"
          lead="Founder OS behaves like an OS daemon rather than a chat window. It keeps cycling, and each pass leaves the company state a little more accurate."
        />
        <ol className="mt-10 grid grid-cols-1 gap-px overflow-hidden rounded-card border border-line bg-line sm:grid-cols-2 lg:grid-cols-5">
          {loops.map((loop, i) => (
            <li key={loop.name} className="bg-surface p-5">
              <span className="font-mono text-xs text-ink-muted">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="mt-2 font-serif text-lg font-semibold text-ink">
                {loop.name}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
                {loop.body}
              </p>
            </li>
          ))}
        </ol>
      </Section>

      {/* ── Features ───────────────────────────────────────────────── */}
      <Section bordered labelledBy="features-title">
        <SectionHeading
          id="features-title"
          eyebrow="What you get"
          title="Built around state, not around chat"
          lead="The moat is not the conversation — it is the canonical model of your company underneath it."
        />
        <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="rounded-card border border-line bg-surface p-6"
            >
              <Icon className="h-5 w-5 text-accent" aria-hidden="true" />
              <h3 className="mt-4 font-serif text-lg font-semibold text-ink">
                {title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
                {body}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-8 text-sm">
          <Link
            href="/features"
            className="inline-flex items-center gap-1.5 font-medium text-accent-text underline underline-offset-2 hover:no-underline"
          >
            Full feature breakdown
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </p>
      </Section>

      {/* ── Long-form SEO copy ─────────────────────────────────────── */}
      <Section bordered labelledBy="about-tool-title">
        <SectionHeading
          id="about-tool-title"
          eyebrow="About the tool"
          title="What Founder OS actually is"
        />
        <Prose className="mt-8">
          <p>
            Founder OS is an <strong>AI operating system for solo founders</strong> and
            teams of two or three. Running a company alone does not fail because
            you lack tools — it fails because you own every role at once. You are
            the product manager, the marketer, the researcher, the support rep and
            the person doing invoices, and the real cost is not the work itself but
            the fragmentation between the tools that each hold a piece of it. Your
            roadmap lives in one app, your issues in another, your revenue in a
            third, your promises to customers in a DM thread. Each tool is
            internally consistent and none of them knows the company.
          </p>
          <p>
            Most AI products answer this with a better chat box. That helps with
            isolated tasks — write this post, summarise this document — and then
            forgets everything the moment the tab closes. A co-pilot that starts
            from zero context every morning is not a co-founder. Founder OS is
            built the other way round: the conversation is the interface, but the
            product is the state underneath it.
          </p>

          <h3>The Company State Engine</h3>
          <p>
            At the centre is the <strong>Company State Engine</strong>: a canonical,
            living model of your company covering goals, projects, tasks,
            decisions, metrics, people and meetings. It is fed three ways —
            passively <em>observed</em> from the tools you connect, handed over
            directly in the documents you give it, and written by the system
            itself as agents learn. A hygiene layer keeps it honest: a write gate
            rejects low-confidence or contradictory updates, a reconciler merges
            the same project arriving under three different names from three
            different tools into one entity, and decay marks state that nothing has
            touched in a long time so stale work surfaces instead of quietly
            rotting. The result is a written answer to <em>what is actually going
            on</em> that you did not have to assemble by hand.
          </p>

          <h3>Agents that use that state</h3>
          <p>
            On top of state sit the agents. You talk to one{" "}
            <strong>Orchestrator</strong> and never choose a specialist: it analyses
            the request, decomposes it into subtasks, delegates to Planner, Content,
            Research or Support agents, and synthesises one coherent answer. Agents
            delegate to each other rather than making you play project manager, and
            long-running work runs in the background on a task queue with status,
            history and cancellation. Memory is four-layered and backed by a
            temporal knowledge graph with composite scoring, entity linking and
            spaced-repetition review, which is why a decision recorded in March is
            still available in August.
          </p>

          <h3>It mirrors back into your tools</h3>
          <p>
            Nothing has to migrate. Pluggable adapters treat each tool as a
            synchronisation endpoint: Founder OS reads it as a state source, and
            the renderer writes the reconciled picture back out as ordinary content
            in that tool. Obsidian ships today and Notion is in progress, with
            Google Calendar feeding real capacity into planning. You keep working
            where you already work — the change is that your notes, your tracker
            and your calendar stop contradicting each other.
          </p>

          <h3>Autonomy with a brake</h3>
          <p>
            Autonomy is only useful if it is safe, so every proposed action is
            classified into three risk tiers. Low-risk work runs unattended;
            anything irreversible or outward-facing — sending a message, issuing a
            refund, deleting something — is held until you explicitly approve it,
            and agents cannot route around that gate. The stack is OSS-first and
            local-first: Ollama runs inference on your own machine by default, so
            you can operate the whole system without sending company data to a
            model vendor, and swap in Claude, Gemini or any OpenAI-compatible
            endpoint when you want to.
          </p>
          <p>
            The honest summary: Founder OS is for founders whose bottleneck is
            context switching rather than typing speed. If you want to see the
            shape of it, read the{" "}
            <Link href="/features">feature breakdown</Link>, walk through an{" "}
            <Link href="/case-studies">illustrative scenario</Link>, or{" "}
            <Link href="/sign-up">start on the free tier</Link> and connect one tool.
          </p>
        </Prose>
      </Section>

      {/* ── Case studies teaser ────────────────────────────────────── */}
      <Section bordered labelledBy="scenarios-title">
        <SectionHeading
          id="scenarios-title"
          eyebrow="Case studies"
          title="What this looks like in a real week"
          lead="Three illustrative scenarios — not customer accounts — showing how the engine and the agents are actually used."
        />
        <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3">
          {caseStudies.map((study) => (
            <Link
              key={study.slug}
              href={`/case-studies/${study.slug}`}
              className="group flex flex-col rounded-card border border-line bg-surface p-6 transition-colors duration-150 hover:bg-surface-muted"
            >
              <p className="text-[13px] font-medium text-accent-text">
                {study.persona}
              </p>
              <h3 className="mt-2 font-serif text-lg font-semibold leading-snug text-ink">
                {study.title}
              </h3>
              <p className="mt-3 flex-1 text-sm leading-relaxed text-ink-secondary">
                {study.description}
              </p>
              <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-accent-text">
                Read the walkthrough
                <ArrowRight
                  className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5"
                  aria-hidden="true"
                />
              </span>
            </Link>
          ))}
        </div>
      </Section>

      {/* ── FAQ (schema is emitted on /faq only) ───────────────────── */}
      <Section bordered labelledBy="faq-title">
        <SectionHeading
          id="faq-title"
          eyebrow="Questions"
          title="Frequently asked questions"
        />
        <div className="mt-8 max-w-3xl">
          <FaqSection items={homeFaqs} />
          <p className="mt-6 text-sm">
            <Link
              href="/faq"
              className="inline-flex items-center gap-1.5 font-medium text-accent-text underline underline-offset-2 hover:no-underline"
            >
              All questions
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </p>
        </div>
      </Section>

      <CtaBand />
    </>
  );
}
