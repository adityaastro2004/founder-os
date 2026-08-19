import Link from "next/link";
import { Check } from "lucide-react";
import { clsx } from "clsx";
import { PageHero } from "../_components/page-hero";
import { CtaLink } from "../_components/cta-link";
import { FaqSection } from "../_components/faq-section";
import { Section, SectionHeading, Prose } from "../_components/section";
import { JsonLd } from "../../_components/json-ld";
import { plans, priceRange, pricingFaqs, yearlySavingPercent } from "../../../lib/pricing";
import {
  absoluteUrl,
  faqPageSchema,
  organizationSchema,
  pageMetadata,
  siteName,
} from "../../../lib/site";

export const metadata = pageMetadata({
  title: "Pricing — free tier, then $99, $299 or $999 a month",
  description:
    "Founder OS pricing in full: a free plan with no card, Starter at $99/month, Pro at $299/month and Enterprise at $999/month. Annual billing saves about 16%. Self-hosting is free.",
  path: "/pricing",
  keywords: [
    "Founder OS pricing",
    "AI operating system pricing",
    "AI co-founder cost",
    "solo founder AI tool price",
    "free AI agent platform",
  ],
});

/**
 * Product + AggregateOffer, with one Offer per plan.
 *
 * Prices come from `lib/pricing.ts`, which mirrors the `subscription_plans`
 * seed. Publishing a price in structured data that the checkout does not charge
 * is a rich-result violation, so the two must be changed together.
 */
const productSchema = {
  "@context": "https://schema.org",
  "@type": "Product",
  name: siteName,
  description:
    "An AI operating system for solo founders: a Company State Engine, an Orchestrator with specialist agents, four-layer memory, and two-way sync with the tools you already use.",
  url: absoluteUrl("/pricing"),
  brand: { "@id": organizationSchema["@id"] },
  category: "BusinessApplication",
  offers: {
    "@type": "AggregateOffer",
    priceCurrency: priceRange.currency,
    lowPrice: String(priceRange.low),
    highPrice: String(priceRange.high),
    offerCount: plans.length,
    url: absoluteUrl("/pricing"),
    offers: plans.map((plan) => ({
      "@type": "Offer",
      name: plan.name,
      description: plan.tagline,
      price: String(plan.monthlyUsd),
      priceCurrency: priceRange.currency,
      url: `${absoluteUrl("/pricing")}#${plan.id}`,
      availability: "https://schema.org/InStock",
      priceSpecification: {
        "@type": "UnitPriceSpecification",
        price: String(plan.monthlyUsd),
        priceCurrency: priceRange.currency,
        billingDuration: 1,
        billingIncrement: 1,
        unitCode: "MON",
      },
    })),
  },
};

function formatPrice(usd: number): string {
  return usd === 0 ? "$0" : `$${usd.toLocaleString("en-US")}`;
}

