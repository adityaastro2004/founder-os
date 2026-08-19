import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PageHero } from "../_components/page-hero";
import { CtaBand } from "../_components/cta-band";
import { Section, SectionHeading, Prose } from "../_components/section";
import { JsonLd } from "../../_components/json-ld";
import { comparisons } from "../../../lib/comparisons";
import { itemListSchema, pageMetadata } from "../../../lib/site";

export const metadata = pageMetadata({
  title: "Compare — Founder OS vs ChatGPT, Notion AI and a virtual assistant",
  description:
    "Honest comparisons of Founder OS against the alternatives founders actually weigh it against, including a plain statement of when each alternative is the better choice.",
  path: "/compare",
  keywords: [
    "Founder OS vs ChatGPT",
    "Notion AI alternative",
    "AI co-founder comparison",
    "alternative to hiring a virtual assistant",
  ],
});

const listSchema = itemListSchema(
  "Founder OS comparisons",
  comparisons.map((comparison) => ({
    href: `/compare/${comparison.slug}`,
    name: comparison.title,
    description: comparison.summary,
  })),
);

export default function ComparePage() {
  return (
    <>
      <JsonLd data={listSchema} />

      <PageHero
        eyebrow="Compare"
        title="What you are actually choosing between"
        lead="Founder OS is not the only way to spend this budget, and pretending otherwise wastes your time. Each comparison below states the real structural difference and names the cases where the alternative wins."
        crumbs={[{ href: "/compare", label: "Compare" }]}
      />

      <Section>
        <div className="grid gap-6 lg:grid-cols-3">
          {comparisons.map((comparison) => (
            <article
              key={comparison.slug}
              className="flex flex-col rounded-card border border-line bg-surface p-6"
            >
              <p className="text-[13px] font-medium text-accent-text">
                vs {comparison.other}
              </p>
              <h2 className="mt-2 font-serif text-xl font-semibold leading-snug tracking-tight text-ink">
                <Link
                  href={`/compare/${comparison.slug}`}
                  className="transition-colors duration-150 hover:text-accent-text"
                >
                  {comparison.title}
                </Link>
              </h2>
              <p className="mt-3 flex-1 text-sm leading-relaxed text-ink-secondary">
                {comparison.summary}
              </p>
              <Link
                href={`/compare/${comparison.slug}`}
                className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-accent-text underline underline-offset-2 hover:no-underline"
              >
                Read the comparison
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </article>
          ))}
        </div>
      </Section>

      <Section bordered labelledBy="compare-rule-title">
        <SectionHeading
          id="compare-rule-title"
          title="How these are written"
          lead="A comparison page written by the vendor is worth reading only if it can say where the vendor loses."
        />
        <Prose className="mt-6">
          <ul>
            <li>
              Every comparison carries a{" "}
              <strong>&ldquo;when the alternative is the better choice&rdquo;</strong>{" "}
              section. It is not a formality — if one of those cases is yours,
              buy the other thing.
            </li>
            <li>
              Claims about other products describe their publicly documented
              behaviour. Where something is genuinely a matter of fit rather than
              capability, it is described that way.
            </li>
            <li>
              No performance numbers, time-saved percentages or customer counts
              appear anywhere on this site, because none have been measured. The{" "}
              <Link href="/case-studies">case studies</Link> are labelled
              illustrative for the same reason.
            </li>
            <li>
              Founder OS features are stated at their real status —{" "}
              <Link href="/integrations">Obsidian and Google Calendar are live,
              Notion is in progress</Link>.
            </li>
          </ul>
        </Prose>
      </Section>

      <CtaBand
        title="Or skip the comparison and try it"
        body="Ten minutes on the free plan with one tool connected settles the fit question better than any table."
      />
    </>
  );
}
