import type { Metadata } from "next";

/**
 * Single source of truth for the public marketing site: canonical origin,
 * contact details, navigation, and the structured-data (JSON-LD) builders.
 *
 * Every marketing page derives its <title>, meta description, canonical URL and
 * social-share tags from `pageMetadata()` here, so a page can never ship with
 * the generic site-wide defaults by accident.
 */

/** Canonical origin, no trailing slash. Overridable per environment. */
export const siteUrl = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://myfounder.vercel.app"
).replace(/\/$/, "");

export const siteName = "Founder OS";
export const siteTagline = "The autonomous operating system for founders";
export const siteDescription =
  "Founder OS is an AI operating system for solo founders. One Orchestrator, specialist agents, and a Company State Engine that keeps a single source of truth across the tools you already use.";

export const contactEmail = "adityaastro.id2004@gmail.com";
/** Shown on /contact, /faq and in the footer — keep these three in sync. */
export const responseTimePromise =
  "We reply to every message within 24 hours on business days.";
export const supportHours = "Mon–Fri, 10:00–19:00 IST";

export const businessLocality = "New Delhi";
export const businessRegion = "Delhi";
export const businessCountry = "IN";
export const foundingYear = "2026";

/** Header nav — kept short on purpose; the footer carries the full link map. */
export const primaryNav = [
  { href: "/features", label: "Features" },
  { href: "/case-studies", label: "Case studies" },
  { href: "/about", label: "About" },
  { href: "/faq", label: "FAQ" },
  { href: "/contact", label: "Contact" },
] as const;

export const footerNav = [
  {
    heading: "Product",
    links: [
      { href: "/features", label: "Features" },
      { href: "/case-studies", label: "Case studies" },
      { href: "/faq", label: "FAQ" },
      { href: "/sign-up", label: "Get started free" },
    ],
  },
  {
    heading: "Company",
    links: [
      { href: "/about", label: "About us" },
      { href: "/contact", label: "Contact us" },
      { href: "https://github.com/adityaastro2004/founder-os", label: "GitHub" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { href: "/privacy", label: "Privacy policy" },
      { href: "/terms", label: "Terms & conditions" },
    ],
  },
] as const;

/** Absolute URL for a site-relative path — required by OG tags and sitemaps. */
export function absoluteUrl(path = "/"): string {
  return `${siteUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

type PageMetaInput = {
  /** Page-specific title, without the " · Founder OS" suffix. */
  title: string;
  /** 120–165 characters is the sweet spot before Google truncates. */
  description: string;
  /** Site-relative path, used for the canonical URL. */
  path: string;
  keywords?: string[];
  /** Set for legal/thank-you pages that should not be indexed or ranked. */
  noindex?: boolean;
  /** Marks the page as an article for richer social cards. */
  type?: "website" | "article";
};

/**
 * The generated social card, served by `app/opengraph-image.tsx` and
 * `app/twitter-image.tsx`.
 *
 * These have to be referenced explicitly: a page that exports its own
 * `openGraph` object replaces the root layout's wholesale, which drops the
 * file-based image Next.js attached there. Without this, pages ship with no
 * og:image at all.
 */
const ogImage = {
  url: "/opengraph-image",
  width: 1200,
  height: 630,
  type: "image/png",
};

/**
 * Builds a complete, unique metadata block for one page: title, description,
 * canonical link, Open Graph and Twitter cards. `metadataBase` in the root
 * layout resolves the relative OG image path against the canonical origin.
 */
export function pageMetadata({
  title,
  description,
  path,
  keywords,
  noindex,
  type = "website",
}: PageMetaInput): Metadata {
  const url = absoluteUrl(path);
  return {
    title,
    description,
    keywords,
    alternates: { canonical: url },
    robots: noindex ? { index: false, follow: true } : undefined,
    openGraph: {
      type,
      url,
      siteName,
      locale: "en_US",
      title: `${title} · ${siteName}`,
      description,
      images: [{ ...ogImage, alt: `${title} — ${siteName}` }],
    },
    twitter: {
      card: "summary_large_image",
      title: `${title} · ${siteName}`,
      description,
      images: [{ url: "/twitter-image", alt: `${title} — ${siteName}` }],
    },
  };
}

/* ── Structured data (schema.org) ─────────────────────────────────────────
   Emitted as JSON-LD via the <JsonLd> component. Organization + WebSite +
   SoftwareApplication are site-wide (root layout); the rest are per page. */

export const organizationSchema = {
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": `${siteUrl}/#organization`,
  name: siteName,
  url: siteUrl,
  logo: absoluteUrl("/logo-icon.png"),
  description: siteDescription,
  foundingDate: foundingYear,
  email: contactEmail,
  address: {
    "@type": "PostalAddress",
    addressLocality: businessLocality,
    addressRegion: businessRegion,
    addressCountry: businessCountry,
  },
  contactPoint: {
    "@type": "ContactPoint",
    contactType: "customer support",
    email: contactEmail,
    availableLanguage: ["English", "Hindi"],
    areaServed: "Worldwide",
  },
  sameAs: ["https://github.com/adityaastro2004/founder-os"],
};

export const websiteSchema = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": `${siteUrl}/#website`,
  url: siteUrl,
  name: siteName,
  description: siteDescription,
  inLanguage: "en",
  publisher: { "@id": `${siteUrl}/#organization` },
};

export const softwareApplicationSchema = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: siteName,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web browser",
  url: siteUrl,
  description: siteDescription,
  featureList: [
    "Company State Engine — one canonical model of your company",
    "Orchestrator with specialist AI agents",
    "Four-layer long-term memory and temporal knowledge graph",
    "Two-way sync with Obsidian and Notion",
    "Weekly planning with Google Calendar",
    "Human-in-the-loop approval gate",
  ],
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
    description: "Free tier — no credit card required",
  },
  publisher: { "@id": `${siteUrl}/#organization` },
};

/**
 * Local business schema. Founder OS is sold worldwide as software, so this
 * describes the operating entity's location for local search — it is not a
 * storefront claim.
 */
export const localBusinessSchema = {
  "@context": "https://schema.org",
  "@type": "ProfessionalService",
  "@id": `${siteUrl}/#localbusiness`,
  name: siteName,
  description: `${siteName} builds AI operating-system software for solo founders and small teams, operated from ${businessLocality}, India and available worldwide.`,
  url: siteUrl,
  image: absoluteUrl("/logo-icon.png"),
  email: contactEmail,
  priceRange: "Free – paid plans",
  address: {
    "@type": "PostalAddress",
    addressLocality: businessLocality,
    addressRegion: businessRegion,
    addressCountry: businessCountry,
  },
  areaServed: [
    { "@type": "City", name: businessLocality },
    { "@type": "Country", name: "India" },
    { "@type": "Place", name: "Worldwide (remote)" },
  ],
  openingHoursSpecification: {
    "@type": "OpeningHoursSpecification",
    dayOfWeek: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    opens: "10:00",
    closes: "19:00",
  },
  parentOrganization: { "@id": `${siteUrl}/#organization` },
};

export type FaqItem = { question: string; answer: string };

export function faqPageSchema(items: readonly FaqItem[]) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };
}

export type Crumb = { href: string; label: string };

export function breadcrumbSchema(crumbs: readonly Crumb[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: crumbs.map((crumb, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: crumb.label,
      item: absoluteUrl(crumb.href),
    })),
  };
}
