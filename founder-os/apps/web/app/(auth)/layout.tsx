export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-white">
      <div className="flex flex-col items-center gap-8">
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-[var(--color-accent)] flex items-center justify-center">
            <span className="text-[var(--color-accent-foreground)] font-bold text-base">F</span>
          </div>
          <span className="text-xl font-semibold tracking-tight">
            Founder OS
          </span>
        </div>

        {/* Clerk form */}
        {children}

        {/* Footer */}
        <p className="text-xs text-[var(--color-text-muted)]">
          AI-powered operating system for founders
        </p>
      </div>
    </div>
  );
}
