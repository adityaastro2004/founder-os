import type { MetadataRoute } from "next";
import { siteDescription, siteName } from "../lib/site";

/**
 * Serves /manifest.webmanifest — makes the site installable and gives Android
 * / Chrome the icon set that a plain favicon.ico cannot provide.
 *
 * The icon files themselves come from `app/icon.png` (512×512),
 * `app/apple-icon.png` (180×180) and `public/logo-icon.png`; Next.js emits the
 * <link rel="icon"> tags for the first two automatically from their filenames.
 *
 * `id` is set explicitly: without it the identity of the installed app is the
 * start URL, so changing `start_url` later would register as a different app
 * and orphan every existing install.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: `${siteName} — the autonomous operating system for founders`,
    short_name: siteName,
    description: siteDescription,
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    lang: "en",
    dir: "ltr",
    categories: ["productivity", "business", "utilities"],
    background_color: "#faf9f5",
    theme_color: "#faf9f5",
    icons: [
      // Both entries point at the same 512×512 asset. `sizes` values here are
      // the file's real dimensions — a declared size that does not match the
      // file makes Chrome pick the wrong icon or skip it entirely.
      // TODO: cut a dedicated maskable variant with ~10% safe-zone padding;
      // Android crops the current one to its circle mask without it.
      { src: "/logo-icon.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/logo-icon.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
