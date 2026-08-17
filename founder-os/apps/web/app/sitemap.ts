import type { MetadataRoute } from "next";
import { caseStudies } from "../lib/case-studies";
import { absoluteUrl } from "../lib/site";

/**
 * Serves /sitemap.xml (referenced from robots.txt).
 *
 * Only indexable public pages belong here — authenticated routes and the
 * noindex'd /thank-you page are deliberately absent. `priority` and
 * `changeFrequency` are hints only; the useful signal is the complete,
 * canonical URL list.
 */

type Entry = { path: string; priority: number; changeFrequency: "daily" | "weekly" | "monthly" | "yearly" };

const staticPages: Entry[] = [
  { path: "/", priority: 1, changeFrequency: "weekly" },
  { path: "/features", priority: 0.9, changeFrequency: "monthly" },
  { path: "/case-studies", priority: 0.8, changeFrequency: "monthly" },
  { path: "/about", priority: 0.7, changeFrequency: "monthly" },
  { path: "/faq", priority: 0.7, changeFrequency: "monthly" },
  { path: "/contact", priority: 0.6, changeFrequency: "yearly" },
  { path: "/privacy", priority: 0.3, changeFrequency: "yearly" },
  { path: "/terms", priority: 0.3, changeFrequency: "yearly" },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return [
    ...staticPages.map((page) => ({
      url: absoluteUrl(page.path),
      lastModified,
      changeFrequency: page.changeFrequency,
      priority: page.priority,
    })),
    ...caseStudies.map((study) => ({
      url: absoluteUrl(`/case-studies/${study.slug}`),
      lastModified,
      changeFrequency: "monthly" as const,
      priority: 0.6,
    })),
  ];
}
