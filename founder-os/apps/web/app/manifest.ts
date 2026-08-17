import type { MetadataRoute } from "next";
import { siteDescription, siteName } from "../lib/site";

/**
 * Serves /manifest.webmanifest — makes the site installable and gives Android
 * / Chrome the icon set that a plain favicon.ico cannot provide.
 *
 * The icon files themselves come from `app/icon.png` (512×512),
 * `app/apple-icon.png` (180×180) and `public/logo-icon.png`; Next.js emits the
 * <link rel="icon"> tags for the first two automatically from their filenames.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${siteName} — the autonomous operating system for founders`,
    short_name: siteName,
    description: siteDescription,
    start_url: "/",
    display: "standalone",
    background_color: "#faf9f5",
    theme_color: "#faf9f5",
    icons: [
      { src: "/logo-icon.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/logo-icon.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
