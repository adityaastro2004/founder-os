import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";
import { SiteHeader } from "./(marketing)/_components/site-header";
import { SiteFooter } from "./(marketing)/_components/site-footer";
import { CtaLink } from "./(marketing)/_components/cta-link";
import { Container } from "./(marketing)/_components/section";

/**
 * Custom 404.
 *
 * `app/not-found.tsx` renders directly inside the root layout — it is outside
 * the `(marketing)` route group — so the header and footer are composed here by
 * hand instead of being inherited. Serves a real HTTP 404 status, and offers the
 * main destinations so a bad link is a detour rather than a dead end.
 */

// Next.js already emits `<meta name="robots" content="noindex">` for
// not-found, so this only supplies the unique title and description.
export const metadata = {
  title: "Page not found (404)",
  description:
    "That page does not exist. Jump to the Founder OS home page, features, case studies, FAQ or contact page instead.",
};

const destinations = [
  {
    href: "/",
    title: "Home",
    body: "What Founder OS is, how the five loops work, and why company state is the point.",
  },
  {
    href: "/features",
    title: "Features",
    body: "The state engine, the agents, memory, tool sync, planning and the approval gate.",
  },
  {
    href: "/case-studies",
    title: "Case studies",
    body: "Three illustrative walkthroughs of a week with Founder OS.",
  },
  {
    href: "/faq",
    title: "FAQ",
    body: "Cost, setup time, models, data handling and self-hosting.",
  },
  {
    href: "/about",
    title: "About us",
    body: "Who builds this, and the principles it is built on.",
  },
  {
    href: "/contact",
    title: "Contact us",
    body: "Email a person and get an answer within 24 hours on business days.",
  },
];

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <SiteHeader />
      <main className="flex-1">
        <Container className="py-16 md:py-24">
          <div className="max-w-2xl">
            <p className="font-mono text-sm text-accent-text">404</p>
            <h1 className="mt-4 font-serif text-3xl font-semibold leading-tight tracking-tight text-ink sm:text-4xl md:text-5xl">
              That page is not part of the system
            </h1>
            <p className="mt-5 text-base leading-relaxed text-ink-secondary md:text-lg">
              The URL you followed does not exist — it may have moved, or the link
              may have been mistyped. Nothing is broken on your side.
            </p>
            <div className="mt-8 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
              <CtaLink href="/" size="lg">
                Back to home
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </CtaLink>
              <CtaLink href="/contact" variant="secondary" size="lg">
                Report a broken link
              </CtaLink>
            </div>
          </div>
        </Container>

        <section aria-labelledby="not-found-links" className="border-t border-line">
          <Container className="py-14 md:py-20">
            <div className="flex items-center gap-2.5">
              <Search className="h-4 w-4 text-ink-muted" aria-hidden="true" />
              <h2
                id="not-found-links"
                className="font-serif text-xl font-semibold tracking-tight text-ink md:text-2xl"
              >
                Try one of these instead
              </h2>
            </div>
            <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {destinations.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group rounded-card border border-line bg-surface p-5 transition-colors duration-150 hover:bg-surface-muted"
                >
                  <h3 className="font-serif text-lg font-semibold text-ink">
                    {item.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
                    {item.body}
                  </p>
                </Link>
              ))}
            </div>
          </Container>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
