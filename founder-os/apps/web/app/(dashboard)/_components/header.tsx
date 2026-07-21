"use client";

import { UserButton } from "@clerk/nextjs";
import { Menu, Search } from "lucide-react";
import { Kbd } from "@/app/_components/ui";

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b border-line bg-paper/80 px-5 backdrop-blur-md md:px-8 lg:px-10">
      {/* Mobile menu button */}
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open menu"
        className="-m-1 rounded-control p-2 transition-colors duration-150 hover:bg-surface-muted lg:hidden"
      >
        <Menu className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
      </button>

      {/* Search bar */}
      <div className="max-w-md flex-1">
        <div className="relative">
          <Search
            className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted"
            aria-hidden="true"
          />
          <input
            type="search"
            placeholder="Search"
            aria-label="Search"
            className="w-full rounded-control border border-line bg-surface py-1.5 pl-9 pr-4 text-sm text-ink placeholder:text-ink-muted transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
          <span className="absolute right-3 top-1/2 hidden -translate-y-1/2 md:inline-flex">
            <Kbd>⌘K</Kbd>
          </span>
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
