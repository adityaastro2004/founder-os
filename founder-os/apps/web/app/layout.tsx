import type { Metadata } from "next";
import localFont from "next/font/local";
import { Source_Serif_4 } from "next/font/google";
import { PostHogIdentify } from "./_components/posthog-identify";
import { AppClerkProvider } from "./_components/app-clerk-provider";
import { ThemeProvider, themeInitScript } from "./_components/theme";
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
  title: "Founder OS",
  description: "AI-powered operating system for founders",
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
