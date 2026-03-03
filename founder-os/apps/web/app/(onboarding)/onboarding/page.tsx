"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { clsx } from "clsx";
import {
  Building2,
  Target,
  BarChart3,
  Settings2,
  ChevronRight,
  ChevronLeft,
  Rocket,
  Check,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

/* ── Types ─────────────────────────────────────────── */
interface FormData {
  // Step 1
  business_name: string;
  business_type: string;
  industry: string;
  target_audience: string;
  // Step 2
  business_stage: string;
  primary_goal: string;
  team_size: number;
  team_roles: string[];
  // Step 3
  current_mrr: number;
  current_users: number;
  monthly_traffic: number;
  // Step 4
  preferred_communication: string;
  writing_voice: string;
  working_hours: { start: string; end: string };
}

const INITIAL: FormData = {
  business_name: "",
  business_type: "",
  industry: "",
  target_audience: "",
  business_stage: "",
  primary_goal: "",
  team_size: 1,
  team_roles: [],
  current_mrr: 0,
  current_users: 0,
  monthly_traffic: 0,
  preferred_communication: "email",
  writing_voice: "",
  working_hours: { start: "09:00", end: "18:00" },
};

const STEPS = [
  { label: "Business", icon: Building2 },
  { label: "Goals", icon: Target },
  { label: "Metrics", icon: BarChart3 },
  { label: "Preferences", icon: Settings2 },
];

/* ── Option Cards ─────────────────────────────────── */
const BUSINESS_TYPES = [
  { value: "saas", label: "SaaS", emoji: "💻" },
  { value: "ecommerce", label: "E-Commerce", emoji: "🛒" },
  { value: "agency", label: "Agency / Services", emoji: "🏢" },
  { value: "marketplace", label: "Marketplace", emoji: "🔄" },
  { value: "content", label: "Content / Media", emoji: "📝" },
  { value: "fintech", label: "FinTech", emoji: "💰" },
  { value: "healthtech", label: "HealthTech", emoji: "🏥" },
  { value: "edtech", label: "EdTech", emoji: "📚" },
  { value: "other", label: "Other", emoji: "✨" },
];

const INDUSTRIES = [
  "Technology",
  "Finance",
  "Healthcare",
  "Education",
  "Retail",
  "Real Estate",
  "Marketing",
  "Legal",
  "Entertainment",
  "Food & Beverage",
  "Travel",
  "Other",
];

const STAGES = [
  { value: "idea", label: "Idea Stage", desc: "Validating the concept", emoji: "💡" },
  { value: "pre_launch", label: "Pre-Launch", desc: "Building the MVP", emoji: "🔨" },
  { value: "launched", label: "Just Launched", desc: "Finding first customers", emoji: "🚀" },
  { value: "growth", label: "Growing", desc: "Scaling revenue & team", emoji: "📈" },
  { value: "scaling", label: "Scaling", desc: "$10K+ MRR, expanding", emoji: "🏗️" },
  { value: "established", label: "Established", desc: "Profitable & optimizing", emoji: "🏆" },
];

const GOALS = [
  { value: "grow_revenue", label: "Grow Revenue", emoji: "💸" },
  { value: "acquire_users", label: "Acquire Users", emoji: "👥" },
  { value: "launch_product", label: "Launch Product", emoji: "🚀" },
  { value: "raise_funding", label: "Raise Funding", emoji: "🤝" },
  { value: "build_team", label: "Build Team", emoji: "🧑‍🤝‍🧑" },
  { value: "automate_ops", label: "Automate Operations", emoji: "⚡" },
  { value: "improve_retention", label: "Improve Retention", emoji: "🔄" },
  { value: "expand_market", label: "Expand to New Markets", emoji: "🌍" },
];

const COMMUNICATION = [
  { value: "email", label: "Email", emoji: "📧" },
  { value: "slack", label: "Slack", emoji: "💬" },
  { value: "sms", label: "SMS", emoji: "📱" },
  { value: "in_app", label: "In-App", emoji: "🔔" },
];

const VOICE_OPTIONS = [
  { value: "professional", label: "Professional & Formal" },
  { value: "friendly", label: "Friendly & Casual" },
  { value: "concise", label: "Concise & Direct" },
  { value: "storytelling", label: "Storytelling & Narrative" },
  { value: "technical", label: "Technical & Detailed" },
];

/* ── Reusable Components ──────────────────────────── */
function OptionCard({
  selected,
  onClick,
  emoji,
  label,
  desc,
}: {
  selected: boolean;
  onClick: () => void;
  emoji?: string;
  label: string;
  desc?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex items-center gap-3 p-4 rounded-xl border-2 text-left transition-all duration-150",
        selected
          ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 shadow-sm"
          : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-indigo-300 dark:hover:border-indigo-500/40"
      )}
    >
      {emoji && <span className="text-2xl shrink-0">{emoji}</span>}
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm">{label}</p>
        {desc && (
          <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
            {desc}
          </p>
        )}
      </div>
      {selected && (
        <div className="w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center shrink-0">
          <Check className="w-3 h-3 text-white" />
        </div>
      )}
    </button>
  );
}

