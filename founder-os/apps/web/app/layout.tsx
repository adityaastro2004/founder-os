import type { Metadata } from "next";
import localFont from "next/font/local";
import { Source_Serif_4 } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { PostHogIdentify } from "./_components/posthog-identify";
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

const clerkAppearance = {
  variables: {
    colorPrimary: "#c96442",
    colorText: "#1f1e1d",
    colorTextSecondary: "#63605b",
    colorBackground: "#ffffff",
    colorInputBackground: "#ffffff",
    borderRadius: "8px",
    fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
  },
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
      className={`${geistSans.variable} ${geistMono.variable} ${sourceSerif.variable}`}
    >
      {/* Font variable classes live on <html>: the @theme font tokens are
          defined on :root and resolve nested var()s there, not on <body>. */}
      <body className="antialiased">
        {hasClerk ? (
          <ClerkProvider appearance={clerkAppearance}>
            {children}
            <PostHogIdentify />
          </ClerkProvider>
        ) : (
          children
        )}
      </body>
    </html>
  );
}
