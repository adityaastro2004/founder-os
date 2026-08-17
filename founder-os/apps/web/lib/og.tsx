import { ImageResponse } from "next/og";
import { siteName, siteUrl } from "./site";

/**
 * The social share card, generated at request time by `next/og` (Satori) so
 * there is no binary asset to keep in sync with the brand.
 *
 * Shared by `app/opengraph-image.tsx` and `app/twitter-image.tsx` — both must
 * exist as separate route files, but they render the same card.
 *
 * Satori supports a flexbox subset of CSS only: every container needs an
 * explicit `display: flex`, and no custom font is loaded on purpose (the
 * bundled default always renders, whereas a missing/variable woff would fail
 * the build).
 */

export const ogSize = { width: 1200, height: 630 };
export const ogContentType = "image/png";

const paper = "#FAF9F5";
const ink = "#1F1E1D";
const inkSecondary = "#63605B";
const accent = "#C96442";
const line = "#E8E6DD";

export function renderOgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          width: "100%",
          height: "100%",
          backgroundColor: paper,
          padding: "72px 80px",
          borderTop: `16px solid ${accent}`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              display: "flex",
              width: 44,
              height: 44,
              borderRadius: 12,
              backgroundColor: accent,
            }}
          />
          <div style={{ display: "flex", fontSize: 30, color: ink, fontWeight: 600 }}>
            {siteName}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              display: "flex",
              fontSize: 68,
              lineHeight: 1.1,
              color: ink,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              maxWidth: 940,
            }}
          >
            One system that knows your whole company
          </div>
          <div
            style={{
              display: "flex",
              marginTop: 28,
              fontSize: 30,
              lineHeight: 1.4,
              color: inkSecondary,
              maxWidth: 880,
            }}
          >
            An AI operating system for solo founders — autonomous agents, long-term
            memory, and one canonical company state.
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderTop: `2px solid ${line}`,
            paddingTop: 24,
            fontSize: 24,
            color: inkSecondary,
          }}
        >
          <div style={{ display: "flex" }}>{siteUrl.replace(/^https?:\/\//, "")}</div>
          <div style={{ display: "flex", color: accent, fontWeight: 600 }}>
            Start for free
          </div>
        </div>
      </div>
    ),
    ogSize,
  );
}
