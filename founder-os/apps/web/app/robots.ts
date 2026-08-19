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

/** Authenticated, machine-only or no-search-value paths. */
const privatePaths = [
  "/api/",
  "/dashboard",
  "/dashboard/",
  "/onboarding",
  "/onboarding/",
  "/sign-in",
  "/sign-up",
  "/thank-you",
];

/**
 * Answer-engine crawlers, listed explicitly rather than left to the wildcard.
 *
 * Founder OS is an AI product, so a meaningful share of its qualified traffic
 * now arrives through AI answers rather than blue links. These agents are
 * allowed deliberately — and naming them means the decision is visible and
 * reversible in one place instead of being an accident of the `*` rule.
 */
const answerEngines = [
  "GPTBot",
  "OAI-SearchBot",
  "ChatGPT-User",
  "ClaudeBot",
  "Claude-User",
  "Claude-SearchBot",
  "PerplexityBot",
  "Perplexity-User",
  "Google-Extended",
  "Applebot-Extended",
  "Bingbot",
  "DuckDuckBot",
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: privatePaths,
      },
      {
        userAgent: answerEngines,
        allow: "/",
        disallow: privatePaths,
      },
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
    host: siteUrl,
  };
}
