import { clsx } from "clsx";

export function Card({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={clsx("rounded-card border border-line bg-surface", className)}>
      {children}
    </div>
  );
}
