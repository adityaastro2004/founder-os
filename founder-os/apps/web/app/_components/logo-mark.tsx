import Image from "next/image";
import { clsx } from "clsx";

/**
 * The Founder OS brand mark.
 *
 * Source art (`public/logo-mark.png`) is ink-black on transparent. The theme is
 * driven by the `.dark` class (see globals.css), not `prefers-color-scheme`, so
 * the inversion for dark mode lives in the `.logo-mark` rule there rather than
 * in a Tailwind `dark:` variant.
 *
 * Pass a height utility (`h-8`); the width follows the intrinsic aspect ratio.
 *
 * The art and the width/height below are both produced by
 * `scripts/generate-brand-assets.py` — re-run it after a logo drop and copy the
 * mark size it reports, or Next.js will letterbox the new proportions.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <Image
      src="/logo-mark.png"
      alt=""
      width={314}
      height={256}
      priority
      className={clsx("logo-mark w-auto", className)}
    />
  );
}
