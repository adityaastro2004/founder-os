import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import Link from "next/link";

export default async function Home() {
  const { userId } = await auth();

  if (userId) {
    redirect("/dashboard");
  }

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-indigo-50 via-white to-purple-50 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950">
      {/* Decorative blobs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-indigo-200/30 dark:bg-indigo-500/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-purple-200/30 dark:bg-purple-500/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-100/20 dark:bg-indigo-500/5 rounded-full blur-3xl" />
      </div>

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-6 md:px-12 py-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg">
            <span className="text-white font-bold text-base">F</span>
          </div>
          <span className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">
            Founder OS
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/sign-in"
            className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors"
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="px-5 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] transition-all"
          >
            Get started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 mb-6 bg-indigo-100 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 rounded-full text-sm font-medium">
          <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
          AI-Powered
        </div>

        <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-slate-900 dark:text-white max-w-3xl leading-[1.1]">
          Your AI operating system for{" "}
          <span className="bg-gradient-to-r from-indigo-500 to-purple-600 bg-clip-text text-transparent">
            building faster
          </span>
        </h1>

        <p className="mt-6 text-lg text-slate-600 dark:text-slate-400 max-w-xl leading-relaxed">
          Autonomous agents, smart scheduling, long-term memory, and deep
          integrations — all in one place. Focus on what matters, let AI
          handle the rest.
        </p>

        <div className="flex items-center gap-4 mt-10">
          <Link
            href="/sign-up"
            className="px-8 py-3.5 text-base font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] transition-all"
          >
            Start for free
          </Link>
          <Link
            href="/sign-in"
            className="px-8 py-3.5 text-base font-semibold text-slate-700 dark:text-slate-300 border border-[var(--color-border)] rounded-2xl hover:bg-[var(--color-surface-muted)] transition-all"
          >
            Sign in
          </Link>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 py-6 text-center text-sm text-slate-500 dark:text-slate-500">
        © 2026 Founder OS. Built for founders, by AI.
      </footer>
    </div>
  );
}
