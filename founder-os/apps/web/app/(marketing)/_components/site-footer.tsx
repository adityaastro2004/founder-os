import Link from "next/link";
import { LogoMark } from "../../_components/logo-mark";
import {
  contactEmail,
  footerNav,
  responseTimePromise,
  siteName,
} from "../../../lib/site";

/**
 * Site footer.
 *
 * Doubles as the site's internal link map: every indexable page is reachable
 * from every other page in one hop, which is what stops the deeper pages
 * (case studies, legal) from becoming orphans.
 */
export function SiteFooter() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto w-full max-w-6xl px-6 py-12 md:px-10 md:py-16">
        <div className="grid grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:pr-8">
            <Link href="/" className="flex items-center gap-2.5">
              <LogoMark className="h-7" />
              <span className="font-serif text-base font-semibold tracking-tight text-ink">
                {siteName}
              </span>
            </Link>
            <p className="mt-4 text-sm leading-relaxed text-ink-secondary">
              An AI operating system for solo founders and tiny teams. One
              canonical company state, kept in sync with the tools you already
              use.
            </p>
            <p className="mt-4 text-sm leading-relaxed text-ink-secondary">
              <a
                href={`mailto:${contactEmail}`}
                className="text-accent-text underline underline-offset-2 hover:no-underline"
              >
                {contactEmail}
              </a>
              <br />
              <span className="text-ink-muted">{responseTimePromise}</span>
            </p>
          </div>

          {footerNav.map((column) => (
            <nav key={column.heading} aria-label={column.heading}>
              <h2 className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                {column.heading}
              </h2>
              <ul className="mt-4 space-y-2.5">
                {column.links.map((link) => {
                  const external = link.href.startsWith("http");
                  return (
                    <li key={link.href}>
                      {external ? (
                        <a
                          href={link.href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-ink-secondary transition-colors duration-150 hover:text-ink"
                        >
                          {link.label}
                        </a>
                      ) : (
                        <Link
                          href={link.href}
                          className="text-sm text-ink-secondary transition-colors duration-150 hover:text-ink"
                        >
                          {link.label}
                        </Link>
                      )}
                    </li>
                  );
                })}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-line pt-6 text-xs text-ink-secondary sm:flex-row sm:items-center sm:justify-between">
          <p>
            &copy; {new Date().getFullYear()} {siteName}. Operated from New Delhi,
            India.
          </p>
          {/* `py-1` + `gap-y-2` take these from 16px-tall targets to 24px with
              8px between them — WCAG 2.5.8 — without moving the row visually. */}
          <p className="flex flex-wrap gap-x-4 gap-y-2">
            <Link href="/privacy" className="inline-block py-1 hover:text-ink">
              Privacy
            </Link>
            <Link href="/terms" className="inline-block py-1 hover:text-ink">
              Terms
            </Link>
            <Link href="/contact" className="inline-block py-1 hover:text-ink">
              Contact
            </Link>
            <a href="/sitemap.xml" className="inline-block py-1 hover:text-ink">
              Sitemap
            </a>
          </p>
        </div>
      </div>
    </footer>
  );
}
