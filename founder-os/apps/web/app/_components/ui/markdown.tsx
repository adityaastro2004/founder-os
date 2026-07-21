import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import clsx from "clsx";

/* Agent output renderer. react-markdown builds a React tree (no
   dangerouslySetInnerHTML), and raw HTML in the source is NOT rendered —
   so model/user-supplied markdown cannot inject markup or scripts. */
export function Markdown({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <div className={clsx("space-y-2.5 break-words", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (props) => (
            <h3 className="font-serif text-lg font-semibold text-ink" {...props} />
          ),
          h2: (props) => (
            <h4 className="font-serif text-base font-semibold text-ink" {...props} />
          ),
          h3: (props) => (
            <h5 className="text-sm font-semibold text-ink" {...props} />
          ),
          h4: (props) => (
            <h6 className="text-sm font-semibold text-ink" {...props} />
          ),
          p: (props) => <p className="leading-relaxed" {...props} />,
          strong: (props) => (
            <strong className="font-semibold text-ink" {...props} />
          ),
          a: ({ href, ...props }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent-text underline underline-offset-2 hover:text-accent-hover"
              {...props}
            />
          ),
          ul: (props) => (
            <ul className="list-disc space-y-1 pl-5" {...props} />
          ),
          ol: (props) => (
            <ol className="list-decimal space-y-1 pl-5" {...props} />
          ),
          li: (props) => <li className="leading-relaxed" {...props} />,
          blockquote: (props) => (
            <blockquote
              className="border-l-2 border-accent/40 pl-3 text-ink-secondary"
              {...props}
            />
          ),
          code: ({ className: codeClass, children, ...props }) => {
            const isBlock = /language-/.test(codeClass ?? "");
            if (isBlock) {
              return (
                <code className={clsx("font-mono text-[13px]", codeClass)} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code
                className="rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[13px] text-ink"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: (props) => (
            <pre
              className="overflow-x-auto rounded-card border border-line bg-surface-muted p-3"
              {...props}
            />
          ),
          table: (props) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm" {...props} />
            </div>
          ),
          th: (props) => (
            <th
              className="border-b border-line px-2 py-1.5 font-semibold text-ink"
              {...props}
            />
          ),
          td: (props) => (
            <td className="border-b border-line-subtle px-2 py-1.5" {...props} />
          ),
          hr: () => <hr className="border-line" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
