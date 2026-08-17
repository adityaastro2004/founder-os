"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Menu, X } from "lucide-react";
import { clsx } from "clsx";
import { LogoMark } from "../../_components/logo-mark";
import { ThemeToggle } from "../../_components/theme-toggle";
import { AuthSwitch } from "./auth-switch";
import { primaryNav } from "../../../lib/site";

function DashboardLink({ className }: { className?: string }) {
  return (
    <Link
      href="/dashboard"
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-control bg-accent px-4 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover",
        className,
      )}
    >
      <LayoutDashboard className="h-4 w-4" aria-hidden="true" />
      Dashboard
    </Link>
  );
}

const mobileSignedOutCtas = (
  <div className="flex gap-3">
    <Link
      href="/sign-in"
      className="flex-1 rounded-control border border-line bg-surface px-4 py-2.5 text-center text-sm font-medium text-ink"
    >
      Sign in
    </Link>
    <Link
      href="/sign-up"
      className="flex-1 rounded-control bg-accent px-4 py-2.5 text-center text-sm font-medium text-white"
    >
      Get started
    </Link>
  </div>
);

const signedOutCtas = (
  <>
    <Link
      href="/sign-in"
      className="hidden px-3 py-2 text-sm font-medium text-ink-secondary transition-colors duration-150 hover:text-ink sm:block"
    >
      Sign in
    </Link>
    <Link
      href="/sign-up"
      className="hidden rounded-control bg-accent px-4 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover sm:block"
    >
      Get started
    </Link>
  </>
);

/**
 * Public site header — the primary internal-linking surface.
 *
 * Client component only because the phone-width menu needs open/closed state;
 * the links themselves are ordinary anchors, so crawlers see the full nav in
 * the server-rendered HTML whether or not the menu is open.
 */
export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Client-side navigation keeps this component mounted, so the panel has to be
  // closed explicitly when the route changes.
  useEffect(() => setOpen(false), [pathname]);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-paper/90 backdrop-blur-sm">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-6 py-4 md:px-10">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5"
          aria-label="Founder OS — home"
        >
          <LogoMark className="h-7" />
          <span className="font-serif text-lg font-semibold tracking-tight text-ink">
            Founder OS
          </span>
        </Link>

        {/* Desktop nav */}
        <nav aria-label="Main" className="hidden items-center gap-1 lg:flex">
          {primaryNav.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={clsx(
                  "rounded-control px-3 py-2 text-sm font-medium transition-colors duration-150",
                  active
                    ? "text-ink"
                    : "text-ink-secondary hover:bg-surface-muted hover:text-ink",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          {/* A signed-in visitor reading /faq or /privacy needs a way back into
              the app — not an invitation to sign up again. */}
          <AuthSwitch
            signedOut={signedOutCtas}
            signedIn={<DashboardLink className="hidden sm:inline-flex" />}
          />
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            className="-mr-1 rounded-control p-2 text-ink transition-colors duration-150 hover:bg-surface-muted lg:hidden"
          >
            {open ? (
              <X className="h-5 w-5" aria-hidden="true" />
            ) : (
              <Menu className="h-5 w-5" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {/* Mobile nav panel */}
      {open && (
        <nav
          id="mobile-nav"
          aria-label="Main (mobile)"
          className="border-t border-line bg-paper px-6 py-3 lg:hidden"
        >
          <ul className="flex flex-col">
            {primaryNav.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="block border-b border-line-subtle py-3 text-[15px] font-medium text-ink"
                >
                  {item.label}
                </Link>
              </li>
            ))}
            <li className="pt-4 sm:hidden">
              <AuthSwitch
                signedOut={mobileSignedOutCtas}
                signedIn={<DashboardLink className="w-full" />}
              />
            </li>
          </ul>
        </nav>
      )}
    </header>
  );
}
