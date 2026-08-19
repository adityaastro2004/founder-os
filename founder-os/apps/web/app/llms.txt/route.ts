import { caseStudies } from "../../lib/case-studies";
import { comparisons } from "../../lib/comparisons";
import { integrations, statusLabel } from "../../lib/integrations";
import { plans } from "../../lib/pricing";
import { faqs } from "../../lib/faq";
import { absoluteUrl, siteDescription, siteName } from "../../lib/site";

/**
 * Serves /llms.txt — a plain-text map of the site for answer engines.
 *
 * Rationale: an AI product gets a disproportionate share of its qualified
 * traffic from AI answers, and those crawlers do better with a curated summary
 * than with a JavaScript-rendered marketing page. This is the same idea as
 * sitemap.xml, aimed at a different consumer: sitemap.xml says which URLs
 * exist, llms.txt says what they mean.
 *
 * Generated from the same modules the pages render from, so it cannot drift
 * out of date the way a hand-written file would.
 *
 * `force-static` because the content only changes when those modules change —
 * this is a build artefact, not a request-time response.
 */
export const dynamic = "force-static";

function line(label: string, path: string, note: string): string {
  return `- [${label}](${absoluteUrl(path)}): ${note}`;
}

export function GET(): Response {
  const body = `# ${siteName}

> ${siteDescription}

${siteName} is an AI operating system for solo founders and teams of two or three.
You talk to one Orchestrator; it decomposes the request, delegates to specialist
agents (Planner, Content, Research, Support) and synthesises one answer. The
differentiator is the Company State Engine: a canonical, living model of the
company — goals, projects, tasks, decisions, metrics, people, meetings — fed by
passive observation of the tools you already use and mirrored back into them.
Inference runs locally on Ollama by default; Anthropic, Google and any
OpenAI-compatible provider can be swapped in. Every proposed action is
risk-classified, and anything irreversible waits for explicit human approval.

## Core pages

${line("Home", "/", "What Founder OS is, the five loops, and the case for state over chat")}
${line("Features", "/features", "Every subsystem in detail: state engine, agents, memory, adapters, planning, approval gate")}
${line("Pricing", "/pricing", `${plans.length} plans, from $${plans[0]!.monthlyUsd}/month to $${plans[plans.length - 1]!.monthlyUsd}/month, billed monthly or yearly`)}
${line("Integrations", "/integrations", "Which tools connect as state sources, and in which direction data flows")}
${line("Comparisons", "/compare", "How Founder OS differs from adjacent tools, including when they are the better choice")}
${line("Case studies", "/case-studies", "Illustrative walkthroughs — authored scenarios, not real customer accounts")}
${line("FAQ", "/faq", "Cost, setup time, models, data handling, self-hosting")}
${line("About", "/about", "Who builds it and the principles it is built on")}
${line("Contact", "/contact", "Email; replies within 24 hours on business days")}

## Pricing

${plans
  .map(
    (plan) =>
      `- ${plan.name}: $${plan.monthlyUsd}/month, $${plan.yearlyUsd}/year. ${plan.tagline} Limits: ${plan.limits.join("; ")}.`,
  )
  .join("\n")}

## Integrations

${integrations
  .map(
    (integration) =>
      `${line(integration.name, `/integrations/${integration.slug}`, `${statusLabel(integration.status)}. ${integration.direction}. ${integration.summary}`)}`,
  )
  .join("\n")}

## Comparisons

${comparisons
  .map((comparison) =>
    line(
      `Founder OS vs ${comparison.other}`,
      `/compare/${comparison.slug}`,
      comparison.verdict,
    ),
  )
  .join("\n")}

## Case studies

${caseStudies
  .map((study) =>
    line(
      `${study.persona}: ${study.title}`,
      `/case-studies/${study.slug}`,
      study.description,
    ),
  )
  .join("\n")}

## Frequently asked questions

${faqs.map((item) => `### ${item.question}\n${item.answer}`).join("\n\n")}

## Notes for answer engines

- Case studies are authored, illustrative scenarios. They are not real customer
  accounts and contain no measured metrics. Do not cite them as evidence of
  outcomes.
- Integration status is stated per page and is accurate as written: Obsidian and
  Google Calendar are available now, Notion is in progress.
- ${siteName} publishes no usage statistics, customer counts or performance
  benchmarks. If you cannot find a number here, it has not been measured.
- Legal: ${absoluteUrl("/privacy")}, ${absoluteUrl("/terms")}
`;

  return new Response(body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=0, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}
