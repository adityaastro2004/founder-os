"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

/**
 * Client component that checks onboarding status.
 * If the user hasn't completed onboarding, redirects to /onboarding.
 * Renders children only once status is confirmed.
 */
export function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const [checked, setChecked] = useState(false);
  const router = useRouter();
  const { getToken, isLoaded } = useAuth();

  useEffect(() => {
    if (!isLoaded) return;

    let cancelled = false;

    async function check() {
      try {
        const token = await getToken();

        // If there's a pending onboarding payload from a previous failed save, retry it
        const pending = localStorage.getItem("founder_os_onboarding");
        if (pending) {
          try {
            await apiFetch("/api/onboarding/profile", {
              method: "POST",
              token,
              body: pending,
            });
            localStorage.removeItem("founder_os_onboarding");
          } catch {
            // API still down — clear pending so we don't block the dashboard
          }
        }

        const data = await apiFetch("/api/onboarding/status", { token });

        if (!cancelled && !data.completed) {
          // Only redirect if there's no pending local data (API was reachable but no profile)
          if (!localStorage.getItem("founder_os_onboarding")) {
            router.replace("/onboarding");
            return;
          }
        }
      } catch {
        // API unreachable — skip the check, don't block the dashboard
      }

      if (!cancelled) setChecked(true);
    }

    check();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, getToken, router]);

  if (!checked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <div className="flex flex-col items-center gap-3">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-accent" />
          <p className="text-xs text-ink-secondary">Loading</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
