import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { Source_Serif_4 } from "next/font/google";
import { PostHogIdentify } from "./_components/posthog-identify";
import { AppClerkProvider } from "./_components/app-clerk-provider";
import { ThemeProvider, themeInitScript } from "./_components/theme";
import { GoogleAnalytics } from "./_components/google-analytics";
import { JsonLd } from "./_components/json-ld";
import {
  organizationSchema,
  siteDescription,
  siteName,
  siteUrl,
  websiteSchema,
} from "../lib/site";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
});
const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
});

export const metadata: Metadata = {
  // Resolves every relative URL below (OG images, canonicals) to an absolute
  // one — crawlers and social scrapers reject relative image paths.
  metadataBase: new URL(siteUrl),
  // Each page exports its own `title` string; this template appends the brand
  // so titles stay unique per page instead of all reading "Founder OS".
  title: {
    default: `${siteName} — the autonomous operating system for founders`,
    template: `%s · ${siteName}`,
  },
  description: siteDescription,
  applicationName: siteName,
  authors: [{ name: siteName, url: siteUrl }],
  creator: siteName,
  publisher: siteName,
  category: "technology",
  formatDetection: { telephone: false, address: false, email: false },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: siteUrl,
    siteName,
    title: `${siteName} — the autonomous operating system for founders`,
    description: siteDescription,
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        type: "image/png",
        alt: `${siteName} — one system that knows your whole company`,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: `${siteName} — the autonomous operating system for founders`,
    description: siteDescription,
    images: [
      {
        url: "/twitter-image",
        alt: `${siteName} — one system that knows your whole company`,
      },
    ],
  },
  robots: {
    index: true,
    follow: true,
    // max-snippet/max-video-preview unbounded and large image previews: without
    // these Google may show a truncated snippet and a thumbnail-sized image.
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  // Search Console / Bing Webmaster ownership proof. Env-gated so a missing key
  // emits no tag at all rather than an empty `content=""` that fails validation.
  verification: {
    google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION || undefined,
    other: process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION
      ? { "msvalidate.01": process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION }
      : undefined,
  },
  // No `alternates.canonical` here on purpose: root metadata is inherited by
  // every route, so a canonical set here would tag the 404 and the auth pages
  // as duplicates of "/". Canonicals come from `pageMetadata()` per page.
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Matches --color-paper in both themes so mobile browser chrome blends in.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9f5" },
    { media: "(prefers-color-scheme: dark)", color: "#262624" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const hasClerk = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${sourceSerif.variable}`}
    >
      {/* Font variable classes live on <html>: the @theme font tokens are
          defined on :root and resolve nested var()s there, not on <body>.
          suppressHydrationWarning: the theme script may add .dark before
          hydration, which the server render can't know about. */}
      <body className="antialiased">
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {/* Site-wide structured data. Page-level schema (FAQPage,
            BreadcrumbList, Article) is emitted by the pages themselves. */}
        <JsonLd data={organizationSchema} />
        <JsonLd data={websiteSchema} />
        <GoogleAnalytics />
        <ThemeProvider>
          {hasClerk ? (
            <AppClerkProvider>
              {children}
              <PostHogIdentify />
            </AppClerkProvider>
          ) : (
            children
          )}
        </ThemeProvider>
      </body>
    </html>
  );
}
