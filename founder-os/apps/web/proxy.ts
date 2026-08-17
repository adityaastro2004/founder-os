import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

/**
 * Authenticated *pages*. These two route groups are the complete set of
 * signed-in surfaces in the app — `(marketing)` and `(auth)` are public.
 *
 * ⚠️ Adding a new authenticated page or route group? Add its prefix HERE, or it
 * ships publicly. This list is the gate.
 */
const isProtectedPage = createRouteMatcher(["/dashboard(.*)", "/onboarding(.*)"]);

/**
 * The API proxy stays deny-by-default: everything under /api is protected
 * except inbound webhooks, which authenticate by signature instead of by
 * session. (The FastAPI backend independently enforces Clerk JWT auth on its
 * own endpoints — this is the outer layer, not the only one.)
 */
const isApiRoute = createRouteMatcher(["/api/(.*)"]);
const isPublicApiRoute = createRouteMatcher(["/api/webhooks(.*)"]);

export default clerkMiddleware(async (auth, request) => {
  // Public marketing pages must fall through untouched — including URLs that
  // match nothing, so unknown paths render the custom 404 with a real 404
  // status instead of bouncing anonymous visitors (and crawlers) to /sign-in.
  if (isProtectedPage(request) || (isApiRoute(request) && !isPublicApiRoute(request))) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Skip Next.js internals and all static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
  ],
};
