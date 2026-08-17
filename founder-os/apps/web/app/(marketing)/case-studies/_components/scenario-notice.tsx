import { Info } from "lucide-react";

/**
 * Disclaimer shown on every case-study surface.
 *
 * Founder OS has no publicly referenceable customers yet, so these pages are
 * explicitly labelled as illustrative. Keep this notice on the page as long as
 * the content in `lib/case-studies.ts` is authored rather than reported — it is
 * the difference between a worked example and a fabricated testimonial.
 */
export function ScenarioNotice({ className }: { className?: string }) {
  return (
    <div
      className={`flex gap-3 rounded-card border border-line bg-surface-muted/60 p-4 ${className ?? ""}`}
    >
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
      <p className="text-[13px] leading-relaxed text-ink-secondary">
        <strong className="font-semibold text-ink">Illustrative scenario.</strong>{" "}
        These walkthroughs describe how Founder OS is designed to be used. They are
        composites written by us — not real customer accounts, and they contain no
        measured results, testimonials or client names.
      </p>
    </div>
  );
}
