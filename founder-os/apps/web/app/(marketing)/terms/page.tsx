import Link from "next/link";
import { PageHero } from "../_components/page-hero";
import { Section, Prose } from "../_components/section";
import { contactEmail, pageMetadata, siteName } from "../../../lib/site";

/**
 * Terms & conditions.
 *
 * Same caveat as the privacy policy: a good-faith engineering draft describing
 * how the product actually behaves (approval gate, provider choice, Stripe
 * billing), not legal advice. Have counsel review before relying on it.
 */

const LAST_UPDATED = "17 August 2026";

export const metadata = pageMetadata({
  title: "Terms & conditions",
  description:
    "The terms governing use of Founder OS: accounts, acceptable use, AI output and the approval gate, connected integrations, billing and cancellation, liability and governing law.",
  path: "/terms",
});

export default function TermsPage() {
  return (
    <>
      <PageHero
        eyebrow="Legal"
        title="Terms & conditions"
        lead={`The agreement between you and ${siteName}. Last updated ${LAST_UPDATED}.`}
        crumbs={[{ href: "/terms", label: "Terms & conditions" }]}
      />

      <Section>
        <Prose>
          <h2>1. Agreement</h2>
          <p>
            By creating an account or using {siteName} (&ldquo;the
            Service&rdquo;) you agree to these terms. If you are using it for a
            company, you confirm you have authority to accept them on that
            company&apos;s behalf. If you do not agree, do not use the Service.
          </p>

          <h2>2. What the Service is</h2>
          <p>
            {siteName} is software that maintains a model of your company&apos;s
            state and runs AI agents against it, synchronising with third-party
            tools you connect. It is provided as a service and is under active
            development: features described as in progress are exactly that, and
            functionality may change as the product evolves.
          </p>

          <h2>3. Your account</h2>
          <ul>
            <li>You must be at least 16 years old and able to enter a contract.</li>
            <li>
              Account information must be accurate, and you are responsible for
              activity under your account.
            </li>
            <li>
              Keep your credentials secure and tell us promptly at{" "}
              <a href={`mailto:${contactEmail}`}>{contactEmail}</a> if you suspect
              unauthorised access.
            </li>
            <li>One account per person unless we agree otherwise in writing.</li>
          </ul>

          <h2>4. Acceptable use</h2>
          <p>You agree not to:</p>
          <ul>
            <li>break the law, or use the Service to help anyone else do so;</li>
            <li>
              upload content you have no right to process, or personal data you
              have no lawful basis to share with us;
            </li>
            <li>
              attempt to bypass authentication, rate limits, or the approval gate,
              or to access another user&apos;s data;
            </li>
            <li>
              probe or load-test the infrastructure without written permission
              (responsible vulnerability reports are welcome — see the{" "}
              <Link href="/privacy">privacy policy</Link>);
            </li>
            <li>
              resell or sublicense the hosted Service, or use it to build a
              directly competing hosted product;
            </li>
            <li>
              use it to generate spam, harassment, disinformation, or content that
              deceives people about who is speaking.
            </li>
          </ul>
          <p>
            We may suspend an account that breaches this section, with notice where
            it is practical to give notice.
          </p>

          <h2>5. AI output, and your responsibility for it</h2>
          <p>
            The Service produces generated text and proposed actions. It can be
            wrong, incomplete, or confidently mistaken. You are responsible for
            reviewing output before you rely on it, and specifically:
          </p>
          <ul>
            <li>
              Output is <strong>not</strong> legal, financial, tax, medical or
              other professional advice.
            </li>
            <li>
              Actions classified as high risk — irreversible or outward-facing —
              require your explicit approval. Approving an action means you take
              responsibility for it.
            </li>
            <li>
              If you enable unattended execution for lower-risk actions, you accept
              the consequences of the actions you allowed to run unattended.
            </li>
            <li>
              You must verify anything you send to a customer, a regulator, or a
              bank.
            </li>
          </ul>

          <h2>6. Your content and your data</h2>
          <p>
            You keep ownership of everything you connect or create. You grant us
            only the licence needed to operate the Service for you: to store,
            process, transform and transmit your content in order to build your
            company state, run the agents you ask for, and sync results back to
            your tools. We do not use your content to train models and we do not
            sell it. See the <Link href="/privacy">privacy policy</Link> for the
            detail.
          </p>

          <h2>7. Connected integrations</h2>
          <p>
            When you connect a third-party tool you authorise us to read from it
            and, where you enable it, write back to it. You are responsible for
            having the right to grant that access. Third-party tools are governed
            by their own terms, we do not control them, and a change or outage on
            their side may break a sync. Disconnecting a source at any time stops
            our further access.
          </p>

          <h2>8. AI providers</h2>
          <p>
            The Service is provider-pluggable and defaults to a local model
            runtime. If you configure a hosted AI provider, your prompts are sent
            to that provider under its terms, and you accept those terms as part of
            choosing it. Provider availability is outside our control.
          </p>

          <h2>9. Plans, billing and cancellation</h2>
          <ul>
            <li>
              There is a free tier. Paid plans are billed in advance through Stripe
              and renew automatically for the same period until cancelled.
            </li>
            <li>
              You can cancel at any time from the billing page. Cancellation takes
              effect at the end of the current paid period; you keep access until
              then.
            </li>
            <li>
              Fees are exclusive of taxes unless stated, and you are responsible for
              applicable taxes.
            </li>
            <li>
              We may change prices with at least 30 days&apos; notice by email; the
              new price applies from your next renewal, and you may cancel before
              it takes effect.
            </li>
            <li>
              Charges are otherwise non-refundable, but if something went wrong on
              our side, write to{" "}
              <a href={`mailto:${contactEmail}`}>{contactEmail}</a> within 14 days
              and we will deal with it fairly.
            </li>
            <li>
              If payment fails we may suspend paid features after notifying you.
            </li>
          </ul>

          <h2>10. Availability</h2>
          <p>
            We aim for a reliable service but do not offer a contractual uptime
            guarantee on the free tier, and maintenance or provider outages will
            occasionally interrupt it. We will give notice of planned downtime where
            we reasonably can.
          </p>

          <h2>11. Our intellectual property</h2>
          <p>
            The Service&apos;s software, design, documentation and brand remain
            ours or our licensors&apos;. These terms grant you a limited,
            non-exclusive, non-transferable right to use the hosted Service; they do
            not transfer ownership. Open-source components that make up the stack
            remain under their own licences.
          </p>

          <h2>12. Feedback</h2>
          <p>
            If you send us ideas or feature suggestions, we may implement them
            without obligation or payment. You keep any rights you already had; you
            simply do not gain a claim over the product because you suggested
            something.
          </p>

          <h2>13. Disclaimer of warranties</h2>
          <p>
            To the maximum extent permitted by law, the Service is provided
            &ldquo;as is&rdquo; and &ldquo;as available&rdquo;, without warranties
            of any kind, whether express or implied, including merchantability,
            fitness for a particular purpose, and non-infringement. We do not
            warrant that output will be accurate or that the Service will be
            uninterrupted or error-free.
          </p>

          <h2>14. Limitation of liability</h2>
          <p>
            To the maximum extent permitted by law, we are not liable for indirect,
            incidental, special, consequential or punitive damages, nor for lost
            profits, lost revenue, lost data or business interruption. Our total
            aggregate liability arising out of or relating to the Service is limited
            to the greater of the amount you paid us in the twelve months before the
            claim, or USD 100. Nothing here excludes liability that cannot lawfully
            be excluded.
          </p>

          <h2>15. Indemnity</h2>
          <p>
            You agree to indemnify us against claims, losses and reasonable costs
            arising from your use of the Service in breach of these terms, from
            content you had no right to process, or from actions you approved.
          </p>

          <h2>16. Termination</h2>
          <p>
            You may stop using the Service and delete your account at any time. We
            may suspend or terminate access for a material breach of these terms,
            for non-payment, or if we are required to by law. On termination your
            right to use the Service ends and your data is deleted according to the
            retention schedule in the{" "}
            <Link href="/privacy">privacy policy</Link>. Sections that by their
            nature should survive termination (ownership, disclaimers, liability,
            governing law) do survive.
          </p>

          <h2>17. Changes to these terms</h2>
          <p>
            We may update these terms. The date at the top always reflects the
            current version, and we will notify account holders by email before a
            material change takes effect. Continuing to use the Service after that
            means you accept the updated terms.
          </p>

          <h2>18. Governing law</h2>
          <p>
            These terms are governed by the laws of India, and the courts of New
            Delhi have exclusive jurisdiction over any dispute — without limiting
            any right you have to bring a claim in your own country of residence
            where the law gives you that right. Before starting formal proceedings,
            please email us so we can try to resolve it directly.
          </p>

          <h2>19. Contact</h2>
          <p>
            Questions about these terms:{" "}
            <a href={`mailto:${contactEmail}`}>{contactEmail}</a>, or via the{" "}
            <Link href="/contact">contact page</Link>.
          </p>
        </Prose>
      </Section>
    </>
  );
}
