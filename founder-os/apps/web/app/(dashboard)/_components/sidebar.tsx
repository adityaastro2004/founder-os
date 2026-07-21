"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { useChatStore } from "@/lib/chat-store";
import { ThemeToggle } from "@/app/_components/theme-toggle";
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
  type LucideIcon,
} from "lucide-react";

type NavItem = { name: string; href: string; icon: LucideIcon };

const navGroups: { section: string | null; items: NavItem[] }[] = [
  {
    section: null,
    items: [{ name: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
  },
  {
    section: "Work",
    items: [
      { name: "Chat", href: "/dashboard/chat", icon: MessageSquare },
      { name: "Agents", href: "/dashboard/agents", icon: Bot },
      { name: "Tasks", href: "/dashboard/tasks", icon: ListTodo },
      { name: "Planner", href: "/dashboard/planner", icon: CalendarDays },
    ],
  },
  {
    section: "Knowledge",
    items: [
      { name: "Memory", href: "/dashboard/memory", icon: Brain },
      { name: "Knowledge", href: "/dashboard/knowledge", icon: BookOpen },
      { name: "Content ideas", href: "/dashboard/content-ideas", icon: Lightbulb },
    ],
  },
  {
    section: "System",
    items: [
      { name: "Automations", href: "/dashboard/workflows", icon: Zap },
      { name: "Apps", href: "/dashboard/apps", icon: Blocks },
    ],
  },
];

const bottomNav: NavItem[] = [
  { name: "Billing", href: "/dashboard/billing", icon: CreditCard },
  { name: "Settings", href: "/dashboard/settings", icon: Settings },
];

function NavLink({
  item,
  isActive,
  onClose,
  running,
}: {
  item: NavItem;
  isActive: boolean;
  onClose: () => void;
  running?: boolean;
}) {
  return (
    <Link
      href={item.href}
      onClick={onClose}
      className={clsx(
        "flex items-center gap-2.5 rounded-control px-3 py-2 text-[13px] font-medium transition-colors duration-150",
        isActive
          ? "bg-surface text-ink"
          : "text-ink-secondary hover:bg-paper/60 hover:text-ink"
      )}
    >
      <item.icon
        className={clsx(
          "h-4 w-4 shrink-0",
          isActive ? "text-accent" : "text-ink-muted"
        )}
        aria-hidden="true"
      />
      {item.name}
      {running && (
        <span
          className="ml-auto h-1.5 w-1.5 animate-pulse rounded-full bg-success"
          title="Agent run in progress"
        />
      )}
    </Link>
  );
}

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const pathname = usePathname();
  const { orchestratorPending, agentChatPending } = useChatStore();

  // A chat run is still in flight — show a pulse so the user knows they can
  // browse anywhere and come back.
  const runningDot: Record<string, boolean> = {
    Chat: orchestratorPending,
    Agents: agentChatPending,
  };

  const isActive = (href: string) =>
    pathname === href || (href !== "/dashboard" && pathname.startsWith(href));

  return (
    <aside
      className={clsx(
        "fixed inset-y-0 left-0 z-50 flex w-[var(--sidebar-width)] flex-col border-r border-line bg-surface-muted transition-transform duration-200 ease-in-out",
        "lg:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full"
      )}
    >
      {/* Brand */}
      <div className="flex h-14 items-center justify-between px-4">
        <Link href="/dashboard" className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent">
            <span className="text-xs font-bold text-white">F</span>
          </div>
          <span className="font-serif text-[15px] font-semibold tracking-tight text-ink">
            Founder OS
          </span>
        </Link>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close menu"
          className="-m-1 rounded-control p-2 transition-colors duration-150 hover:bg-paper/60 lg:hidden"
        >
          <X className="h-4 w-4 text-ink-muted" aria-hidden="true" />
        </button>
      </div>

      {/* Main navigation */}
      <nav className="flex-1 overflow-y-auto px-3 pb-4 pt-2">
        {navGroups.map((group) => (
          <div key={group.section ?? "top"}>
            {group.section && (
              <p className="px-3 pb-1 pt-5 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
                {group.section}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.name}
                  item={item}
                  isActive={isActive(item.href)}
                  onClose={onClose}
                  running={runningDot[item.name]}
                />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Bottom navigation */}
      <div className="space-y-0.5 border-t border-line px-3 py-3">
        <ThemeToggle variant="row" />
        {bottomNav.map((item) => (
          <NavLink
            key={item.name}
            item={item}
            isActive={pathname.startsWith(item.href)}
            onClose={onClose}
          />
        ))}
      </div>
    </aside>
  );
}
