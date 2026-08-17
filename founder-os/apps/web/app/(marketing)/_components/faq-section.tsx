import { Plus } from "lucide-react";
import { JsonLd } from "../../_components/json-ld";
import { faqPageSchema, type FaqItem } from "../../../lib/site";

/**
 * FAQ accordion.
 *
 * Built on native `<details>/<summary>`: the answers exist in the DOM whether
 * open or closed (so they are indexed and findable with in-page search), it
 * works without JavaScript, and it needs no ARIA wiring.
 *
 * Set `emitSchema` on exactly ONE FAQ block per URL — Google treats multiple
 * FAQPage blocks on the same page as invalid markup.
 */
export function FaqSection({
  items,
  emitSchema = false,
}: {
  items: readonly FaqItem[];
  emitSchema?: boolean;
}) {
  return (
    <>
      {emitSchema && <JsonLd data={faqPageSchema(items)} />}
      <dl className="divide-y divide-line border-y border-line">
        {items.map((item) => (
          <div key={item.question}>
            <details className="group">
              <summary className="flex cursor-pointer list-none items-start justify-between gap-4 py-4 text-left transition-colors duration-150 hover:text-ink">
                <dt className="text-[15px] font-medium text-ink md:text-base">
                  {item.question}
                </dt>
                <Plus
                  className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted transition-transform duration-150 group-open:rotate-45"
                  aria-hidden="true"
                />
              </summary>
              <dd className="pb-5 pr-8 text-[15px] leading-relaxed text-ink-secondary">
                {item.answer}
              </dd>
            </details>
          </div>
        ))}
      </dl>
    </>
  );
}
