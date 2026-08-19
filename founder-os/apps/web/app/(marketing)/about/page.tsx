import Link from "next/link";
import { PageHero } from "../_components/page-hero";
import { CtaBand } from "../_components/cta-band";
import { Section, SectionHeading, Prose } from "../_components/section";
import { JsonLd } from "../../_components/json-ld";
import {
  absoluteUrl,
  businessLocality,
  contactEmail,
  founderName,
  organizationSchema,
  pageMetadata,
  personSchema,
  responseTimePromise,
  siteName,
} from "../../../lib/site";

export const metadata = pageMetadata({
  title: "About us",
  description: `Who builds Founder OS and why: a local-first, OSS-first AI operating system for solo founders, built in New Delhi by ${founderName} — the person who needed it first.`,
  path: "/about",
  keywords: [
    "about Founder OS",
    "who built Founder OS",
    founderName,
    "AI co-founder company",
  ],
});

/**
 * AboutPage tied to the named founder.
 *
 * A one-person operation asking founders to trust it with their company state
 * has to be identifiable. `mainEntity` points at the Person node so the name,
 * role and GitHub profile are attached to the organisation rather than left as
 * prose a crawler has to infer authorship from.
 */
const aboutPageSchema = {
  "@context": "https://schema.org",
  "@type": "AboutPage",
  url: absoluteUrl("/about"),
  name: `About ${siteName}`,
  description: `${siteName} is built and operated by ${founderName} in ${businessLocality}, India.`,
  mainEntity: { "@id": organizationSchema["@id"] },
  about: { "@id": personSchema["@id"] },
  inLanguage: "en",
};

const principles = [
  {
    title: "State before chat",
    body: "A chat window with no memory of your company is a demo. We invest in the canonical model underneath — the part that is hard, boring and actually load-bearing.",
  },
  {
    title: "Meet founders in their tools",
    body: "We will not ask you to migrate. Every tool is a synchronisation endpoint, and the unified picture is mirrored back into the app you already open every morning.",
  },
  {
    title: "Local-first, OSS-first",
    body: "Inference runs on Ollama by default so the system works with nothing leaving your machine. Hosted models are an upgrade you choose, never a requirement we impose.",
  },
  {
    title: "Autonomy needs a brake",
    body: "Anything irreversible waits for a human. We would rather ship a system that asks one question too many than one that sends the wrong email confidently.",
  },
  {
    title: "Honest about what ships",
    body: "Obsidian is shipped; Notion is in progress and described that way. No screenshot on this site shows a feature that does not exist.",
  },
];

export default function AboutPage() {
  return (
    <>
      <JsonLd data={personSchema} />
      <JsonLd data={aboutPageSchema} />

      <PageHero
        eyebrow="About us"
        title="Built by a solo founder, for solo founders"
        lead="Founder OS started as the tool its author needed: one system that knows the whole company, so the day stops being spent reassembling context by hand."
        crumbs={[{ href: "/about", label: "About us" }]}
      />

      <Section>
        <Prose>
          <h2>Why this exists</h2>
          <p>
            Running a company alone is not hard because the work is hard. It is
            hard because you hold every role at once — product, sales, support,
            ops, finance — and each of those roles lives in a different tool. By
            the time you have re-read five apps to work out what is actually going
            on, the morning is gone. The bottleneck is not typing speed. It is
            context switching.
          </p>
          <p>
            The obvious response — another AI chat assistant — does not fix that.
            It starts from near-zero context, produces something plausible, and
            forgets the conversation. What was missing was not a better writer. It
            was a system that holds a durable, structured model of the company and
            keeps it true.
          </p>
          <p>
            So that is what Founder OS is: a{" "}
            <Link href="/features">Company State Engine</Link> with autonomous
            agents on top of it, fed by the tools you already use and mirrored back
            into them. It is being built in public, in the open, in{" "}
            {businessLocality}, India.
          </p>

          <h2>Who is behind it</h2>
          <p>
            Founder OS is built and operated by {founderName}, an engineer in{" "}
            {businessLocality}. It is a small, independent operation — which is
            exactly the constraint the product is designed around, and the reason
            support is answered by the person who wrote the code rather than by a
            queue. {responseTimePromise}
          </p>
          <p>
            The codebase is developed in the open. If you want to read the
            architecture before trusting it with your company&apos;s state, that is
            encouraged — the repository, the architecture decision records, and the
            roadmap are all public.
          </p>

          <h2>How we work</h2>
        </Prose>

        <ul className="mt-6 grid grid-cols-1 max-w-4xl gap-4 sm:grid-cols-2">
          {principles.map((principle) => (
            <li
              key={principle.title}
              className="rounded-card border border-line bg-surface p-5"
            >
              <h3 className="font-serif text-lg font-semibold text-ink">
                {principle.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
                {principle.body}
              </p>
            </li>
          ))}
        </ul>
      </Section>

      <Section bordered labelledBy="about-contact-title">
        <SectionHeading
          id="about-contact-title"
          title="Talk to a person"
          lead="There is no support tier and no gatekeeping. Questions about the product, the architecture, or whether this is the wrong tool for you are all fair."
        />
        <Prose className="mt-6">
          <ul>
            <li>
              Email directly:{" "}
              <a href={`mailto:${contactEmail}`}>{contactEmail}</a>
            </li>
            <li>
              Or use the <Link href="/contact">contact page</Link> — it tells you
              what to include so the first reply is useful rather than a request
              for more detail.
            </li>
            <li>
              Practical questions about pricing, setup and self-hosting are
              answered on the <Link href="/faq">FAQ</Link>.
            </li>
          </ul>
        </Prose>
      </Section>

      <CtaBand
        title="See whether it fits your week"
        body="Start on the free tier, connect one tool, and judge it on your own company state rather than on a marketing page."
      />
    </>
  );
}
