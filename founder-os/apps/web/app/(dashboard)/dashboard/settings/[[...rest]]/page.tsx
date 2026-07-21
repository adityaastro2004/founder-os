"use client";

import { UserProfile } from "@clerk/nextjs";
import { PageHeader, Card } from "@/app/_components/ui";

export default function SettingsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="Settings"
        description="Manage your account and preferences"
      />
      <Card className="overflow-x-hidden p-6">
        <UserProfile
          routing="path"
          path="/dashboard/settings"
          appearance={{
            elements: {
              rootBox: "w-full",
              card: "shadow-none border-0 w-full",
            },
          }}
        />
      </Card>
    </div>
  );
}
