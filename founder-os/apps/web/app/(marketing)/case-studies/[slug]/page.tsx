import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { PageHero } from "../../_components/page-hero";
import { CtaBand } from "../../_components/cta-band";
import { Section, SectionHeading } from "../../_components/section";
import { ScenarioNotice } from "../_components/scenario-notice";
import { JsonLd } from "../../../_components/json-ld";
import { caseStudies, getCaseStudy } from "../../../../lib/case-studies";
import {
  absoluteUrl,
  organizationSchema,
  pageMetadata,
  siteName,
} from "../../../../lib/site";

/**
 * One static page per case study — a real URL each, so every scenario can rank
 * and be linked to on its own rather than living inside a tab on one page.
 */
export function generateStaticParams() {
  return caseStudies.map((study) => ({ slug: study.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const study = getCaseStudy(slug);
  if (!study) return {};

  return pageMetadata({
    title: `${study.persona}: ${study.title}`,
    description: study.description,
    path: `/case-studies/${study.slug}`,
    type: "article",
    keywords: [
      "Founder OS case study",
      study.persona.toLowerCase(),
      ...study.stack.map((tool) => `${tool} AI workflow`),
    ],
  });
}

export default async function CaseStudyPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const study = getCaseStudy(slug);
  if (!study) notFound();

  const articleSchema = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: `${study.persona}: ${study.title}`,
    description: study.description,
    url: absoluteUrl(`/case-studies/${study.slug}`),
    author: { "@id": organizationSchema["@id"] },
    publisher: { "@id": organizationSchema["@id"] },
    inLanguage: "en",
    isAccessibleForFree: true,
    about: study.featureFocus,
    // Marked explicitly so the scenario is never mistaken for reportage.
    disambiguatingDescription:
      "Illustrative scenario authored by Founder OS. Not a real customer account.",
  };

  return (
    <>
      <JsonLd data={articleSchema} />

      <PageHero
        eyebrow={study.persona}
        title={study.title}
        lead={study.description}
        crumbs={[
          { href: "/case-studies", label: "Case studies" },
          { href: `/case-studies/${study.slug}`, label: study.persona },
        ]}
      >
        <ul className="mt-6 flex flex-wrap gap-1.5">
          {study.stack.map((tool) => (
            <li
              key={tool}
              className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-ink-secondary"
            >
              {tool}
            </li>
          ))}
        </ul>
        <ScenarioNotice className="mt-6" />
      </PageHero>

      {/* ── Before ─────────────────────────────────────────────────── */}
      <Section labelledBy="situation-title">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
          <div>
            <SectionHeading
              id="situation-title"
              eyebrow="Before"
              title="The situation"
            />
            <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-ink-secondary md:text-base">
              {study.situation}
            </p>
          </div>
          <div className="rounded-card border border-line bg-surface p-6">
            <h3 className="font-serif text-lg font-semibold text-ink">
              Where the week leaks
            </h3>
            <ul className="mt-4 space-y-3">
              {study.friction.map((item) => (
                <li
                  key={item}
                  className="flex gap-2.5 text-sm leading-relaxed text-ink-secondary"
                >
                  <span
                    className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-danger"
                    aria-hidden="true"
                  />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      {/* ── What the system does ───────────────────────────────────── */}
      <Section bordered labelledBy="steps-title">
        <SectionHeading
          id="steps-title"
          eyebrow="What Founder OS does"
          title="Step by step"
          lead={`This scenario leans mostly on ${study.featureFocus.toLowerCase()}.`}
        />
        <ol className="mt-10 space-y-px overflow-hidden rounded-card border border-line bg-line">
          {study.steps.map((step, i) => (
            <li key={step.heading} className="bg-surface p-6 md:p-7">
              <div className="flex gap-4">
                <span className="font-mono text-xs text-ink-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="max-w-2xl">
                  <h3 className="font-serif text-lg font-semibold text-ink md:text-xl">
                    {step.heading}
                  </h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-ink-secondary">
                    {step.body}
                  </p>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      {/* ── After ──────────────────────────────────────────────────── */}
      <Section bordered labelledBy="outcomes-title">
        <SectionHeading
          id="outcomes-title"
          eyebrow="After"
          title="What changes"
          lead="Described as behaviour, not as percentages — we do not publish numbers we have not measured."
        />
        <ul className="mt-8 grid max-w-4xl gap-4 sm:grid-cols-2">
          {study.outcomes.map((outcome) => (
            <li
              key={outcome}
              className="rounded-card border border-line bg-surface p-5 text-sm leading-relaxed text-ink-secondary"
            >
              {outcome}
            </li>
          ))}
        </ul>
      </Section>

      {/* ── Other scenarios ───────────────────────────────────────── */}
      <Section bordered labelledBy="other-title">
        <SectionHeading id="other-title" title="Other scenarios" />
        <div className="mt-8 grid gap-6 md:grid-cols-2">
          {caseStudies
            .filter((other) => other.slug !== study.slug)
            .map((other) => (
              <Link
                key={other.slug}
                href={`/case-studies/${other.slug}`}
                className="group rounded-card border border-line bg-surface p-6 transition-colors duration-150 hover:bg-surface-muted"
              >
                <p className="text-[13px] font-medium text-accent-text">
                  {other.persona}
                </p>
                <h3 className="mt-2 font-serif text-lg font-semibold text-ink">
                  {other.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
                  {other.description}
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
        <p className="mt-8 text-sm text-ink-secondary">
          Or read the mechanics behind all of them in the{" "}
          <Link
            href="/features"
            className="font-medium text-accent-text underline underline-offset-2 hover:no-underline"
          >
            {siteName} feature breakdown
          </Link>
          .
        </p>
      </Section>

      <CtaBand />
    </>
  );
}
