import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { ThemeToggle } from "./_components/theme-toggle";

const features = [
  "7 AI agents",
  "Smart scheduling",
  "Long-term memory",
  "MCP integrations",
  "Human-in-the-loop",
];

export default async function Home() {
  const { userId } = await auth();

  if (userId) {
    redirect("/dashboard");
  }

  return (
    <div className="flex min-h-screen flex-col bg-paper">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-5 md:px-12 lg:px-20">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent">
            <span className="text-sm font-bold text-white">F</span>
          </div>
          <span className="font-serif text-lg font-semibold tracking-tight text-ink">
            Founder OS
          </span>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link
            href="/sign-in"
            className="px-4 py-2 text-sm font-medium text-ink-secondary transition-colors duration-150 hover:text-ink"
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="rounded-control bg-accent px-5 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover"
          >
            Get started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <p className="mb-8 text-[13px] font-medium text-ink-secondary">
          The tireless co-founder for solo founders
        </p>

        <h1 className="max-w-3xl font-serif text-4xl font-semibold leading-[1.12] tracking-tight text-ink sm:text-5xl md:text-6xl">
          One system that knows your whole company
        </h1>

        <p className="mt-6 max-w-lg text-base leading-relaxed text-ink-secondary md:text-lg">
          Autonomous agents, smart scheduling, long-term memory, and deep
          integrations — so you can focus on what only you can do.
        </p>

        <div className="mt-10 flex items-center gap-3">
          <Link
            href="/sign-up"
            className="rounded-control bg-accent px-7 py-3 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover"
          >
            Start for free
          </Link>
          <Link
            href="/sign-in"
            className="rounded-control border border-line bg-surface px-7 py-3 text-sm font-medium text-ink transition-colors duration-150 hover:bg-surface-muted"
          >
            Sign in
          </Link>
        </div>

        {/* Feature chips */}
        <div className="mt-16 flex max-w-xl flex-wrap items-center justify-center gap-3">
          {features.map((f) => (
            <span
              key={f}
              className="rounded-full border border-line px-3 py-1.5 text-xs font-medium text-ink-secondary"
            >
              {f}
            </span>
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-line py-6 text-center text-xs text-ink-secondary">
        &copy; 2026 Founder OS
      </footer>
    </div>
  );
}
