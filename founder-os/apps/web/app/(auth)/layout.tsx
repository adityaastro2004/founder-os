import { LogoMark } from "@/app/_components/logo-mark";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // Clerk's card renders at a fixed ~400px, so the gutter here is what keeps
    // it off the edge on a 320–375px phone instead of being clipped.
    <div className="flex min-h-screen items-center justify-center bg-paper px-4 py-10">
      <div className="flex w-full max-w-md flex-col items-center gap-8">
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