export default function PricingPage() {
  return (
    <>
      <JsonLd data={productSchema} />
      <JsonLd data={faqPageSchema(pricingFaqs)} />

      <PageHero
        eyebrow="Pricing"
        title="Free to start. $99 a month when it earns it."
        lead="One subscription, four plans, no per-seat surprise. The free plan is a real plan rather than a countdown — connect a tool, build your company state, and judge the thing on your own data before paying anything."
        crumbs={[{ href: "/pricing", label: "Pricing" }]}
      />

      <Section>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {plans.map((plan) => {
            const saving = yearlySavingPercent(plan);
            return (
              <article
                key={plan.id}
                id={plan.id}
                className={clsx(
                  "flex scroll-mt-24 flex-col rounded-card border bg-surface p-6",
                  plan.featured
                    ? "border-accent ring-1 ring-accent"
                    : "border-line",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <h2 className="font-serif text-xl font-semibold tracking-tight text-ink">
                    {plan.name}
                  </h2>
                  {plan.featured && (
                    <span className="rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-accent-text">
                      Most picked
                    </span>
                  )}
                </div>

                <p className="mt-3 text-sm leading-relaxed text-ink-secondary">
                  {plan.tagline}
                </p>

                <p className="mt-6 flex items-baseline gap-1.5">
                  <span className="font-serif text-4xl font-semibold tracking-tight text-ink">
                    {formatPrice(plan.monthlyUsd)}
                  </span>
                  <span className="text-sm text-ink-secondary">/month</span>
                </p>
                <p className="mt-1.5 text-[13px] text-ink-muted">
                  {plan.monthlyUsd === 0
                    ? "Free forever"
                    : `or ${formatPrice(plan.yearlyUsd)}/year${saving ? ` — save ${saving}%` : ""}`}
                </p>
                {plan.note && (
                  <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
                    {plan.note}
                  </p>
                )}

                <div className="mt-6">
                  <CtaLink
                    href={plan.ctaHref}
                    variant={plan.featured ? "primary" : "secondary"}
                    className="w-full justify-center"
                  >
                    {plan.ctaLabel}
                  </CtaLink>
                </div>

                <ul className="mt-6 space-y-2 border-t border-line-subtle pt-5">
                  {plan.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex gap-2.5 text-sm leading-relaxed text-ink-secondary"
                    >
                      <Check
                        className="mt-0.5 h-4 w-4 shrink-0 text-accent"
                        aria-hidden="true"
                      />
                      {feature}
                    </li>
                  ))}
                </ul>

                <div className="mt-5 flex-1 border-t border-line-subtle pt-5">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                    Limits
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {plan.limits.map((limit) => (
                      <li key={limit} className="text-[13px] text-ink-secondary">
                        {limit}
                      </li>
                    ))}
                  </ul>
                </div>
              </article>
            );
          })}
        </div>

        <p className="mt-8 text-sm text-ink-secondary">
          All prices in USD, excluding any local taxes. Change or cancel from the
          billing page at any time — cancelling drops you to the Free plan
          limits and leaves your company state intact.
        </p>
      </Section>

      {/* ── The honest bit: it is free to self-host ─────────────────── */}
      <Section bordered labelledBy="pricing-selfhost-title">
        <SectionHeading
          id="pricing-selfhost-title"
          eyebrow="The other option"
          title="Self-hosting costs nothing"
          lead="This is worth saying on the pricing page rather than burying it in the FAQ."
        />
        <Prose className="mt-6">
          <p>
            The stack is OSS-first by design — FastAPI, Postgres with pgvector,
            Redis, Celery, and Ollama for inference — and it runs on your own
            machine or your own server. What the paid plans buy is hosting,
            support and the managed integrations. They do not buy the right to
            use the software, and there is no feature held hostage behind a
            licence check.
          </p>
          <p>
            The same applies to model costs. On the default configuration Ollama
            runs inference locally, so there is no per-token vendor bill at all.
            Point Founder OS at{" "}
            <Link href="/features">Anthropic, Google or an OpenAI-compatible endpoint</Link>{" "}
            and you supply your own key and pay that provider directly — Founder
            OS does not resell tokens or mark them up.
          </p>
          <p>
            If you want to see what you would be running before you decide, the{" "}
            <Link href="/features">feature breakdown</Link> describes each
            subsystem, and the{" "}
            <Link href="/integrations">integrations pages</Link> say exactly
            which tools connect today and in which direction data flows.
          </p>
        </Prose>
      </Section>

      {/* ── Pricing FAQ (its own FAQPage block — /faq owns the general set) ── */}
      <Section bordered labelledBy="pricing-faq-title">
        <SectionHeading
          id="pricing-faq-title"
          eyebrow="Questions"
          title="Pricing questions"
        />
        <div className="mt-8 max-w-3xl">
          {/* Schema is emitted above via `faqPageSchema(pricingFaqs)`, so this
              renderer must not emit a second FAQPage block for the same URL. */}
          <FaqSection items={pricingFaqs} />
          <p className="mt-6 text-sm text-ink-secondary">
            Everything else — setup time, data handling, which models it runs on
            — is on the{" "}
            <Link
              href="/faq"
              className="font-medium text-accent-text underline underline-offset-2 hover:no-underline"
            >
              general FAQ
            </Link>
            , or{" "}
            <Link
              href="/contact"
              className="font-medium text-accent-text underline underline-offset-2 hover:no-underline"
            >
              ask directly
            </Link>
            .
          </p>
        </div>
      </Section>
    </>
  );
}
