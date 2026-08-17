import type { FaqItem } from "./site";
import { responseTimePromise } from "./site";

/**
 * FAQ content, shared by the home page (first six) and /faq (all of them).
 *
 * Only /faq emits the FAQPage structured data — see `emitSchema` on
 * `<FaqSection>`; two FAQPage blocks on one URL is invalid markup.
 *
 * Answers are plain strings, not JSX, because the same text is reused verbatim
 * inside the JSON-LD.
 */
export const faqs: FaqItem[] = [
  {
    question: "What is Founder OS?",
    answer:
      "Founder OS is an AI operating system for solo founders and tiny teams. You talk to one Orchestrator; it decomposes your request, delegates to specialist agents, and returns a single answer. Underneath it maintains a Company State Engine — a canonical, living model of your goals, projects, tasks, decisions, metrics, people and meetings — that stays in sync with the tools you already use.",
  },
  {
    question: "How is this different from ChatGPT or Claude?",
    answer:
      "A general chat assistant starts every conversation from near-zero context and forgets it afterwards. Founder OS keeps a persistent, structured model of your company plus four layers of long-term memory, so it answers from what your tools actually say rather than from what you can remember to paste into a prompt. It also acts in the background on a schedule instead of only when you open a chat window.",
  },
  {
    question: "Do I have to move my work into Founder OS?",
    answer:
      "No. That is the point of the adapter model. Founder OS reads your existing tools as state sources and mirrors the reconciled picture back into them. Obsidian is supported today and Notion is in progress, so you keep writing where you already write — the difference is that your notes stop disagreeing with your issue tracker and your calendar.",
  },
  {
    question: "Can it take actions on its own, or does it just suggest things?",
    answer:
      "Both, deliberately split by risk. Every proposed action is classified into one of three tiers — low, medium or high. Low-risk work can run unattended, and anything irreversible or outward-facing (sending messages, refunds, deletions) is blocked until you approve it. Agents cannot bypass that gate.",
  },
  {
    question: "Which AI models does it run on?",
    answer:
      "It is provider-pluggable with a three-tier fallback. Ollama runs locally by default, so you can use Founder OS without sending your company data to a model vendor at all. You can swap in Anthropic Claude, Google Gemini, or any OpenAI-compatible endpoint per your own cost and privacy preferences.",
  },
  {
    question: "Is my company data used to train models?",
    answer:
      "No. Your data is used to serve you. Running the default local Ollama provider means prompts never leave your infrastructure; if you configure a hosted provider, the prompt goes only to that provider to answer your request. See the privacy policy for the full detail on what is stored and for how long.",
  },
  {
    question: "What does it cost to start?",
    answer:
      "There is a free tier and it does not ask for a card. You can connect a tool, let the engine build your company state, and decide whether the unified picture is worth paying for before you spend anything.",
  },
  {
    question: "How long does setup take?",
    answer:
      "Signing up and connecting your first state source is a few minutes. The useful part — the engine having enough observed history to reason well about your company — builds over the first week as it reads your existing docs and watches new activity arrive.",
  },
  {
    question: "Who is Founder OS for?",
    answer:
      "Solo founders and teams of two or three who need the output of a small operations team and cannot hire one. It assumes you are the person doing product, sales, support and admin at the same time, and that context switching is your real bottleneck.",
  },
  {
    question: "Does it replace my project management tool?",
    answer:
      "It is not trying to. Founder OS sits above your tools rather than beside them: it reconciles what they each know into one canonical state and writes the result back. If you love Notion or GitHub Projects, keep them.",
  },
  {
    question: "Can I self-host it?",
    answer:
      "Yes. The stack is OSS-first and local-first by design — FastAPI, Postgres with pgvector, Redis, Celery, and Ollama for inference — so it runs on your own machine or your own server. Cloud hosting is a convenience, not a requirement.",
  },
  {
    question: "How fast do you reply to support questions?",
    answer: `${responseTimePromise} Write to us from the contact page with what you were doing and what you expected to happen, and you will get a real answer from the person who built the thing — not a ticket number.`,
  },
];

/** The subset shown on the home page. */
export const homeFaqs = faqs.slice(0, 6);
