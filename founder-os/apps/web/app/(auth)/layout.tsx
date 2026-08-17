import { LogoMark } from "@/app/_components/logo-mark";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper">
      <div className="flex flex-col items-center gap-8">
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <LogoMark className="h-9" />
          <span className="font-serif text-xl font-semibold tracking-tight text-ink">
            Founder OS
          </span>
        </div>

        {/* Clerk form */}
        {children}

        {/* Footer */}
        <p className="text-xs text-ink-secondary">
          The AI operating system for founders
        </p>
      </div>
    </div>
  );
}
