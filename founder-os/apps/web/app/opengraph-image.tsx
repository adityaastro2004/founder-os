import { ogContentType, ogSize, renderOgImage } from "../lib/og";

// Applies to every route that does not define its own opengraph-image.
export const alt =
  "Founder OS — one system that knows your whole company. An AI operating system for solo founders.";
export const size = ogSize;
export const contentType = ogContentType;

export default function Image() {
  return renderOgImage();
}
