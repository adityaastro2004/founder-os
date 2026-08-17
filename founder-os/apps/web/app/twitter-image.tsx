import { ogContentType, ogSize, renderOgImage } from "../lib/og";

// Same card as the Open Graph image; Twitter/X requires its own route file.
export const alt =
  "Founder OS — one system that knows your whole company. An AI operating system for solo founders.";
export const size = ogSize;
export const contentType = ogContentType;

export default function Image() {
  return renderOgImage();
}
