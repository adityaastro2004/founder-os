/**
 * Renders a schema.org JSON-LD block.
 *
 * `data` is built in `lib/site.ts` (or a page's own module) from values we
 * control, never from user input — the `<` escape below is belt-and-braces so a
 * string can never terminate the script tag early.
 */
export function JsonLd({ data }: { data: object }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify(data).replace(/</g, "\\u003c"),
      }}
    />
  );
}
