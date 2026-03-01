"use client";

import { UserButton } from "@clerk/nextjs";
import { Menu, Bell, Search } from "lucide-react";

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header className="sticky top-0 z-30 h-16 bg-[var(--color-surface)]/80 backdrop-blur-md border-b border-[var(--color-border)] flex items-center gap-4 px-4 md:px-6">
      {/* Mobile menu button */}
      <button
        onClick={onMenuClick}
        className="lg:hidden p-2 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
      >
        <Menu className="w-5 h-5 text-[var(--color-text-secondary)]" />
      </button>

      {/* Search bar */}
      <div className="flex-1 max-w-xl">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-muted)]" />
          <input
            type="text"
            placeholder="Search agents, tasks, knowledge..."
            className="w-full pl-10 pr-4 py-2 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
          />
          <kbd className="hidden md:inline-flex absolute right-3 top-1/2 -translate-y-1/2 items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-text-muted)] bg-[var(--color-surface-muted)] rounded border border-[var(--color-border)]">
            ⌘K
          </kbd>
        </div>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-3">
        {/* Notifications */}
        <button className="relative p-2 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors">
          <Bell className="w-5 h-5 text-[var(--color-text-secondary)]" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
        </button>

        {/* User button from Clerk */}
        <UserButton
          afterSignOutUrl="/"
          appearance={{
            elements: {
              avatarBox: "w-8 h-8",
            },
          }}
        />
      </div>
    </header>
  );
}
