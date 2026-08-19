import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

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
    return;
  }

  // Signed-in visitors get the product, not the pitch.
  //
  // This lives here rather than in `(marketing)/page.tsx` for one reason: an
  // `await auth()` inside the page opts the route out of static generation, so
  // the single most important URL on the site was re-rendered on every request
  // — including every crawl. Doing the check in middleware leaves `/` a
  // prerendered static page served from the edge cache. It is a convenience
  // redirect, not an access gate: `/` is public to anonymous visitors either
  // way, and the real gate is `isProtectedPage` above.
  if (request.nextUrl.pathname === "/") {
    const { userId } = await auth();
    if (userId) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
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
