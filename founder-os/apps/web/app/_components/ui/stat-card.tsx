import { Card } from "./card";
import { Skeleton } from "./skeleton";

export function StatCard({
  label,
  value,
  sub,
  loading,
}: {
  label: string;
  value: string | number;
  sub?: string;
  loading?: boolean;
}) {
  return (
    <Card className="p-4">
      <p className="text-[13px] text-ink-secondary">{label}</p>
      {loading ? (
        <Skeleton className="mt-1.5 h-7 w-12" />
      ) : (
        <p className="mt-1 text-2xl font-semibold tracking-tight text-ink">{value}</p>
      )}
      {sub && <p className="mt-1 text-xs text-ink-secondary">{sub}</p>}
    </Card>
  );
}
