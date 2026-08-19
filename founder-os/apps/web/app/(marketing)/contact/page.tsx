import Link from "next/link";
import { Clock, Github, Mail, MapPin } from "lucide-react";
import { PageHero } from "../_components/page-hero";
import { Section, SectionHeading, Prose } from "../_components/section";
import { ContactForm } from "./_components/contact-form";
import { JsonLd } from "../../_components/json-ld";
import {
  absoluteUrl,
  businessLocality,
  businessRegion,
  contactEmail,
  organizationSchema,
  pageMetadata,
  responseTimePromise,
  supportHours,
} from "../../../lib/site";

export const metadata = pageMetadata({
  title: "Contact us",
  description:
    "Contact Founder OS. Email us directly and get a reply from the person who built it within 24 hours on business days. Operated from New Delhi, India, supporting founders worldwide.",
  path: "/contact",
  keywords: ["contact Founder OS", "Founder OS support", "AI founder tool support"],
});

/** ContactPage schema, tied to the site-wide Organization node. */
const contactPageSchema = {
  "@context": "https://schema.org",
  "@type": "ContactPage",
  url: absoluteUrl("/contact"),
  name: "Contact Founder OS",
  description:
    "Reach the Founder OS team by email. Replies within 24 hours on business days.",
  mainEntity: {
    "@type": "Organization",
    "@id": organizationSchema["@id"],
    contactPoint: {
      "@type": "ContactPoint",
      contactType: "customer support",
      email: contactEmail,
      areaServed: "Worldwide",
      availableLanguage: ["English", "Hindi"],
      hoursAvailable: {
        "@type": "OpeningHoursSpecification",
        dayOfWeek: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        opens: "10:00",
        closes: "19:00",
      },
    },
  },
};

const channels = [
  {
    icon: Mail,
    label: "Email",
    value: contactEmail,
    href: `mailto:${contactEmail}`,
    note: "The fastest route. Goes straight to the person who wrote the code.",
  },
  {
    icon: Clock,
    label: "Response time",
    value: "Within 24 hours",
    note: `${responseTimePromise} Support hours are ${supportHours}; messages sent over the weekend are answered on Monday.`,
  },
  {
    icon: MapPin,
    label: "Based in",
    value: `${businessLocality}, ${businessRegion}, India`,
    note: "Remote-first and available worldwide — timezone overlap is easiest with Europe and Asia.",
  },
  {
    icon: Github,
    label: "Code and issues",
    value: "github.com/adityaastro2004/founder-os",
    href: "https://github.com/adityaastro2004/founder-os",
    note: "Bug reports with reproduction steps are welcome as issues.",
  },
];

export default function ContactPage() {
  return (
    <>
      <JsonLd data={contactPageSchema} />

      <PageHero
        eyebrow="Contact us"
        title="Talk to the person who built it"
        lead={`${responseTimePromise} No ticket queue, no tiered support, no bot deflecting you into a help centre.`}
        crumbs={[{ href: "/contact", label: "Contact us" }]}
      />

      <Section>
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
          <div>
            <SectionHeading id="form-title" title="Send a message" />
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-secondary">
              For a bug, include what you were doing, what you expected, and what
              happened instead — that usually turns two round-trips into one.
            </p>
            <div className="mt-8">
              <ContactForm />
            </div>
          </div>

          <div>
            <h2 className="font-serif text-xl font-semibold tracking-tight text-ink md:text-2xl">
              Other ways to reach us
            </h2>
            <ul className="mt-6 space-y-px overflow-hidden rounded-card border border-line bg-line">
              {channels.map(({ icon: Icon, label, value, href, note }) => (
                <li key={label} className="bg-surface p-5">
                  <div className="flex items-center gap-2.5">
                    <Icon className="h-4 w-4 text-accent" aria-hidden="true" />
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                      {label}
                    </span>
                  </div>
                  <p className="mt-2 text-[15px] font-medium text-ink">
                    {href ? (
                      <a
                        href={href}
                        {...(href.startsWith("http")
                          ? { target: "_blank", rel: "noopener noreferrer" }
                          : {})}
                        className="text-accent-text underline underline-offset-2 hover:no-underline"
                      >
                        {value}
                      </a>
                    ) : (
                      value
                    )}
                  </p>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-ink-secondary">
                    {note}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      <Section bordered labelledBy="before-you-write-title">
        <SectionHeading
          id="before-you-write-title"
          title="Before you write"
          lead="Two of the three most common questions are already answered — this saves you the 24 hours."
        />
        <Prose className="mt-6">
          <ul>
            <li>
              Pricing, setup time, data handling and self-hosting are covered on
              the <Link href="/faq">FAQ</Link>.
            </li>
            <li>
              How a specific part works is covered in the{" "}
              <Link href="/features">feature breakdown</Link>.
            </li>
            <li>
              Whether it fits your situation is easiest to judge from an{" "}
              <Link href="/case-studies">illustrative scenario</Link>.
            </li>
            <li>
              For how we handle what you send us, see the{" "}
              <Link href="/privacy">privacy policy</Link>.
            </li>
          </ul>
        </Prose>
      </Section>
    </>
  );
}
