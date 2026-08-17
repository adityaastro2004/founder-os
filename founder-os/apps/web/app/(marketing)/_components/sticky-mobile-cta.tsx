import Link from "next/link";
import { ArrowRight } from "lucide-react";

/**
 * Persistent conversion bar for phone widths only (`lg:hidden`).
 *
 * The marketing layout reserves matching bottom padding on <main> so the bar
 * never covers the last line of the footer. Hidden from `lg` up, where the
 * header CTA is always on screen anyway.
 */
export function StickyMobileCta() {
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-paper/95 px-4 py-3 backdrop-blur-sm lg:hidden">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-ink">
            Free to start
          </p>
          <p className="truncate text-[11px] text-ink-secondary">
            No credit card required
          </p>
        </div>
        <Link
          href="/sign-up"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-control bg-accent px-5 py-2.5 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover"
        >
          Start free
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      </div>
    </div>
  );
}
