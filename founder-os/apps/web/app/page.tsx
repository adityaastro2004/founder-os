import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import Link from "next/link";

export default async function Home() {
  const { userId } = await auth();

  if (userId) {
    redirect("/dashboard");
  }

  return (
    <div className="min-h-screen flex flex-col bg-white">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 md:px-12 lg:px-20 py-5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center">
            <span className="text-[var(--color-accent-foreground)] font-bold text-sm">F</span>
          </div>
          <span className="text-lg font-semibold tracking-tight">
            Founder OS
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/sign-in"
            className="px-4 py-2 text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="px-5 py-2 text-sm font-medium text-[var(--color-accent-foreground)] bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] rounded-lg transition-colors"
          >
            Get started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 text-center">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 mb-8 border border-[var(--color-border)] rounded-full text-xs font-medium text-[var(--color-text-secondary)]">
          <span className="w-1.5 h-1.5 bg-[var(--color-success)] rounded-full" />
          AI-Powered
        </div>

        <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight max-w-3xl leading-[1.08]">
          Your AI co-pilot for building faster
        </h1>

        <p className="mt-6 text-base md:text-lg text-[var(--color-text-secondary)] max-w-lg leading-relaxed">
          Autonomous agents, smart scheduling, long-term memory, and deep
          integrations. Focus on what matters.
        </p>

        <div className="flex items-center gap-3 mt-10">
          <Link
            href="/sign-up"
            className="px-7 py-3 text-sm font-medium text-[var(--color-accent-foreground)] bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] rounded-lg transition-colors"
          >
            Start for free
          </Link>
          <Link
            href="/sign-in"
            className="px-7 py-3 text-sm font-medium text-[var(--color-text)] border border-[var(--color-border)] rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
          >
            Sign in
          </Link>
        </div>

        {/* Feature pills */}
        <div className="flex flex-wrap items-center justify-center gap-3 mt-16 max-w-xl">
          {["7 AI Agents", "Smart Scheduling", "Long-term Memory", "MCP Integrations", "Human-in-the-loop"].map((f) => (
            <span key={f} className="px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-full">
              {f}
            </span>
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="py-6 text-center text-xs text-[var(--color-text-muted)] border-t border-[var(--color-border)]">
        &copy; 2026 Founder OS
      </footer>
    </div>
  );
}
