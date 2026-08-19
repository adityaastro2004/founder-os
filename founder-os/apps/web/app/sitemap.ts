import type { MetadataRoute } from "next";
import { caseStudies } from "../lib/case-studies";
import { comparisons } from "../lib/comparisons";
import { integrations } from "../lib/integrations";
import { absoluteUrl } from "../lib/site";

/**
 * Serves /sitemap.xml (referenced from robots.txt).
 *
 * Only indexable public pages belong here — authenticated routes and the
 * noindex'd /thank-you page are deliberately absent. `priority` and
 * `changeFrequency` are hints only; the useful signal is the complete,
 * canonical URL list.
 *
 * `lastModified` is a per-page date, not `new Date()`. Stamping every URL with
 * the build time tells a crawler the legal pages changed on every deploy, which
 * trains it to ignore the field. Bump a page's date when its content actually
 * changes.
 */

type Entry = {
  path: string;
  priority: number;
  changeFrequency: "daily" | "weekly" | "monthly" | "yearly";
  /** ISO date of the last meaningful content change to this page. */
  lastModified: string;
};

const SEO_REVISION = "2026-08-19";

const staticPages: Entry[] = [
  { path: "/", priority: 1, changeFrequency: "weekly", lastModified: SEO_REVISION },
  { path: "/features", priority: 0.9, changeFrequency: "monthly", lastModified: SEO_REVISION },
  { path: "/pricing", priority: 0.9, changeFrequency: "monthly", lastModified: SEO_REVISION },
  { path: "/integrations", priority: 0.8, changeFrequency: "monthly", lastModified: SEO_REVISION },
  { path: "/compare", priority: 0.8, changeFrequency: "monthly", lastModified: SEO_REVISION },
  { path: "/case-studies", priority: 0.8, changeFrequency: "monthly", lastModified: SEO_REVISION },
  { path: "/faq", priority: 0.7, changeFrequency: "monthly", lastModified: SEO_REVISION },
  { path: "/about", priority: 0.7, changeFrequency: "monthly", lastModified: SEO_REVISION },
  { path: "/contact", priority: 0.6, changeFrequency: "yearly", lastModified: SEO_REVISION },
  { path: "/privacy", priority: 0.3, changeFrequency: "yearly", lastModified: "2026-08-17" },
  { path: "/terms", priority: 0.3, changeFrequency: "yearly", lastModified: "2026-08-17" },
];

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    ...staticPages.map((page) => ({
      url: absoluteUrl(page.path),
      lastModified: page.lastModified,
      changeFrequency: page.changeFrequency,
      priority: page.priority,
    })),
    ...integrations.map((integration) => ({
      url: absoluteUrl(`/integrations/${integration.slug}`),
      lastModified: SEO_REVISION,
      changeFrequency: "monthly" as const,
      priority: 0.7,
    })),
    ...comparisons.map((comparison) => ({
      url: absoluteUrl(`/compare/${comparison.slug}`),
      lastModified: SEO_REVISION,
      changeFrequency: "monthly" as const,
      priority: 0.7,
    })),
    ...caseStudies.map((study) => ({
      url: absoluteUrl(`/case-studies/${study.slug}`),
      lastModified: "2026-08-17",
      changeFrequency: "monthly" as const,
      priority: 0.6,
    })),
  ];
}
