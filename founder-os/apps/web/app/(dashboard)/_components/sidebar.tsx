"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Bot,
  Brain,
  ListTodo,
  Settings,
  Zap,
  MessageSquare,
  BookOpen,
  Blocks,
  Lightbulb,
  CalendarDays,
  CreditCard,
  X,
} from "lucide-react";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Chat", href: "/dashboard/chat", icon: MessageSquare },
  { name: "Agents", href: "/dashboard/agents", icon: Bot },
  { name: "Tasks", href: "/dashboard/tasks", icon: ListTodo },
  { name: "Planner", href: "/dashboard/planner", icon: CalendarDays },
  { name: "Memory", href: "/dashboard/memory", icon: Brain },
  { name: "Knowledge", href: "/dashboard/knowledge", icon: BookOpen },
  { name: "Content Ideas", href: "/dashboard/content-ideas", icon: Lightbulb },
  { name: "Automations", href: "/dashboard/automations", icon: Zap },
  { name: "Apps", href: "/dashboard/apps", icon: Blocks },
];

const bottomNav = [
  { name: "Billing", href: "/dashboard/billing", icon: CreditCard },
  { name: "Settings", href: "/dashboard/settings", icon: Settings },
];

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const pathname = usePathname();

  return (
    <aside
      className={clsx(
        "fixed inset-y-0 left-0 z-50 w-[var(--sidebar-width)] bg-white border-r border-[var(--color-border)] flex flex-col transition-transform duration-200 ease-in-out",
        "lg:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full"
      )}
    >
      {/* Brand */}
      <div className="flex items-center justify-between h-14 px-4">
        <Link href="/dashboard" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-[var(--color-accent)] flex items-center justify-center">
            <span className="text-[var(--color-accent-foreground)] font-bold text-xs">F</span>
          </div>
          <span className="font-semibold text-sm tracking-tight">
            Founder OS
          </span>
        </Link>
        <button
          onClick={onClose}
          className="lg:hidden p-1 rounded-md hover:bg-[var(--color-surface-muted)] transition-colors"
        >
          <X className="w-4 h-4 text-[var(--color-text-muted)]" />
        </button>
      </div>

      {/* Main navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {navigation.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/dashboard" && pathname.startsWith(item.href));

          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={onClose}
              className={clsx(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-100",
                isActive
                  ? "bg-[var(--color-surface-muted)] text-[var(--color-text)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text)]"
              )}
            >
              <item.icon
                className={clsx(
                  "w-4 h-4 shrink-0",
                  isActive
                    ? "text-[var(--color-text)]"
                    : "text-[var(--color-text-muted)]"
                )}
              />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Bottom navigation */}
      <div className="px-3 py-3 border-t border-[var(--color-border)] space-y-0.5">
        {bottomNav.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={onClose}
              className={clsx(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-100",
                isActive
                  ? "bg-[var(--color-surface-muted)] text-[var(--color-text)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-text)]"
              )}
            >
              <item.icon className="w-4 h-4 shrink-0 text-[var(--color-text-muted)]" />
              {item.name}
            </Link>
          );
        })}
      </div>
    </aside>
  );
}
