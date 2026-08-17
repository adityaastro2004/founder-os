"use client";

import { useAuth } from "@clerk/nextjs";

/**
 * Renders one of two CTAs depending on whether the visitor is signed in.
 *
 * Deliberately NOT Clerk's `<SignedIn>/<SignedOut>`: those render `null` until
 * auth state resolves, and the marketing pages are statically prerendered, so
 * there is no request at build time to resolve against. The result would be a
 * header with no call to action in the served HTML — invisible to crawlers and
 * a flash of nothing for every visitor.
 *
 * Here the signed-out CTA is the prerendered default (`isLoaded` is false on the
 * server), and only a signed-in visitor swaps to the app link after hydration.
 *
 * `hasClerk` is inlined at build time; with no key there is no <ClerkProvider>
 * and `useAuth()` would throw, so the hook lives in an inner component that is
 * never mounted in that case (the branch is constant, so hook order is stable).
 */

const hasClerk = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

type Props = { signedOut: React.ReactNode; signedIn: React.ReactNode };

function ClerkAuthSwitch({ signedOut, signedIn }: Props) {
  const { isLoaded, isSignedIn } = useAuth();
  return <>{isLoaded && isSignedIn ? signedIn : signedOut}</>;
}

export function AuthSwitch({ signedOut, signedIn }: Props) {
  if (!hasClerk) return <>{signedOut}</>;
  return <ClerkAuthSwitch signedOut={signedOut} signedIn={signedIn} />;
}