function InputField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1.5">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-4 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
      />
    </div>
  );
}

/* ── Main Component ───────────────────────────────── */
export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormData>(INITIAL);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  const { getToken } = useAuth();

  const update = <K extends keyof FormData>(key: K, value: FormData[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const canNext = (): boolean => {
    switch (step) {
      case 0:
        return !!(form.business_name && form.business_type && form.industry);
      case 1:
        return !!(form.business_stage && form.primary_goal);
      case 2:
        return true; // metrics are optional
      case 3:
        return true; // preferences are optional
      default:
        return false;
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const token = await getToken();
      await apiFetch("/api/onboarding/profile", {
        method: "POST",
        token,
        body: JSON.stringify({
          ...form,
          working_hours: form.working_hours,
        }),
      });
    } catch (err: unknown) {
      // If it's a network error (API not running), store locally and continue
      if (err instanceof TypeError && err.message.includes("fetch")) {
        console.warn("API unreachable — saving onboarding data to localStorage");
        localStorage.setItem("founder_os_onboarding", JSON.stringify(form));
      } else {
        const message = err instanceof Error ? err.message : "Something went wrong. Please try again.";
        setError(message);
        setSubmitting(false);
        return;
      }
    }
    // Always navigate to dashboard
    router.push("/dashboard");
  };

  return (
    <div className="w-full max-w-2xl">
      {/* Progress */}
      <div className="flex items-center justify-center gap-2 mb-8">
        {STEPS.map((s, i) => (
          <div key={s.label} className="flex items-center gap-2">
            <button
              onClick={() => i < step && setStep(i)}
              className={clsx(
                "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                i === step
                  ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-400"
                  : i < step
                    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 cursor-pointer"
                    : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
              )}
            >
              {i < step ? (
                <Check className="w-3.5 h-3.5" />
              ) : (
                <s.icon className="w-3.5 h-3.5" />
              )}
              <span className="hidden sm:inline">{s.label}</span>
            </button>
            {i < STEPS.length - 1 && (
              <div
                className={clsx(
                  "w-8 h-0.5 rounded-full",
                  i < step
                    ? "bg-emerald-300 dark:bg-emerald-500/40"
                    : "bg-[var(--color-border)]"
                )}
              />
            )}
          </div>
        ))}
      </div>

      {/* Card */}
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] shadow-xl shadow-black/5 p-6 md:p-8">
        {/* ── Step 0: Business Info ────────────────────── */}
        {step === 0 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-bold">Tell us about your business</h2>
              <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                This helps your AI agents understand your context.
              </p>
            </div>

            <InputField
              label="Business Name"
              value={form.business_name}
              onChange={(v) => update("business_name", v)}
              placeholder="Acme Inc."
            />

            <div>
              <label className="block text-sm font-medium mb-3">
                Business Type
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {BUSINESS_TYPES.map((t) => (
                  <OptionCard
                    key={t.value}
                    selected={form.business_type === t.value}
                    onClick={() => update("business_type", t.value)}
                    emoji={t.emoji}
                    label={t.label}
                  />
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-3">Industry</label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {INDUSTRIES.map((ind) => (
                  <button
                    key={ind}
                    type="button"
                    onClick={() => update("industry", ind.toLowerCase())}
                    className={clsx(
                      "px-3 py-2 rounded-lg border text-sm font-medium transition-all",
                      form.industry === ind.toLowerCase()
                        ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400"
                        : "border-[var(--color-border)] hover:border-indigo-300"
                    )}
                  >
                    {ind}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1.5">
                Who is your target audience?
              </label>
              <textarea
                value={form.target_audience}
                onChange={(e) => update("target_audience", e.target.value)}
                placeholder="e.g., SaaS founders with $1K-$50K MRR looking to automate growth..."
                rows={3}
                className="w-full px-4 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all resize-none"
              />
            </div>
          </div>
        )}

        {/* ── Step 1: Stage & Goals ────────────────────── */}
        {step === 1 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-bold">Stage & Goals</h2>
              <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                Where are you now and where do you want to go?
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-3">
                What stage is your business at?
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {STAGES.map((s) => (
                  <OptionCard
                    key={s.value}
                    selected={form.business_stage === s.value}
                    onClick={() => update("business_stage", s.value)}
                    emoji={s.emoji}
                    label={s.label}
                    desc={s.desc}
                  />
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-3">
                What is your primary goal right now?
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {GOALS.map((g) => (
                  <OptionCard
                    key={g.value}
                    selected={form.primary_goal === g.value}
                    onClick={() => update("primary_goal", g.value)}
                    emoji={g.emoji}
                    label={g.label}
                  />
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1.5">
                  Team Size
                </label>
                <input
                  type="number"
                  min={1}
                  value={form.team_size}
                  onChange={(e) =>
                    update("team_size", Math.max(1, parseInt(e.target.value) || 1))
                  }
                  className="w-full px-4 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1.5">
                  Team Roles
                </label>
                <input
                  type="text"
                  value={form.team_roles.join(", ")}
                  onChange={(e) =>
                    update(
                      "team_roles",
                      e.target.value
                        .split(",")
                        .map((r) => r.trim())
                        .filter(Boolean)
                    )
                  }
                  placeholder="e.g., CTO, Designer"
                  className="w-full px-4 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                />
              </div>
            </div>
          </div>
        )}

        {/* ── Step 2: Metrics ──────────────────────────── */}
        {step === 2 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-bold">Current Metrics</h2>
              <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                Help your AI agents track your progress. These are optional.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-[var(--color-surface-subtle)] rounded-xl border border-[var(--color-border)] p-4">
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1">
                  Monthly Recurring Revenue
                </label>
                <div className="flex items-center gap-1">
                  <span className="text-lg font-bold text-[var(--color-text-muted)]">$</span>
                  <input
                    type="number"
                    min={0}
                    value={form.current_mrr || ""}
                    onChange={(e) =>
                      update("current_mrr", parseFloat(e.target.value) || 0)
                    }
                    placeholder="0"
                    className="w-full text-2xl font-bold bg-transparent focus:outline-none"
                  />
                </div>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">MRR</p>
              </div>

              <div className="bg-[var(--color-surface-subtle)] rounded-xl border border-[var(--color-border)] p-4">
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1">
                  Active Users / Customers
                </label>
                <input
                  type="number"
                  min={0}
                  value={form.current_users || ""}
                  onChange={(e) =>
                    update("current_users", parseInt(e.target.value) || 0)
                  }
                  placeholder="0"
                  className="w-full text-2xl font-bold bg-transparent focus:outline-none"
                />
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  Users
                </p>
              </div>

              <div className="bg-[var(--color-surface-subtle)] rounded-xl border border-[var(--color-border)] p-4">
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1">
                  Monthly Website Traffic
                </label>
                <input
                  type="number"
                  min={0}
                  value={form.monthly_traffic || ""}
                  onChange={(e) =>
                    update("monthly_traffic", parseInt(e.target.value) || 0)
                  }
                  placeholder="0"
                  className="w-full text-2xl font-bold bg-transparent focus:outline-none"
                />
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  Visitors / mo
                </p>
              </div>
            </div>

            <div className="bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/20 rounded-xl p-4">
              <p className="text-sm text-amber-800 dark:text-amber-300">
                💡 Don&apos;t worry if you don&apos;t have these yet. Your AI agents will learn
                and adapt as your business grows.
              </p>
            </div>
          </div>
        )}

        {/* ── Step 3: Preferences ──────────────────────── */}
        {step === 3 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-bold">Your Preferences</h2>
              <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                Customize how your AI agents communicate and operate.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-3">
                Preferred Communication Channel
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {COMMUNICATION.map((c) => (
                  <OptionCard
                    key={c.value}
                    selected={form.preferred_communication === c.value}
                    onClick={() => update("preferred_communication", c.value)}
                    emoji={c.emoji}
                    label={c.label}
                  />
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-3">
                Writing Voice for AI
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {VOICE_OPTIONS.map((v) => (
                  <button
                    key={v.value}
                    type="button"
                    onClick={() => update("writing_voice", v.value)}
                    className={clsx(
                      "px-4 py-3 rounded-xl border-2 text-sm font-medium text-left transition-all",
                      form.writing_voice === v.value
                        ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400"
                        : "border-[var(--color-border)] hover:border-indigo-300"
                    )}
                  >
                    {v.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-3">
                Working Hours
              </label>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-[var(--color-text-secondary)] mb-1">
                    Start
                  </label>
                  <input
                    type="time"
                    value={form.working_hours.start}
                    onChange={(e) =>
                      update("working_hours", {
                        ...form.working_hours,
                        start: e.target.value,
                      })
                    }
                    className="w-full px-4 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[var(--color-text-secondary)] mb-1">
                    End
                  </label>
                  <input
                    type="time"
                    value={form.working_hours.end}
                    onChange={(e) =>
                      update("working_hours", {
                        ...form.working_hours,
                        end: e.target.value,
                      })
                    }
                    className="w-full px-4 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Error ────────────────────────────────────── */}
        {error && (
          <div className="mt-4 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* ── Navigation ───────────────────────────────── */}
        <div className="flex items-center justify-between mt-8 pt-6 border-t border-[var(--color-border)]">
          {step > 0 ? (
            <button
              onClick={() => setStep(step - 1)}
              className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] rounded-xl hover:bg-[var(--color-surface-muted)] transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </button>
          ) : (
            <div />
          )}

          {step < STEPS.length - 1 ? (
            <button
              onClick={() => canNext() && setStep(step + 1)}
              disabled={!canNext()}
              className={clsx(
                "flex items-center gap-2 px-6 py-2.5 text-sm font-semibold rounded-xl transition-all",
                canNext()
                  ? "bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02]"
                  : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)] cursor-not-allowed"
              )}
            >
              Continue
              <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex items-center gap-2 px-6 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-emerald-500 to-teal-600 rounded-xl shadow-lg shadow-emerald-500/25 hover:shadow-emerald-500/40 hover:scale-[1.02] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Setting up...
                </>
              ) : (
                <>
                  <Rocket className="w-4 h-4" />
                  Launch Founder OS
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Step hint */}
      <p className="text-center text-xs text-[var(--color-text-muted)] mt-4">
        Step {step + 1} of {STEPS.length} — You can always update this later in
        Settings
      </p>
    </div>
  );
}
