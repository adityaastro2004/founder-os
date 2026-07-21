"use client";

import { useUser } from "@clerk/nextjs";
import posthog from "posthog-js";
import { useEffect } from "react";

/**
 * Ties PostHog identity to the Clerk session: identify on sign-in, reset on
 * sign-out so a shared browser doesn't keep attributing events to the previous
 * user. Renders nothing; must sit inside <ClerkProvider>.
 */
export function PostHogIdentify() {
  const { isLoaded, isSignedIn, user } = useUser();

  useEffect(() => {
    // No key at build time → posthog was never initialized (see
    // instrumentation-client.ts), so every call here would be a no-op anyway.
    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY || !isLoaded) return;

    if (isSignedIn && user) {
      if (posthog.get_distinct_id() !== user.id) {
        posthog.identify(user.id, {
          email: user.primaryEmailAddress?.emailAddress,
          name: user.fullName ?? undefined,
        });
      }
    } else if (posthog.get_distinct_id()?.startsWith("user_")) {
      // Signed out but the device is still identified as a Clerk user
      // (Clerk ids are `user_…`) — drop back to a fresh anonymous id.
      posthog.reset();
    }
  }, [isLoaded, isSignedIn, user]);

  return null;
}
