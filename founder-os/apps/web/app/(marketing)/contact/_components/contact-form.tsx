"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Mail } from "lucide-react";
import { contactEmail } from "../../../../lib/site";

/**
 * Contact form.
 *
 * There is no transactional email service wired up on the marketing side, and a
 * form that pretends to send while dropping the message on the floor is worse
 * than no form. So this composes a pre-filled draft in the visitor's own mail
 * client and then routes to /thank-you — the message really does reach us, and
 * the visitor keeps a copy in their sent folder.
 *
 * When a server-side inbox exists (roadmap item), swap `handleSubmit` for a
 * server action and keep the same fields and the same /thank-you redirect.
 */

const topics = [
  "Product question",
  "Setup or self-hosting help",
  "Bug report",
  "Billing",
  "Partnership or press",
  "Something else",
] as const;

const fieldClass =
  "mt-1.5 w-full rounded-control border border-line bg-surface px-3 py-2.5 text-[15px] text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none";

export function ContactForm() {
  const router = useRouter();
  const [topic, setTopic] = useState<string>(topics[0]);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") ?? "").trim();
    const from = String(data.get("email") ?? "").trim();
    const message = String(data.get("message") ?? "").trim();

    const body = [
      message,
      "",
      "—",
      name && `From: ${name}`,
      from && `Reply to: ${from}`,
      "Sent from the Founder OS contact page",
    ]
      .filter(Boolean)
      .join("\n");

    window.location.href = `mailto:${contactEmail}?subject=${encodeURIComponent(
      `[${topic}] ${name ? `from ${name}` : "Founder OS enquiry"}`,
    )}&body=${encodeURIComponent(body)}`;

    router.push("/thank-you");
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-xl">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="name" className="text-sm font-medium text-ink">
            Your name
          </label>
          <input
            id="name"
            name="name"
            type="text"
            required
            autoComplete="name"
            placeholder="Aditya"
            className={fieldClass}
          />
        </div>
        <div>
          <label htmlFor="email" className="text-sm font-medium text-ink">
            Your email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            required
            autoComplete="email"
            placeholder="you@company.com"
            className={fieldClass}
          />
        </div>
      </div>

      <div className="mt-4">
        <label htmlFor="topic" className="text-sm font-medium text-ink">
          What is this about?
        </label>
        <select
          id="topic"
          name="topic"
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          className={fieldClass}
        >
          {topics.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4">
        <label htmlFor="message" className="text-sm font-medium text-ink">
          Your message
        </label>
        <textarea
          id="message"
          name="message"
          required
          rows={6}
          placeholder="What were you doing, what did you expect, and what happened instead?"
          className={fieldClass}
        />
      </div>

      <button
        type="submit"
        className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-control bg-accent px-6 py-3 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover sm:w-auto"
      >
        <Mail className="h-4 w-4" aria-hidden="true" />
        Compose the email
      </button>

      <p className="mt-3 text-[13px] leading-relaxed text-ink-secondary">
        This opens a pre-filled draft in your own mail app addressed to{" "}
        <a
          href={`mailto:${contactEmail}`}
          className="text-accent-text underline underline-offset-2 hover:no-underline"
        >
          {contactEmail}
        </a>{" "}
        — nothing is sent from this page, so you keep a copy in your sent folder.
      </p>
    </form>
  );
}
