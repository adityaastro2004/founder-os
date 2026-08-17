import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { JsonLd } from "../../_components/json-ld";
import { breadcrumbSchema, type Crumb } from "../../../lib/site";

/**
 * Breadcrumb trail + matching BreadcrumbList JSON-LD, so Google can render the
 * hierarchy in the result snippet instead of a bare URL.
 *
 * Pass the full trail including Home and the current page; the last crumb is
 * rendered as plain text (`aria-current="page"`), not a link.
 */
export function Breadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  const trail: Crumb[] = [{ href: "/", label: "Home" }, ...crumbs];

  return (
    <>
      <JsonLd data={breadcrumbSchema(trail)} />
      <nav aria-label="Breadcrumb">
        <ol className="flex flex-wrap items-center gap-1 text-[13px] text-ink-secondary">
          {trail.map((crumb, i) => {
            const last = i === trail.length - 1;
            return (
              <li key={crumb.href} className="flex items-center gap-1">
                {i > 0 && (
                  <ChevronRight
                    className="h-3.5 w-3.5 text-ink-muted"
                    aria-hidden="true"
                  />
                )}
                {last ? (
                  <span aria-current="page" className="text-ink">
                    {crumb.label}
                  </span>
                ) : (
                  <Link
                    href={crumb.href}
                    className="transition-colors duration-150 hover:text-ink"
                  >
                    {crumb.label}
                  </Link>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
    </>
  );
}
