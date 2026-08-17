import { Breadcrumbs } from "./breadcrumbs";
import { Container } from "./section";
import type { Crumb } from "../../../lib/site";

/**
 * Standard header band for inner marketing pages: breadcrumbs, the single
 * `<h1>`, and one lead paragraph. Every inner page uses it so page titles keep
 * one visual weight and every page has exactly one h1.
 */
export function PageHero({
  eyebrow,
  title,
  lead,
  crumbs,
  children,
}: {
  eyebrow?: string;
  title: string;
  lead?: string;
  crumbs: Crumb[];
  children?: React.ReactNode;
}) {
  return (
    <div className="border-b border-line bg-surface-muted/40">
      <Container className="py-8 md:py-12">
        <Breadcrumbs crumbs={crumbs} />
        <div className="mt-6 max-w-3xl">
          {eyebrow && (
            <p className="mb-3 text-[13px] font-medium text-accent-text">
              {eyebrow}
            </p>
          )}
          <h1 className="font-serif text-3xl font-semibold leading-[1.15] tracking-tight text-ink sm:text-4xl md:text-5xl">
            {title}
          </h1>
          {lead && (
            <p className="mt-5 text-base leading-relaxed text-ink-secondary md:text-lg">
              {lead}
            </p>
          )}
          {children}
        </div>
      </Container>
    </div>
  );
}
