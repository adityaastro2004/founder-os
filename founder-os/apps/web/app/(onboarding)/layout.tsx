export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      {/* Header */}
      <header className="flex items-center justify-between px-6 md:px-12 py-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-[var(--color-accent)] flex items-center justify-center">
            <span className="text-[var(--color-accent-foreground)] font-bold text-base">F</span>
          </div>
          <span className="text-xl font-bold tracking-tight">
            Founder OS
          </span>
        </div>
      </header>

      {/* Content */}
      <main className="flex flex-col items-center px-4 pt-4 pb-12">
        {children}
      </main>
    </div>
  );
}
