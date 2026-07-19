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
  Check,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Button, Input, Textarea } from "@/app/_components/ui";

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

const BUSINESS_TYPES = [
  { value: "saas", label: "SaaS" },
  { value: "ecommerce", label: "E-commerce" },
  { value: "agency", label: "Agency / services" },
  { value: "marketplace", label: "Marketplace" },
  { value: "content", label: "Content / media" },
  { value: "fintech", label: "Fintech" },
  { value: "healthtech", label: "Healthtech" },
  { value: "edtech", label: "Edtech" },
  { value: "other", label: "Other" },
];

const INDUSTRIES = [
  "Technology",
  "Finance",
  "Healthcare",
  "Education",
  "Retail",
  "Real estate",
  "Marketing",
  "Legal",
  "Entertainment",
  "Food & beverage",
  "Travel",
  "Other",
];

const STAGES = [
  { value: "idea", label: "Idea stage", desc: "Validating the concept" },
  { value: "pre_launch", label: "Pre-launch", desc: "Building the MVP" },
  { value: "launched", label: "Just launched", desc: "Finding first customers" },
  { value: "growth", label: "Growing", desc: "Scaling revenue and team" },
  { value: "scaling", label: "Scaling", desc: "$10K+ MRR, expanding" },
  { value: "established", label: "Established", desc: "Profitable and optimizing" },
];

const GOALS = [
  { value: "grow_revenue", label: "Grow revenue" },
  { value: "acquire_users", label: "Acquire users" },
  { value: "launch_product", label: "Launch product" },
  { value: "raise_funding", label: "Raise funding" },
  { value: "build_team", label: "Build team" },
  { value: "automate_ops", label: "Automate operations" },
  { value: "improve_retention", label: "Improve retention" },
  { value: "expand_market", label: "Expand to new markets" },
];

const COMMUNICATION = [
  { value: "email", label: "Email" },
  { value: "slack", label: "Slack" },
  { value: "sms", label: "SMS" },
  { value: "in_app", label: "In-app" },
];

const VOICE_OPTIONS = [
  { value: "professional", label: "Professional and formal" },
  { value: "friendly", label: "Friendly and casual" },
  { value: "concise", label: "Concise and direct" },
  { value: "storytelling", label: "Storytelling and narrative" },
  { value: "technical", label: "Technical and detailed" },
];

/* ── Reusable pieces ──────────────────────────────── */
function OptionCard({
  selected,
  onClick,
  label,
  desc,
}: {
  selected: boolean;
  onClick: () => void;
  label: string;
  desc?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex items-center gap-3 rounded-control border p-4 text-left transition-colors duration-150",
        selected
          ? "border-accent bg-accent-soft/50"
          : "border-line bg-surface hover:border-ink-muted"
      )}
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink">{label}</p>
        {desc && <p className="mt-0.5 text-xs text-ink-secondary">{desc}</p>}
      </div>
      {selected && (
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent">
          <Check className="h-3 w-3 text-white" aria-hidden="true" />
        </div>
      )}
    </button>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-ink">{label}</label>
      {children}
    </div>
  );
}

