/**
 * Markdown rendering utilities for Agent chat messages.
 * Configures marked.js with highlight.js code highlighting,
 * mermaid diagram placeholders, and HTML artifact blocks.
 */

import { marked, type MarkedOptions, type TokenizerAndRendererExtension } from 'marked'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'

/* ── Custom renderer ────────────────────────────────── */

const renderer = new marked.Renderer()

renderer.code = ({ text, lang }: { text: string; lang?: string | undefined }) => {
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

  // Mermaid diagrams: emit a placeholder div for post-render hydration
  if (lang === 'mermaid') {
    return `<div class="mermaid-block" data-code="${escaped}"></div>`
  }

  // HTML artifacts: emit a placeholder for ArtifactRenderer
  if (lang === 'html:artifact' || lang === 'html') {
    return `<div class="artifact-block" data-code="${escaped}"></div>`
  }

  // Standard code: highlight with hljs
  let highlighted: string
  if (lang && hljs.getLanguage(lang)) {
    highlighted = hljs.highlight(text, { language: lang, ignoreIllegals: true }).value
  } else {
    highlighted = hljs.highlightAuto(text).value
  }

  const label = lang || 'code'

  return (
    `<div class="code-block-wrapper">` +
    `<div class="code-block-header">` +
    `<span class="code-block-lang">${label}</span>` +
    `<button class="code-copy-btn" data-code="${escaped}" title="复制代码">复制</button>` +
    `</div>` +
    `<pre><code class="hljs language-${label}">${highlighted}</code></pre>` +
    `</div>`
  )
}

// @ts-expect-error marked types mismatch for table token
renderer.table = ({ header, body }: { header: string; body: string }) => {
  return (
    `<div class="table-wrapper"><table class="md-table">` +
    `<thead>${header}</thead><tbody>${body}</tbody>` +
    `</table></div>`
  )
}

renderer.link = ({ href, title, text }: { href: string; title?: string | null; text: string }) => {
  const titleAttr = title ? ` title="${title}"` : ''
  return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`
}

/* ── Configure marked ───────────────────────────────── */

marked.setOptions({
  renderer,
  gfm: true,
  breaks: true,
})

/* ── DOMPurify configuration ────────────────────────── */

const PURIFY_CONFIG = {
  ADD_TAGS: ['div'],
  ADD_ATTR: ['data-code', 'class', 'target', 'rel', 'title'],
  ALLOW_DATA_ATTR: false,
}

/* ── Public API ─────────────────────────────────────── */

/**
 * Render a markdown string to sanitized HTML.
 * Embeds placeholder elements for mermaid blocks and artifact blocks
 * that downstream React components can hydrate.
 */
export function renderMarkdown(text: string): string {
  const raw = marked.parse(text) as string
  return DOMPurify.sanitize(raw, PURIFY_CONFIG) as string
}
