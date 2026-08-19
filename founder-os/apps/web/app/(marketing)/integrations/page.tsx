import Link from "next/link";
import { ArrowRight, ArrowLeftRight, ArrowDownToLine } from "lucide-react";
import { PageHero } from "../_components/page-hero";
import { CtaBand } from "../_components/cta-band";
import { Section, SectionHeading, Prose } from "../_components/section";
import { JsonLd } from "../../_components/json-ld";
import { integrations, statusLabel } from "../../../lib/integrations";
import { itemListSchema, pageMetadata } from "../../../lib/site";

export const metadata = pageMetadata({
  title: "Integrations — Obsidian, Notion and Google Calendar",
  description:
    "Founder OS connects to the tools you already use as state sources and mirrors your company state back into them. Obsidian and Google Calendar are live; Notion is in progress.",
  path: "/integrations",
  keywords: [
    "Founder OS integrations",
    "Obsidian AI integration",
    "Notion AI integration",
    "Google Calendar AI planning",
    "two-way AI tool sync",
  ],
});

const listSchema = itemListSchema(
  "Founder OS integrations",
  integrations.map((integration) => ({
    href: `/integrations/${integration.slug}`,
    name: integration.name,
    description: integration.summary,
  })),
);

export default function IntegrationsPage() {
  return (
    <>
      <JsonLd data={listSchema} />

      <PageHero
        eyebrow="Integrations"
        title="Your tools stay where they are"
        lead="Founder OS does not ask you to migrate. Each tool is treated as a synchronisation endpoint: an adapter reads it as a state source, and the reconciled company state is written back out as ordinary content in that tool."
        crumbs={[{ href: "/integrations", label: "Integrations" }]}
      />

      <Section>
        <div className="grid gap-6 lg:grid-cols-3">
          {integrations.map((integration) => {
            const twoWay = integration.writes.length > 0;
            return (
              <article
                key={integration.slug}
                className="flex flex-col rounded-card border border-line bg-surface p-6"
              >
                <div className="flex items-center justify-between gap-3">
                  <h2 className="font-serif text-xl font-semibold tracking-tight text-ink">
                    <Link
                      href={`/integrations/${integration.slug}`}
                      className="transition-colors duration-150 hover:text-accent-text"
                    >
                      {integration.name}
                    </Link>
                  </h2>
                  <span
                    className={
                      integration.status === "shipped"
                        ? "rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-accent-text"
                        : "rounded-full border border-line px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted"
                    }
                  >
                    {statusLabel(integration.status)}
                  </span>
                </div>

                <p className="mt-3 flex items-center gap-2 text-[13px] text-ink-muted">
                  {twoWay ? (
                    <ArrowLeftRight className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <ArrowDownToLine className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  {twoWay ? "Two-way sync" : "Read-only"}
                </p>

                <p className="mt-4 flex-1 text-sm leading-relaxed text-ink-secondary">
                  {integration.summary}
                </p>

                <Link
                  href={`/integrations/${integration.slug}`}
                  className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-accent-text underline underline-offset-2 hover:no-underline"
                >
                  How the {integration.name} integration works
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </article>
            );
          })}
        </div>
      </Section>

      <Section bordered labelledBy="integrations-model-title">
        <SectionHeading
          id="integrations-model-title"
          eyebrow="The adapter model"
          title="Why a new tool is a new adapter, not a new product"
        />
        <Prose className="mt-6">
          <p>
            Every integration implements the same small interface, with three
            capabilities: <strong>observe</strong> (pull external state into
            Founder OS), <strong>sync</strong> (push canonical state back out),
            and <strong>health</strong> (report whether the connection is
            actually working). A tool that can only be read declares observe and
            health and nothing else, and the rest of the system knows not to try
            writing to it.
          </p>
          <p>
            That uniformity is what makes the{" "}
            <Link href="/features">Company State Engine</Link> possible. The
            reconciler does not care that a project arrived from a Markdown vault
            rather than a database — it sees typed entities with provenance
            attached, decides they are the same project, and merges them into one.
            The write gate rejects updates it cannot support from the source, and
            decay surfaces the entity nothing has touched in weeks.
          </p>
          <p>
            The practical consequence for you is that adding a tool never means
            re-learning the product, and removing one never strands your data.
            Mirrored content is ordinary content in the destination tool — plain
            Markdown files, ordinary database properties — readable with or
            without Founder OS running.
          </p>

          <h2>What is not connected yet</h2>
          <p>
            Nothing on this site describes a feature that does not exist. Today
            that means: Obsidian and Google Calendar are live, Notion is in
            progress with its OAuth connect flow already shipped, and everything
            else is unbuilt. If the tool you need is not listed,{" "}
            <Link href="/contact">say which one</Link> — the adapter interface is
            small, and a real request from a real founder is how the queue gets
            ordered.
          </p>
        </Prose>
      </Section>

      <CtaBand
        title="Connect one tool and watch the state build"
        body="The free plan is enough to point Founder OS at an existing vault or calendar and see what it extracts. That is the honest way to judge it."
      />
    </>
  );
}
