import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { PageHero } from "../../_components/page-hero";
import { CtaBand } from "../../_components/cta-band";
import { Section, SectionHeading, Prose } from "../../_components/section";
import { JsonLd } from "../../../_components/json-ld";
import { comparisons, getComparison } from "../../../../lib/comparisons";
import {
  absoluteUrl,
  organizationSchema,
  pageMetadata,
  siteName,
} from "../../../../lib/site";

/**
 * One static page per comparison.
 *
 * "X vs Y" is the highest-intent query a software category has — the searcher
 * has already decided they need the category and is choosing a vendor — and the
 * site had no page for any of them.
 */
export function generateStaticParams() {
  return comparisons.map((comparison) => ({ slug: comparison.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const comparison = getComparison(slug);
  if (!comparison) return {};

  return pageMetadata({
    title: comparison.title,
    description: comparison.summary,
    path: `/compare/${comparison.slug}`,
    type: "article",
    keywords: comparison.keywords,
  });
}

export default async function ComparisonPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const comparison = getComparison(slug);
  if (!comparison) notFound();

  const others = comparisons.filter((other) => other.slug !== comparison.slug);

  const articleSchema = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: comparison.title,
    description: comparison.summary,
    url: absoluteUrl(`/compare/${comparison.slug}`),
    author: { "@id": organizationSchema["@id"] },
    publisher: { "@id": organizationSchema["@id"] },
    inLanguage: "en",
    isAccessibleForFree: true,
    about: `${siteName} compared with ${comparison.other}`,
    // Says in machine-readable form what the page says in prose: this is a
    // vendor comparison, written by the vendor.
    disambiguatingDescription: `Vendor-authored comparison. Claims about ${comparison.other} describe its publicly documented behaviour, and the page states when ${comparison.other} is the better choice.`,
  };

  return (
    <>
      <JsonLd data={articleSchema} />

      <PageHero
        eyebrow={`Founder OS vs ${comparison.other}`}
        title={comparison.title}
        lead={comparison.summary}
        crumbs={[
          { href: "/compare", label: "Compare" },
          { href: `/compare/${comparison.slug}`, label: `vs ${comparison.other}` },
        ]}
      >
        {/* The short answer, above the fold — this is the paragraph a featured
            snippet or an AI answer will lift, so it has to stand alone. */}
        <div className="mt-8 rounded-card border-l-2 border-accent bg-surface p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            The short answer
          </p>
          <p className="mt-2 text-[15px] leading-relaxed text-ink md:text-base">
            {comparison.verdict}
          </p>
        </div>
      </PageHero>

      {/* ── Side by side ───────────────────────────────────────────── */}
      <Section labelledBy="table-title">
        <SectionHeading
          id="table-title"
          eyebrow="Side by side"
          title={`${siteName} and ${comparison.other}, compared`}
        />
        {/* Overflow wrapper: the table must scroll inside its own box rather
            than making the whole page scroll sideways on a phone. */}
        <div className="mt-10 overflow-x-auto rounded-card border border-line">
          <table className="w-full min-w-[42rem] border-collapse text-left">
            <caption className="sr-only">
              {siteName} compared with {comparison.other}, by dimension
            </caption>
            <thead>
              <tr className="border-b border-line bg-surface-muted/60">
                <th
                  scope="col"
                  className="w-1/4 px-5 py-3.5 text-[11px] font-semibold uppercase tracking-wider text-ink-muted"
                >
                  Dimension
                </th>
                <th
                  scope="col"
                  className="px-5 py-3.5 text-[13px] font-semibold text-ink"
                >
                  {siteName}
                </th>
                <th
                  scope="col"
                  className="px-5 py-3.5 text-[13px] font-semibold text-ink"
                >
                  {comparison.other}
                </th>
              </tr>
            </thead>
            <tbody>
              {comparison.rows.map((row) => (
                <tr
                  key={row.dimension}
                  className="border-b border-line-subtle bg-surface last:border-b-0"
                >
                  <th
                    scope="row"
                    className="px-5 py-4 align-top text-sm font-medium text-ink"
                  >
                    {row.dimension}
                  </th>
                  <td className="px-5 py-4 align-top text-sm leading-relaxed text-ink-secondary">
                    {row.founderOs}
                  </td>
                  <td className="px-5 py-4 align-top text-sm leading-relaxed text-ink-secondary">
                    {row.other}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* ── Long-form ──────────────────────────────────────────────── */}
      {comparison.body.map((block) => (
        <Section key={block.heading} bordered>
          <Prose>
            <h2>{block.heading}</h2>
            {block.paragraphs.map((paragraph) => (
              <p key={paragraph.slice(0, 40)}>{paragraph}</p>
            ))}
          </Prose>
        </Section>
      ))}

      {/* ── When the other one wins ────────────────────────────────── */}
      <Section bordered labelledBy="when-other-title">
        <SectionHeading
          id="when-other-title"
          eyebrow="Honestly"
          title={`When ${comparison.other} is the better choice`}
          lead="If one of these is your situation, this is the wrong product for you and it is cheaper to find that out here."
        />
        <ul className="mt-8 grid max-w-4xl gap-4 sm:grid-cols-2">
          {comparison.whenOther.map((item) => (
            <li
              key={item}
              className="rounded-card border border-line bg-surface p-5 text-sm leading-relaxed text-ink-secondary"
            >
              {item}
            </li>
          ))}
        </ul>
      </Section>

      {/* ── Other comparisons ──────────────────────────────────────── */}
      <Section bordered labelledBy="other-comparisons-title">
        <SectionHeading id="other-comparisons-title" title="Other comparisons" />
        <div className="mt-8 grid gap-6 md:grid-cols-2">
          {others.map((other) => (
            <Link
              key={other.slug}
              href={`/compare/${other.slug}`}
              className="group rounded-card border border-line bg-surface p-6 transition-colors duration-150 hover:bg-surface-muted"
            >
              <p className="text-[13px] font-medium text-accent-text">
                vs {other.other}
              </p>
              <h3 className="mt-2 font-serif text-lg font-semibold text-ink">
                {other.title}
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
        <p className="mt-8 text-sm text-ink-secondary">
          Or go straight to the mechanics in the{" "}
          <Link
            href="/features"
            className="font-medium text-accent-text underline underline-offset-2 hover:no-underline"
          >
            feature breakdown
          </Link>{" "}
          and the{" "}
          <Link
            href="/pricing"
            className="font-medium text-accent-text underline underline-offset-2 hover:no-underline"
          >
            pricing page
          </Link>
          .
        </p>
      </Section>

      <CtaBand />
    </>
  );
}
