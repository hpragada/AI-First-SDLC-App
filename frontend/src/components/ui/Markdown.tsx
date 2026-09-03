// Markdown renderer for artifact previews (Bugs.xlsx row 28.1). Generated artifacts are
// Markdown; the preview must render them (GitHub-flavoured: headings, tables, lists, code) and
// render ```mermaid fenced blocks as diagrams instead of showing raw source. This is a pure
// renderer — read-through only, it never edits or persists the body.
import { useEffect, useId, useState } from "react";
import type { ComponentPropsWithoutRef, ReactElement } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";

let mermaidReady = false;
function ensureMermaid() {
  if (!mermaidReady) {
    // securityLevel "strict" sanitises the rendered SVG (no script/foreignObject execution).
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
    mermaidReady = true;
  }
}

function Mermaid({ code }: { code: string }) {
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);
  const rawId = useId();

  useEffect(() => {
    let alive = true;
    ensureMermaid();
    const id = `mermaid-${rawId.replace(/[^a-zA-Z0-9]/g, "")}`;
    mermaid
      .render(id, code)
      .then((res) => {
        if (alive) {
          setSvg(res.svg);
          setFailed(false);
        }
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [code, rawId]);

  // If the diagram can't be parsed, fall back to the source so nothing is lost.
  if (failed) return <pre className="md-body__code">{code}</pre>;
  // NOTE: do NOT reuse the `diagram-frame` class here — its `svg { width:40px }` placeholder
  // rule would shrink the rendered diagram to a tiny smudge (Bugs S.No 165). This container
  // owns its own sizing so real diagrams render full-size.
  return <div className="md-body__mermaid" dangerouslySetInnerHTML={{ __html: svg }} />;
}

function isMermaid(className: string | undefined): boolean {
  return /\blanguage-mermaid\b/.test(className ?? "");
}

// `className` defaults to the full artifact-preview card. Callers embedding markdown inside an
// existing Panel (e.g. a work-item description) pass "prose md-body" to skip the nested card
// while keeping typography + GFM styling (Bugs S.No 167).
export function Markdown({
  children,
  className = "doc-preview prose md-body",
}: {
  children: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // A ```mermaid block: render the diagram; the matching `pre` override drops the
          // surrounding <pre> so the diagram isn't wrapped in monospace/whitespace styling.
          code({ className, children, ...props }: ComponentPropsWithoutRef<"code">) {
            const text = String(children ?? "").replace(/\n$/, "");
            if (isMermaid(className)) return <Mermaid code={text} />;
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre({ children, ...props }: ComponentPropsWithoutRef<"pre">) {
            const child = Array.isArray(children) ? children[0] : children;
            const cls = (child as ReactElement<{ className?: string }>)?.props?.className;
            if (isMermaid(cls)) return <>{children}</>;
            return <pre {...props}>{children}</pre>;
          },
          // Wrap wide tables (e.g. the NFR traceability matrix) in a horizontal scroll
          // container so they stay inside their pane instead of over-extending it (S.No 165).
          table({ children, ...props }: ComponentPropsWithoutRef<"table">) {
            return (
              <div className="md-body__table-wrap">
                <table {...props}>{children}</table>
              </div>
            );
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
