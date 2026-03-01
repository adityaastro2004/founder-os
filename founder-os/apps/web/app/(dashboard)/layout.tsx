import { DashboardShell } from "./_components/dashboard-shell";
import { OnboardingGuard } from "./_components/onboarding-guard";

// Dashboard requires auth — never statically render
export const dynamic = "force-dynamic";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <OnboardingGuard>
      <DashboardShell>{children}</DashboardShell>
    </OnboardingGuard>
  );
}
