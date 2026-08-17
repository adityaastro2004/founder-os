import { clsx } from "clsx";

/**
 * Layout primitives shared by every marketing page, so page files carry copy
 * and structure rather than repeated spacing utilities.
 *
 * `Container` fixes one horizontal rhythm (px-6 on phones, wider gutters from
 * `md`) — every page uses it, which is what keeps the site responsive without
 * per-page media queries.
 */

export function Container({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("mx-auto w-full max-w-6xl px-6 md:px-10", className)}>
      {children}
    </div>
  );
}

export function Section({
  children,
  className,
  bordered,
  id,
  labelledBy,
}: {
  children: React.ReactNode;
  className?: string;
  /** Adds the hairline top border that separates content bands. */
  bordered?: boolean;
  id?: string;
  labelledBy?: string;
}) {
  return (
    <section
      id={id}
      aria-labelledby={labelledBy}
      className={clsx(
        "py-14 md:py-20",
        bordered && "border-t border-line",
        className,
      )}
    >
      <Container>{children}</Container>
    </section>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  id,
  lead,
  align = "left",
}: {
  eyebrow?: string;
  title: string;
  id?: string;
  lead?: string;
  align?: "left" | "center";
}) {
  return (
    <div
      className={clsx(
        "max-w-2xl",
        align === "center" && "mx-auto text-center",
      )}
    >
      {eyebrow && (
        <p className="mb-3 text-[13px] font-medium text-accent-text">{eyebrow}</p>
      )}
      <h2
        id={id}
        className="font-serif text-2xl font-semibold leading-tight tracking-tight text-ink sm:text-3xl md:text-4xl"
      >
        {title}
      </h2>
      {lead && (
        <p className="mt-4 text-base leading-relaxed text-ink-secondary md:text-lg">
          {lead}
        </p>
      )}
    </div>
  );
}

/**
 * Long-form copy wrapper for the legal, about and case-study pages. Styles are
 * applied by element so page bodies can stay plain semantic HTML.
 */
export function Prose({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "max-w-3xl text-[15px] leading-relaxed text-ink-secondary md:text-base",
        "[&_a]:text-accent-text [&_a]:underline [&_a]:underline-offset-2 [&_a:hover]:no-underline",
        "[&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:font-serif [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:tracking-tight [&_h2]:text-ink [&_h2]:md:text-2xl",
        "[&_h3]:mt-7 [&_h3]:mb-2 [&_h3]:font-serif [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-ink",
        "[&_p]:mt-4 [&_ul]:mt-4 [&_ol]:mt-4 [&_ul]:space-y-2 [&_ol]:space-y-2",
        "[&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5",
        "[&_li::marker]:text-ink-muted",
        "[&_strong]:font-semibold [&_strong]:text-ink",
        className,
      )}
    >
      {children}
    </div>
  );
}
