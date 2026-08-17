import Link from "next/link";
import { appFooterNav, siteName } from "@/lib/site";

/**
 * Dashboard footer — copyright plus the public pages (help, contact, legal).
 *
 * Signed-in users are redirected away from `/`, so without this the marketing
 * site's footer is unreachable from inside the app and the legal pages could
 * only be found by typing the URL. Deliberately quiet: one hairline, small
 * type, no CTA — the dashboard is a workspace, not a landing page.
 */
export function AppFooter() {
  return (
    <footer className="border-t border-line px-5 py-5 md:px-8 lg:px-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 text-xs text-ink-secondary sm:flex-row sm:items-center sm:justify-between">
        <p>
          &copy; {new Date().getFullYear()} {siteName}
        </p>
        <nav aria-label="Help and legal">
          <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
            {appFooterNav.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="transition-colors duration-150 hover:text-ink"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}
