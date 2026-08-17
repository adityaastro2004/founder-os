import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PageHero } from "../_components/page-hero";
import { CtaBand } from "../_components/cta-band";
import { Section } from "../_components/section";
import { ScenarioNotice } from "./_components/scenario-notice";
import { caseStudies } from "../../../lib/case-studies";
import { pageMetadata } from "../../../lib/site";

export const metadata = pageMetadata({
  title: "Case studies — Founder OS in a real week",
  description:
    "Three illustrative walkthroughs of Founder OS in use: a solo SaaS founder reconciling six tools, a three-person agency generating a weekly plan, and an indie developer triaging support safely.",
  path: "/case-studies",
  keywords: [
    "Founder OS case studies",
    "AI operating system examples",
    "solo founder workflow example",
  ],
});

export default function CaseStudiesPage() {
  return (
    <>
      <PageHero
        eyebrow="Case studies"
        title="What a week with Founder OS looks like"
        lead="Features are easier to judge with a week attached. Each walkthrough takes one kind of founder, describes the friction honestly, and shows which part of the system removes it."
        crumbs={[{ href: "/case-studies", label: "Case studies" }]}
      >
        <ScenarioNotice className="mt-8" />
      </PageHero>

      <Section>
        <div className="grid gap-6 lg:grid-cols-3">
          {caseStudies.map((study) => (
            <article
              key={study.slug}
              className="flex flex-col rounded-card border border-line bg-surface p-6"
            >
              <p className="text-[13px] font-medium text-accent-text">
                {study.persona}
              </p>
              <h2 className="mt-2 font-serif text-xl font-semibold leading-snug tracking-tight text-ink">
                <Link
                  href={`/case-studies/${study.slug}`}
                  className="transition-colors duration-150 hover:text-accent-text"
                >
                  {study.title}
                </Link>
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-ink-secondary">
                {study.description}
              </p>

              <p className="mt-5 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                Stack
              </p>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {study.stack.map((tool) => (
                  <li
                    key={tool}
                    className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-secondary"
                  >
                    {tool}
                  </li>
                ))}
              </ul>

              <p className="mt-5 flex-1 text-sm text-ink-secondary">
                <span className="font-medium text-ink">Leans on:</span>{" "}
                {study.featureFocus}
              </p>

              <Link
                href={`/case-studies/${study.slug}`}
                className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-accent-text underline underline-offset-2 hover:no-underline"
              >
                Read the walkthrough
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </article>
          ))}
        </div>
      </Section>

      <CtaBand
        title="Run the scenario on your own company"
        body="Every walkthrough here starts the same way: connect one tool and let the engine build your state. That part is free."
      />
    </>
  );
}
