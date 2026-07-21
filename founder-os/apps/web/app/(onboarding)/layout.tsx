export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-paper">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-5 md:px-12">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent">
            <span className="text-base font-bold text-white">F</span>
          </div>
          <span className="font-serif text-xl font-semibold tracking-tight text-ink">
            Founder OS
          </span>
        </div>
      </header>

      {/* Content */}
      <main className="flex flex-col items-center px-4 pb-12 pt-4">
        {children}
      </main>
    </div>
  );
}
