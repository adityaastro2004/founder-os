import Link from "next/link";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Container } from "../_components/section";
import { CtaLink } from "../_components/cta-link";
import {
  contactEmail,
  pageMetadata,
  responseTimePromise,
  supportHours,
} from "../../../lib/site";

/**
 * Post-submission confirmation.
 *
 * `noindex` on purpose: a thank-you page has no search value, and letting it
 * rank would put visitors at the end of a funnel they never entered. It stays
 * `follow` so the links out of it still pass authority, and it is excluded from
 * both robots.txt and the sitemap.
 *
 * It is also the natural conversion goal to configure in Google Analytics —
 * reaching /thank-you is the event worth counting.
 */
export const metadata = pageMetadata({
  title: "Thank you — your message is on its way",
  description:
    "Your message has been composed. We reply to every message within 24 hours on business days.",
  path: "/thank-you",
  noindex: true,
});

const next = [
  {
    href: "/features",
    title: "Read the feature breakdown",
    body: "Every part of the system, in detail — state engine, agents, memory, adapters, approval gate.",
  },
  {
    href: "/case-studies",
    title: "See a week in practice",
    body: "Three illustrative walkthroughs showing which part of the system removes which friction.",
  },
  {
    href: "/faq",
    title: "Check the FAQ",
    body: "Cost, setup time, models, data handling and self-hosting — answered without a sales call.",
  },
];

export default function ThankYouPage() {
  return (
    <>
      <Container className="py-16 md:py-24">
        <div className="max-w-2xl">
          <CheckCircle2 className="h-8 w-8 text-success" aria-hidden="true" />
          <h1 className="mt-6 font-serif text-3xl font-semibold leading-tight tracking-tight text-ink sm:text-4xl md:text-5xl">
            Thank you — that reached the right person
          </h1>
          <p className="mt-5 text-base leading-relaxed text-ink-secondary md:text-lg">
            {responseTimePromise} Support hours are {supportHours}, so a message
            sent over the weekend gets answered on Monday. If your mail app did not
            open, write to{" "}
            <a
              href={`mailto:${contactEmail}`}
              className="text-accent-text underline underline-offset-2 hover:no-underline"
            >
              {contactEmail}
            </a>{" "}
            directly.
          </p>

          <div className="mt-9 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
            <CtaLink href="/sign-up" size="lg">
              Start for free while you wait
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </CtaLink>
            <CtaLink href="/" variant="secondary" size="lg">
              Back to home
            </CtaLink>
          </div>
        </div>
      </Container>

      <section
        aria-labelledby="thank-you-next-title"
        className="border-t border-line"
      >
        <Container className="py-14 md:py-20">
          <h2
            id="thank-you-next-title"
            className="font-serif text-2xl font-semibold tracking-tight text-ink md:text-3xl"
          >
            While you wait
          </h2>
          <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
            {next.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="group rounded-card border border-line bg-surface p-6 transition-colors duration-150 hover:bg-surface-muted"
              >
                <h3 className="font-serif text-lg font-semibold text-ink">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
                  {item.body}
                </p>
                <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-accent-text">
                  Open
                  <ArrowRight
                    className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5"
                    aria-hidden="true"
                  />
                </span>
              </Link>
            ))}
          </div>
        </Container>
      </section>
    </>
  );
}
