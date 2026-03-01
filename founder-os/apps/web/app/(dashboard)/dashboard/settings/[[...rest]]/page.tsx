"use client";

import { UserProfile } from "@clerk/nextjs";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">
          Manage your account and preferences
        </p>
      </div>
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-6">
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
      </div>
    </div>
  );
}
