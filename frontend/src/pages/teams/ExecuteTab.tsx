/**
 * 团队任务执行标签页 (SSE)
 */

import { useState, useRef, useCallback } from 'react'
import toast from 'react-hot-toast'
import { cn, getErrorMessage } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import type { Team } from '@/types/team'

export function ExecuteTab({ team }: { team: Team }) {
  const role = useAuthStore((s) => s.user?.role)
  const isAdmin = role === 'admin'
  const [instruction, setInstruction] = useState('')
  const [messages, setMessages] = useState<Array<{ agent: string; content: string; type: string }>>([])
  const [isRunning, setIsRunning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const executeTeam = useCallback(async () => {
    if (!instruction.trim() || !isAdmin) return
    setIsRunning(true)
    setMessages([])
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch(`/api/agents/teams/${team.id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction }),
        credentials: 'include',
        signal: controller.signal,
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      if (!response.body) throw new Error('No response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6))
              const eventType = currentEvent || (payload.event ?? payload.type)
              const data = payload.data ?? payload
              currentEvent = ''

              if (eventType === 'agent_message' || eventType === 'message') {
                setMessages((prev) => [...prev, { agent: data.agent ?? data.from_agent ?? 'system', content: data.content ?? data.text ?? '', type: 'message' }])
              } else if (eventType === 'agent_tool_call' || eventType === 'tool_call') {
                setMessages((prev) => [...prev, { agent: data.agent ?? '', content: `调用工具: ${data.tool ?? ''}`, type: 'tool' }])
              } else if (eventType === 'agent_tool_result' || eventType === 'tool_result') {
                setMessages((prev) => [...prev, { agent: data.agent ?? '', content: `工具结果: ${(data.output ?? '').toString().slice(0, 200)}`, type: 'result' }])
              } else if (eventType === 'team_error' || eventType === 'error') {
                setMessages((prev) => [...prev, { agent: 'system', content: `错误: ${data.error ?? data.message ?? ''}`, type: 'error' }])
              } else if (eventType === 'team_complete') {
                const status = String(data.status ?? 'done')
                const failStatuses = ['failed', 'timeout', 'cancelled']
                const msgType = status === 'success' ? 'complete' : failStatuses.includes(status) ? 'error' : 'complete'
                const label = status === 'success' ? '完成' : failStatuses.includes(status) ? `${status} — 执行未成功` : `完成 (${status})`
                const tokens = data.usage?.total_tokens ? `, tokens: ${data.usage.total_tokens}` : ''
                setMessages((prev) => [...prev, { agent: 'system', content: `${label} — 耗时: ${data.duration ?? '-'}s, 步数: ${data.steps ?? '-'}${tokens}`, type: msgType }])
              }
              // 'done' is stream-end marker only, no UI message needed
            } catch { /* ignore parse errors */ }
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        toast.error(getErrorMessage(err, '执行失败'))
      }
    } finally {
      setIsRunning(false)
      abortRef.current = null
    }
  }, [instruction, team.id, isAdmin])

  if (!isAdmin) return <p className="text-text3 text-sm">需要管理员权限才能执行任务</p>

  return (
    <div>
      <div className="flex gap-2 mb-4">
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="输入执行指令..."
          rows={3}
          disabled={isRunning}
          className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none flex-1 resize-none"
        />
        <div className="flex flex-col gap-2">
          {isRunning ? (
            <button onClick={() => abortRef.current?.abort()} className="bg-red/20 text-red px-3 py-1.5 rounded-md text-sm font-medium hover:bg-red/30">停止</button>
          ) : (
            <button onClick={executeTeam} disabled={!instruction.trim()} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">执行</button>
          )}
        </div>
      </div>

      {messages.length > 0 && (
        <div className="bg-bg border border-border rounded-lg p-3 max-h-[400px] overflow-y-auto space-y-2">
          {messages.map((msg, i) => (
            <div key={i} className={cn('text-xs p-2 rounded', msg.type === 'error' ? 'bg-red/10 text-red' : msg.type === 'complete' ? 'bg-green/10 text-green' : msg.type === 'tool' ? 'bg-blue/10 text-blue' : msg.type === 'result' ? 'bg-purple/10 text-purple' : 'bg-bg2 text-text2')}>
              <span className="font-medium text-accent">[{msg.agent}]</span> {msg.content}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
