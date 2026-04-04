import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import mermaid from "mermaid";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Mermaid initialization (once per module load)
// ---------------------------------------------------------------------------
mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  themeVariables: { primaryColor: "#38bdf8" },
});

// ---------------------------------------------------------------------------
// MermaidBlock — renders a mermaid diagram from raw source
// ---------------------------------------------------------------------------
interface MermaidBlockProps {
  code: string;
}

const MermaidBlock: React.FC<MermaidBlockProps> = ({ code }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2)}`;

    mermaid
      .render(id, code)
      .then(({ svg }) => {
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) {
    return (
      <div className="my-4 rounded border border-red/40 bg-bg2 p-3 font-mono text-sm text-red">
        <span className="font-semibold">Mermaid error: </span>
        {error}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-4 flex justify-center overflow-x-auto rounded border border-border bg-bg2 p-4"
    />
  );
};

// ---------------------------------------------------------------------------
// ArtifactBlock — renders HTML artifacts in a sandboxed iframe
// ---------------------------------------------------------------------------
interface ArtifactBlockProps {
  html: string;
}

const ArtifactBlock: React.FC<ArtifactBlockProps> = ({ html }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="my-4 overflow-hidden rounded border border-border">
      <div className="flex items-center justify-between border-b border-border bg-bg2 px-3 py-1.5">
        <span className="text-xs font-medium text-text2">HTML Artifact</span>
        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="rounded px-2 py-0.5 text-xs text-accent hover:bg-bg transition-colors"
        >
          {expanded ? "Collapse" : "Expand"}
        </button>
      </div>
      <iframe
        srcDoc={html}
        sandbox="allow-scripts"
        style={{ height: expanded ? 400 : 200 }}
        className="w-full border-0 bg-white transition-all duration-200"
        title="HTML Artifact"
      />
    </div>
  );
};

// ---------------------------------------------------------------------------
// CopyButton — clipboard copy with brief "Copied!" feedback
// ---------------------------------------------------------------------------
interface CopyButtonProps {
  code: string;
}

const CopyButton: React.FC<CopyButtonProps> = ({ code }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <button
      onClick={handleCopy}
      className={cn(
        "absolute right-2 top-2 rounded px-2 py-0.5 text-xs font-medium transition-colors",
        copied
          ? "bg-green/20 text-green"
          : "bg-bg/60 text-text3 hover:bg-bg hover:text-text2"
      )}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
};

// ---------------------------------------------------------------------------
// isArtifact — detect HTML artifact fenced blocks
// ---------------------------------------------------------------------------
function isArtifact(language: string | null, code: string): boolean {
  if (language === "html:artifact") return true;
  if (language === "html") {
    return /<!DOCTYPE\s+html/i.test(code) || /<html[\s>]/i.test(code);
  }
  return false;
}

// ---------------------------------------------------------------------------
// MarkdownContent
// ---------------------------------------------------------------------------
export interface MarkdownContentProps {
  content: string;
  className?: string;
}

export const MarkdownContent = React.memo<MarkdownContentProps>(
  function MarkdownContent({ content, className }) {
    return (
      <div
        className={cn(
          "text-inherit prose-sm max-w-none space-y-0",
          // Headings
          "[&_h1]:mb-3 [&_h1]:mt-5 [&_h1]:text-xl [&_h1]:font-bold [&_h1]:text-text",
          "[&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-text",
          "[&_h3]:mb-2 [&_h3]:mt-3 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-text",
          "[&_h4]:mb-1 [&_h4]:mt-2 [&_h4]:text-sm [&_h4]:font-semibold [&_h4]:text-text",
          // Paragraphs
          "[&_p]:mb-3 [&_p]:last:mb-0 [&_p]:leading-relaxed",
          // HR
          "[&_hr]:my-4 [&_hr]:border-border",
          className
        )}
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // ----------------------------------------------------------------
            // Code blocks and inline code
            // ----------------------------------------------------------------
            code({ className: cls, children, ...rest }) {
              // react-markdown passes `node` which we don't need on the DOM
              const { node: _node, ...domRest } = rest as typeof rest & {
                node?: unknown;
              };
              const match = /language-(\S+)/.exec(cls ?? "");
              const language = match ? match[1] : null;
              const isBlock = Boolean(match);
              const codeString = String(children).replace(/\n$/, "");

              if (!isBlock) {
                // Inline code
                return (
                  <code
                    {...domRest}
                    className="rounded bg-bg2 px-1 py-0.5 font-mono text-[0.9em] text-text"
                  >
                    {children}
                  </code>
                );
              }

              // Mermaid diagram
              if (language === "mermaid") {
                return <MermaidBlock code={codeString} />;
              }

              // HTML artifact
              if (isArtifact(language, codeString)) {
                return <ArtifactBlock html={codeString} />;
              }

              // Regular syntax-highlighted code block
              return (
                <div className="relative">
                  <CopyButton code={codeString} />
                  <SyntaxHighlighter
                    language={language ?? "text"}
                    style={oneDark}
                    wrapLines
                    wrapLongLines
                    customStyle={{
                      margin: 0,
                      borderRadius: "0.375rem",
                      fontSize: "0.85em",
                    }}
                  >
                    {codeString}
                  </SyntaxHighlighter>
                </div>
              );
            },

            // ----------------------------------------------------------------
            // Pre wrapper
            // ----------------------------------------------------------------
            pre({ children }) {
              return (
                <pre className="my-4 max-w-full overflow-hidden last:mb-0">
                  {children}
                </pre>
              );
            },

            // ----------------------------------------------------------------
            // Tables
            // ----------------------------------------------------------------
            table({ children }) {
              return (
                <div className="my-4 overflow-x-auto">
                  <table className="w-full border-collapse text-sm">
                    {children}
                  </table>
                </div>
              );
            },
            thead({ children }) {
              return (
                <thead className="border-b border-border bg-bg2">
                  {children}
                </thead>
              );
            },
            tbody({ children }) {
              return (
                <tbody className="divide-y divide-border">{children}</tbody>
              );
            },
            tr({ children }) {
              return (
                <tr className="hover:bg-bg2/50 transition-colors">{children}</tr>
              );
            },
            th({ children }) {
              return (
                <th className="px-3 py-2 text-left font-semibold text-text">
                  {children}
                </th>
              );
            },
            td({ children }) {
              return (
                <td className="px-3 py-2 text-text2">{children}</td>
              );
            },

            // ----------------------------------------------------------------
            // Links
            // ----------------------------------------------------------------
            a({ href, children }) {
              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline"
                >
                  {children}
                </a>
              );
            },

            // ----------------------------------------------------------------
            // Blockquotes
            // ----------------------------------------------------------------
            blockquote({ children }) {
              return (
                <blockquote className="my-3 border-l-4 border-border pl-4 italic text-text2/60">
                  {children}
                </blockquote>
              );
            },

            // ----------------------------------------------------------------
            // Lists
            // ----------------------------------------------------------------
            ul({ children }) {
              return (
                <ul className="mb-3 list-disc pl-6 text-text2 [&_li]:mb-1">
                  {children}
                </ul>
              );
            },
            ol({ children }) {
              return (
                <ol className="mb-3 list-decimal pl-6 text-text2 [&_li]:mb-1">
                  {children}
                </ol>
              );
            },
            li({ children }) {
              return <li className="leading-relaxed">{children}</li>;
            },

            // ----------------------------------------------------------------
            // Headings — already styled via className on the outer div,
            // but explicit components let us suppress the `node` prop warning
            // ----------------------------------------------------------------
            h1({ children }) {
              return <h1>{children}</h1>;
            },
            h2({ children }) {
              return <h2>{children}</h2>;
            },
            h3({ children }) {
              return <h3>{children}</h3>;
            },
            h4({ children }) {
              return <h4>{children}</h4>;
            },

            // ----------------------------------------------------------------
            // Paragraphs
            // ----------------------------------------------------------------
            p({ children }) {
              return <p>{children}</p>;
            },

            // ----------------------------------------------------------------
            // Strong / Em
            // ----------------------------------------------------------------
            strong({ children }) {
              return (
                <strong className="font-semibold text-text">{children}</strong>
              );
            },
            em({ children }) {
              return <em className="italic text-text2">{children}</em>;
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    );
  }
);
