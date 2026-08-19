import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, Check, Download, Upload } from "lucide-react";
import { PageHero } from "../../_components/page-hero";
import { CtaBand } from "../../_components/cta-band";
import { Section, SectionHeading, Prose } from "../../_components/section";
import { JsonLd } from "../../../_components/json-ld";
import {
  getIntegration,
  integrations,
  statusLabel,
} from "../../../../lib/integrations";
import { howToSchema, pageMetadata, siteName } from "../../../../lib/site";

/**
 * One static page per integration.
 *
 * These are the pages that answer "does Founder OS work with <tool>" and "how
 * do I connect <tool>" — both head terms in this category, and both unanswerable
 * from a feature list. A real URL each means each tool's query has somewhere to
 * land, and the HowTo schema puts the setup steps in the result itself.
 */
export function generateStaticParams() {
  return integrations.map((integration) => ({ slug: integration.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const integration = getIntegration(slug);
  if (!integration) return {};

  // The title suffix is derived, not hard-coded: Google Calendar is read-only,
  // and titling it "two-way sync" would be the kind of claim /about promises
  // this site does not make.
  const suffix = integration.writes.length
    ? "two-way company state sync"
    : "company state from your calendar";

  return pageMetadata({
    title: `${integration.name} integration — ${suffix}`,
    description: `${integration.summary} ${statusLabel(integration.status)}. ${integration.direction}.`,
    path: `/integrations/${integration.slug}`,
    keywords: integration.keywords,
  });
}

export default async function IntegrationPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const integration = getIntegration(slug);
  if (!integration) notFound();

  const others = integrations.filter((other) => other.slug !== integration.slug);
  const setupSchema = howToSchema({
    name: `How to connect ${integration.name} to ${siteName}`,
    description: `Connect ${integration.name} as a state source so ${siteName} can build and maintain your company state from it.`,
    path: `/integrations/${integration.slug}`,
    steps: integration.setup,
  });

  return (
    <>
      <JsonLd data={setupSchema} />

      <PageHero
        eyebrow={`${statusLabel(integration.status)} · ${integration.direction}`}
        title={`${integration.name} integration`}
        lead={integration.summary}
        crumbs={[
          { href: "/integrations", label: "Integrations" },
          { href: `/integrations/${integration.slug}`, label: integration.name },
        ]}
      />

      {/* ── What flows, in each direction ──────────────────────────── */}
      <Section labelledBy="flow-title">
        <SectionHeading
          id="flow-title"
          eyebrow="Data flow"
          title={`What Founder OS reads${integration.writes.length ? " and writes" : ""}`}
          lead={
            integration.writes.length
              ? "Stated in both directions, because an integration that only reads and one that also writes are very different commitments."
              : "This adapter is read-only. Founder OS observes the tool and never modifies it."
          }
        />
        <div className="mt-10 grid gap-6 lg:grid-cols-2">
          <div className="rounded-card border border-line bg-surface p-6">
            <div className="flex items-center gap-2.5">
              <Download className="h-4 w-4 text-accent" aria-hidden="true" />
              <h3 className="font-serif text-lg font-semibold text-ink">
                Reads from {integration.name}
              </h3>
            </div>
            <ul className="mt-5 space-y-2.5">
              {integration.reads.map((item) => (
                <li
                  key={item}
                  className="flex gap-2.5 text-sm leading-relaxed text-ink-secondary"
                >
                  <Check
                    className="mt-0.5 h-4 w-4 shrink-0 text-accent"
                    aria-hidden="true"
                  />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-card border border-line bg-surface p-6">
            <div className="flex items-center gap-2.5">
              <Upload className="h-4 w-4 text-accent" aria-hidden="true" />
              <h3 className="font-serif text-lg font-semibold text-ink">
                Writes back to {integration.name}
              </h3>
            </div>
            {integration.writes.length ? (
              <ul className="mt-5 space-y-2.5">
                {integration.writes.map((item) => (
                  <li
                    key={item}
                    className="flex gap-2.5 text-sm leading-relaxed text-ink-secondary"
                  >
                    <Check
                      className="mt-0.5 h-4 w-4 shrink-0 text-accent"
                      aria-hidden="true"
                    />
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-5 text-sm leading-relaxed text-ink-secondary">
                Nothing. This adapter declares observe and health only — it has
                no write capability at all, so Founder OS cannot create, modify
                or delete anything in {integration.name} even if an agent asked
                it to.
              </p>
            )}
          </div>
        </div>
      </Section>

      {/* ── Setup (mirrors the HowTo schema above) ─────────────────── */}
      <Section bordered labelledBy="setup-title">
        <SectionHeading
          id="setup-title"
          eyebrow="Setup"
          title={`Connecting ${integration.name}`}
          lead="Roughly ten minutes, most of which is deciding what to connect rather than doing it."
        />
        <ol className="mt-10 space-y-px overflow-hidden rounded-card border border-line bg-line">
          {integration.setup.map((step, i) => (
            <li key={step} id={`step-${i + 1}`} className="scroll-mt-24 bg-surface p-6">
              <div className="flex gap-4">
                <span className="font-mono text-xs text-ink-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <p className="max-w-2xl text-[15px] leading-relaxed text-ink-secondary">
                  {step}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      {/* ── Long-form ──────────────────────────────────────────────── */}
      <Section bordered labelledBy="detail-title">
        <SectionHeading
          id="detail-title"
          eyebrow="In detail"
          title={`How the ${integration.name} adapter actually works`}
        />
        <Prose className="mt-8">
          {integration.body.map((paragraph) => (
            <p key={paragraph.slice(0, 40)}>{paragraph}</p>
          ))}
          <p>
            The mechanics behind every adapter are the same — see the{" "}
            <Link href="/features">feature breakdown</Link> for the state engine,
            the reconciler and the approval gate, or{" "}
            <Link href="/case-studies">an illustrative scenario</Link> for what
            this looks like across a working week.
          </p>
        </Prose>
      </Section>

      {/* ── Other integrations ─────────────────────────────────────── */}
      <Section bordered labelledBy="other-integrations-title">
        <SectionHeading id="other-integrations-title" title="Other integrations" />
        <div className="mt-8 grid gap-6 md:grid-cols-2">
          {others.map((other) => (
            <Link
              key={other.slug}
              href={`/integrations/${other.slug}`}
              className="group rounded-card border border-line bg-surface p-6 transition-colors duration-150 hover:bg-surface-muted"
            >
              <p className="text-[13px] font-medium text-accent-text">
                {statusLabel(other.status)}
              </p>
              <h3 className="mt-2 font-serif text-lg font-semibold text-ink">
                {other.name}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
                {other.summary}
              </p>
              <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-accent-text">
                Read it
                <ArrowRight
                  className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5"
                  aria-hidden="true"
                />
              </span>
            </Link>
          ))}
        </div>
      </Section>

      <CtaBand
        title={`Point Founder OS at your ${integration.name}`}
        body="The free plan covers one state source. Connect it, run the first observe pass, and look at what the engine extracted before deciding anything."
      />
    </>
  );
}
