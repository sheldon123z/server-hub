/**
 * TerminalPanel - xterm.js WebSocket terminal wrapper.
 * Connects to /api/agents/ws/terminal for bidirectional PTY communication.
 */

import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export function TerminalPanel() {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const dataDisposableRef = useRef<{ dispose: () => void } | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')

  /** Create a WebSocket connection and wire it to the terminal */
  function connectWebSocket(term: Terminal) {
    // Close existing connection if any
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      wsRef.current.close()
    }

    // Dispose previous data handler
    if (dataDisposableRef.current) {
      dataDisposableRef.current.dispose()
      dataDisposableRef.current = null
    }

    setStatus('connecting')

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/agents/ws/terminal`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('connected')
      term.writeln('\x1b[38;5;45m--- Terminal connected ---\x1b[0m\r\n')
      // Send initial resize info
      if (term.cols && term.rows) {
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
      }
    }

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        term.write(event.data)
      }
    }

    ws.onclose = () => {
      setStatus('disconnected')
      term.writeln('\r\n\x1b[38;5;245m--- Connection closed ---\x1b[0m')
    }

    ws.onerror = () => {
      setStatus('error')
      term.writeln('\r\n\x1b[38;5;196m--- Connection error ---\x1b[0m')
    }

    /* Terminal input -> WebSocket */
    const disposable = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data)
      }
    })
    dataDisposableRef.current = disposable
  }

  function reconnect() {
    const term = termRef.current
    if (!term) return
    term.writeln('\r\n\x1b[38;5;45m--- Reconnecting... ---\x1b[0m')
    connectWebSocket(term)
  }

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    /* Create terminal */
    const term = new Terminal({
      theme: {
        background: '#0a0e17',
        foreground: '#e2e8f0',
        cursor: '#38bdf8',
        cursorAccent: '#0a0e17',
        selectionBackground: 'rgba(56, 189, 248, 0.3)',
        black: '#0a0f1a',
        red: '#f87171',
        green: '#4ade80',
        yellow: '#fbbf24',
        blue: '#38bdf8',
        magenta: '#a78bfa',
        cyan: '#22d3ee',
        white: '#e2e8f0',
      },
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
      fontSize: 13,
      lineHeight: 1.2,
      cursorBlink: true,
      cursorStyle: 'bar',
      scrollback: 5000,
    })
    termRef.current = term

    const fit = new FitAddon()
    fitRef.current = fit
    term.loadAddon(fit)
    term.open(container)

    // Initial fit after a frame
    requestAnimationFrame(() => {
      try { fit.fit() } catch { /* container may not be sized yet */ }
    })

    /* WebSocket connection */
    connectWebSocket(term)

    /* Resize handler — fit terminal and notify backend */
    const handleResize = () => {
      try {
        fit.fit()
        if (wsRef.current?.readyState === WebSocket.OPEN && termRef.current) {
          wsRef.current.send(JSON.stringify({ type: 'resize', cols: termRef.current.cols, rows: termRef.current.rows }))
        }
      } catch { /* ignore */ }
    }
    window.addEventListener('resize', handleResize)

    // Also observe container resize
    const observer = new ResizeObserver(handleResize)
    observer.observe(container)

    /* Cleanup */
    return () => {
      dataDisposableRef.current?.dispose()
      dataDisposableRef.current = null
      observer.disconnect()
      window.removeEventListener('resize', handleResize)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
      term.dispose()
      termRef.current = null
      wsRef.current = null
      fitRef.current = null
    }
  }, [])

  const statusColor: Record<ConnectionStatus, string> = {
    connecting: 'bg-yellow',
    connected: 'bg-green',
    disconnected: 'bg-text3',
    error: 'bg-red',
  }

  const statusText: Record<ConnectionStatus, string> = {
    connecting: '连接中...',
    connected: '已连接',
    disconnected: '已断开',
    error: '连接失败',
  }

  return (
    <div className="flex flex-col h-full bg-[#0a0e17]">
      {/* Status bar */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-bg2 border-b border-border shrink-0">
        <span className={`w-2 h-2 rounded-full ${statusColor[status]}`} />
        <span className="text-xs text-text3">{statusText[status]}</span>
        {status === 'disconnected' && (
          <button
            className="ml-auto text-xs text-accent hover:underline"
            onClick={reconnect}
          >
            重新连接
          </button>
        )}
      </div>

      {/* Terminal container */}
      <div ref={containerRef} className="flex-1 min-h-0 px-1 py-1" />
    </div>
  )
}
