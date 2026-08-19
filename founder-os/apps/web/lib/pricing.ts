/**
 * Public pricing content for `/pricing`.
 *
 * ⚠️ These numbers are a mirror of the `subscription_plans` seed in
 * `apps/api/schema.sql` (and `alembic/versions/0000_baseline.py`). That table is
 * the source of truth — Stripe checkout, the limit enforcement and the in-app
 * billing page all read it. If a plan price or limit changes there, change it
 * here in the same commit, or the public page starts advertising a plan the
 * product does not sell.
 *
 * Deliberately a static module rather than a fetch: `/pricing` has to be
 * statically rendered to be crawlable and fast, and a marketing page must not
 * depend on the API being reachable.
 */

export type Plan = {
  /** Matches `subscription_plans.name` — also the URL fragment (#starter). */
  id: string;
  name: string;
  tagline: string;
  /** USD per month. `null` renders as "Custom". */
  monthlyUsd: number;
  /** USD per year, billed once. */
  yearlyUsd: number;
  /** Headline limits, phrased for a buyer rather than for the schema. */
  limits: string[];
  features: string[];
  ctaLabel: string;
  ctaHref: string;
  /** Exactly one plan may set this — it drives the visual emphasis. */
  featured?: boolean;
  /** Shown under the price; keeps the trial/refund caveat next to the number. */
  note?: string;
};

export const plans: Plan[] = [
  {
    id: "free",
    name: "Free",
    tagline: "Enough to build your company state and judge it on your own data.",
    monthlyUsd: 0,
    yearlyUsd: 0,
    limits: [
      "50 agent tasks per month",
      "3 agents",
      "2 workflows",
      "10 knowledge items",
      "1 seat",
    ],
    features: [
      "Company State Engine",
      "Basic agents",
      "Manual workflows",
      "One state source (Obsidian)",
      "Local inference on Ollama",
    ],
    ctaLabel: "Start for free",
    ctaHref: "/sign-up",
    note: "No card required. Full-feature access runs as a 14-day trial.",
  },
  {
    id: "starter",
    name: "Starter",
    tagline: "For the solo founder who wants the whole system running.",
    monthlyUsd: 99,
    yearlyUsd: 999,
    limits: [
      "500 agent tasks per month",
      "5 agents",
      "10 workflows",
      "100 knowledge items",
      "1 seat",
    ],
    features: [
      "Everything in Free",
      "All specialist agents",
      "Scheduled workflows + automatic weekly planning",
      "Basic integrations",
      "Email support",
    ],
    ctaLabel: "Start with Starter",
    ctaHref: "/sign-up",
    featured: true,
  },
  {
    id: "pro",
    name: "Pro",
    tagline: "For a small team that has outgrown one person's context.",
    monthlyUsd: 299,
    yearlyUsd: 2999,
    limits: [
      "2,000 agent tasks per month",
      "10 agents",
      "50 workflows",
      "500 knowledge items",
      "5 seats",
    ],
    features: [
      "Everything in Starter",
      "Custom workflows",
      "Advanced integrations",
      "API access",
      "Priority support",
    ],
    ctaLabel: "Start with Pro",
    ctaHref: "/sign-up",
  },
  {
    id: "enterprise",
    name: "Enterprise",
    tagline: "For teams that need it inside their own boundary.",
    monthlyUsd: 999,
    yearlyUsd: 9999,
    limits: [
      "Unlimited agent tasks",
      "Unlimited agents and workflows",
      "50 seats",
    ],
    features: [
      "Everything in Pro",
      "All integrations",
      "White-label",
      "SLA",
      "Dedicated support",
    ],
    ctaLabel: "Talk to us",
    ctaHref: "/contact",
  },
];

/** Cheapest and dearest monthly price — feeds the AggregateOffer schema. */
export const priceRange = {
  low: Math.min(...plans.map((p) => p.monthlyUsd)),
  high: Math.max(...plans.map((p) => p.monthlyUsd)),
  currency: "USD",
};

/** Yearly saving vs paying monthly, as a whole-number percentage. */
export function yearlySavingPercent(plan: Plan): number | null {
  if (plan.monthlyUsd <= 0) return null;
  const monthlyTotal = plan.monthlyUsd * 12;
  return Math.round(((monthlyTotal - plan.yearlyUsd) / monthlyTotal) * 100);
}

/**
 * Pricing-specific FAQs. Kept here rather than in `lib/faq.ts` because only
 * `/pricing` emits them as FAQPage structured data — `/faq` owns the general
 * set, and two FAQPage blocks answering different questions is the correct
 * split (one per URL).
 */
export const pricingFaqs = [
  {
    question: "Is there a free plan?",
    answer:
      "Yes. The Free plan costs nothing and never asks for a card. It gives you 50 agent tasks a month, three agents and one state source — enough to connect a tool, let the Company State Engine build your company state, and decide whether the unified picture is worth paying for. Full-feature access is available as a 14-day trial on top of it.",
  },
  {
    question: "How much does Founder OS cost?",
    answer:
      "Starter is $99 per month or $999 per year. Pro is $299 per month or $2,999 per year. Enterprise is $999 per month or $9,999 per year. Annual billing saves roughly 16 percent — about two months free — on every paid plan.",
  },
  {
    question: "What counts as an agent task?",
    answer:
      "One task is one unit of delegated work: a request you send the Orchestrator, a subtask it delegates to a specialist agent, or a scheduled job such as the Monday plan. Reading your state sources and syncing state back into your tools do not consume task quota.",
  },
  {
    question: "Can I self-host instead of paying?",
    answer:
      "Yes. The stack is OSS-first — FastAPI, Postgres with pgvector, Redis, Celery and Ollama for inference — so you can run the whole system on your own machine or server. The paid plans buy hosting, support and the managed integrations, not the right to use the software.",
  },
  {
    question: "Do I pay extra for the AI models?",
    answer:
      "Not on the default configuration. Ollama runs inference locally, so there is no per-token vendor bill at all. If you point Founder OS at Anthropic, Google or an OpenAI-compatible endpoint, you supply your own API key and pay that provider directly — Founder OS does not resell tokens.",
  },
  {
    question: "Can I change or cancel my plan?",
    answer:
      "Yes, at any time, from the billing page in your dashboard. Upgrades take effect immediately and downgrades take effect at the end of the current billing period. Cancelling leaves your company state intact and drops you back to the Free plan limits.",
  },
];
