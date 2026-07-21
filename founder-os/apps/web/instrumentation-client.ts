import posthog from "posthog-js";

// Runs once in the browser before the app hydrates (Next.js instrumentation
// client hook). Analytics is opt-in: with no NEXT_PUBLIC_POSTHOG_KEY at build
// time nothing initializes and no events are sent — safe for local dev and CI.
const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;

if (key) {
  posthog.init(key, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com",
    // 2025-05-24 defaults: automatic pageview/pageleave capture on history
    // (App Router) navigations, so no per-route capture code is needed.
    defaults: "2025-05-24",
    // Only create person profiles for signed-in (identified) users — anonymous
    // landing-page traffic stays in the cheaper anonymous event tier.
    person_profiles: "identified_only",
  });
}
