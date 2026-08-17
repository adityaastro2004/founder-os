import Link from "next/link";
import { ArrowRight, LayoutDashboard } from "lucide-react";
import { AuthSwitch } from "./auth-switch";

/**
 * Persistent conversion bar for phone widths only (`lg:hidden`).
 *
 * The marketing layout reserves matching bottom padding on <main> so the bar
 * never covers the last line of the footer. Hidden from `lg` up, where the
 * header CTA is always on screen anyway.
 *
 * A signed-in visitor gets a route back into the app instead of a sign-up
 * prompt — same reasoning as the header. `AuthSwitch` keeps the signed-out bar
 * as the prerendered default so the CTA is in the served HTML.
 */

function Bar({
  title,
  subtitle,
  href,
  label,
  icon,
}: {
  title: string;
  subtitle: string;
  href: string;
  label: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-ink">{title}</p>
        <p className="truncate text-[11px] text-ink-secondary">{subtitle}</p>
      </div>
      <Link
        href={href}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-control bg-accent px-5 py-2.5 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover"
      >
        {label}
        {icon}
      </Link>
    </div>
  );
}

const signedOutBar = (
  <Bar
    title="Free to start"
    subtitle="No credit card required"
    href="/sign-up"
    label="Start free"
    icon={<ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />}
  />
);

export function StickyMobileCta() {
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-paper/95 px-4 py-3 backdrop-blur-sm lg:hidden">
      <AuthSwitch
        signedOut={signedOutBar}
        signedIn={
          <Bar
            title="You're signed in"
            subtitle="Pick up where you left off"
            href="/dashboard"
            label="Dashboard"
            icon={<LayoutDashboard className="h-3.5 w-3.5" aria-hidden="true" />}
          />
        }
      />
    </div>
  );
}
