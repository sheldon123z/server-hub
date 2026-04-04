import React, { useEffect, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText } from "lucide-react";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import yaml from "react-syntax-highlighter/dist/esm/languages/prism/yaml";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import css from "react-syntax-highlighter/dist/esm/languages/prism/css";
import docker from "react-syntax-highlighter/dist/esm/languages/prism/docker";
import nginx from "react-syntax-highlighter/dist/esm/languages/prism/nginx";
import markdown from "react-syntax-highlighter/dist/esm/languages/prism/markdown";
import { cn } from "@/lib/utils";

SyntaxHighlighter.registerLanguage("bash", bash);
SyntaxHighlighter.registerLanguage("shell", bash);
SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("js", javascript);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("ts", typescript);
SyntaxHighlighter.registerLanguage("json", json);
SyntaxHighlighter.registerLanguage("yaml", yaml);
SyntaxHighlighter.registerLanguage("yml", yaml);
SyntaxHighlighter.registerLanguage("sql", sql);
SyntaxHighlighter.registerLanguage("css", css);
SyntaxHighlighter.registerLanguage("dockerfile", docker);
SyntaxHighlighter.registerLanguage("nginx", nginx);
SyntaxHighlighter.registerLanguage("markdown", markdown);
SyntaxHighlighter.registerLanguage("md", markdown);

// ---------------------------------------------------------------------------
// FilePathChip — 沙箱/服务器路径可点击芯片，点击调出 Artifact 查看器
// ---------------------------------------------------------------------------

/** 匹配沙箱路径和常见服务器路径（不在 <code> 内，仅纯文本节点） */
const FILE_PATH_RE =
  /(\/(?:tmp\/serverhub-sandbox|home|var\/log|etc|opt|mnt)\/[\w.\-/]+(?:\.\w{1,10})?)/g;

function FilePathChip({ path }: { path: string }) {
  const basename = path.split("/").pop() ?? path;
  const handleClick = () => {
    // 动态导入避免循环依赖
    import("@/stores/artifactStore").then(({ useArtifactStore }) => {
      const store = useArtifactStore.getState();
      // 如果 artifact 列表中有该路径，直接 select 打开查看器
      const exists = store.artifacts.some((a) => a.filePath === path);
      if (exists) {
        store.select(path);
      } else {
        // 没有则添加为临时 artifact 并打开
        store.addArtifact({
          filePath: path,
          action: "write_file",
          timestamp: Date.now(),
        });
        store.select(path);
      }
    });
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      title={path}
      className={cn(
        "inline-flex items-center gap-1 mx-0.5 px-1.5 py-0.5 rounded",
        "bg-accent/10 border border-accent/30 text-accent text-[0.85em]",
        "hover:bg-accent/20 hover:border-accent/50 transition-colors",
        "cursor-pointer font-mono leading-tight"
      )}
    >
      <FileText size={12} className="shrink-0 opacity-70" />
      <span className="truncate max-w-[200px]">{basename}</span>
    </button>
  );
}

/**
 * 将 React children 中的文本节点拆分，把文件路径替换为 FilePathChip。
 * 跳过非字符串节点（已经是 React 元素的不处理）。
 */
function processChildrenWithPaths(children: ReactNode): ReactNode {
  return React.Children.map(children, (child) => {
    if (typeof child !== "string") return child;
    const parts: ReactNode[] = [];
    let lastIdx = 0;
    for (const match of child.matchAll(FILE_PATH_RE)) {
      const idx = match.index!;
      if (idx > lastIdx) parts.push(child.slice(lastIdx, idx));
      parts.push(<FilePathChip key={`fp-${idx}`} path={match[0]} />);
      lastIdx = idx + match[0].length;
    }
    if (lastIdx === 0) return child; // 无匹配，原样返回
    if (lastIdx < child.length) parts.push(child.slice(lastIdx));
    return <>{parts}</>;
  });
}

// ---------------------------------------------------------------------------
// Mermaid — lazy-loaded on first use, initialized only once
// ---------------------------------------------------------------------------
let _mermaidInitialized = false;

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

    async function render() {
      const { default: mermaid } = await import("mermaid");
      if (cancelled) return;
      if (!_mermaidInitialized) {
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          themeVariables: { primaryColor: "#38bdf8" },
        });
        _mermaidInitialized = true;
      }
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
    }
    render();

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
                <td className="px-3 py-2 text-text2">{processChildrenWithPaths(children)}</td>
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
              return <li className="leading-relaxed">{processChildrenWithPaths(children)}</li>;
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
              return <p>{processChildrenWithPaths(children)}</p>;
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
