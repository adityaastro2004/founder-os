"use client";

import { UserButton } from "@clerk/nextjs";
import { Menu, Search } from "lucide-react";
import { Kbd } from "@/app/_components/ui";

export function Header({
  onMenuClick,
  onSearchClick,
}: {
  onMenuClick: () => void;
  onSearchClick: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 grid h-14 grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-line bg-paper/80 px-5 backdrop-blur-md md:px-8 lg:px-10">
      {/* Left — mobile menu button (its column balances the right so the
          center search trigger stays truly centered) */}
      <div className="flex items-center justify-self-start">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open menu"
          className="-m-1 rounded-control p-2 transition-colors duration-150 hover:bg-surface-muted lg:hidden"
        >
          <Menu className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
        </button>
      </div>

      {/* Center — search trigger (opens the command palette) */}
      <button
        type="button"
        onClick={onSearchClick}
        aria-label="Search — open command palette"
        aria-keyshortcuts="Meta+K Control+K"
        className="group flex h-9 w-[min(62vw,26rem)] items-center gap-2 justify-self-center rounded-control border border-line bg-surface px-3 text-sm text-ink-muted transition-colors duration-150 hover:border-ink-muted focus-visible:border-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
      >
        <Search className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="flex-1 text-left transition-colors group-hover:text-ink-secondary">
          Search or ask…
        </span>
        <span className="hidden md:inline-flex">
          <Kbd>⌘K</Kbd>
        </span>
      </button>

      {/* Right — user actions */}
      <div className="flex items-center gap-2 justify-self-end">
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
