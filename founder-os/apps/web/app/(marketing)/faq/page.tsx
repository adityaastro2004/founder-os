import Link from "next/link";
import { PageHero } from "../_components/page-hero";
import { CtaBand } from "../_components/cta-band";
import { FaqSection } from "../_components/faq-section";
import { Section, SectionHeading, Prose } from "../_components/section";
import { faqs } from "../../../lib/faq";
import { contactEmail, pageMetadata, responseTimePromise } from "../../../lib/site";

export const metadata = pageMetadata({
  title: "FAQ — pricing, setup, privacy and self-hosting",
  description:
    "Answers to the practical questions about Founder OS: what it costs, how long setup takes, which AI models it runs on, whether your data trains models, and how to self-host it.",
  path: "/faq",
  keywords: [
    "Founder OS FAQ",
    "Founder OS pricing",
    "self-host AI assistant",
    "does AI train on my data",
  ],
});

export default function FaqPage() {
  return (
    <>
      <PageHero
        eyebrow="FAQ"
        title="Frequently asked questions"
        lead="The practical ones — cost, setup, models, data handling and self-hosting. If yours is not here, ask it directly and it will be answered by a person."
        crumbs={[{ href: "/faq", label: "FAQ" }]}
      />

      <Section>
        <div className="max-w-3xl">
          {/* The one FAQPage schema block for this URL — the home page FAQ
              deliberately omits it (duplicate FAQPage markup is invalid). */}
          <FaqSection items={faqs} emitSchema />
        </div>
      </Section>

      <Section bordered labelledBy="faq-still-title">
        <SectionHeading
          id="faq-still-title"
          title="Still unanswered?"
          lead={responseTimePromise}
        />
        <Prose className="mt-6">
          <ul>
            <li>
              Email <a href={`mailto:${contactEmail}`}>{contactEmail}</a> — the
              fastest route.
            </li>
            <li>
              Use the <Link href="/contact">contact page</Link> if you would rather
              have a form, including what to include for a useful first reply.
            </li>
            <li>
              For depth on how a specific part works, read the{" "}
              <Link href="/features">feature breakdown</Link> or an{" "}
              <Link href="/case-studies">illustrative scenario</Link>.
            </li>
            <li>
              For plan limits and exact prices, see{" "}
              <Link href="/pricing">pricing</Link>; for which tools connect
              today, see <Link href="/integrations">integrations</Link>.
            </li>
            <li>
              If you are still choosing between options, the{" "}
              <Link href="/compare">comparison pages</Link> say when something
              else is the better fit.
            </li>
          </ul>
        </Prose>
      </Section>

      <CtaBand
        title="Answers are cheaper once you have your own state"
        body="Most questions about fit resolve in ten minutes on the free tier with one tool connected."
      />
    </>
  );
}
