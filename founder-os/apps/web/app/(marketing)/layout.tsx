import { SiteHeader } from "./_components/site-header";
import { SiteFooter } from "./_components/site-footer";
import { StickyMobileCta } from "./_components/sticky-mobile-cta";
import { JsonLd } from "../_components/json-ld";
import { localBusinessSchema, softwareApplicationSchema } from "../../lib/site";

/**
 * Shell for every public, indexable page (a multi-page site: one URL per topic,
 * each server-rendered with its own title, description and canonical).
 *
 * The route group `(marketing)` adds no URL segment — `/`, `/about`, `/faq` …
 * all live here while the dashboard keeps its own shell.
 *
 * `pb-24 lg:pb-0` on <main> reserves room for the sticky phone CTA so it never
 * covers the end of the footer.
 */
export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <JsonLd data={softwareApplicationSchema} />
      <JsonLd data={localBusinessSchema} />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
      >
        Skip to content
      </a>
      <SiteHeader />
      <main id="main" className="flex-1 pb-24 lg:pb-0">
        {children}
      </main>
      <SiteFooter />
      <StickyMobileCta />
    </div>
  );
}
