import Script from "next/script";

/**
 * Google Analytics 4.
 *
 * Opt-in, exactly like the PostHog init in `instrumentation-client.ts`: with no
 * NEXT_PUBLIC_GA_ID at build time nothing is injected and no requests are made,
 * so local dev, CI and previews stay clean.
 *
 * `afterInteractive` keeps gtag.js off the critical path — it loads once the
 * page is interactive, so it does not cost anything in Core Web Vitals (LCP).
 * GA4 tracks App Router client navigations itself via History API events.
 */
export function GoogleAnalytics() {
  const gaId = process.env.NEXT_PUBLIC_GA_ID;
  if (!gaId) return null;

  return (
    <>
      <Script
        src={`https://www.googletagmanager.com/gtag/js?id=${gaId}`}
        strategy="afterInteractive"
      />
      <Script id="ga4-init" strategy="afterInteractive">
        {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${gaId}');`}
      </Script>
    </>
  );
}
