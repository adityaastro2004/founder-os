"use client";

import { UserButton } from "@clerk/nextjs";
import { Menu, Search } from "lucide-react";

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header className="sticky top-0 z-30 h-14 bg-white/80 backdrop-blur-md border-b border-[var(--color-border)] flex items-center gap-4 px-5 md:px-8 lg:px-10">
      {/* Mobile menu button */}
      <button
        onClick={onMenuClick}
        className="lg:hidden p-1.5 rounded-md hover:bg-[var(--color-surface-muted)] transition-colors"
      >
        <Menu className="w-4 h-4 text-[var(--color-text-secondary)]" />
      </button>

      {/* Search bar */}
      <div className="flex-1 max-w-md">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--color-text-muted)]" />
          <input
            type="text"
            placeholder="Search..."
            className="w-full pl-9 pr-4 py-1.5 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-text)] transition-all"
          />
          <kbd className="hidden md:inline-flex absolute right-3 top-1/2 -translate-y-1/2 items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-text-muted)] bg-[var(--color-surface-muted)] rounded border border-[var(--color-border)]">
            ⌘K
          </kbd>
        </div>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-2">
        <UserButton
          afterSignOutUrl="/"
          appearance={{
            elements: {
              avatarBox: "w-7 h-7",
            },
          }}
        />
      </div>
    </header>
  );
}
