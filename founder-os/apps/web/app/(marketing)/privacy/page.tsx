import Link from "next/link";
import { PageHero } from "../_components/page-hero";
import { Section, Prose } from "../_components/section";
import { contactEmail, pageMetadata, siteName } from "../../../lib/site";

/**
 * Privacy policy.
 *
 * Written to describe what the system genuinely does today (Clerk for auth,
 * Stripe for billing, PostHog + GA4 for analytics, Postgres on AWS ap-south-1,
 * pluggable LLM providers with local Ollama as the default). Keep it in sync
 * when a new sub-processor or data flow is added — this page is a factual claim
 * about the product, not marketing copy.
 *
 * NOTE for maintainers: this is a good-faith engineering draft, not legal
 * advice. Have it reviewed by counsel before relying on it for a jurisdiction
 * that matters to you.
 */

const LAST_UPDATED = "17 August 2026";

export const metadata = pageMetadata({
  title: "Privacy policy",
  description:
    "How Founder OS collects, uses, stores and protects your data — including AI model processing, sub-processors, analytics cookies, retention periods and your access and deletion rights.",
  path: "/privacy",
});

export default function PrivacyPage() {
  return (
    <>
      <PageHero
        eyebrow="Legal"
        title="Privacy policy"
        lead={`How ${siteName} handles your data. Last updated ${LAST_UPDATED}.`}
        crumbs={[{ href: "/privacy", label: "Privacy policy" }]}
      />

      <Section>
        <Prose>
          <h2>1. Who we are</h2>
          <p>
            {siteName} (&ldquo;we&rdquo;, &ldquo;us&rdquo;) is an independent
            software product operated from New Delhi, India. We are the data
            controller for the personal data described in this policy. For any
            privacy question or request, write to{" "}
            <a href={`mailto:${contactEmail}`}>{contactEmail}</a>.
          </p>

          <h2>2. Scope</h2>
          <p>
            This policy covers this website and the {siteName} application. It
            does not cover the third-party tools you choose to connect (your note
            app, calendar, code host and so on) — those remain governed by their
            own privacy policies and by your account settings with them.
          </p>

          <h2>3. What we collect</h2>
          <h3>Account data</h3>
          <p>
            Authentication is handled by Clerk. When you sign up we receive your
            name, email address, and the authentication identifiers Clerk issues.
            We never see or store your password; if you sign in with a social
            provider we receive only the profile fields that provider releases.
          </p>
          <h3>Company content you connect or provide</h3>
          <p>
            When you connect a state source or upload a document, we process its
            contents to build your company state: goals, projects, tasks,
            decisions, metrics, people and meetings, plus the agent memories
            derived from them. This is the core of the service and can include
            business information, and incidentally personal data about people you
            work with (names in meeting notes, for example). It is stored against
            your account and is not shared with other users.
          </p>
          <h3>Integration credentials</h3>
          <p>
            Tokens for connected tools are stored encrypted and used only to read
            from and write to that tool on your behalf. You can disconnect a
            source at any time from the app, which revokes our further use of that
            token.
          </p>
          <h3>Billing data</h3>
          <p>
            Payments are processed by Stripe. Card numbers never reach our
            servers — we store only the subscription state and customer reference
            that Stripe returns.
          </p>
          <h3>Usage and device data</h3>
          <p>
            We collect product analytics events (pages viewed, features used),
            plus the technical data any web server receives: IP address, browser
            and operating system, and timestamps. Server logs are sanitised to
            redact secrets and tokens before they are written.
          </p>
          <h3>Support correspondence</h3>
          <p>
            If you email us or use the contact form, we keep the message and your
            email address so we can answer it and follow up.
          </p>

          <h2>4. How AI models process your data</h2>
          <p>
            This is the part founders ask about most, so it is stated plainly:
          </p>
          <ul>
            <li>
              <strong>Your data is never used to train models.</strong> Not ours,
              not a provider&apos;s.
            </li>
            <li>
              {siteName} is provider-pluggable. The default provider is a{" "}
              <strong>local Ollama instance</strong>, in which case prompts and
              company content are processed on your own infrastructure and are not
              transmitted to any model vendor at all.
            </li>
            <li>
              If you configure a hosted provider (Anthropic, Google, or an
              OpenAI-compatible endpoint), the specific prompt needed to answer
              your request — which may include excerpts of your company state — is
              sent to that provider to generate the response, and is subject to
              that provider&apos;s terms. Choosing the provider is your decision,
              and you can change it.
            </li>
            <li>
              Agent output is generated text. It can be wrong. Actions classified
              as irreversible or outward-facing are held at the approval gate
              until you approve them.
            </li>
          </ul>

          <h2>5. Why we process it (legal bases)</h2>
          <ul>
            <li>
              <strong>Performance of a contract</strong> — to provide the service
              you signed up for: authentication, company state, agents, sync.
            </li>
            <li>
              <strong>Legitimate interests</strong> — to keep the service secure,
              debug failures, prevent abuse, and understand which features are
              used.
            </li>
            <li>
              <strong>Consent</strong> — for optional analytics cookies and any
              marketing email, withdrawable at any time.
            </li>
            <li>
              <strong>Legal obligation</strong> — to keep the tax and payment
              records we are required to keep.
            </li>
          </ul>

          <h2>6. Cookies and analytics</h2>
          <p>
            We use a small number of cookies and similar technologies:
          </p>
          <ul>
            <li>
              <strong>Strictly necessary</strong> — session and authentication
              cookies set by Clerk, and a local preference for your light/dark
              theme choice. The site does not work without these.
            </li>
            <li>
              <strong>Analytics</strong> — PostHog for product analytics and Google
              Analytics 4 for website traffic. These tell us which pages and
              features get used. Anonymous website visitors are not given a person
              profile in PostHog.
            </li>
          </ul>
          <p>
            You can block analytics with your browser settings, an extension, or a
            Global Privacy Control / Do Not Track signal; the product itself will
            continue to work. We do not run advertising or cross-site tracking
            pixels.
          </p>

          <h2>7. Sub-processors</h2>
          <p>
            We use these providers to run the service. Each receives only what it
            needs for its function:
          </p>
          <ul>
            <li>
              <strong>Clerk</strong> — authentication and user identity
            </li>
            <li>
              <strong>Amazon Web Services</strong> (Mumbai region, ap-south-1) —
              application servers, Postgres database, encrypted backups
            </li>
            <li>
              <strong>Vercel</strong> — hosting and delivery of this website and
              the dashboard front end
            </li>
            <li>
              <strong>Stripe</strong> — payment processing and subscription
              management
            </li>
            <li>
              <strong>PostHog</strong> and <strong>Google Analytics</strong> —
              analytics
            </li>
            <li>
              <strong>Your chosen AI provider</strong> — inference, only if you
              configure a hosted one instead of local Ollama
            </li>
          </ul>

          <h2>8. International transfers</h2>
          <p>
            Our primary infrastructure is in India (AWS ap-south-1). Some
            sub-processors above operate in the United States and the EU, so data
            may be transferred outside your country. Those transfers rely on the
            providers&apos; standard contractual clauses and equivalent safeguards.
          </p>

          <h2>9. Retention</h2>
          <ul>
            <li>
              <strong>Account and company state</strong> — kept while your account
              is active. Deleted within 30 days of account deletion, except where
              we must keep records longer by law.
            </li>
            <li>
              <strong>Backups</strong> — encrypted database backups roll off on a
              fixed schedule; deleted data disappears from backups as they expire.
            </li>
            <li>
              <strong>Server logs</strong> — short-lived, and sanitised of secrets
              when written.
            </li>
            <li>
              <strong>Billing records</strong> — kept as long as tax law requires.
            </li>
            <li>
              <strong>Support email</strong> — kept while useful for context, and
              removed on request.
            </li>
          </ul>

          <h2>10. Security</h2>
          <p>
            Authentication is enforced on every non-public endpoint with signed
            JWTs. Traffic is encrypted in transit with TLS. Integration
            credentials are encrypted at rest, secrets live only in server
            environment configuration, logs are sanitised to strip tokens, and the
            API applies security headers, rate limiting and request validation.
            Dependencies are scanned automatically and static security analysis
            runs on every change. No system is perfectly secure; if you believe
            you have found a vulnerability, please email{" "}
            <a href={`mailto:${contactEmail}`}>{contactEmail}</a> rather than
            disclosing it publicly, and we will work with you on a fix.
          </p>

          <h2>11. Your rights</h2>
          <p>
            Depending on where you live — including under the EU/UK GDPR and
            India&apos;s Digital Personal Data Protection Act, 2023 — you can ask
            us to:
          </p>
          <ul>
            <li>confirm what personal data we hold about you and give you a copy;</li>
            <li>correct data that is wrong or incomplete;</li>
            <li>delete your account and the data associated with it;</li>
            <li>restrict or object to a particular use;</li>
            <li>
              export your data in a portable format — much of it is plain Markdown
              in your own connected tools by design;
            </li>
            <li>withdraw consent you previously gave.</li>
          </ul>
          <p>
            Email <a href={`mailto:${contactEmail}`}>{contactEmail}</a> and we will
            respond within 30 days. You will not be charged and you will not be
            treated differently for asking. If you are unhappy with our response,
            you may complain to your local data protection authority.
          </p>

          <h2>12. Children</h2>
          <p>
            {siteName} is a business tool and is not directed at children under 16.
            We do not knowingly collect their data; if you believe we have, tell us
            and we will delete it.
          </p>

          <h2>13. Changes to this policy</h2>
          <p>
            We will update the date at the top when this policy changes, and will
            notify account holders by email before a material change takes effect.
          </p>

          <h2>14. Contact</h2>
          <p>
            Privacy questions, access requests and complaints:{" "}
            <a href={`mailto:${contactEmail}`}>{contactEmail}</a>. See also our{" "}
            <Link href="/terms">terms &amp; conditions</Link> and the{" "}
            <Link href="/contact">contact page</Link>.
          </p>
        </Prose>
      </Section>
    </>
  );
}
