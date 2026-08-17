import { CtaLink } from "./cta-link";
import { Container } from "./section";
import { responseTimePromise } from "../../../lib/site";

/**
 * Closing conversion band, repeated at the bottom of every marketing page so a
 * reader who scrolls to the end always has the next step in front of them.
 */
export function CtaBand({
  title = "Start with one source of truth",
  body = "Connect your first tool, let the engine build your company state, and see what one system that knows everything actually feels like.",
  primaryLabel = "Start for free",
  primaryHref = "/sign-up",
  secondaryLabel = "Talk to us",
  secondaryHref = "/contact",
}: {
  title?: string;
  body?: string;
  primaryLabel?: string;
  primaryHref?: string;
  secondaryLabel?: string;
  secondaryHref?: string;
}) {
  return (
    <section aria-labelledby="cta-band-title" className="border-t border-line bg-surface-muted/40">
      <Container className="py-14 text-center md:py-20">
        <h2
          id="cta-band-title"
          className="mx-auto max-w-2xl font-serif text-2xl font-semibold leading-tight tracking-tight text-ink sm:text-3xl md:text-4xl"
        >
          {title}
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-ink-secondary">
          {body}
        </p>
        <div className="mt-8 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
          <CtaLink href={primaryHref} size="lg">
            {primaryLabel}
          </CtaLink>
          <CtaLink href={secondaryHref} variant="secondary" size="lg">
            {secondaryLabel}
          </CtaLink>
        </div>
        <p className="mt-5 text-[13px] text-ink-secondary">
          Free tier, no credit card. {responseTimePromise}
        </p>
      </Container>
    </section>
  );
}
