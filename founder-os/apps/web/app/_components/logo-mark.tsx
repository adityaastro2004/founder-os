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
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <Image
      src="/logo-mark.png"
      alt=""
      width={175}
      height={256}
      priority
      className={clsx("logo-mark w-auto", className)}
    />
  );
}
