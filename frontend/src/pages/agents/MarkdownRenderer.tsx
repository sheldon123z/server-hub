/**
 * MarkdownRenderer — renders markdown content with mermaid diagrams,
 * HTML artifact blocks, and copy-to-clipboard code blocks.
 */

import { useEffect, useRef, useCallback } from 'react'
import mermaid from 'mermaid'
import toast from 'react-hot-toast'
import { renderMarkdown } from '@/lib/markdown'

/* ── Mermaid init (once) ────────────────────────────── */

let mermaidInitialized = false

function ensureMermaidInit() {
  if (mermaidInitialized) return
  mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    themeVariables: {
      primaryColor: '#1e293b',
      primaryTextColor: '#e2e8f0',
      primaryBorderColor: '#334155',
      lineColor: '#38bdf8',
      secondaryColor: '#0f172a',
      tertiaryColor: '#0a0f1a',
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    },
  })
  mermaidInitialized = true
}

/* ── Unique ID counter for mermaid SVGs ─────────────── */

let mermaidCounter = 0

/* ── Component ──────────────────────────────────────── */

interface MarkdownRendererProps {
  content: string
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  const hydrate = useCallback(async () => {
    const el = containerRef.current
    if (!el) return

    /* ── Mermaid blocks ──────────────────────────── */
    const mermaidBlocks = el.querySelectorAll<HTMLDivElement>('.mermaid-block')
    if (mermaidBlocks.length > 0) {
      ensureMermaidInit()
      for (const block of mermaidBlocks) {
        const code = block.getAttribute('data-code')
          ?.replace(/&amp;/g, '&')
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&quot;/g, '"')
        if (!code) continue
        try {
          const id = `mermaid-${++mermaidCounter}`
          const { svg } = await mermaid.render(id, code)
          block.innerHTML = svg
          block.classList.add('mermaid-rendered')
        } catch {
          block.textContent = code
          block.classList.add('mermaid-error')
        }
      }
    }

    /* ── Artifact blocks (render as sandboxed iframe) */
    const artifactBlocks = el.querySelectorAll<HTMLDivElement>('.artifact-block')
    for (const block of artifactBlocks) {
      const code = block.getAttribute('data-code')
        ?.replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
      if (!code) continue

      const wrapper = document.createElement('div')
      wrapper.className = 'artifact-wrapper'

      const header = document.createElement('div')
      header.className = 'artifact-header'
      header.innerHTML =
        '<span class="artifact-label">HTML 预览</span>' +
        '<button class="artifact-toggle-btn">展开</button>'

      const iframe = document.createElement('iframe')
      iframe.sandbox.add('allow-scripts')
      iframe.className = 'artifact-iframe'
      iframe.srcdoc = code

      let expanded = false
      header.querySelector('.artifact-toggle-btn')?.addEventListener('click', () => {
        expanded = !expanded
        iframe.style.height = expanded ? '400px' : '200px'
        const btn = header.querySelector('.artifact-toggle-btn')
        if (btn) btn.textContent = expanded ? '收起' : '展开'
      })

      wrapper.appendChild(header)
      wrapper.appendChild(iframe)
      block.replaceWith(wrapper)
    }

    /* ── Copy buttons ────────────────────────────── */
    const copyBtns = el.querySelectorAll<HTMLButtonElement>('.code-copy-btn')
    for (const btn of copyBtns) {
      // Avoid double-binding
      if (btn.dataset.bound) continue
      btn.dataset.bound = '1'
      btn.addEventListener('click', () => {
        const code = btn.getAttribute('data-code')
          ?.replace(/&amp;/g, '&')
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&quot;/g, '"')
        if (!code) return
        navigator.clipboard.writeText(code).then(() => {
          toast.success('已复制')
        })
      })
    }
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.innerHTML = renderMarkdown(content)
    hydrate()
  }, [content, hydrate])

  return <div ref={containerRef} className="markdown-body" />
}
