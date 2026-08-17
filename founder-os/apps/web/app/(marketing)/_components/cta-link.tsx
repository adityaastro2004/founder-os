import Link from "next/link";
import { clsx } from "clsx";

/**
 * Link-shaped call to action for the marketing site.
 *
 * The dashboard's `<Button>` renders a real `<button>` and is a client
 * component; marketing CTAs are navigations, so they must be anchors for
 * crawlers and for middle-click / open-in-new-tab. Same tokens, no client JS.
 */

const variants = {
  primary: "bg-accent text-white hover:bg-accent-hover",
  secondary: "border border-line bg-surface text-ink hover:bg-surface-muted",
};

const sizes = {
  md: "px-5 py-2.5 text-sm",
  lg: "px-6 py-3 text-sm sm:px-7 sm:text-base",
};

export function CtaLink({
  href,
  children,
  variant = "primary",
  size = "md",
  className,
}: {
  href: string;
  children: React.ReactNode;
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-control font-medium transition-colors duration-150",
        variants[variant],
        sizes[size],
        className,
      )}
    >
      {children}
    </Link>
  );
}
