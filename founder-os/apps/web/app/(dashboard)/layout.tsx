import { DashboardShell } from "./_components/dashboard-shell";
import { OnboardingGuard } from "./_components/onboarding-guard";
import { ChatProvider } from "@/lib/chat-store";

// Dashboard requires auth — never statically render
export const dynamic = "force-dynamic";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // ChatProvider lives at the layout so chats and their in-flight agent
  // runs survive navigation between dashboard tabs.
  return (
    <OnboardingGuard>
      <ChatProvider>
        <DashboardShell>{children}</DashboardShell>
      </ChatProvider>
    </OnboardingGuard>
  );
}