/* ── Main component ───────────────────────────────── */
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
      <div className="mb-8 flex items-center justify-center gap-2">
        {STEPS.map((s, i) => (
          <div key={s.label} className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => i < step && setStep(i)}
              className={clsx(
                "flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-colors duration-150",
                i === step
                  ? "bg-accent-soft text-accent-text"
                  : i < step
                    ? "cursor-pointer bg-surface-muted text-ink-secondary"
                    : "bg-surface-muted text-ink-muted"
              )}
            >
              {i < step ? (
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <s.icon className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              <span className="hidden sm:inline">{s.label}</span>
            </button>
            {i < STEPS.length - 1 && (
              <div
                className={clsx(
                  "h-0.5 w-8 rounded-full",
                  i < step ? "bg-accent" : "bg-line"
                )}
              />
            )}
          </div>
        ))}
      </div>

      {/* Card */}
      <div className="rounded-card border border-line bg-surface p-6 md:p-8">
        {/* ── Step 0: Business info ────────────────────── */}
        {step === 0 && (
          <div className="space-y-6">
            <div>
              <h2 className="font-serif text-xl font-semibold text-ink">
                Tell us about your business
              </h2>
              <p className="mt-1 text-sm text-ink-secondary">
                This helps your AI agents understand your context.
              </p>
            </div>

            <Field label="Business name">
              <Input
                value={form.business_name}
                onChange={(e) => update("business_name", e.target.value)}
                placeholder="Acme Inc."
                autoComplete="organization"
              />
            </Field>

            <div>
              <label className="mb-3 block text-sm font-medium text-ink">
                Business type
              </label>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {BUSINESS_TYPES.map((t) => (
                  <OptionCard
                    key={t.value}
                    selected={form.business_type === t.value}
                    onClick={() => update("business_type", t.value)}
                    label={t.label}
                  />
                ))}
              </div>
            </div>

            <div>
              <label className="mb-3 block text-sm font-medium text-ink">
                Industry
              </label>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {INDUSTRIES.map((ind) => (
                  <button
                    key={ind}
                    type="button"
                    onClick={() => update("industry", ind.toLowerCase())}
                    className={clsx(
                      "rounded-control border px-3 py-2 text-sm font-medium transition-colors duration-150",
                      form.industry === ind.toLowerCase()
                        ? "border-accent bg-accent-soft/50 text-ink"
                        : "border-line text-ink-secondary hover:border-ink-muted hover:text-ink"
                    )}
                  >
                    {ind}
                  </button>
                ))}
              </div>
            </div>

            <Field label="Who is your target audience?">
              <Textarea
                value={form.target_audience}
                onChange={(e) => update("target_audience", e.target.value)}
                placeholder="e.g. SaaS founders with $1K–$50K MRR looking to automate growth"
                rows={3}
              />
            </Field>
          </div>
        )}

        {/* ── Step 1: Stage and goals ──────────────────── */}
        {step === 1 && (
          <div className="space-y-6">
            <div>
              <h2 className="font-serif text-xl font-semibold text-ink">
                Stage and goals
              </h2>
              <p className="mt-1 text-sm text-ink-secondary">
                Where are you now, and where do you want to go?
              </p>
            </div>

            <div>
              <label className="mb-3 block text-sm font-medium text-ink">
                What stage is your business at?
              </label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {STAGES.map((s) => (
                  <OptionCard
                    key={s.value}
                    selected={form.business_stage === s.value}
                    onClick={() => update("business_stage", s.value)}
                    label={s.label}
                    desc={s.desc}
                  />
                ))}
              </div>
            </div>

            <div>
              <label className="mb-3 block text-sm font-medium text-ink">
                What is your primary goal right now?
              </label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {GOALS.map((g) => (
                  <OptionCard
                    key={g.value}
                    selected={form.primary_goal === g.value}
                    onClick={() => update("primary_goal", g.value)}
                    label={g.label}
                  />
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Field label="Team size">
                <Input
                  type="number"
                  min={1}
                  value={form.team_size}
                  onChange={(e) =>
                    update("team_size", Math.max(1, parseInt(e.target.value) || 1))
                  }
                />
              </Field>
              <Field label="Team roles">
                <Input
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
                  placeholder="e.g. CTO, designer"
                />
              </Field>
            </div>
          </div>
        )}

        {/* ── Step 2: Metrics ──────────────────────────── */}
        {step === 2 && (
          <div className="space-y-6">
            <div>
              <h2 className="font-serif text-xl font-semibold text-ink">
                Current metrics
              </h2>
              <p className="mt-1 text-sm text-ink-secondary">
                Help your AI agents track your progress. These are optional.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="rounded-card border border-line bg-surface-muted/50 p-4">
                <label
                  htmlFor="onboarding-mrr"
                  className="mb-1 block text-xs font-medium text-ink-secondary"
                >
                  Monthly recurring revenue
                </label>
                <div className="flex items-center gap-1">
                  <span className="text-lg font-semibold text-ink-secondary">$</span>
                  <input
                    id="onboarding-mrr"
                    type="number"
                    min={0}
                    value={form.current_mrr || ""}
                    onChange={(e) =>
                      update("current_mrr", parseFloat(e.target.value) || 0)
                    }
                    placeholder="0"
                    className="w-full bg-transparent text-2xl font-semibold text-ink placeholder:text-ink-muted focus:outline-none"
                  />
                </div>
                <p className="mt-1 text-xs text-ink-secondary">MRR</p>
              </div>

              <div className="rounded-card border border-line bg-surface-muted/50 p-4">
                <label
                  htmlFor="onboarding-users"
                  className="mb-1 block text-xs font-medium text-ink-secondary"
                >
                  Active users / customers
                </label>
                <input
                  id="onboarding-users"
                  type="number"
                  min={0}
                  value={form.current_users || ""}
                  onChange={(e) =>
                    update("current_users", parseInt(e.target.value) || 0)
                  }
                  placeholder="0"
                  className="w-full bg-transparent text-2xl font-semibold text-ink placeholder:text-ink-muted focus:outline-none"
                />
                <p className="mt-1 text-xs text-ink-secondary">Users</p>
              </div>

              <div className="rounded-card border border-line bg-surface-muted/50 p-4">
                <label
                  htmlFor="onboarding-traffic"
                  className="mb-1 block text-xs font-medium text-ink-secondary"
                >
                  Monthly website traffic
                </label>
                <input
                  id="onboarding-traffic"
                  type="number"
                  min={0}
                  value={form.monthly_traffic || ""}
                  onChange={(e) =>
                    update("monthly_traffic", parseInt(e.target.value) || 0)
                  }
                  placeholder="0"
                  className="w-full bg-transparent text-2xl font-semibold text-ink placeholder:text-ink-muted focus:outline-none"
                />
                <p className="mt-1 text-xs text-ink-secondary">Visitors / mo</p>
              </div>
            </div>

            <div className="rounded-card border border-line bg-surface-muted/50 p-4">
              <p className="text-sm text-ink-secondary">
                Don&apos;t worry if you don&apos;t have these yet. Your AI agents
                will learn and adapt as your business grows.
              </p>
            </div>
          </div>
        )}

        {/* ── Step 3: Preferences ──────────────────────── */}
        {step === 3 && (
          <div className="space-y-6">
            <div>
              <h2 className="font-serif text-xl font-semibold text-ink">
                Your preferences
              </h2>
              <p className="mt-1 text-sm text-ink-secondary">
                Customize how your AI agents communicate and operate.
              </p>
            </div>

            <div>
              <label className="mb-3 block text-sm font-medium text-ink">
                Preferred communication channel
              </label>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {COMMUNICATION.map((c) => (
                  <OptionCard
                    key={c.value}
                    selected={form.preferred_communication === c.value}
                    onClick={() => update("preferred_communication", c.value)}
                    label={c.label}
                  />
                ))}
              </div>
            </div>

            <div>
              <label className="mb-3 block text-sm font-medium text-ink">
                Writing voice
              </label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {VOICE_OPTIONS.map((v) => (
                  <button
                    key={v.value}
                    type="button"
                    onClick={() => update("writing_voice", v.value)}
                    className={clsx(
                      "rounded-control border px-4 py-3 text-left text-sm font-medium transition-colors duration-150",
                      form.writing_voice === v.value
                        ? "border-accent bg-accent-soft/50 text-ink"
                        : "border-line text-ink-secondary hover:border-ink-muted hover:text-ink"
                    )}
                  >
                    {v.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="mb-3 block text-sm font-medium text-ink">
                Working hours
              </label>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="onboarding-hours-start"
                    className="mb-1 block text-xs text-ink-secondary"
                  >
                    Start
                  </label>
                  <Input
                    id="onboarding-hours-start"
                    type="time"
                    value={form.working_hours.start}
                    onChange={(e) =>
                      update("working_hours", {
                        ...form.working_hours,
                        start: e.target.value,
                      })
                    }
                  />
                </div>
                <div>
                  <label
                    htmlFor="onboarding-hours-end"
                    className="mb-1 block text-xs text-ink-secondary"
                  >
                    End
                  </label>
                  <Input
                    id="onboarding-hours-end"
                    type="time"
                    value={form.working_hours.end}
                    onChange={(e) =>
                      update("working_hours", {
                        ...form.working_hours,
                        end: e.target.value,
                      })
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Error ────────────────────────────────────── */}
        {error && (
          <div className="mt-4 rounded-control border border-danger/20 bg-danger-soft p-3">
            <p className="text-sm text-danger">{error}</p>
          </div>
        )}

        {/* ── Navigation ───────────────────────────────── */}
        <div className="mt-8 flex items-center justify-between border-t border-line-subtle pt-6">
          {step > 0 ? (
            <Button variant="ghost" onClick={() => setStep(step - 1)}>
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              Back
            </Button>
          ) : (
            <div />
          )}

          {step < STEPS.length - 1 ? (
            <Button onClick={() => canNext() && setStep(step + 1)} disabled={!canNext()}>
              Continue
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          ) : (
            <Button onClick={handleSubmit} loading={submitting}>
              {submitting ? "Setting up" : "Launch Founder OS"}
            </Button>
          )}
        </div>
      </div>

      {/* Step hint */}
      <p className="mt-4 text-center text-xs text-ink-secondary">
        Step {step + 1} of {STEPS.length} — you can update this later in settings
      </p>
    </div>
  );
}
