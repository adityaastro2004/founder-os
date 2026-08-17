import type { MetadataRoute } from "next";
import { absoluteUrl, siteUrl } from "../lib/site";

/**
 * Serves /robots.txt.
 *
 * Public marketing pages are crawlable; everything behind auth (dashboard,
 * onboarding, Clerk's sign-in/sign-up flows) and the API proxy is disallowed —
 * those pages are user-specific, return redirects to crawlers, and would only
 * dilute the crawl budget for the pages that can actually rank.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/api/",
          "/dashboard",
          "/dashboard/",
          "/onboarding",
          "/onboarding/",
          "/sign-in",
          "/sign-up",
          "/thank-you",
        ],
      },
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
    host: siteUrl,
  };
}
