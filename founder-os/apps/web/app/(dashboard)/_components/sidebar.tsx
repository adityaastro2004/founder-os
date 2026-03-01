"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Bot,
  CalendarDays,
  Brain,
  ListTodo,
  Settings,
  Zap,
  MessageSquare,
  BookOpen,
  X,
} from "lucide-react";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Agents", href: "/dashboard/agents", icon: Bot },
  { name: "Planner", href: "/dashboard/planner", icon: CalendarDays },
  { name: "Tasks", href: "/dashboard/tasks", icon: ListTodo },
  { name: "Memory", href: "/dashboard/memory", icon: Brain },
  { name: "Chat", href: "/dashboard/chat", icon: MessageSquare },
  { name: "Knowledge", href: "/dashboard/knowledge", icon: BookOpen },
  { name: "Automations", href: "/dashboard/automations", icon: Zap },
];

const bottomNav = [
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
        "fixed inset-y-0 left-0 z-50 w-[var(--sidebar-width)] bg-[var(--color-surface)] border-r border-[var(--color-border)] flex flex-col transition-transform duration-200 ease-in-out",
        "lg:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full"
      )}
    >
      {/* Brand */}
      <div className="flex items-center justify-between h-16 px-5 border-b border-[var(--color-border)]">
        <Link href="/dashboard" className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-sm">
            <span className="text-white font-bold text-sm">F</span>
          </div>
          <span className="font-semibold text-lg tracking-tight">
            Founder OS
          </span>
        </Link>
        <button
          onClick={onClose}
          className="lg:hidden p-1 rounded-md hover:bg-[var(--color-surface-muted)] transition-colors"
        >
          <X className="w-5 h-5 text-[var(--color-text-secondary)]" />
        </button>
      </div>

      {/* Main navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
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
                "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150",
                isActive
                  ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400 shadow-sm"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text)]"
              )}
            >
              <item.icon
                className={clsx(
                  "w-5 h-5 shrink-0",
                  isActive
                    ? "text-indigo-600 dark:text-indigo-400"
                    : "text-[var(--color-text-muted)]"
                )}
              />
              {item.name}
              {isActive && (
                <div className="ml-auto w-1.5 h-1.5 rounded-full bg-indigo-500" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Bottom navigation */}
      <div className="px-3 py-4 border-t border-[var(--color-border)] space-y-1">
        {bottomNav.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={onClose}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150",
                isActive
                  ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text)]"
              )}
            >
              <item.icon className="w-5 h-5 shrink-0 text-[var(--color-text-muted)]" />
              {item.name}
            </Link>
          );
        })}
      </div>
    </aside>
  );
}
